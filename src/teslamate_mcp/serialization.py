"""JSON-safe value conversion for query results."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID


def to_jsonable(value: Any) -> Any:
    """Recursively convert a value into JSON-serializable primitives.

    Decimal becomes float so language models can do arithmetic on the values
    instead of seeing them as opaque strings. TeslaMate stores telemetry,
    not currency, so precision loss is acceptable.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in value]
    return str(value)


def rows_to_jsonable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert a list of dict rows from psycopg into JSON-safe dicts."""
    return [to_jsonable(row) for row in rows]
