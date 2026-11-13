"""Kiểm thử lớp HTTP Yuanta bằng session giả — không gọi mạng."""

from __future__ import annotations

import json

import pytest
import requests

from scripts.yuanta_client import YuantaHTTPError, fetch_board

HTML_BLOCK = "<!DOCTYPE html><html><body>Request blocked by WAF</body></html>"


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
    """Trả lần lượt các phản hồi/ngoại lệ đã định; ghi lại request để kiểm tra header."""

    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.closed = False

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

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
    assert session.calls[0]["url"].endswith("list_stock_info?stock_type=EW")
    assert session.calls[0]["timeout"] == (5, 25)


def test_html_block_page_raises_actionable_error_after_retries():
    session = FakeSession(FakeResponse(200, HTML_BLOCK, "text/html"))
    waits: list[float] = []
    with pytest.raises(YuantaHTTPError) as info:
        fetch_board(session=session, retries=3, sleep=waits.append)
    error = info.value
    assert len(session.calls) == 3
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
    assert len(session.calls) == 1


def test_transient_network_error_recovers_on_retry():
    session = FakeSession(requests.ConnectionError("boom"), _ok())
    payload = fetch_board(session=session, sleep=lambda _: None)
    assert payload["success"] is True
    assert len(session.calls) == 2


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
        fetch_board(sleep=lambda _: None)
    finally:
        monkeypatch_requests.undo()
    assert created and created[0].closed is True


def test_retries_must_be_positive():
    with pytest.raises(ValueError):
        fetch_board(retries=0)
