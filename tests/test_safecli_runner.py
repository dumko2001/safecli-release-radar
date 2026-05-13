from safecli_radar.models import ReleaseEvent
from safecli_radar.safecli_runner import package_spec


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
