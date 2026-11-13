#!/usr/bin/env python3
"""HTTP client cho endpoint bảng giá chứng quyền (EW) của Yuanta YS Radar.

Vì sao cần lớp riêng
--------------------
Endpoint nằm sau WAF của CDN (``*.cdn.vnis.vn``) và WAF này có **hai** kiểu chặn:

1. **Chặn theo header** — thiếu ``Referer`` hoặc dùng User-Agent lạ (``python-requests``)
   → HTML/403. Đã xử lý bằng ``BROWSER_HEADERS``.
2. **JS interstitial** — request "sạch" vẫn nhận **HTTP 200 + ``text/html``** với nội dung
   ``<title>Attention Required!</title>`` và đúng một dòng:
   ``<script>window.location.href="…list_stock_info?stock_type=EW&jsKey=…"</script>``.
   Đây là thử thách của WAF: trình duyệt chạy script, gọi lại **cùng URL + ``jsKey``**
   (kèm cookie mà CDN vừa set) và mới nhận JSON. Vì vậy ``requests`` phải làm y hệt:
   đọc ``jsKey`` từ body rồi gọi lại, chứ không thể chỉ đổi header.

Lớp này gom một chỗ duy nhất:
  * header bắt buộc (User-Agent trình duyệt, Referer, Accept);
  * **warm-up**: ghé trang chủ trước để nhận cookie CDN, như trình duyệt vẫn làm;
  * **TLS fingerprint**: nếu có ``curl_cffi`` thì dùng phiên giả lập Chrome (JA3 giống
    trình duyệt thật) — WAF thường chỉ thử thách client có fingerprint lạ như
    ``python-requests``. Thiếu ``curl_cffi`` vẫn chạy được bằng ``requests``;
  * xử lý JS interstitial (``jsKey``) có giới hạn số vòng, kèm cookie qua ``Session``;
  * retry có backoff cho lỗi mạng/5xx/429/403 tạm thời;
  * lỗi có ngữ cảnh: HTTP status, content-type, body (không cắt cụt chỗ quan trọng),
    số lần thử — đủ để phân biệt "bị chặn" với "JSON hỏng" ngay trong log CI.

Chỉ dùng thư viện ``requests``; không phụ thuộc pandas để job publish giữ nhẹ.
"""
from __future__ import annotations

import html as html_lib
import re
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

try:  # tùy chọn: chỉ dùng để có TLS fingerprint giống Chrome
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover - phụ thuộc môi trường
    curl_requests = None

API_URL = (
    "https://ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/"
    "list_stock_info?stock_type=EW"
)

# Header do chủ dự án cung cấp. Thiếu Referer hoặc dùng UA lạ → WAF trả HTML/403.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://ysradar.yuanta.com.vn/",
    "Accept": "application/json, text/plain, */*",
}

LANDING_URL = "https://ysradar.yuanta.com.vn/"
IMPERSONATE = "chrome120"
DEFAULT_TIMEOUT = (5, 25)   # (connect, read) giây
# Body của interstitial rất ngắn (~250 ký tự), nên 400 là đủ để thấy cả jsKey; body đầy đủ
# luôn nằm trong ``YuantaHTTPError.body`` nếu cần đọc chi tiết.
SNIPPET_CHARS = 400
MAX_CHALLENGE_ROUNDS = 2
RETRY_STATUS = frozenset({403, 408, 425, 429, 500, 502, 503, 504})
CHALLENGE_MARKERS = ("jsKey", "Attention Required", "cf-browser-verification",
                     "_Incapsula_Resource", "jschl")

# Các kiểu chuyển hướng mà interstitial của WAF dùng để phát jsKey.
_CHALLENGE_PATTERNS = (
    re.compile(r"""window\.location\.(?:href|replace)\s*[=(]\s*["']([^"']+)["']""", re.I),
    re.compile(r"""location\.(?:href|replace)\s*[=(]\s*["']([^"']+)["']""", re.I),
    re.compile(r"""<meta[^>]+http-equiv=["']?refresh["']?[^>]+content=["'][^"']*url=([^"'>]+)""",
               re.I),
)


class YuantaHTTPError(RuntimeError):
    """Lỗi gọi API Yuanta, kèm ngữ cảnh để chẩn đoán từ log CI."""

    def __init__(self, message: str, *, attempts: int = 0, status: int | None = None,
                 content_type: str | None = None, snippet: str | None = None,
                 body: str | None = None, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.status = status
        self.content_type = content_type
        self.snippet = snippet
        self.body = body if body is not None else snippet
        self.cause = cause


class ChallengeNotSolvable(YuantaHTTPError):
    """WAF trả interstitial nhưng không tìm ra URL kèm ``jsKey`` để gọi lại."""


class _Retry(RuntimeError):
    """Đánh dấu lỗi tạm thời để vòng lặp retry bắt riêng."""


class _Fatal(RuntimeError):
    """Lỗi mà retry không thể sửa (404, endpoint/WAF đổi hành vi) → dừng ngay."""

    def __init__(self, message: str, *, status: int | None = None,
                 content_type: str | None = None, body: str | None = None,
                 snippet: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.content_type = content_type
        self.body = body
        self.snippet = snippet if snippet is not None else (
            _snippet(body) if body is not None else None
        )


def _snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    """Rút gọn body thành một dòng cho vừa log (vẫn giữ nguyên phần chứa jsKey)."""
    flat = " ".join(str(text).split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def _content_type(response: requests.Response) -> str:
    return str(response.headers.get("Content-Type", "") or "không rõ")


def is_challenge_page(text: str) -> bool:
    """True nếu body là trang thử thách JS của WAF thay vì dữ liệu."""
    if not text or not text.lstrip()[:1] == "<":
        return False
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in CHALLENGE_MARKERS)


def extract_challenge_url(text: str, *, base_url: str = API_URL) -> str | None:
    """Lấy URL mà interstitial muốn trình duyệt gọi lại.

    Trả ``None`` khi không tìm thấy. URL được giải mã ``&amp;`` và ghép với ``base_url``
    nếu là đường dẫn tương đối.
    """
    for pattern in _CHALLENGE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        target = html_lib.unescape(match.group(1).strip())
        if not target:
            continue
        if target.startswith(("http://", "https://")):
            return target
        base = urlsplit(base_url)
        origin = f"{base.scheme}://{base.netloc}"
        if target.startswith("/"):
            return origin + target
        return origin + "/" + target.lstrip("./")
    return None


def _same_host(target: str, base_url: str) -> bool:
    return urlsplit(target).netloc == urlsplit(base_url).netloc


def build_session(transport: str = "auto"):
    """Tạo session HTTP. ``curl_cffi`` (nếu có) cho TLS fingerprint giống Chrome.

    ``transport``: ``auto`` (curl_cffi nếu có, không thì requests), ``curl_cffi``
    (bắt buộc, lỗi nếu thiếu), hoặc ``requests``.
    """
    if transport not in {"auto", "curl_cffi", "requests"}:
        raise ValueError(f"transport không hợp lệ: {transport!r}")
    if transport in {"auto", "curl_cffi"}:
        if curl_requests is None:
            if transport == "curl_cffi":
                raise RuntimeError(
                    "transport='curl_cffi' nhưng chưa cài curl_cffi "
                    "(python -m pip install curl_cffi)"
                )
        else:
            try:
                return curl_requests.Session(impersonate=IMPERSONATE)
            except Exception:  # pragma: no cover - bản curl_cffi quá cũ
                if transport == "curl_cffi":
                    raise
    return requests.Session()


def warm_up(session, *, headers: dict, timeout=DEFAULT_TIMEOUT,
            sleep: Callable[[float], None] = time.sleep) -> bool:
    """Ghé trang chủ một lần để nhận cookie CDN trước khi gọi API.

    Trả ``True`` nếu trang chủ trả về 2xx. Mọi lỗi đều bị nuốt (không chặn luồng
    chính): đây chỉ là bước tăng xác suất, không phải điều kiện bắt buộc.
    """
    try:
        response = session.get(LANDING_URL, headers=headers, timeout=timeout)
        return 200 <= int(getattr(response, "status_code", 0)) < 300
    except Exception:
        return False


def _get(session: requests.Session, url: str, headers: dict, timeout) -> requests.Response:
    return session.get(url, headers=headers, timeout=timeout)


def _resolve_challenge(response: requests.Response, session: requests.Session, *,
                       headers: dict, timeout, base_url: str,
                       rounds: int = MAX_CHALLENGE_ROUNDS) -> requests.Response:
    """Gọi lại URL kèm ``jsKey`` như trình duyệt cho tới khi nhận được dữ liệu.

    Raise:
        ChallengeNotSolvable: interstitial không có URL để gọi lại, hoặc URL trỏ sang
            host khác (từ chối đi theo để không bị lợi dụng chuyển hướng).
    """
    for _ in range(rounds):
        body = response.text
        if not is_challenge_page(body):
            return response
        target = extract_challenge_url(body, base_url=base_url)
        if target is None:
            raise ChallengeNotSolvable(
                "WAF trả trang thử thách JS nhưng không tìm thấy URL kèm jsKey; "
                f"content-type={_content_type(response)}; body={_snippet(body)!r}",
                status=response.status_code, content_type=_content_type(response),
                snippet=_snippet(body), body=body,
            )
        if not _same_host(target, base_url):
            raise ChallengeNotSolvable(
                "interstitial trỏ sang host khác, từ chối đi theo: "
                f"{urlsplit(target).netloc}",
                status=response.status_code, content_type=_content_type(response),
                snippet=_snippet(body), body=body,
            )
        # Trang lặp lại có thể trỏ về chính URL gốc (interstitial thứ hai). Gọi lại
        # không kèm jsKey là vô nghĩa và tạo vòng lặp đầu-cuối: phải dừng và báo rõ.
        if urlsplit(target).query == urlsplit(base_url).query:
            raise ChallengeNotSolvable(
                "WAF trả interstitial trỏ lại đúng URL gốc mà không kèm jsKey — "
                "không thể tự giải; nhiều khả năng WAF chặn theo TLS fingerprint/IP "
                "của runner. content-type=" + _content_type(response)
                + f"; body={_snippet(body)!r}",
                status=response.status_code, content_type=_content_type(response),
                snippet=_snippet(body), body=body,
            )
        # Session giữ cookie mà CDN set kèm interstitial — giống trình duyệt.
        response = _get(session, target, headers, timeout)
    return response


def _parse_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise _JsonFailure(
            f"phản hồi không phải JSON; content-type={_content_type(response)}; "
            f"body={_snippet(response.text)!r}",
            status=response.status_code, content_type=_content_type(response),
            snippet=_snippet(response.text), body=response.text, cause=exc,
        ) from exc


class _JsonFailure(YuantaHTTPError):
    """Phản hồi không giải mã được thành JSON."""


def fetch_board(*, session: requests.Session | None = None, retries: int = 3,
                timeout: tuple[float, float] = DEFAULT_TIMEOUT, backoff: float = 1.0,
                sleep: Callable[[float], None] = time.sleep,
                url: str = API_URL, transport: str = "auto",
                warmup: bool = True) -> Any:
    """Gọi endpoint bảng giá EW và trả về JSON đã giải mã.

    Tự vượt JS interstitial (``jsKey``) của WAF. Không kiểm tra schema ở đây — việc đó
    thuộc ``cwintel.yuanta_board`` để tầng phân tích và tầng mạng không trộn trách nhiệm.

    Raise:
        YuantaHTTPError: hết số lần thử, phản hồi không phải JSON, hoặc interstitial
            không giải được.
    """
    if retries < 1:
        raise ValueError("retries phải >= 1")
    own_session = session is None
    session = session or build_session(transport)
    if warmup:
        # Không coi warm-up là lỗi: nếu trang chủ chết, vẫn thử API trực tiếp.
        warm_up(session, headers=BROWSER_HEADERS, timeout=timeout, sleep=sleep)

    last_error: Exception | None = None
    last_status: int | None = None
    last_type: str | None = None
    last_body: str | None = None

    try:
        for attempt in range(1, retries + 1):
            try:
                response = _get(session, url, BROWSER_HEADERS, timeout)
                last_status = response.status_code
                last_type = _content_type(response)
                last_body = response.text

                if response.status_code in RETRY_STATUS:
                    hint = (
                        " (WAF: kiểm tra User-Agent/Referer, có thể cần cookie/jsKey)"
                        if response.status_code in {401, 403} else ""
                    )
                    raise _Retry(
                        f"HTTP {response.status_code}{hint}; content-type={last_type}; "
                        f"body={_snippet(last_body)!r}"
                    )
                if response.status_code != 200:
                    raise _Fatal(
                        f"HTTP {response.status_code}; content-type={last_type}; "
                        f"body={_snippet(last_body)!r}",
                        status=response.status_code, content_type=last_type, body=last_body,
                    )

                # WAF: HTTP 200 + text/html + script chuyển hướng kèm jsKey.
                if is_challenge_page(last_body):
                    response = _resolve_challenge(
                        response, session, headers=BROWSER_HEADERS, timeout=timeout,
                        base_url=url,
                    )
                    last_status = response.status_code
                    last_type = _content_type(response)
                    last_body = response.text
                    if is_challenge_page(last_body):
                        raise _Fatal(
                            "WAF vẫn trả trang thử thách JS sau khi đi theo jsKey "
                            f"({MAX_CHALLENGE_ROUNDS} vòng); content-type={last_type}; "
                            f"body={_snippet(last_body)!r}",
                            status=last_status, content_type=last_type,
                            snippet=_snippet(last_body), body=last_body,
                        )

                return _parse_json(response)
            except _Fatal as exc:
                error = YuantaHTTPError(
                    str(exc), attempts=attempt, status=exc.status,
                    content_type=exc.content_type, snippet=exc.snippet, body=exc.body,
                    cause=exc,
                )
                raise error from exc
            except _Retry as exc:
                last_error = RuntimeError(str(exc))
                if attempt < retries:
                    sleep(backoff * (2 ** (attempt - 1)))
                    continue
                break
            except _JsonFailure as exc:
                # Interstitial không giải được là lỗi cấu trúc: retry vô ích.
                if isinstance(exc, ChallengeNotSolvable):
                    raise
                last_error = exc
                if attempt < retries:
                    sleep(backoff * (2 ** (attempt - 1)))
                    continue
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < retries:
                    sleep(backoff * (2 ** (attempt - 1)))
                    continue
                break
    finally:
        if own_session:
            session.close()

    message = f"Gọi Yuanta thất bại sau {retries} lần thử"
    if last_status is not None:
        message += f" (HTTP cuối={last_status}, content-type={last_type})"
    message += f": {last_error}"
    raise YuantaHTTPError(
        message,
        attempts=retries,
        status=last_status,
        content_type=last_type,
        snippet=_snippet(last_body or ""),
        body=last_body,
        cause=last_error if isinstance(last_error, Exception) else None,
    )
