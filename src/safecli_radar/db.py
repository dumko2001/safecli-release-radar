from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from safecli_radar.models import CandidateScore, ReleaseEvent, SafeCLIResult


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RadarDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        os.makedirs(self.path.parent, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row

    def init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS releases (
              ecosystem TEXT NOT NULL,
              package_name TEXT NOT NULL,
              version TEXT NOT NULL,
              source TEXT NOT NULL,
              cursor TEXT NOT NULL,
              seen_at TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              risk_score INTEGER,
              impact_score INTEGER,
              reasons_json TEXT,
              safecli_command_json TEXT,
              safecli_exit_code INTEGER,
              safecli_stdout TEXT,
              safecli_stderr TEXT,
              safecli_json TEXT,
              scanned_at TEXT,
              event_log_path TEXT,
              PRIMARY KEY (ecosystem, package_name, version)
            );

            CREATE INDEX IF NOT EXISTS idx_releases_seen_at ON releases(seen_at);
            CREATE INDEX IF NOT EXISTS idx_releases_score ON releases(risk_score, impact_score);
            """
        )
        self._ensure_column("releases", "event_log_path", "TEXT")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        if any(str(row["name"]) == column for row in rows):
            return
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def get_state(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_state(self, key: str, value: str | int) -> None:
        self.conn.execute(
            """
            INSERT INTO state(key, value, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value=excluded.value,
              updated_at=excluded.updated_at
            """,
            (key, str(value), now_iso()),
        )
        self.conn.commit()

    def release_exists(self, ecosystem: str, package_name: str, version: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM releases
            WHERE ecosystem=? AND package_name=? AND version=?
            """,
            (ecosystem, package_name, version),
        ).fetchone()
        return row is not None

    def record_release(self, event: ReleaseEvent) -> bool:
        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO releases(
              ecosystem, package_name, version, source, cursor, seen_at, metadata_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.ecosystem,
                event.package_name,
                event.version,
                event.source,
                event.cursor,
                event.seen_at,
                json.dumps(event.metadata, sort_keys=True),
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def update_score(self, event: ReleaseEvent, score: CandidateScore) -> None:
        self.conn.execute(
            """
            UPDATE releases
            SET risk_score=?, impact_score=?, reasons_json=?
            WHERE ecosystem=? AND package_name=? AND version=?
            """,
            (
                score.risk_score,
                score.impact_score,
                json.dumps(score.reasons),
                event.ecosystem,
                event.package_name,
                event.version,
            ),
        )
        self.conn.commit()

    def update_metadata(self, event: ReleaseEvent) -> None:
        self.conn.execute(
            """
            UPDATE releases
            SET metadata_json=?
            WHERE ecosystem=? AND package_name=? AND version=?
            """,
            (
                json.dumps(event.metadata, sort_keys=True),
                event.ecosystem,
                event.package_name,
                event.version,
            ),
        )
        self.conn.commit()

    def record_safecli_result(self, event: ReleaseEvent, result: SafeCLIResult) -> None:
        self.conn.execute(
            """
            UPDATE releases
            SET safecli_command_json=?,
                safecli_exit_code=?,
                safecli_stdout=?,
                safecli_stderr=?,
                safecli_json=?,
                scanned_at=?
            WHERE ecosystem=? AND package_name=? AND version=?
            """,
            (
                json.dumps(result.command),
                result.exit_code,
                result.stdout,
                result.stderr,
                json.dumps(result.parsed_json, sort_keys=True) if result.parsed_json else None,
                now_iso(),
                event.ecosystem,
                event.package_name,
                event.version,
            ),
        )
        self.conn.commit()

    def record_event_log_path(
        self,
        event: ReleaseEvent,
        *,
        jsonl_path: str,
    ) -> None:
        self.conn.execute(
            """
            UPDATE releases
            SET event_log_path=?
            WHERE ecosystem=? AND package_name=? AND version=?
            """,
            (
                jsonl_path,
                event.ecosystem,
                event.package_name,
                event.version,
            ),
        )
        self.conn.commit()

    def package_release_count(
        self,
        ecosystem: str,
        package_name: str,
        *,
        exclude_version: str | None = None,
    ) -> int:
        if exclude_version is None:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM releases
                WHERE ecosystem=? AND package_name=?
                """,
                (ecosystem, package_name),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM releases
                WHERE ecosystem=? AND package_name=? AND version<>?
                """,
                (ecosystem, package_name, exclude_version),
            ).fetchone()
        return int(row["count"] or 0)

    def package_release_count_since(
        self,
        ecosystem: str,
        package_name: str,
        *,
        since_iso: str,
    ) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM releases
            WHERE ecosystem=? AND package_name=? AND seen_at>=?
            """,
            (ecosystem, package_name, since_iso),
        ).fetchone()
        return int(row["count"] or 0)

    def previous_release_seen_at(
        self,
        ecosystem: str,
        package_name: str,
        *,
        exclude_version: str | None = None,
    ) -> str | None:
        if exclude_version is None:
            row = self.conn.execute(
                """
                SELECT seen_at
                FROM releases
                WHERE ecosystem=? AND package_name=?
                ORDER BY seen_at DESC
                LIMIT 1
                """,
                (ecosystem, package_name),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT seen_at
                FROM releases
                WHERE ecosystem=? AND package_name=? AND version<>?
                ORDER BY seen_at DESC
                LIMIT 1
                """,
                (ecosystem, package_name, exclude_version),
            ).fetchone()
        return str(row["seen_at"]) if row else None

    def recent_unscanned(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM releases
            WHERE scanned_at IS NULL
            ORDER BY COALESCE(risk_score, 0) DESC, COALESCE(impact_score, 0) DESC, seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
