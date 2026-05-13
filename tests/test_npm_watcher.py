from safecli_radar.npm_watcher import NpmWatcher


class _FakeDB:
    def __init__(self, known_versions=()):
        self.known_versions = set(known_versions)

    def release_exists(self, ecosystem: str, package_name: str, version: str) -> bool:
        return (ecosystem, package_name, version) in self.known_versions


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
