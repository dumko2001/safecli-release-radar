from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def polite_request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    base_delay_sec: float = 1.0,
    max_delay_sec: float = 60.0,
    **kwargs: Any,
) -> requests.Response:
    for attempt in range(max_retries + 1):
        response = session.request(method, url, **kwargs)
        if response.status_code not in RETRY_STATUS_CODES or attempt >= max_retries:
            return response
        time.sleep(_retry_delay_sec(response, attempt, base_delay_sec, max_delay_sec))
    return response


def _retry_delay_sec(
    response: requests.Response,
    attempt: int,
    base_delay_sec: float,
    max_delay_sec: float,
) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        parsed = _parse_retry_after(retry_after)
        if parsed is not None:
            return min(max(parsed, 0.0), max_delay_sec)

    exponential = base_delay_sec * (2**attempt)
    jitter = random.uniform(0, base_delay_sec)
    return min(exponential + jitter, max_delay_sec)


def _parse_retry_after(value: str) -> float | None:
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return (retry_at - datetime.now(UTC)).total_seconds()
