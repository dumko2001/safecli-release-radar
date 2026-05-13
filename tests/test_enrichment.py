from safecli_radar.models import ReleaseEvent
from safecli_radar.scorer import score_release


def test_blast_radius_enrichment_drives_impact_score():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="is-number",
        version="7.0.0",
        source="test",
        cursor="1",
        seen_at="now",
        metadata={
            "enrichment": {
                "npm_downloads": {"downloads_last_week": 158_984_477},
                "deps_dev_dependents": {
                    "dependent_count": 298_192,
                    "direct_dependent_count": 4_539,
                    "indirect_dependent_count": 293_767,
                },
            }
        },
    )

    score = score_release(event)

    assert score.impact_score == 100
    assert any("npm downloads last week" in reason for reason in score.reasons)
    assert any("deps.dev dependents" in reason for reason in score.reasons)


def test_10k_downloads_is_high_impact():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="some-package",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="now",
        metadata={"enrichment": {"npm_downloads": {"downloads_last_week": 10_000}}},
    )

    assert score_release(event).impact_score == 80


def test_500_downloads_still_counts_as_meaningful_impact():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="some-package",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="now",
        metadata={"enrichment": {"npm_downloads": {"downloads_last_week": 500}}},
    )

    assert score_release(event).impact_score == 50


def test_100_direct_dependents_is_high_impact():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="some-package",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="now",
        metadata={
            "enrichment": {
                "deps_dev_dependents": {
                    "dependent_count": 100,
                    "direct_dependent_count": 100,
                    "indirect_dependent_count": 0,
                }
            }
        },
    )

    assert score_release(event).impact_score == 70
