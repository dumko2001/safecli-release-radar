import requests

from safecli_radar.pypi_watcher import PyPIWatcher


class _FakeDB:
    pass


def test_build_event_keeps_release_when_exact_pypi_metadata_404(monkeypatch):
    watcher = PyPIWatcher(_FakeDB(), user_agent="test")

    def fake_fetch_release_metadata(_package_name, _version):
        raise requests.HTTPError("404 Client Error")

    monkeypatch.setattr(watcher, "fetch_release_metadata", fake_fetch_release_metadata)

    event = watcher._build_event(
        package_name="agentgraf",
        version="0.2.1",
        source="pypi_updates",
        cursor="rss",
        extra_metadata={},
    )

    assert event.package_name == "agentgraf"
    assert event.version == "0.2.1"
    assert "metadata_fetch_error" in event.metadata
