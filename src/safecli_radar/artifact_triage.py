from __future__ import annotations

import io
import re
import tarfile
import zipfile
from dataclasses import dataclass

import requests

from safecli_radar.http import polite_request
from safecli_radar.models import ReleaseEvent

ARCHIVE_MAX_BYTES = 12_000_000
ARCHIVE_MAX_COUNT = 4
SCAN_FILE_MAX_BYTES = 16_000
SCAN_FILE_MAX_COUNT = 80

SUSPICIOUS_PATH_TERMS = {
    ".npmrc",
    ".pypirc",
    ".ssh",
    "postinstall",
    "preinstall",
}

SUSPICIOUS_CONTENT_PATTERNS = {
    "reads environment variables": re.compile(r"\b(process\.env|os\.environ|env\s*\|)", re.I),
    "reads package manager credentials": re.compile(r"\.(npmrc|pypirc)\b", re.I),
    "reads cloud credentials": re.compile(r"(aws_secret_access_key|aws_access_key_id)", re.I),
    "executes shell commands": re.compile(r"\b(child_process|subprocess|os\.system|exec\()", re.I),
    "posts, downloads, or exfiltrates data": re.compile(
        r"\b(requests\.post|http\.client|curl\s+|wget\s+|telegram|webhook|pastebin|ngrok)",
        re.I,
    ),
    "uses dynamic code evaluation": re.compile(
        r"(\beval\s*\(|\bFunction\s*\(|\bexec\s*\(|marshal\.loads)",
    ),
    "contains encoded payload": re.compile(r"[A-Za-z0-9+/]{180,}={0,2}"),
}


@dataclass(frozen=True)
class ArtifactFile:
    path: str
    content: bytes


def triage_artifact(event: ReleaseEvent, *, user_agent: str) -> ReleaseEvent:
    archive_entries = _archive_entries(event)
    if not archive_entries:
        return event

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "*/*"})
    flattened_findings: list[str] = []
    archive_summaries: list[dict[str, object]] = []
    for entry in archive_entries[:ARCHIVE_MAX_COUNT]:
        archive = _download_archive(session, entry["url"])
        files = _read_archive_files(archive, entry["filename"])
        findings = _findings(files)
        archive_summaries.append(
            {
                "filename": entry["filename"],
                "url": entry["url"],
                "file_count_scanned": len(files),
                "findings": findings,
            }
        )
        flattened_findings.extend(f"{entry['filename']}: {finding}" for finding in findings)

    metadata = dict(event.metadata)
    metadata["artifact_triage"] = {
        "archive_count_scanned": len(archive_summaries),
        "archives": archive_summaries,
        "findings": sorted(set(flattened_findings))[:25],
    }
    return ReleaseEvent(
        ecosystem=event.ecosystem,
        package_name=event.package_name,
        version=event.version,
        source=event.source,
        cursor=event.cursor,
        seen_at=event.seen_at,
        metadata=metadata,
    )


def _archive_entries(event: ReleaseEvent) -> list[dict[str, str]]:
    if event.ecosystem == "npm":
        manifest = event.metadata.get("manifest") if isinstance(event.metadata, dict) else {}
        dist = manifest.get("dist") if isinstance(manifest, dict) else {}
        url = dist.get("tarball") if isinstance(dist, dict) else None
        if not url:
            return []
        filename = str(url).rsplit("/", 1)[-1] or f"{event.package_name}-{event.version}.tgz"
        return [{"filename": filename, "url": str(url)}]

    if event.ecosystem == "pypi":
        json_payload = event.metadata.get("json") if isinstance(event.metadata, dict) else {}
        urls = json_payload.get("urls") if isinstance(json_payload, dict) else []
        if not isinstance(urls, list):
            return []
        candidates = [item for item in urls if isinstance(item, dict) and item.get("url")]
        candidates.sort(key=_pypi_artifact_priority)
        return [
            {
                "filename": str(item.get("filename") or str(item["url"]).rsplit("/", 1)[-1]),
                "url": str(item["url"]),
            }
            for item in candidates[:ARCHIVE_MAX_COUNT]
        ]

    return []


def _pypi_artifact_priority(item: dict) -> tuple[int, str]:
    filename = str(item.get("filename") or "").lower()
    package_type = str(item.get("packagetype") or "").lower()
    if package_type == "sdist":
        return (0, filename)
    if any(token in filename for token in ("manylinux", "macosx", "win_amd64", "abi", "cp")):
        return (1, filename)
    return (2, filename)


def _download_archive(session: requests.Session, archive_url: str) -> bytes:
    response = polite_request(session, "GET", archive_url, timeout=30, stream=True)
    response.raise_for_status()

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > ARCHIVE_MAX_BYTES:
            raise RuntimeError(f"archive exceeds {ARCHIVE_MAX_BYTES} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _read_archive_files(archive: bytes, archive_url: str) -> list[ArtifactFile]:
    if archive_url.endswith((".whl", ".zip")):
        return _read_zip_files(archive)
    return _read_tar_files(archive)


def _read_tar_files(archive: bytes) -> list[ArtifactFile]:
    files: list[ArtifactFile] = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
        members = [member for member in tar.getmembers() if member.isfile()]
        members.sort(key=lambda member: _scan_priority(member.name))
        for member in members[:SCAN_FILE_MAX_COUNT]:
            extracted = tar.extractfile(member)
            if not extracted:
                continue
            files.append(ArtifactFile(member.name, extracted.read(SCAN_FILE_MAX_BYTES)))
    return files


def _read_zip_files(archive: bytes) -> list[ArtifactFile]:
    files: list[ArtifactFile] = []
    with zipfile.ZipFile(io.BytesIO(archive)) as zip_archive:
        members = [member for member in zip_archive.infolist() if not member.is_dir()]
        members.sort(key=lambda member: _scan_priority(member.filename))
        for member in members[:SCAN_FILE_MAX_COUNT]:
            files.append(
                ArtifactFile(
                    member.filename,
                    zip_archive.read(member.filename)[:SCAN_FILE_MAX_BYTES],
                )
            )
    return files


def _scan_priority(path: str) -> tuple[int, str]:
    lowered = path.lower()
    base = lowered.rsplit("/", 1)[-1]
    if base in {"package.json", "setup.py", "setup.cfg", "pyproject.toml"}:
        return (0, lowered)
    if any(term in lowered for term in ("install", "script", "bin", "cli")):
        return (1, lowered)
    if lowered.endswith((".js", ".ts", ".mjs", ".cjs", ".py", ".sh", ".ps1")):
        return (2, lowered)
    return (3, lowered)


def _findings(files: list[ArtifactFile]) -> list[str]:
    findings: list[str] = []
    for item in files:
        lowered_path = item.path.lower()
        for term in SUSPICIOUS_PATH_TERMS:
            if term in lowered_path:
                findings.append(f"suspicious path term '{term}' in {item.path}")

        text = item.content.decode("utf-8", errors="ignore")
        for label, pattern in SUSPICIOUS_CONTENT_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label} in {item.path}")

    return sorted(set(findings))[:25]
