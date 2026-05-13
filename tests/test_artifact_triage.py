from safecli_radar.artifact_triage import ArtifactFile, _archive_entries, _findings
from safecli_radar.models import ReleaseEvent


def test_regular_javascript_function_is_not_dynamic_eval():
    findings = _findings([ArtifactFile("package/index.js", b"module.exports = function(num) {}")])

    assert findings == []


def test_javascript_function_constructor_is_dynamic_eval():
    findings = _findings([ArtifactFile("package/index.js", b"const f = Function('return x')")])

    assert any("dynamic code evaluation" in finding for finding in findings)


def test_setup_py_path_alone_is_not_suspicious():
    findings = _findings([ArtifactFile("package/setup.py", b"from setuptools import setup")])

    assert findings == []


def test_browser_fetch_alone_is_not_exfiltration():
    findings = _findings([ArtifactFile("package/client.js", b"fetch('/api/items')")])

    assert findings == []


def test_pypi_archive_entries_include_multiple_distributions():
    event = ReleaseEvent(
        ecosystem="pypi",
        package_name="pkg",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="now",
        metadata={
            "json": {
                "urls": [
                    {
                        "filename": "pkg-1.0.0-py3-none-any.whl",
                        "packagetype": "bdist_wheel",
                        "url": "https://example.invalid/pkg-1.0.0-py3-none-any.whl",
                    },
                    {
                        "filename": "pkg-1.0.0.tar.gz",
                        "packagetype": "sdist",
                        "url": "https://example.invalid/pkg-1.0.0.tar.gz",
                    },
                ]
            }
        },
    )

    entries = _archive_entries(event)

    assert [entry["filename"] for entry in entries] == [
        "pkg-1.0.0.tar.gz",
        "pkg-1.0.0-py3-none-any.whl",
    ]
