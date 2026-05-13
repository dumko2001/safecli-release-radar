from __future__ import annotations

from urllib.parse import quote

import requests

from safecli_radar.db import now_iso
from safecli_radar.models import ReleaseEvent
from safecli_radar.pypi_watcher import PyPIWatcher

NPM_PACKAGE_URL = "https://registry.npmjs.org/{package}"


def resolve_package(ecosystem: str, package_spec: str, *, user_agent: str) -> ReleaseEvent:
    if ecosystem == "npm":
        package_name, requested_version = _parse_npm_spec(package_spec)
        return _resolve_npm(package_name, requested_version, user_agent=user_agent)
    if ecosystem == "pypi":
        package_name, requested_version = _parse_pypi_spec(package_spec)
        return _resolve_pypi(package_name, requested_version, user_agent=user_agent)
    raise ValueError("ecosystem must be npm or pypi")


def _resolve_npm(
    package_name: str,
    requested_version: str,
    *,
    user_agent: str,
) -> ReleaseEvent:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
    response = session.get(NPM_PACKAGE_URL.format(package=quote(package_name, safe="")), timeout=20)
    response.raise_for_status()
    package_doc = response.json()

    dist_tags = package_doc.get("dist-tags") or {}
    version = requested_version
    if requested_version == "latest":
        version = str(dist_tags.get("latest") or "").strip()
    if not version:
        raise ValueError(f"could not resolve npm version for {package_name}")

    versions = package_doc.get("versions") or {}
    manifest = versions.get(version)
    if not isinstance(manifest, dict):
        raise ValueError(f"npm package {package_name}@{version} not found")

    return ReleaseEvent(
        ecosystem="npm",
        package_name=str(package_doc.get("name") or package_name),
        version=version,
        source="manual_check",
        cursor=f"manual:{package_name}@{version}",
        seen_at=now_iso(),
        metadata={
            "description": package_doc.get("description"),
            "dist_tags": dist_tags,
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


def _resolve_pypi(
    package_name: str,
    requested_version: str,
    *,
    user_agent: str,
) -> ReleaseEvent:
    watcher = PyPIWatcher(_NoopDB(), user_agent=user_agent)
    if requested_version == "latest":
        project_metadata = watcher.fetch_project_metadata(package_name)
        requested_version = str((project_metadata.get("info") or {}).get("version") or "").strip()
    if not requested_version:
        raise ValueError(f"could not resolve PyPI version for {package_name}")

    return ReleaseEvent(
        ecosystem="pypi",
        package_name=package_name,
        version=requested_version,
        source="manual_check",
        cursor=f"manual:{package_name}=={requested_version}",
        seen_at=now_iso(),
        metadata={"json": watcher.fetch_release_metadata(package_name, requested_version)},
    )


def _parse_npm_spec(value: str) -> tuple[str, str]:
    token = value.strip()
    if not token:
        raise ValueError("package is required")
    if token.startswith("@"):
        if "@" in token[1:]:
            name, version = token.rsplit("@", 1)
            return name, version or "latest"
        return token, "latest"
    if "@" in token:
        name, version = token.rsplit("@", 1)
        return name, version or "latest"
    return token, "latest"


def _parse_pypi_spec(value: str) -> tuple[str, str]:
    token = value.strip()
    if not token:
        raise ValueError("package is required")
    if "==" in token:
        name, version = token.split("==", 1)
        return name.strip(), version.strip() or "latest"
    return token, "latest"


class _NoopDB:
    def get_state(self, _key: str) -> None:
        return None

    def set_state(self, _key: str, _value: str | int) -> None:
        return None

    def record_release(self, _event: ReleaseEvent) -> bool:
        return False
