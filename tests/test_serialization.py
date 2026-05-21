"""Unit tests for the JSON-safe value converter."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from teslamate_mcp.serialization import rows_to_jsonable, to_jsonable


def test_decimal_becomes_float() -> None:
    assert to_jsonable(Decimal("12.5")) == 12.5
    assert isinstance(to_jsonable(Decimal("12.5")), float)


def test_datetime_becomes_iso_string() -> None:
    assert to_jsonable(datetime(2025, 1, 2, 3, 4, 5)) == "2025-01-02T03:04:05"
    assert to_jsonable(date(2025, 1, 2)) == "2025-01-02"


def test_timedelta_becomes_seconds() -> None:
    assert to_jsonable(timedelta(minutes=2)) == 120.0


def test_uuid_becomes_string() -> None:
    u = UUID("12345678-1234-5678-1234-567812345678")
    assert to_jsonable(u) == "12345678-1234-5678-1234-567812345678"


def test_nested_structures_are_recursive() -> None:
    value = {"a": [Decimal("1.5"), {"b": date(2025, 1, 1)}]}
    assert to_jsonable(value) == {"a": [1.5, {"b": "2025-01-01"}]}


def test_rows_to_jsonable() -> None:
    rows = [
        {"id": 1, "battery_kwh": Decimal("75.00"), "logged_at": date(2025, 1, 1)},
        {"id": 2, "battery_kwh": Decimal("82.50"), "logged_at": date(2025, 1, 2)},
    ]
    out = rows_to_jsonable(rows)
    assert out == [
        {"id": 1, "battery_kwh": 75.0, "logged_at": "2025-01-01"},
        {"id": 2, "battery_kwh": 82.5, "logged_at": "2025-01-02"},
    ]
