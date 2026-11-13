from __future__ import annotations

import pytest

from scripts.fetch_yuanta_snapshot import fetch_payload
from scripts.yuanta_snapshot import API_URL


class FakeResponse:
    def __init__(self, *, status=200, text="", payload=None, headers=None):
        self.status_code = status
        self.ok = 200 <= status < 400
        self.text = text
        self._payload = payload
        self.headers = headers or {"Content-Type": "application/json"}
        self.url = API_URL

    def json(self):
        if self._payload is not None:
            return self._payload
        raise ValueError("no JSON")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        assert url == API_URL
        assert kwargs["headers"]["Accept"] == "application/json"
        return self.response


def test_non_json_200_reports_status_content_type_and_short_preview():
    response = FakeResponse(
        status=200,
        text="<html><title>Access denied</title></html>",
        headers={"Content-Type": "text/html"},
    )
    session = FakeSession(response)
    with pytest.raises(RuntimeError, match="non-JSON/empty response") as error:
        fetch_payload(session, retries=3)
    message = str(error.value)
    assert "HTTP 200" in message
    assert "text/html" in message
    assert "Access denied" in message
    assert session.calls == 1  # Contract errors are diagnosed, not retried pointlessly.


def test_empty_200_body_is_reported_explicitly():
    response = FakeResponse(status=200, text="", headers={"Content-Type": "text/plain"})
    with pytest.raises(RuntimeError, match="<empty body>"):
        fetch_payload(FakeSession(response))


def test_http_error_includes_small_body_preview():
    response = FakeResponse(
        status=403,
        text="Forbidden by provider gateway",
        headers={"Content-Type": "text/plain"},
    )
    with pytest.raises(RuntimeError, match="HTTP 403") as error:
        fetch_payload(FakeSession(response))
    assert "Forbidden by provider gateway" in str(error.value)
