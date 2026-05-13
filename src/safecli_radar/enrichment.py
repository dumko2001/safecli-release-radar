from __future__ import annotations

from urllib.parse import quote

import requests

from safecli_radar.models import ReleaseEvent

NPM_DOWNLOADS_URL = "https://api.npmjs.org/downloads/point/last-week/{package}"
DEPS_DEV_DEPENDENTS_URL = (
    "https://api.deps.dev/v3alpha/systems/{system}/packages/{package}/versions/{version}:dependents"
)


def enrich_release(event: ReleaseEvent, *, user_agent: str) -> ReleaseEvent:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    enrichment: dict[str, object] = {}
    if event.ecosystem == "npm":
        enrichment["npm_downloads"] = _npm_downloads(session, event.package_name)

    deps_dev = _deps_dev_dependents(session, event)
    if deps_dev:
        enrichment["deps_dev_dependents"] = deps_dev

    if not enrichment:
        return event

    metadata = dict(event.metadata)
    metadata["enrichment"] = enrichment
    return ReleaseEvent(
        ecosystem=event.ecosystem,
        package_name=event.package_name,
        version=event.version,
        source=event.source,
        cursor=event.cursor,
        seen_at=event.seen_at,
        metadata=metadata,
    )


def _npm_downloads(session: requests.Session, package_name: str) -> dict[str, object] | None:
    encoded = quote(package_name, safe="")
    response = session.get(NPM_DOWNLOADS_URL.format(package=encoded), timeout=20)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    return {
        "downloads_last_week": int(payload.get("downloads") or 0),
        "start": payload.get("start"),
        "end": payload.get("end"),
    }


def _deps_dev_dependents(session: requests.Session, event: ReleaseEvent) -> dict[str, int] | None:
    system = _deps_dev_system(event.ecosystem)
    if not system:
        return None

    encoded_name = quote(event.package_name, safe="")
    encoded_version = quote(event.version, safe="")
    response = session.get(
        DEPS_DEV_DEPENDENTS_URL.format(
            system=system,
            package=encoded_name,
            version=encoded_version,
        ),
        timeout=20,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    return {
        "dependent_count": int(payload.get("dependentCount") or 0),
        "direct_dependent_count": int(payload.get("directDependentCount") or 0),
        "indirect_dependent_count": int(payload.get("indirectDependentCount") or 0),
    }


def _deps_dev_system(ecosystem: str) -> str | None:
    if ecosystem == "npm":
        return "NPM"
    if ecosystem == "pypi":
        return "PYPI"
    return None
