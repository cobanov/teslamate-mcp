"""Opt-in charging-cost write tools (gated by Settings.enable_charging_writes).

Write tools are deliberately hand-written code, not registry catalog entries:
the declarative .sql/.toml registry stays read-only by design. The database
role's column-scoped grant (UPDATE (cost) ON charging_processes) is the real
boundary — even a bug here cannot touch anything else.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..db import execute_write

_SET_COST_SQL = """
UPDATE charging_processes
SET cost = %(cost)s::numeric(10, 2)
WHERE id = %(charging_process_id)s::int
RETURNING id AS charging_process_id,
    start_date,
    end_date,
    charge_energy_added AS energy_added_kwh,
    cost;
"""


def register_charging_write_tools(mcp: FastMCP) -> None:
    """Register `set_charging_cost` and its receipt-backfill prompt."""

    annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,  # overwrites any previously stored cost
        idempotentHint=True,
        openWorldHint=False,
    )

    description = (
        "Set the total cost of one charging session in the TeslaMate database "
        "(the same field TeslaMate's own UI edits). Find the session id with "
        "search_charging_sessions first. Overwrites any existing cost. Returns "
        "the updated session for confirmation."
    )

    async def set_charging_cost(
        ctx: Context,
        charging_process_id: int = Field(
            ...,
            description="The charging session's id, as returned by search_charging_sessions.",
        ),
        cost: float = Field(
            ...,
            ge=0,
            le=100000,
            description="Total cost of the session, in the currency configured in TeslaMate.",
        ),
    ) -> list[dict[str, Any]]:
        pool = ctx.request_context.lifespan_context.pool
        await ctx.info(f"Setting cost of charging session {charging_process_id} to {cost}")
        rows = await execute_write(
            pool,
            _SET_COST_SQL,
            {"charging_process_id": charging_process_id, "cost": cost},
        )
        if not rows:
            raise ValueError(
                f"No charging session with id {charging_process_id}. "
                "Find ids with search_charging_sessions."
            )
        await ctx.info(f"Charging session {charging_process_id} updated")
        return rows

    set_charging_cost.__annotations__["ctx"] = Context
    mcp.tool(name="set_charging_cost", description=description, annotations=annotations)(
        set_charging_cost
    )

    @mcp.prompt(
        name="backfill_costs_from_receipts",
        description="Match charging receipts to recorded sessions and write their costs.",
    )
    async def backfill_costs_from_receipts() -> str:
        return (
            "The user will provide charging receipts. For each receipt:\n"
            "1. Extract the date, the energy delivered (kWh), and the amount paid.\n"
            "2. Call `search_charging_sessions` with start_date/end_date covering the "
            "receipt date plus or minus one day (add the `location` filter if the "
            "receipt names a place).\n"
            "3. Match on the closest `energy_added_kwh`. If no session is within a "
            "sensible tolerance, or several are equally close, show the candidates "
            "and ask the user instead of guessing.\n"
            "4. For each confirmed match, call `set_charging_cost` with the session's "
            "`charging_process_id` and the receipt amount.\n"
            "5. When all receipts are processed, call `get_charging_costs` with "
            "group_by='month' and present a short summary of what was updated."
        )
