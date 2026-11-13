"""Kiểm thử lớp HTTP Yuanta bằng session giả — không gọi mạng."""

from __future__ import annotations

import json

import pytest
import requests

from scripts.yuanta_client import (
    ChallengeNotSolvable,
    YuantaHTTPError,
    extract_challenge_url,
    fetch_board,
    is_challenge_page,
)

HTML_BLOCK = "<!DOCTYPE html><html><body>Request blocked by WAF</body></html>"
API_ENDPOINT = "https://ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/list_stock_info"


class FakeResponse:
    def __init__(self, status: int = 200, body: str = "{}",
                 content_type: str = "application/json") -> None:
        self.status_code = status
        self.text = body
        self.headers = {"Content-Type": content_type}
        self.ok = status < 400

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """Trả lần lượt các phản hồi/ngoại lệ đã định; ghi lại request để kiểm tra header.

    Request tới trang chủ (warm-up) được trả 200 và **không** tiêu tốn outcome của API.
    """

    def __init__(self, *outcomes, landing: FakeResponse | Exception | None = None) -> None:
        self.outcomes = list(outcomes)
        self.landing = landing if landing is not None else FakeResponse(200, "<html>ok</html>", "text/html")
        self.calls: list[dict] = []
        self.followed: FakeResponse | None = None
        self.closed = False

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        if not url.startswith(API_ENDPOINT) and "jsKey=" not in url:
            # warm-up: ghé trang chủ, không tiêu tốn outcome của API
            if isinstance(self.landing, Exception):
                raise self.landing
            return self.landing
        if "jsKey=" in url and self.followed is not None:
            return self.followed
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def api_calls(self) -> list[dict]:
        """Các lần gọi endpoint gốc (không tính warm-up và call theo jsKey)."""
        return [c for c in self.calls
                if c["url"].startswith(API_ENDPOINT) and "jsKey=" not in c["url"]]

    @property
    def followed_calls(self) -> list[dict]:
        return [c for c in self.calls if "jsKey=" in c["url"]]

    def close(self):
        self.closed = True


def _ok() -> FakeResponse:
    return FakeResponse(200, '{"success": true, "response": [{"StockCode": "CAAA2501"}]}')


def test_request_sends_the_headers_the_waf_requires():
    session = FakeSession(_ok())
    payload = fetch_board(session=session, sleep=lambda _: None)
    assert payload["success"] is True
    headers = session.calls[0]["headers"]
    # Đây chính là nguyên nhân job trước fail: thiếu Referer + UA lạ → HTML/403.
    assert headers["User-Agent"].startswith("Mozilla/5.0")
    assert headers["Referer"] == "https://ysradar.yuanta.com.vn/"
    assert headers["Accept"] == "application/json, text/plain, */*"
    assert session.api_calls[0]["url"].endswith("list_stock_info?stock_type=EW")
    assert session.api_calls[0]["timeout"] == (5, 25)


def test_html_block_page_raises_actionable_error_after_retries():
    session = FakeSession(FakeResponse(200, HTML_BLOCK, "text/html"))
    waits: list[float] = []
    with pytest.raises(YuantaHTTPError) as info:
        fetch_board(session=session, retries=3, sleep=waits.append)
    error = info.value
    assert len(session.api_calls) == 3
    assert waits == [1.0, 2.0]                  # backoff luỹ thừa
    assert "text/html" in str(error)
    assert "Request blocked" in (error.snippet or "")
    assert error.status == 200
    assert "3 lần thử" in str(error)


def test_403_is_retried_then_reported_with_waf_hint():
    session = FakeSession(FakeResponse(403, "Forbidden", "text/html"))
    with pytest.raises(YuantaHTTPError) as info:
        fetch_board(session=session, retries=2, sleep=lambda _: None)
    message = str(info.value)
    assert "HTTP 403" in message
    assert "WAF" in message
    assert info.value.status == 403


def test_non_retryable_status_fails_fast():
    session = FakeSession(FakeResponse(404, "not found", "text/plain"))
    with pytest.raises(YuantaHTTPError):
        fetch_board(session=session, retries=3, sleep=lambda _: None)
    assert len(session.api_calls) == 1


def test_transient_network_error_recovers_on_retry():
    session = FakeSession(requests.ConnectionError("boom"), _ok())
    payload = fetch_board(session=session, sleep=lambda _: None)
    assert payload["success"] is True
    assert len(session.api_calls) == 2


def test_empty_body_is_reported_not_silently_empty():
    session = FakeSession(FakeResponse(200, "", "application/json"))
    with pytest.raises(YuantaHTTPError) as info:
        fetch_board(session=session, retries=2, sleep=lambda _: None)
    assert "không phải JSON" in str(info.value)


def test_session_created_by_client_is_closed_but_caller_session_is_not():
    owned = FakeSession(_ok())
    fetch_board(session=owned, sleep=lambda _: None)
    assert owned.closed is False          # session do caller truyền vào thì không đóng

    class SessionFactory(FakeSession):
        pass

    created: list[FakeSession] = []

    def factory():
        session = SessionFactory(_ok())
        created.append(session)
        return session

    monkeypatch_requests = pytest.MonkeyPatch()
    monkeypatch_requests.setattr("scripts.yuanta_client.requests.Session", factory)
    try:
        fetch_board(transport="requests", sleep=lambda _: None)
    finally:
        monkeypatch_requests.undo()
    assert created and created[0].closed is True


def test_retries_must_be_positive():
    with pytest.raises(ValueError):
        fetch_board(retries=0)


# ──────────────────────────────────────────────────────────────────
# JS INTERSTITIAL CỦA WAF (jsKey) — dạng body thật trong log CI
# ──────────────────────────────────────────────────────────────────
CHALLENGE_BODY = (
    '<html><head><title>Attention Required!</title></head><body>'
    '<script>window.location.href="https://ysradar.yuanta.com.vn/api/v3/market_data/'
    'price_board/stock/list_stock_info?stock_type=EW&jsKey=B0C9rGjdylmkSlSFSFPDt3AZVjC%2FmQ'
    '&amp;lang=vi";</script></body></html>'
)
API_JSON = json.dumps({"success": True, "response": [{"StockCode": "CACB2515"}]})


def test_js_interstitial_is_followed_with_jskey_like_a_browser():
    """WAF trả 200 + HTML kèm jsKey; client phải gọi lại đúng URL đó để lấy JSON."""
    session = FakeSession(FakeResponse(200, CHALLENGE_BODY, "text/html"))
    session.followed = FakeResponse(200, API_JSON, "application/json")
    payload = fetch_board(session=session, sleep=lambda _: None)
    assert payload["success"] is True
    assert len(session.api_calls) == 1          # chỉ một lần vào endpoint gốc
    retry_url = session.followed_calls[0]["url"]
    assert "jsKey=B0C9rGjdylmkSlSFSFPDt3AZVjC%2FmQ" in retry_url
    assert "stock_type=EW" in retry_url
    assert "&lang=vi" in retry_url          # &amp; trong HTML đã được giải mã
    # Cookie CDN set ở lần đầu vẫn còn vì dùng chung Session (giống trình duyệt)
    assert session.followed_calls[0]["headers"]["Referer"] == \
        "https://ysradar.yuanta.com.vn/"


def test_interstitial_with_relative_redirect_is_resolved():
    body = ('<html><head><title>Attention Required!</title></head><body>'
            '<script>window.location.replace("/api/v3/x?stock_type=EW&jsKey=abc123");'
            '</script></body></html>')
    session = FakeSession(FakeResponse(200, body, "text/html"))
    session.followed = FakeResponse(200, API_JSON, "application/json")
    payload = fetch_board(session=session, sleep=lambda _: None)
    assert payload["success"] is True
    # "/api/v3/x" là đường dẫn tương đối → ghép với origin của endpoint
    assert session.followed_calls[0]["url"] == \
        "https://ysradar.yuanta.com.vn/api/v3/x?stock_type=EW&jsKey=abc123"


def test_unresolvable_interstitial_fails_fast_with_full_body():
    body = ('<html><head><title>Attention Required!</title></head>'
            '<body>chặn</body></html>')
    session = FakeSession(FakeResponse(200, body, "text/html"))
    with pytest.raises(ChallengeNotSolvable) as info:
        fetch_board(session=session, retries=3, sleep=lambda _: None)
    # Không retry vô ích: lỗi cấu trúc, chỉ một lần gọi
    assert len(session.api_calls) == 1
    assert info.value.content_type == "text/html"
    assert "không tìm thấy URL" in str(info.value)
    # Body đầy đủ được giữ lại để đọc trong log (trước đây bị cắt ở 220 ký tự)
    assert info.value.body == body


def test_interstitial_pointing_to_another_host_is_refused():
    body = ('<html><head><title>Attention Required!</title></head><body>'
            '<script>window.location.href="https://evil.example/x?jsKey=abc";</script>'
            '</body></html>')
    session = FakeSession(FakeResponse(200, body, "text/html"))
    with pytest.raises(ChallengeNotSolvable, match="host khác"):
        fetch_board(session=session, sleep=lambda _: None)
    assert len(session.api_calls) == 1


def test_repeated_interstitial_is_reported_not_looped_forever():
    """Interstitial trả lại chính nó (URL kèm jsKey vẫn là HTML) → dừng sau 2 vòng."""
    session = FakeSession(FakeResponse(200, CHALLENGE_BODY, "text/html"))
    session.followed = FakeResponse(200, CHALLENGE_BODY, "text/html")
    with pytest.raises(YuantaHTTPError, match="vẫn trả trang thử thách"):
        fetch_board(session=session, sleep=lambda _: None)
    assert len(session.api_calls) == 1        # không gọi lại endpoint gốc
    assert len(session.followed_calls) == 2   # đúng MAX_CHALLENGE_ROUNDS vòng


def test_detector_does_not_mistake_json_for_a_challenge():
    assert is_challenge_page(API_JSON) is False
    assert is_challenge_page("") is False
    assert is_challenge_page('<html><body>{"ok": true}</body></html>') is False
    assert is_challenge_page(CHALLENGE_BODY) is True


def test_challenge_url_extraction_variants():
    meta = ('<html><head><meta http-equiv="refresh" content="0; url=/a?jsKey=zz&amp;b=1">'
            '</head></html>')
    assert extract_challenge_url(meta) == "https://ysradar.yuanta.com.vn/a?jsKey=zz&b=1"
    assert extract_challenge_url("<html>nothing</html>") is None


# ──────────────────────────────────────────────────────────────────
# WARM-UP & TRANSPORT
# ──────────────────────────────────────────────────────────────────
def test_warm_up_hits_landing_page_before_the_api():
    session = FakeSession(_ok())
    fetch_board(session=session, sleep=lambda _: None)
    assert session.calls[0]["url"] == "https://ysradar.yuanta.com.vn/"


def test_dead_landing_page_does_not_block_the_api():
    session = FakeSession(_ok(), landing=requests.ConnectionError("landing down"))
    payload = fetch_board(session=session, sleep=lambda _: None)
    assert payload["success"] is True
    assert len(session.api_calls) == 1


def test_warm_up_can_be_disabled():
    session = FakeSession(_ok())
    fetch_board(session=session, warmup=False, sleep=lambda _: None)
    assert all(c["url"].startswith(API_ENDPOINT) for c in session.calls)


def test_build_session_transport_selection():
    from scripts.yuanta_client import build_session, curl_requests

    forced = build_session("requests")
    assert type(forced).__module__ == "requests.sessions"
    forced.close()
    if curl_requests is not None:
        impersonated = build_session("curl_cffi")
        assert impersonated is not None
        impersonated.close()
    with pytest.raises(ValueError):
        build_session("browser")
