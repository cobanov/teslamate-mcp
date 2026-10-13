"""Unit tests for the SQL pre-check validator."""

from __future__ import annotations

import pytest

from teslamate_mcp.tools.custom_sql import SqlValidationError, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT * FROM cars",
        "  select id from cars where id = 1  ",
        "WITH recent AS (SELECT * FROM cars) SELECT * FROM recent",
        "SELECT 'DROP TABLE foo' AS s",  # forbidden keyword only inside a string literal
        "SELECT 1 -- DROP TABLE foo\n",  # forbidden keyword in a comment
        "SELECT 1;",  # single trailing semicolon
    ],
)
def test_accepts_valid_queries(sql: str) -> None:
    validate_sql(sql)


@pytest.mark.parametrize(
    ("sql", "fragment"),
    [
        ("", "empty"),
        ("DROP TABLE cars", "Only SELECT"),
        ("INSERT INTO cars VALUES (1)", "Only SELECT"),
        ("UPDATE cars SET name = 'x'", "Only SELECT"),
        ("SELECT 1; SELECT 2", "Multiple"),
        ("EXPLAIN ANALYZE SELECT 1", "Only SELECT"),
        ("VACUUM cars", "Only SELECT"),
        ("SELECT * FROM cars; DROP TABLE cars", "Multiple"),
        # forbidden-keyword check catches DDL/DML hidden inside an otherwise
        # SELECT-shaped query (e.g. an attempted CTE-DML)
        (
            "WITH x AS (DELETE FROM cars RETURNING *) SELECT * FROM x",
            "forbidden",
        ),
    ],
)
def test_rejects_invalid_queries(sql: str, fragment: str) -> None:
    with pytest.raises(SqlValidationError, match=fragment):
        validate_sql(sql)
