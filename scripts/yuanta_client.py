#!/usr/bin/env python3
"""HTTP client cho endpoint bảng giá chứng quyền (EW) của Yuanta YS Radar.

Vì sao cần lớp riêng
--------------------
Lần chạy workflow trước fail với ``Expecting value: line 1 column 1 (char 0)``.
Nguyên nhân không phải JSON hỏng của Yuanta mà là WAF/CDN của họ trả về **trang HTML
chặn truy cập** khi request không giống trình duyệt: client cũ chỉ gửi
``User-Agent: CW-Intelligence/1.0`` và **không có ``Referer``**. Hàm ``json()`` khi đó
báo lỗi giải mã rất khó đọc.

Lớp này gom một chỗ duy nhất:
  * header bắt buộc (User-Agent trình duyệt, Referer, Accept);
  * retry có backoff cho lỗi mạng/5xx/429/403 tạm thời;
  * lỗi có ngữ cảnh: HTTP status, content-type, đoạn đầu body, số lần thử — đủ để
    phân biệt "bị chặn" với "JSON hỏng" mà không cần đọc log của runner.

Chỉ dùng thư viện ``requests``; không phụ thuộc pandas để job publish giữ nhẹ.
"""
from __future__ import annotations

import time
from typing import Any, Callable

import requests

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

DEFAULT_TIMEOUT = (5, 25)   # (connect, read) giây
SNIPPET_CHARS = 220
RETRY_STATUS = frozenset({403, 408, 425, 429, 500, 502, 503, 504})


class YuantaHTTPError(RuntimeError):
    """Lỗi gọi API Yuanta, kèm ngữ cảnh để chẩn đoán từ log CI."""

    def __init__(self, message: str, *, attempts: int = 0, status: int | None = None,
                 content_type: str | None = None, snippet: str | None = None,
                 cause: Exception | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.status = status
        self.content_type = content_type
        self.snippet = snippet
        self.cause = cause


def _snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    """Rút gọn body thành một dòng để nhét vừa log."""
    flat = " ".join(str(text).split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def _content_type(response: requests.Response) -> str:
    return str(response.headers.get("Content-Type", "") or "không rõ")


def fetch_board(*, session: requests.Session | None = None, retries: int = 3,
                timeout: tuple[float, float] = DEFAULT_TIMEOUT, backoff: float = 1.0,
                sleep: Callable[[float], None] = time.sleep,
                url: str = API_URL) -> Any:
    """Gọi endpoint bảng giá EW và trả về JSON đã giải mã.

    Không kiểm tra schema ở đây — việc đó thuộc ``cwintel.yuanta_board`` để tầng
    phân tích và tầng mạng không trộn trách nhiệm.

    Raise:
        YuantaHTTPError: hết số lần thử, hoặc phản hồi không phải JSON.
    """
    if retries < 1:
        raise ValueError("retries phải >= 1")
    own_session = session is None
    session = session or requests.Session()

    last_error: Exception | None = None
    last_status: int | None = None
    last_type: str | None = None
    last_snippet: str | None = None

    try:
        for attempt in range(1, retries + 1):
            try:
                response = session.get(url, headers=BROWSER_HEADERS, timeout=timeout)
                last_status = response.status_code
                last_type = _content_type(response)
                if response.status_code != 200:
                    body = _snippet(response.text)
                    last_snippet = body
                    hint = (
                        " (nhiều khả năng bị WAF chặn: kiểm tra User-Agent/Referer)"
                        if response.status_code in {401, 403} else ""
                    )
                    last_error = RuntimeError(
                        f"HTTP {response.status_code}{hint}; content-type={last_type}; "
                        f"body={body!r}"
                    )
                    if response.status_code in RETRY_STATUS:
                        raise _Retry(last_error)
                    break

                try:
                    payload = response.json()
                except ValueError:
                    # Thường là trang HTML chặn truy cập hoặc body rỗng bị cắt.
                    last_snippet = _snippet(response.text)
                    last_error = ValueError(
                        "phản hồi không phải JSON; "
                        f"content-type={last_type}; body={last_snippet!r}"
                    )
                    if attempt < retries:
                        sleep(backoff * (2 ** (attempt - 1)))
                        continue
                    break
                return payload
            except _Retry:
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
        snippet=last_snippet,
        cause=last_error if isinstance(last_error, Exception) else None,
    )


class _Retry(RuntimeError):
    """Đánh dấu lỗi tạm thời để vòng lặp retry bắt riêng."""
