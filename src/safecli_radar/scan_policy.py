from __future__ import annotations

from dataclasses import dataclass

from safecli_radar.models import CandidateScore, ReleaseEvent


@dataclass(frozen=True)
class ScanDecision:
    should_scan: bool
    reasons: list[str]


def decide_scan(
    event: ReleaseEvent,
    score: CandidateScore,
    *,
    risk_threshold: int,
    impact_threshold: int,
    force_scan: bool = False,
) -> ScanDecision:
    reasons: list[str] = []

    if force_scan:
        reasons.append("manual check requested")

    if score.risk_score >= risk_threshold:
        reasons.append(f"risk_score {score.risk_score} >= {risk_threshold}")

    if score.impact_score >= impact_threshold:
        reasons.append(f"impact_score {score.impact_score} >= {impact_threshold}")

    enrichment = event.metadata.get("enrichment") if isinstance(event.metadata, dict) else {}
    if isinstance(enrichment, dict):
        npm_downloads = enrichment.get("npm_downloads")
        if isinstance(npm_downloads, dict):
            downloads = int(npm_downloads.get("downloads_last_week") or 0)
            if downloads >= 10_000:
                reasons.append(f"downloads_last_week {downloads} >= 10000")

        deps_dev = enrichment.get("deps_dev_dependents")
        if isinstance(deps_dev, dict):
            direct = int(deps_dev.get("direct_dependent_count") or 0)
            indirect = int(deps_dev.get("indirect_dependent_count") or 0)
            total = int(deps_dev.get("dependent_count") or 0)
            if direct >= 10:
                reasons.append(f"direct_dependents {direct} >= 10")
            if indirect >= 100:
                reasons.append(f"indirect_dependents {indirect} >= 100")
            if total >= 100:
                reasons.append(f"total_dependents {total} >= 100")

    if any("name is very close to popular package" in reason for reason in score.reasons):
        reasons.append("name similarity to popular package")

    return ScanDecision(should_scan=bool(reasons), reasons=reasons)
