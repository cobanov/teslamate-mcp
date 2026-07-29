"""Discover and register predefined SQL-backed tools."""

from __future__ import annotations

import inspect
import logging
import re
import tomllib
from dataclasses import dataclass, field
from importlib.resources import as_file, files
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, create_model

from ..db import fetch_all

logger = logging.getLogger(__name__)

_PARAM_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}
_PARAM_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
_PLACEHOLDER_RE = re.compile(r"%\((\w+)\)s")
# A bare % that is neither %% nor the start of a %(name)s placeholder breaks
# psycopg's client-side substitution once a params argument is supplied.
_STRAY_PERCENT_RE = re.compile(r"(?<!%)%(?![%(])")
# "tz" is injected by the registry from Settings.report_timezone; "ctx" is the
# MCP context argument. Neither may be declared as a user-facing param.
_RESERVED_PARAM_NAMES = frozenset({"ctx", "tz"})
_ALLOWED_PARAM_KEYS = frozenset(
    {"name", "type", "description", "required", "default", "minimum", "maximum", "enum"}
)
_ALLOWED_OUTPUT_KEYS = frozenset({"name", "type", "description"})


@dataclass(frozen=True)
class ToolParam:
    """A typed, optional-by-default tool argument declared in a .toml sidecar."""

    name: str
    type: str
    description: str
    required: bool = False
    default: Any = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    enum: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ToolOutputColumn:
    """One result column declared in a .toml [[output]] table.

    Advisory typing: every column is nullable and undeclared columns still
    pass through, so a declaration drifting behind the SQL can never turn a
    working query into a runtime error — it only under-documents it.
    """

    name: str
    type: str
    description: str | None = None


@dataclass(frozen=True)
class PredefinedTool:
    """A SQL query exposed as an MCP tool, declared via a .sql + .toml pair."""

    name: str
    description: str
    sql: str
    source: str  # filename, for diagnostics
    params: tuple[ToolParam, ...] = field(default=())
    uses_tz: bool = False
    output: tuple[ToolOutputColumn, ...] = field(default=())


def _queries_dir() -> Path:
    """Locate the bundled `queries/` directory inside the installed package."""
    resource = files("teslamate_mcp").joinpath("queries")
    with as_file(resource) as path:
        return Path(path)


def _default_matches_type(default: Any, param_type: str) -> bool:
    # bool is checked first because isinstance(True, int) is True in Python.
    if param_type == "boolean":
        return isinstance(default, bool)
    if isinstance(default, bool):
        return False
    if param_type == "integer":
        return isinstance(default, int)
    if param_type == "number":
        return isinstance(default, int | float)
    return isinstance(default, str)


def _parse_param(raw: Any, source: str) -> ToolParam:
    """Validate one [[params]] table. All failures raise ValueError naming the file."""
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: each [[params]] entry must be a table")
    unknown = set(raw) - _ALLOWED_PARAM_KEYS
    if unknown:
        raise ValueError(f"{source}: unknown param key(s) {sorted(unknown)!r}")

    for key in ("name", "type", "description"):
        if key not in raw:
            raise ValueError(f"{source}: param is missing required key {key!r}")

    name = raw["name"]
    if not isinstance(name, str) or not _PARAM_NAME_RE.match(name):
        raise ValueError(f"{source}: invalid param name {name!r} (want ^[a-z][a-z0-9_]{{0,29}}$)")
    if name in _RESERVED_PARAM_NAMES:
        raise ValueError(f"{source}: param name {name!r} is reserved")

    param_type = raw["type"]
    if param_type not in _PARAM_TYPES:
        raise ValueError(
            f"{source}: param {name!r} has unknown type {param_type!r} "
            f"(want one of {sorted(_PARAM_TYPES)})"
        )

    description = raw["description"]
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{source}: param {name!r} needs a non-empty description")

    required = raw.get("required", False)
    if not isinstance(required, bool):
        raise ValueError(f"{source}: param {name!r} 'required' must be a boolean")

    default = raw.get("default")
    if required and "default" in raw:
        raise ValueError(f"{source}: param {name!r} is required and must not have a default")
    if "default" in raw and not _default_matches_type(default, param_type):
        raise ValueError(
            f"{source}: param {name!r} default {default!r} does not match type {param_type!r}"
        )

    minimum = raw.get("minimum")
    maximum = raw.get("maximum")
    if (minimum is not None or maximum is not None) and param_type not in ("integer", "number"):
        raise ValueError(f"{source}: param {name!r} minimum/maximum only apply to numeric types")

    enum_raw = raw.get("enum")
    enum: tuple[str, ...] | None = None
    if enum_raw is not None:
        if param_type != "string":
            raise ValueError(f"{source}: param {name!r} enum only applies to string params")
        if (
            not isinstance(enum_raw, list)
            or not enum_raw
            or not all(isinstance(v, str) for v in enum_raw)
        ):
            raise ValueError(f"{source}: param {name!r} enum must be a non-empty list of strings")
        enum = tuple(enum_raw)
        if "default" in raw and default not in enum:
            raise ValueError(f"{source}: param {name!r} default {default!r} is not in enum")

    return ToolParam(
        name=name,
        type=param_type,
        description=description,
        required=required,
        default=default,
        minimum=minimum,
        maximum=maximum,
        enum=enum,
    )


def _parse_output_column(raw: Any, source: str) -> ToolOutputColumn:
    """Validate one [[output]] table. All failures raise ValueError naming the file."""
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: each [[output]] entry must be a table")
    unknown = set(raw) - _ALLOWED_OUTPUT_KEYS
    if unknown:
        raise ValueError(f"{source}: unknown output key(s) {sorted(unknown)!r}")
    for key in ("name", "type"):
        if key not in raw:
            raise ValueError(f"{source}: output column is missing required key {key!r}")

    name = raw["name"]
    if not isinstance(name, str) or not _PARAM_NAME_RE.match(name):
        raise ValueError(f"{source}: invalid output column name {name!r}")

    col_type = raw["type"]
    if col_type not in _PARAM_TYPES:
        raise ValueError(
            f"{source}: output column {name!r} has unknown type {col_type!r} "
            f"(want one of {sorted(_PARAM_TYPES)})"
        )

    description = raw.get("description")
    if description is not None and (not isinstance(description, str) or not description.strip()):
        raise ValueError(f"{source}: output column {name!r} description must be a non-empty string")

    return ToolOutputColumn(name=name, type=col_type, description=description)


def _validate_sql_placeholders(sql: str, params: tuple[ToolParam, ...], source: str) -> bool:
    """Cross-check SQL `%(name)s` placeholders against declared params.

    Returns whether the SQL uses the reserved `tz` placeholder (injected at
    call time from Settings.report_timezone, never declared in the .toml).
    """
    placeholders = set(_PLACEHOLDER_RE.findall(sql))
    uses_tz = "tz" in placeholders
    declared = {p.name for p in params}

    undeclared = placeholders - {"tz"} - declared
    if undeclared:
        raise ValueError(
            f"{source}: SQL placeholder(s) {sorted(undeclared)!r} are not declared in [[params]]"
        )
    unused = declared - placeholders
    if unused:
        raise ValueError(f"{source}: declared param(s) {sorted(unused)!r} are not used in the SQL")

    if (params or uses_tz) and _STRAY_PERCENT_RE.search(sql):
        raise ValueError(
            f"{source}: SQL contains a bare '%' — escape literal percent signs as '%%' "
            "in parameterized queries"
        )
    return uses_tz


def discover_predefined_tools(directory: Path | None = None) -> list[PredefinedTool]:
    """Scan a directory for .sql files and load each one's sidecar .toml metadata.

    Each .sql file must have a sibling .toml with `name` and `description` keys
    and optional [[params]] tables. Missing sidecars or contract violations raise
    so misconfiguration fails fast at startup rather than silently producing a
    half-empty or mis-typed tool list.
    """
    base = directory or _queries_dir()
    tools: list[PredefinedTool] = []
    for sql_path in sorted(base.glob("*.sql")):
        toml_path = sql_path.with_suffix(".toml")
        if not toml_path.exists():
            raise FileNotFoundError(
                f"Missing sidecar metadata for {sql_path.name}: expected {toml_path.name}"
            )
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        try:
            name = meta["name"]
            description = meta["description"]
        except KeyError as exc:
            raise ValueError(f"{toml_path.name} is missing required key {exc.args[0]!r}") from exc

        raw_params = meta.get("params", [])
        if not isinstance(raw_params, list):
            raise ValueError(f"{toml_path.name}: 'params' must be an array of tables")
        params = tuple(_parse_param(raw, toml_path.name) for raw in raw_params)
        seen: set[str] = set()
        for p in params:
            if p.name in seen:
                raise ValueError(f"{toml_path.name}: duplicate param name {p.name!r}")
            seen.add(p.name)

        raw_output = meta.get("output", [])
        if not isinstance(raw_output, list):
            raise ValueError(f"{toml_path.name}: 'output' must be an array of tables")
        output = tuple(_parse_output_column(raw, toml_path.name) for raw in raw_output)
        seen_cols: set[str] = set()
        for col in output:
            if col.name in seen_cols:
                raise ValueError(f"{toml_path.name}: duplicate output column {col.name!r}")
            seen_cols.add(col.name)

        sql = sql_path.read_text(encoding="utf-8")
        uses_tz = _validate_sql_placeholders(sql, params, toml_path.name)

        tools.append(
            PredefinedTool(
                name=name,
                description=description,
                sql=sql,
                source=sql_path.name,
                params=params,
                uses_tz=uses_tz,
                output=output,
            )
        )
    return tools


def build_row_model(tool: PredefinedTool) -> type[BaseModel] | None:
    """Build a pydantic row model from [[output]] declarations, or None.

    Used as the handler's `list[Model]` return annotation so the SDK derives a
    typed outputSchema (per-column names/types) instead of an open object.
    Every field is `T | None = None` and the model allows extras, so column
    drift between the .toml and the SQL degrades documentation, never calls.
    """
    if not tool.output:
        return None
    fields: dict[str, Any] = {
        col.name: (
            _PARAM_TYPES[col.type] | None,
            Field(default=None, description=col.description),
        )
        for col in tool.output
    }
    return create_model(f"{tool.name}_row", __config__=ConfigDict(extra="allow"), **fields)


def _annotation_for(param: ToolParam) -> Any:
    base: Any = Literal[param.enum] if param.enum else _PARAM_TYPES[param.type]
    if not param.required and param.default is None:
        base = base | None  # nullable = "filter off" (binds SQL NULL)
    return Annotated[base, Field(description=param.description, ge=param.minimum, le=param.maximum)]


def _build_signature(tool: PredefinedTool) -> inspect.Signature:
    """Craft the signature the SDK introspects to build the tool's input schema.

    ctx must be the FIRST parameter (the SDK's Context detection stops there) and
    defaults must live on inspect.Parameter, never inside Field() — pydantic 2
    rejects a default in both places.
    """
    parameters = [
        inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Context)
    ]
    ordered = sorted(tool.params, key=lambda p: not p.required)
    for p in ordered:
        default = inspect.Parameter.empty if p.required else p.default
        parameters.append(
            inspect.Parameter(
                p.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=_annotation_for(p),
            )
        )
    row_model = build_row_model(tool)
    return_annotation = list[row_model] if row_model else list[dict[str, Any]]
    return inspect.Signature(parameters, return_annotation=return_annotation)


def register_predefined_tools(
    mcp: MCPServer, tools: list[PredefinedTool], *, report_timezone: str
) -> None:
    """Attach each predefined tool to the MCP server.

    A small factory captures the SQL per tool so the registered coroutine
    closes over only its own query — without a factory, every registered
    coroutine would share the loop variable and run the same SQL.
    """
    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    for tool in tools:
        _register_one(mcp, tool, annotations, report_timezone=report_timezone)


def _register_one(
    mcp: MCPServer,
    tool: PredefinedTool,
    annotations: ToolAnnotations,
    *,
    report_timezone: str,
) -> None:
    async def handler(ctx: Context, **params: Any) -> list[dict[str, Any]]:
        pool = ctx.request_context.lifespan_context.pool
        bound = {p.name: params.get(p.name, p.default) for p in tool.params}
        if tool.uses_tz:
            bound["tz"] = report_timezone
        logger.info("Running %s (%s)", tool.name, tool.source)
        # `or None` keeps psycopg's %-escaping rules off for param-less SQL.
        rows = await fetch_all(pool, tool.sql, bound or None)
        logger.info("%s returned %d row(s)", tool.name, len(rows))
        return rows

    handler.__name__ = tool.name
    handler.__doc__ = tool.description
    # The crafted signature (real annotation objects, not strings) is what
    # the SDK introspects — it both excludes ctx from the client-facing schema
    # and surfaces the declared params with types, defaults, and constraints.
    handler.__signature__ = _build_signature(tool)  # type: ignore[attr-defined]
    mcp.tool(name=tool.name, description=tool.description, annotations=annotations)(handler)
