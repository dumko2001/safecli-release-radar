from __future__ import annotations

from urllib.parse import quote

import requests

from safecli_radar.db import RadarDB, now_iso
from safecli_radar.http import polite_request
from safecli_radar.models import ReleaseEvent

NPM_CHANGES_URL = "https://replicate.npmjs.com/registry/_changes"
NPM_PACKAGE_URL = "https://registry.npmjs.org/{package}"


class NpmWatcher:
    def __init__(self, db: RadarDB, *, user_agent: str) -> None:
        self.db = db
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json",
            }
        )

    def poll(self, *, limit: int = 100) -> list[ReleaseEvent]:
        cursor = self.db.get_state("npm_seq")
        if cursor is None:
            self.db.set_state("npm_seq", self._current_sequence())
            return []

        response = polite_request(
            self.session,
            "GET",
            NPM_CHANGES_URL,
            params={"since": cursor, "limit": str(limit)},
            headers={"Cache-Control": "no-cache"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()

        events: list[ReleaseEvent] = []
        for item in payload.get("results", []):
            seq = int(item["seq"])
            package_name = str(item.get("id") or "").strip()
            if not package_name or item.get("deleted"):
                self.db.set_state("npm_seq", seq)
                continue

            package_doc = self._fetch_package_doc(package_name)
            for event in self._events_from_package_doc(package_doc, seq):
                if self.db.record_release(event):
                    events.append(event)

            self.db.set_state("npm_seq", seq)

        return events

    def _current_sequence(self) -> int:
        response = polite_request(
            self.session,
            "GET",
            NPM_CHANGES_URL,
            params={"limit": "1", "descending": "true"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        seqs = [int(item["seq"]) for item in payload.get("results", []) if "seq" in item]
        seqs.append(int(payload.get("last_seq") or 0))
        return max(seqs)

    def _fetch_package_doc(self, package_name: str) -> dict:
        encoded = quote(package_name, safe="")
        response = polite_request(
            self.session,
            "GET",
            NPM_PACKAGE_URL.format(package=encoded),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def _events_from_package_doc(self, package_doc: dict, seq: int) -> list[ReleaseEvent]:
        package_name = str(package_doc.get("name") or "").strip()
        if not package_name:
            return []

        versions = package_doc.get("versions") or {}
        if not isinstance(versions, dict):
            return []

        version_names = self._candidate_versions(package_name, package_doc)
        events = []
        for version in version_names:
            manifest = versions.get(version)
            if not isinstance(manifest, dict):
                continue
            events.append(
                ReleaseEvent(
                    ecosystem="npm",
                    package_name=package_name,
                    version=version,
                    source="npm_changes",
                    cursor=str(seq),
                    seen_at=now_iso(),
                    metadata={
                        "description": package_doc.get("description"),
                        "dist_tags": package_doc.get("dist-tags") or {},
                        "maintainers": package_doc.get("maintainers") or [],
                        "version_count": len(versions),
                        "created": (package_doc.get("time") or {}).get("created"),
                        "modified": (package_doc.get("time") or {}).get("modified"),
                        "time": (package_doc.get("time") or {}).get(version),
                        "manifest": {
                            "scripts": manifest.get("scripts") or {},
                            "dependencies": manifest.get("dependencies") or {},
                            "optionalDependencies": manifest.get("optionalDependencies") or {},
                            "dist": manifest.get("dist") or {},
                            "repository": manifest.get("repository"),
                            "homepage": manifest.get("homepage"),
                        },
                    },
                )
            )
        return events

    def _candidate_versions(self, package_name: str, package_doc: dict) -> list[str]:
        versions = package_doc.get("versions") or {}
        time_payload = package_doc.get("time") or {}
        dist_tags = package_doc.get("dist-tags") or {}

        latest = dist_tags.get("latest")
        version_times = [
            (version, str(time_payload.get(version) or ""))
            for version in versions
            if isinstance(version, str)
        ]
        recent_versions = [
            version
            for version, _timestamp in sorted(
                version_times,
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ]

        if isinstance(latest, str) and latest in versions and latest not in recent_versions:
            recent_versions.insert(0, latest)

        known_any = any(
            self.db.release_exists("npm", package_name, version) for version in recent_versions
        )
        if not known_any:
            if isinstance(latest, str) and latest in versions:
                return [latest]
            return recent_versions[:1]

        return [
            version
            for version in recent_versions
            if not self.db.release_exists("npm", package_name, version)
        ]
