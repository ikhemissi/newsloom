"""Shared Retry-After parsing; callers assign their own safe failure category."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def retry_delay(value: str | None, attempt: int) -> float:
    if value is None:
        return float(2**attempt)
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except ValueError, TypeError, OverflowError:
            raise ValueError("invalid_retry_after") from None
    if not 0 <= seconds < float("inf"):
        raise ValueError("invalid_retry_after")
    return seconds
