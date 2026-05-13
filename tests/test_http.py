import requests

from safecli_radar.http import polite_request


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def request(self, *_args, **_kwargs):
        self.calls += 1
        return self.responses.pop(0)


def _response(status_code: int, *, retry_after: str | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    return response


def test_polite_request_retries_429_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr("safecli_radar.http.time.sleep", sleeps.append)
    session = _FakeSession([_response(429, retry_after="2"), _response(200)])

    response = polite_request(session, "GET", "https://example.test")

    assert response.status_code == 200
    assert session.calls == 2
    assert sleeps == [2.0]


def test_polite_request_does_not_retry_normal_success(monkeypatch):
    monkeypatch.setattr("safecli_radar.http.time.sleep", lambda _delay: None)
    session = _FakeSession([_response(200)])

    response = polite_request(session, "GET", "https://example.test")

    assert response.status_code == 200
    assert session.calls == 1
