import subprocess

from safecli_radar.models import ReleaseEvent
from safecli_radar.safecli_runner import package_spec, run_safecli


def test_package_spec_npm_scoped_package():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="@scope/pkg",
        version="1.2.3",
        source="test",
        cursor="1",
        seen_at="now",
    )

    assert package_spec(event) == "@scope/pkg@1.2.3"


def test_package_spec_pypi_exact_pin():
    event = ReleaseEvent(
        ecosystem="pypi",
        package_name="requests",
        version="2.32.3",
        source="test",
        cursor="1",
        seen_at="now",
    )

    assert package_spec(event) == "requests==2.32.3"


def test_run_safecli_uses_env_timeout(monkeypatch):
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="is-number",
        version="7.0.0",
        source="test",
        cursor="1",
        seen_at="now",
    )
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setenv("SAFECLI_RADAR_SAFECLI_TIMEOUT_SEC", "601")
    monkeypatch.setattr("safecli_radar.safecli_runner.shutil.which", lambda _name: "/tmp/safecli")
    monkeypatch.setattr("safecli_radar.safecli_runner.subprocess.run", fake_run)

    result = run_safecli(event)

    assert result.exit_code == 0
    assert captured["command"] == ["/tmp/safecli", "check", "npm", "is-number@7.0.0"]
    assert captured["timeout"] == 601
