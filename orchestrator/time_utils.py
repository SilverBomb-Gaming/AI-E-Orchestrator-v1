from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


AUDIT_TIMEZONE = timezone(timedelta(hours=-4), name="UTC-04:00")
AUDIT_TIMEZONE_LABEL = "Eastern Time — New York"
STANDARD_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2} \(Eastern Time — New York\)$"
)


def format_timestamp(value: datetime) -> str:
    current = value
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    eastern = current.astimezone(AUDIT_TIMEZONE)
    return f"{eastern.strftime('%Y-%m-%d %H:%M:%S %z')[:-2]}:{eastern.strftime('%z')[-2:]} ({AUDIT_TIMEZONE_LABEL})"


def get_current_timestamp(value: datetime | None = None) -> str:
    return format_timestamp(value or datetime.now(timezone.utc))


def is_standard_timestamp(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    return STANDARD_TIMESTAMP_PATTERN.fullmatch(value.strip()) is not None


def parse_timestamp(value: str | None) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp value is required")
    text = value.strip()
    if is_standard_timestamp(text):
        base = text.split(" (", 1)[0]
        return datetime.strptime(base, "%Y-%m-%d %H:%M:%S %z")
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_timestamp(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp value is required")
    return format_timestamp(parse_timestamp(value))


__all__ = [
    "AUDIT_TIMEZONE_LABEL",
    "STANDARD_TIMESTAMP_PATTERN",
    "format_timestamp",
    "get_current_timestamp",
    "is_standard_timestamp",
    "normalize_timestamp",
    "parse_timestamp",
]