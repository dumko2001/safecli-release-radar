from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
import xmlrpc.client
from typing import Any

import requests

from safecli_radar.db import RadarDB, now_iso
from safecli_radar.http import polite_request
from safecli_radar.models import ReleaseEvent

PYPI_RSS_UPDATES_URL = "https://pypi.org/rss/updates.xml"
PYPI_RSS_PACKAGES_URL = "https://pypi.org/rss/packages.xml"
PYPI_PROJECT_JSON_URL = "https://pypi.org/pypi/{package}/json"
PYPI_JSON_URL = "https://pypi.org/pypi/{package}/{version}/json"
PYPI_XMLRPC_URL = "https://pypi.org/pypi"
DEFAULT_CHANGELOG_INTERVAL_SEC = 300


class PyPIWatcher:
    def __init__(
        self,
        db: RadarDB,
        *,
        user_agent: str,
        changelog_interval_sec: int = DEFAULT_CHANGELOG_INTERVAL_SEC,
    ) -> None:
        self.db = db
        self.changelog_interval_sec = changelog_interval_sec
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json, application/xml, text/xml",
            }
        )

    def poll(self) -> list[ReleaseEvent]:
        events: list[ReleaseEvent] = []
        events.extend(self.poll_rss(PYPI_RSS_UPDATES_URL, state_prefix="pypi_updates"))
        events.extend(self.poll_rss(PYPI_RSS_PACKAGES_URL, state_prefix="pypi_packages"))
        if self._should_poll_changelog():
            events.extend(self.poll_changelog())
        return events

    def poll_rss(self, url: str, *, state_prefix: str) -> list[ReleaseEvent]:
        headers = {}
        etag = self.db.get_state(f"{state_prefix}_etag")
        if etag:
            headers["If-None-Match"] = etag

        response = polite_request(self.session, "GET", url, headers=headers, timeout=20)
        if response.status_code == 304:
            return []
        response.raise_for_status()

        if response.headers.get("etag"):
            self.db.set_state(f"{state_prefix}_etag", response.headers["etag"])

        root = ET.fromstring(response.text)
        events: list[ReleaseEvent] = []
        for item in root.findall("./channel/item"):
            parsed = self._parse_rss_item(item, source=state_prefix)
            if parsed and self.db.record_release(parsed):
                events.append(parsed)
        return events

    def poll_changelog(self) -> list[ReleaseEvent]:
        serial = self.db.get_state("pypi_serial")
        if serial is None:
            self.db.set_state("pypi_serial", self._xmlrpc_call("changelog_last_serial")[0])
            self.db.set_state("pypi_changelog_checked_at_epoch", str(int(time.time())))
            return []

        rows = self._xmlrpc_call("changelog_since_serial", int(serial))[0]
        events: list[ReleaseEvent] = []
        max_serial = int(serial)
        for row in rows:
            if len(row) != 5:
                continue
            package_name, version, timestamp, action, event_serial = row
            max_serial = max(max_serial, int(event_serial))
            if action != "new release" or not package_name or not version:
                continue
            event = self._build_event(
                package_name=str(package_name),
                version=str(version),
                source="pypi_changelog",
                cursor=str(event_serial),
                extra_metadata={"upload_epoch": timestamp, "action": action},
            )
            if self.db.record_release(event):
                events.append(event)

        self.db.set_state("pypi_serial", max_serial)
        self.db.set_state("pypi_changelog_checked_at_epoch", str(int(time.time())))
        return events

    def _should_poll_changelog(self) -> bool:
        if self.changelog_interval_sec <= 0:
            return True
        if self.db.get_state("pypi_serial") is None:
            return True
        checked_at = self.db.get_state("pypi_changelog_checked_at_epoch")
        if checked_at is None:
            return True
        try:
            age = time.time() - float(checked_at)
        except ValueError:
            return True
        return age >= self.changelog_interval_sec

    def _parse_rss_item(self, item: ET.Element, *, source: str) -> ReleaseEvent | None:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        author = (item.findtext("author") or "").strip()

        if source == "pypi_packages":
            match = re.search(r"/project/([^/]+)/?", link)
            if not match:
                return None
            package_name = match.group(1)
            try:
                project_metadata = self.fetch_project_metadata(package_name)
            except requests.RequestException:
                return None
            version = str((project_metadata.get("info") or {}).get("version") or "").strip()
            if not version:
                return None
            return ReleaseEvent(
                ecosystem="pypi",
                package_name=package_name,
                version=version,
                source=source,
                cursor=pub_date or title,
                seen_at=now_iso(),
                metadata={
                    "title": title,
                    "link": link,
                    "pubDate": pub_date,
                    "description": description,
                    "author": author,
                    "json": self._compact_pypi_payload(project_metadata),
                },
            )
        else:
            match = re.search(r"/project/([^/]+)/([^/]+)/?", link)
            if match:
                package_name, version = match.group(1), match.group(2)
            else:
                title_match = re.match(r"^(.+)\s+([^\s]+)$", title)
                if not title_match:
                    return None
                package_name, version = title_match.group(1), title_match.group(2)

        return self._build_event(
            package_name=package_name,
            version=version,
            source=source,
            cursor=pub_date or title,
            extra_metadata={
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "description": description,
                "author": author,
            },
        )

    def _build_event(
        self,
        *,
        package_name: str,
        version: str,
        source: str,
        cursor: str,
        extra_metadata: dict[str, Any],
    ) -> ReleaseEvent:
        metadata = dict(extra_metadata)
        if version != "latest":
            try:
                metadata["json"] = self.fetch_release_metadata(package_name, version)
            except requests.RequestException as exc:
                metadata["metadata_fetch_error"] = str(exc)
        return ReleaseEvent(
            ecosystem="pypi",
            package_name=package_name,
            version=version,
            source=source,
            cursor=cursor,
            seen_at=now_iso(),
            metadata=metadata,
        )

    def fetch_release_metadata(self, package_name: str, version: str) -> dict[str, Any]:
        url = PYPI_JSON_URL.format(package=package_name, version=version)
        response = polite_request(self.session, "GET", url, timeout=20)
        response.raise_for_status()
        return self._compact_pypi_payload(response.json())

    def fetch_project_metadata(self, package_name: str) -> dict[str, Any]:
        url = PYPI_PROJECT_JSON_URL.format(package=package_name)
        response = polite_request(self.session, "GET", url, timeout=20)
        response.raise_for_status()
        return response.json()

    def _compact_pypi_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "info": {
                "name": (payload.get("info") or {}).get("name"),
                "version": (payload.get("info") or {}).get("version"),
                "summary": (payload.get("info") or {}).get("summary"),
                "author_email": (payload.get("info") or {}).get("author_email"),
                "project_urls": (payload.get("info") or {}).get("project_urls"),
            },
            "release_count": len(payload.get("releases") or {}),
            "urls": [
                {
                    "filename": item.get("filename"),
                    "packagetype": item.get("packagetype"),
                    "upload_time_iso_8601": item.get("upload_time_iso_8601"),
                    "url": item.get("url"),
                    "sha256": (item.get("digests") or {}).get("sha256"),
                    "size": item.get("size"),
                }
                for item in payload.get("urls", [])
                if isinstance(item, dict)
            ],
        }

    def _xmlrpc_call(self, method: str, *params: object) -> tuple[Any, ...]:
        body = xmlrpc.client.dumps(params, methodname=method, allow_none=True)
        response = polite_request(
            self.session,
            "POST",
            PYPI_XMLRPC_URL,
            data=body,
            headers={"Content-Type": "text/xml"},
            timeout=30,
        )
        response.raise_for_status()
        values, _method_name = xmlrpc.client.loads(response.content)
        return values
