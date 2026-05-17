from safecli_radar.npm_watcher import NpmWatcher
import requests


class _FakeDB:
    def __init__(self, known_versions=(), state=None):
        self.known_versions = set(known_versions)
        self.state = dict(state or {})
        self.recorded = []

    def release_exists(self, ecosystem: str, package_name: str, version: str) -> bool:
        return (ecosystem, package_name, version) in self.known_versions

    def get_state(self, key):
        return self.state.get(key)

    def set_state(self, key, value):
        self.state[key] = str(value)

    def record_release(self, event):
        self.recorded.append(event)
        return True


def test_candidate_versions_first_seen_package_uses_latest_only():
    watcher = NpmWatcher(_FakeDB(), user_agent="test")
    package_doc = {
        "dist-tags": {"latest": "1.1.0"},
        "versions": {"1.0.0": {}, "1.1.0": {}},
        "time": {
            "1.0.0": "2026-05-01T00:00:00.000Z",
            "1.1.0": "2026-05-02T00:00:00.000Z",
        },
    }

    assert watcher._candidate_versions("pkg", package_doc) == ["1.1.0"]


def test_candidate_versions_existing_package_returns_unseen_recent_versions():
    watcher = NpmWatcher(
        _FakeDB({("npm", "pkg", "1.1.0")}),
        user_agent="test",
    )
    package_doc = {
        "dist-tags": {"latest": "1.2.0"},
        "versions": {"1.0.0": {}, "1.1.0": {}, "1.2.0": {}},
        "time": {
            "1.0.0": "2026-05-01T00:00:00.000Z",
            "1.1.0": "2026-05-02T00:00:00.000Z",
            "1.2.0": "2026-05-03T00:00:00.000Z",
        },
    }

    assert watcher._candidate_versions("pkg", package_doc) == ["1.2.0", "1.0.0"]


def test_poll_first_run_bootstraps_recent_changes(monkeypatch):
    fake_db = _FakeDB()
    watcher = NpmWatcher(fake_db, user_agent="test")

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    calls = []

    def fake_request(_session, _method, _url, **kwargs):
        calls.append(kwargs.get("params"))
        return _Response({"results": [{"seq": 100, "id": "pkg"}]})

    monkeypatch.setattr(watcher, "_current_sequence", lambda: 100)
    monkeypatch.setattr(
        watcher,
        "_fetch_package_doc",
        lambda _package_name: {
            "name": "pkg",
            "dist-tags": {"latest": "1.1.0"},
            "versions": {"1.1.0": {}},
            "time": {"1.1.0": "2026-05-02T00:00:00.000Z"},
        },
    )
    monkeypatch.setattr("safecli_radar.npm_watcher.polite_request", fake_request)

    events = watcher.poll(limit=5)

    assert len(events) == 1
    assert events[0].package_name == "pkg"
    assert events[0].version == "1.1.0"
    assert calls[0] == {"since": "95", "limit": "5"}
    assert fake_db.get_state("npm_seq") == "100"


def test_poll_skips_packages_with_missing_registry_doc(monkeypatch):
    fake_db = _FakeDB(state={"npm_seq": "50"})
    watcher = NpmWatcher(fake_db, user_agent="test")

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"seq": 51, "id": "missing-pkg"}]}

    monkeypatch.setattr(
        "safecli_radar.npm_watcher.polite_request",
        lambda _session, _method, _url, **_kwargs: _Response(),
    )

    def raise_not_found(_package_name):
        raise requests.HTTPError("404 Client Error")

    monkeypatch.setattr(watcher, "_fetch_package_doc", raise_not_found)

    events = watcher.poll(limit=5)

    assert events == []
    assert fake_db.get_state("npm_seq") == "51"
