from __future__ import annotations

import re
from typing import Any

from safecli_radar.models import CandidateScore, ReleaseEvent

POPULAR_NAMES = {
    "axios",
    "chalk",
    "django",
    "express",
    "fastapi",
    "flask",
    "lodash",
    "numpy",
    "pandas",
    "pytest",
    "react",
    "requests",
    "scipy",
    "tensorflow",
    "torch",
    "urllib3",
}

HIGH_RISK_NAME_TERMS = {
    "aws",
    "crypto",
    "discord",
    "download",
    "free",
    "hack",
    "login",
    "mcp",
    "password",
    "token",
    "wallet",
    "webhook",
}

SUSPICIOUS_CODE_TERMS = {
    ".npmrc",
    ".pypirc",
    "aws_secret_access_key",
    "child_process",
    "curl ",
    "discord.com/api/webhooks",
    "eval(",
    "exec(",
    "github_token",
    "npm_token",
    "pastebin",
    "powershell",
    "process.env",
    "requests.post",
    "subprocess",
    "telegram",
    "wget ",
}


def score_release(event: ReleaseEvent) -> CandidateScore:
    risk = 0
    impact = _impact_from_enrichment(event.metadata)
    reasons: list[str] = []
    normalized_name = _normalize_name(event.package_name)

    if normalized_name in POPULAR_NAMES:
        impact += 90
        reasons.append("package name is on the popular-package watchlist")

    typo_target = _closest_popular_name(normalized_name)
    if typo_target:
        risk += 45
        impact += 55
        reasons.append(f"name is very close to popular package '{typo_target}'")

    name_terms = sorted(term for term in HIGH_RISK_NAME_TERMS if term in normalized_name)
    if name_terms:
        risk += min(30, 10 * len(name_terms))
        reasons.append(f"name contains high-risk terms: {', '.join(name_terms)}")

    metadata_text = _metadata_text(event.metadata)
    code_terms = sorted(term for term in SUSPICIOUS_CODE_TERMS if term in metadata_text)
    if code_terms:
        risk += min(40, 10 * len(code_terms))
        joined_terms = ", ".join(code_terms)
        reasons.append(f"metadata contains suspicious execution/exfil terms: {joined_terms}")

    if event.ecosystem == "npm":
        risk += _score_npm_manifest(event.metadata, reasons)

    if event.ecosystem == "pypi":
        risk += _score_pypi_files(event.metadata, reasons)

    risk += _score_history(event.metadata, reasons)
    risk += _score_artifact_triage(event.metadata, reasons)

    if event.source in {"pypi_packages", "pypi_changelog"}:
        risk += 5
        reasons.append("new PyPI package/release event")

    reasons.extend(_enrichment_reasons(event.metadata))

    return CandidateScore(
        risk_score=min(risk, 100),
        impact_score=min(impact, 100),
        reasons=reasons or ["no strong static risk signal"],
    )


def _impact_from_enrichment(metadata: dict[str, Any]) -> int:
    enrichment = metadata.get("enrichment") if isinstance(metadata, dict) else {}
    if not isinstance(enrichment, dict):
        return 0

    impact = 0
    npm_downloads = enrichment.get("npm_downloads")
    if isinstance(npm_downloads, dict):
        downloads = int(npm_downloads.get("downloads_last_week") or 0)
        if downloads >= 1_000_000:
            impact += 100
        elif downloads >= 100_000:
            impact += 90
        elif downloads >= 10_000:
            impact += 80
        elif downloads >= 1_000:
            impact += 65
        elif downloads >= 500:
            impact += 50
        elif downloads >= 100:
            impact += 30

    deps_dev = enrichment.get("deps_dev_dependents")
    if isinstance(deps_dev, dict):
        dependent_count = int(deps_dev.get("dependent_count") or 0)
        direct_count = int(deps_dev.get("direct_dependent_count") or 0)
        indirect_count = int(deps_dev.get("indirect_dependent_count") or 0)
        if dependent_count >= 10_000:
            impact += 100
        elif dependent_count >= 1_000:
            impact += 85
        elif dependent_count >= 100:
            impact += 70
        elif direct_count >= 100:
            impact += 70
        elif direct_count >= 10:
            impact += 50
        elif indirect_count >= 100:
            impact += 45

    return min(impact, 100)


def _enrichment_reasons(metadata: dict[str, Any]) -> list[str]:
    enrichment = metadata.get("enrichment") if isinstance(metadata, dict) else {}
    if not isinstance(enrichment, dict):
        return []

    reasons: list[str] = []
    npm_downloads = enrichment.get("npm_downloads")
    if isinstance(npm_downloads, dict):
        downloads = int(npm_downloads.get("downloads_last_week") or 0)
        if downloads:
            reasons.append(f"npm downloads last week: {downloads}")

    deps_dev = enrichment.get("deps_dev_dependents")
    if isinstance(deps_dev, dict):
        direct_count = int(deps_dev.get("direct_dependent_count") or 0)
        indirect_count = int(deps_dev.get("indirect_dependent_count") or 0)
        total_count = int(deps_dev.get("dependent_count") or 0)
        if total_count or direct_count or indirect_count:
            reasons.append(
                "deps.dev dependents:"
                f" direct={direct_count}"
                f" indirect={indirect_count}"
                f" total={total_count}"
            )
    return reasons


def _score_npm_manifest(metadata: dict[str, Any], reasons: list[str]) -> int:
    manifest = metadata.get("manifest") if isinstance(metadata, dict) else {}
    if not isinstance(manifest, dict):
        return 0

    scripts = manifest.get("scripts") or {}
    if not isinstance(scripts, dict) or not scripts:
        return 0

    install_scripts = {
        key: value
        for key, value in scripts.items()
        if key in {"preinstall", "install", "postinstall", "prepare"}
    }
    if not install_scripts:
        return 0

    reasons.append(f"npm install-time script present: {', '.join(sorted(install_scripts))}")
    score = 35
    script_text = " ".join(str(value).lower() for value in install_scripts.values())
    if any(term in script_text for term in ("curl", "wget", "powershell", "node -e", "bash")):
        score += 25
        reasons.append("install script shells out or downloads code")
    return score


def _score_pypi_files(metadata: dict[str, Any], reasons: list[str]) -> int:
    json_payload = metadata.get("json") if isinstance(metadata, dict) else {}
    urls = json_payload.get("urls") if isinstance(json_payload, dict) else []
    if not isinstance(urls, list):
        return 0

    filenames = " ".join(
        str(item.get("filename") or "").lower()
        for item in urls
        if isinstance(item, dict)
    )
    score = 0
    if ".whl" in filenames and ".tar.gz" not in filenames and ".zip" not in filenames:
        score += 10
        reasons.append("PyPI release has wheel-only artifacts")
    if re.search(r"(cp\d+|abi|macosx|manylinux|win_amd64)", filenames):
        score += 10
        reasons.append("PyPI release includes platform-specific binary artifact")
    return score


def _score_history(metadata: dict[str, Any], reasons: list[str]) -> int:
    score = 0
    version_count = metadata.get("version_count") if isinstance(metadata, dict) else None
    if isinstance(version_count, int) and version_count <= 1:
        score += 10
        reasons.append("first npm version observed in registry metadata")

    json_payload = metadata.get("json") if isinstance(metadata, dict) else {}
    release_count = json_payload.get("release_count") if isinstance(json_payload, dict) else None
    if isinstance(release_count, int) and release_count <= 1:
        score += 10
        reasons.append("first PyPI release observed in project metadata")

    maintainers = metadata.get("maintainers") if isinstance(metadata, dict) else None
    if isinstance(maintainers, list) and not maintainers:
        score += 5
        reasons.append("npm package metadata has no maintainers listed")

    history = metadata.get("history") if isinstance(metadata, dict) else {}
    if isinstance(history, dict):
        prior_count = int(history.get("radar_prior_release_count") or 0)
        recent_count = int(history.get("radar_recent_release_count_1h") or 0)
        if prior_count == 0:
            score += 5
            reasons.append("first release seen by this radar instance")
        if recent_count >= 5:
            score += 20
            reasons.append(f"release burst seen by radar: {recent_count} releases in 1h")
        elif recent_count >= 3:
            score += 10
            reasons.append(f"release burst seen by radar: {recent_count} releases in 1h")

    return score


def _score_artifact_triage(metadata: dict[str, Any], reasons: list[str]) -> int:
    triage = metadata.get("artifact_triage") if isinstance(metadata, dict) else {}
    if not isinstance(triage, dict):
        return 0

    findings = triage.get("findings") or []
    if not isinstance(findings, list) or not findings:
        return 0

    reasons.extend(f"artifact triage: {finding}" for finding in findings[:5])
    return min(80, sum(_artifact_finding_weight(str(finding)) for finding in findings))


def _artifact_finding_weight(finding: str) -> int:
    if "package manager credentials" in finding or "cloud credentials" in finding:
        return 35
    if "posts, downloads, or exfiltrates" in finding:
        return 30
    if "executes shell commands" in finding:
        return 30
    if "dynamic code evaluation" in finding:
        return 20
    if "encoded payload" in finding:
        return 20
    if "suspicious path term" in finding:
        return 10
    if "reads environment variables" in finding:
        return 5
    return 10


def _metadata_text(metadata: dict[str, Any]) -> str:
    return repr(metadata).lower()


def _normalize_name(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith("@"):
        lowered = lowered.split("/", 1)[-1]
    return re.sub(r"[-_.]+", "", lowered)


def _closest_popular_name(normalized_name: str) -> str | None:
    for popular in POPULAR_NAMES:
        normalized_popular = _normalize_name(popular)
        if normalized_name == normalized_popular:
            continue
        is_short_name_extension = len(normalized_name) <= len(normalized_popular) + 8
        if normalized_popular in normalized_name and is_short_name_extension:
            return popular
        if _edit_distance(normalized_name, normalized_popular) <= 2:
            return popular
    return None


def _edit_distance(left: str, right: str) -> int:
    if abs(len(left) - len(right)) > 2:
        return 3
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]
