from safecli_radar.models import CandidateScore, ReleaseEvent
from safecli_radar.scan_policy import decide_scan


def test_high_impact_scans_even_when_risk_is_low():
    score = CandidateScore(risk_score=0, impact_score=80, reasons=[])

    assert score.should_scan(risk_threshold=70, impact_threshold=80) is True


def test_high_risk_scans_even_when_impact_is_low():
    score = CandidateScore(risk_score=80, impact_score=0, reasons=[])

    assert score.should_scan(risk_threshold=70, impact_threshold=80) is True


def test_low_risk_low_impact_does_not_scan():
    score = CandidateScore(risk_score=20, impact_score=40, reasons=[])

    assert score.should_scan(risk_threshold=70, impact_threshold=80) is False


def test_100_indirect_dependents_scan_even_with_zero_risk():
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
                    "direct_dependent_count": 0,
                    "indirect_dependent_count": 100,
                }
            }
        },
    )
    score = CandidateScore(risk_score=0, impact_score=45, reasons=[])

    decision = decide_scan(event, score, risk_threshold=70, impact_threshold=80)

    assert decision.should_scan is True
    assert "indirect_dependents 100 >= 100" in decision.reasons
