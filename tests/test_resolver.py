from safecli_radar.resolver import _parse_npm_spec, _parse_pypi_spec


def test_parse_npm_spec_scoped_package():
    assert _parse_npm_spec("@scope/pkg@1.2.3") == ("@scope/pkg", "1.2.3")


def test_parse_npm_spec_defaults_to_latest():
    assert _parse_npm_spec("is-number") == ("is-number", "latest")


def test_parse_pypi_spec_exact_version():
    assert _parse_pypi_spec("requests==2.32.3") == ("requests", "2.32.3")
