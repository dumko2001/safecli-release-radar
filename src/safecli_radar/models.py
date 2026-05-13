from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReleaseEvent:
    ecosystem: str
    package_name: str
    version: str
    source: str
    cursor: str
    seen_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateScore:
    risk_score: int
    impact_score: int
    reasons: list[str]

    def should_scan(self, *, risk_threshold: int, impact_threshold: int) -> bool:
        return self.risk_score >= risk_threshold or self.impact_score >= impact_threshold


@dataclass(frozen=True)
class SafeCLIResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    parsed_json: dict[str, Any] | None
