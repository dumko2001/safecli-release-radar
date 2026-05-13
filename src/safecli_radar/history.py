from __future__ import annotations

from datetime import UTC, datetime, timedelta

from safecli_radar.db import RadarDB
from safecli_radar.models import ReleaseEvent


def annotate_history(event: ReleaseEvent, db: RadarDB) -> ReleaseEvent:
    history = {
        "radar_prior_release_count": db.package_release_count(
            event.ecosystem,
            event.package_name,
            exclude_version=event.version,
        ),
        "radar_recent_release_count_1h": db.package_release_count_since(
            event.ecosystem,
            event.package_name,
            since_iso=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        ),
        "radar_previous_seen_at": db.previous_release_seen_at(
            event.ecosystem,
            event.package_name,
            exclude_version=event.version,
        ),
    }

    metadata = dict(event.metadata)
    metadata["history"] = history
    return ReleaseEvent(
        ecosystem=event.ecosystem,
        package_name=event.package_name,
        version=event.version,
        source=event.source,
        cursor=event.cursor,
        seen_at=event.seen_at,
        metadata=metadata,
    )
