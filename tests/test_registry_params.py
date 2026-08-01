"""Unit tests for the [[params]] TOML contract validation (no Docker needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from teslamate_mcp.tools.registry import discover_predefined_tools


def _write_pair(tmp_path: Path, sql: str, toml: str) -> Path:
    (tmp_path / "q.sql").write_text(sql, encoding="utf-8")
    (tmp_path / "q.toml").write_text(toml, encoding="utf-8")
    return tmp_path


_BASE = 'name = "get_q"\ndescription = "A test query for the contract."\n'


def test_valid_contract_roundtrips(tmp_path: Path) -> None:
    _write_pair(
        tmp_path,
        "SELECT 1 WHERE (%(car_name)s::text IS NULL OR name ILIKE '%%' || %(car_name)s || '%%')"
        " AND d >= %(days)s::int AND k = %(kind)s::text"
        " AND t < (x AT TIME ZONE %(tz)s::text) LIMIT %(limit)s::int",
        _BASE
        + """
[[params]]
name = "car_name"
type = "string"
description = "Car filter."

[[params]]
name = "days"
type = "integer"
description = "Window."
required = true

[[params]]
name = "kind"
type = "string"
description = "Kind."
default = "a"
enum = ["a", "b"]

[[params]]
name = "limit"
type = "integer"
description = "Cap."
default = 10
minimum = 1
maximum = 100
""",
    )
    (tool,) = discover_predefined_tools(tmp_path)
    assert tool.uses_tz is True
    by_name = {p.name: p for p in tool.params}
    assert by_name["car_name"].required is False and by_name["car_name"].default is None
    assert by_name["days"].required is True
    assert by_name["kind"].enum == ("a", "b")
    assert (by_name["limit"].default, by_name["limit"].minimum, by_name["limit"].maximum) == (
        10,
        1,
        100,
    )


@pytest.mark.parametrize(
    ("param_toml", "match"),
    [
        ('name = "x"\ntype = "decimal"\ndescription = "d."', "unknown type"),
        (
            'name = "x"\ntype = "integer"\ndescription = "d."\nrequired = true\ndefault = 3',
            "must not have a default",
        ),
        ('name = "x"\ntype = "integer"\ndescription = "d."\ndefault = "y"', "does not match type"),
        ('name = "x"\ntype = "boolean"\ndescription = "d."\ndefault = 1', "does not match type"),
        ('name = "x"\ntype = "integer"\ndescription = "d."\nenum = ["a"]', "enum only applies"),
        (
            'name = "x"\ntype = "string"\ndescription = "d."\ndefault = "c"\nenum = ["a", "b"]',
            "is not in enum",
        ),
        ('name = "x"\ntype = "string"\ndescription = "d."\nminimum = 1', "only apply to numeric"),
        ('name = "_x"\ntype = "string"\ndescription = "d."', "invalid param name"),
        ('name = "1a"\ntype = "string"\ndescription = "d."', "invalid param name"),
        ('name = "ctx"\ntype = "string"\ndescription = "d."', "reserved"),
        ('name = "tz"\ntype = "string"\ndescription = "d."', "reserved"),
        ('name = "x"\ntype = "string"\ndescription = ""', "non-empty description"),
        ('name = "x"\ntype = "string"\ndescription = "d."\nfoo = 1', "unknown param key"),
    ],
)
def test_bad_param_contract_raises(tmp_path: Path, param_toml: str, match: str) -> None:
    _write_pair(tmp_path, "SELECT %(x)s::text", _BASE + f"\n[[params]]\n{param_toml}\n")
    with pytest.raises(ValueError, match=match):
        discover_predefined_tools(tmp_path)


def test_declared_param_missing_from_sql_raises(tmp_path: Path) -> None:
    _write_pair(
        tmp_path,
        "SELECT 1",
        _BASE + '\n[[params]]\nname = "x"\ntype = "string"\ndescription = "d."\n',
    )
    with pytest.raises(ValueError, match="not used in the SQL"):
        discover_predefined_tools(tmp_path)


def test_sql_placeholder_not_declared_raises(tmp_path: Path) -> None:
    _write_pair(tmp_path, "SELECT %(mystery)s::text", _BASE)
    with pytest.raises(ValueError, match="not declared"):
        discover_predefined_tools(tmp_path)


def test_tz_placeholder_sets_uses_tz_without_declaration(tmp_path: Path) -> None:
    _write_pair(tmp_path, "SELECT x AT TIME ZONE %(tz)s::text FROM t", _BASE)
    (tool,) = discover_predefined_tools(tmp_path)
    assert tool.uses_tz is True
    assert tool.params == ()


def test_stray_percent_raises_when_parameterized(tmp_path: Path) -> None:
    _write_pair(
        tmp_path,
        "SELECT 1 -- 100% of the time\nWHERE x = %(x)s::text",
        _BASE + '\n[[params]]\nname = "x"\ntype = "string"\ndescription = "d."\n',
    )
    with pytest.raises(ValueError, match="bare '%'"):
        discover_predefined_tools(tmp_path)


def test_stray_percent_allowed_without_params(tmp_path: Path) -> None:
    _write_pair(tmp_path, "SELECT 1 -- 100% fine", _BASE)
    (tool,) = discover_predefined_tools(tmp_path)
    assert tool.params == () and tool.uses_tz is False


def test_duplicate_param_names_raise(tmp_path: Path) -> None:
    _write_pair(
        tmp_path,
        "SELECT %(x)s::text",
        _BASE
        + '\n[[params]]\nname = "x"\ntype = "string"\ndescription = "d."\n'
        + '\n[[params]]\nname = "x"\ntype = "integer"\ndescription = "d."\n',
    )
    with pytest.raises(ValueError, match="duplicate param name"):
        discover_predefined_tools(tmp_path)


def test_params_must_be_a_list(tmp_path: Path) -> None:
    (tmp_path / "q.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "q.toml").write_text(_BASE + "params = 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="array of tables"):
        discover_predefined_tools(tmp_path)
