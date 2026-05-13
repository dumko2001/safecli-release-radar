import xml.etree.ElementTree as ET

import requests

from safecli_radar.pypi_watcher import PyPIWatcher


class _FakeDB:
    def __init__(self, state=None):
        self.state = dict(state or {})

    def get_state(self, key):
        return self.state.get(key)

    def set_state(self, key, value):
        self.state[key] = str(value)


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


def test_updates_rss_resolves_exact_version_from_link(monkeypatch):
    watcher = PyPIWatcher(_FakeDB(), user_agent="test")
    monkeypatch.setattr(watcher, "fetch_release_metadata", lambda _name, _version: {})
    item = ET.fromstring(
        """
        <item>
          <title>requests 2.32.3</title>
          <link>https://pypi.org/project/requests/2.32.3/</link>
          <pubDate>Wed, 13 May 2026 10:00:00 GMT</pubDate>
        </item>
        """
    )

    event = watcher._parse_rss_item(item, source="pypi_updates")

    assert event is not None
    assert event.package_name == "requests"
    assert event.version == "2.32.3"


def test_packages_rss_resolves_exact_version_from_project_json(monkeypatch):
    watcher = PyPIWatcher(_FakeDB(), user_agent="test")
    monkeypatch.setattr(
        watcher,
        "fetch_project_metadata",
        lambda _name: {
            "info": {"name": "newpkg", "version": "0.1.0"},
            "releases": {"0.1.0": []},
            "urls": [],
        },
    )
    item = ET.fromstring(
        """
        <item>
          <title>newpkg added to PyPI</title>
          <link>https://pypi.org/project/newpkg/</link>
          <pubDate>Wed, 13 May 2026 10:00:00 GMT</pubDate>
        </item>
        """
    )

    event = watcher._parse_rss_item(item, source="pypi_packages")

    assert event is not None
    assert event.package_name == "newpkg"
    assert event.version == "0.1.0"


def test_changelog_interval_skips_recent_xmlrpc_check(monkeypatch):
    fake_db = _FakeDB(
        {
            "pypi_serial": "100",
            "pypi_changelog_checked_at_epoch": "1000",
        }
    )
    monkeypatch.setattr("safecli_radar.pypi_watcher.time.time", lambda: 1100)
    watcher = PyPIWatcher(fake_db, user_agent="test", changelog_interval_sec=300)

    assert watcher._should_poll_changelog() is False


def test_changelog_interval_allows_due_xmlrpc_check(monkeypatch):
    fake_db = _FakeDB(
        {
            "pypi_serial": "100",
            "pypi_changelog_checked_at_epoch": "1000",
        }
    )
    monkeypatch.setattr("safecli_radar.pypi_watcher.time.time", lambda: 1400)
    watcher = PyPIWatcher(fake_db, user_agent="test", changelog_interval_sec=300)

    assert watcher._should_poll_changelog() is True
