"""MCP Apps extension: interactive charts rendered in-conversation.

Each `AppSpec` binds a bundled query to a self-contained HTML app
(ext-apps spec 2026-01-26) that the host renders in a sandboxed iframe.
Per SEP-2133 every app tool degrades gracefully: it returns the same rows
as its backing `get_*` query tool, so clients that did not negotiate the
Apps extension still get the data.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

from mcp.server.apps import Apps, ResourceCsp
from mcp.types import ToolAnnotations

from .registry import PredefinedTool, make_query_handler

# Basemap for the map views (drive, trip, places). They draw with MapLibre GL,
# inlined from apps/vendor/ so nothing loads from a CDN, over CARTO's keyless
# vector styles (Positron / Dark Matter): the style from MAP_STYLE_HOST, then
# tiles, fonts, and sprites from the tile hosts. Where MapLibre cannot run (no
# WebGL, or a host that forbids blob: workers) the views draw their SVG map
# over Esri's gray canvas raster tiles instead; CARTO's keyless raster tiles
# answer every request with a "key required" placeholder. Fetching either
# tells that provider the rough area being viewed; MAP_TILES=false keeps the
# views fully self-contained.
MAP_STYLE_HOST = "https://basemaps.cartocdn.com"
# Listed one by one: not every host accepts a wildcard in a CSP domain.
MAP_VECTOR_HOSTS = (
    MAP_STYLE_HOST,
    "https://tiles.basemaps.cartocdn.com",
    *(f"https://tiles-{shard}.basemaps.cartocdn.com" for shard in "abcd"),
)
MAP_TILE_HOST = "https://server.arcgisonline.com"
_MAP_TILE_PLACEHOLDER = "__MAP_TILE_HOST__"
_MAP_STYLE_PLACEHOLDER = "__MAP_STYLE_HOST__"


@cache
def _load_app_file(*path: str) -> str:
    return files("teslamate_mcp").joinpath("apps", *path).read_text(encoding="utf-8")


def _load_app_html(filename: str) -> str:
    return _load_app_file(filename)


def _uses_map_tiles(filename: str) -> bool:
    return _MAP_TILE_PLACEHOLDER in _load_app_html(filename)


def _map_gl_inlines(map_tiles: bool) -> dict[str, str]:
    """What fills a map view's MapLibre slots: the library, or nothing when tiles are off."""
    if not map_tiles:
        return {"/*__MAP_GL_CSS__*/": "", "/*__MAPLIBRE_JS__*/": "", "/*__MAP_GL_JS__*/": ""}
    return {
        "/*__MAP_GL_CSS__*/": (
            _load_app_file("vendor", "maplibre-gl.css") + "\n" + _load_app_file("map_gl.css")
        ),
        "/*__MAPLIBRE_JS__*/": _load_app_file("vendor", "maplibre-gl.js"),
        "/*__MAP_GL_JS__*/": _load_app_file("map_gl.js").replace(
            _MAP_STYLE_PLACEHOLDER, MAP_STYLE_HOST
        ),
    }


@cache
def _render_app_html(filename: str, map_tiles: bool) -> str:
    """The view as served: basemap hosts and MapLibre filled in, or neither when tiles are off."""
    html = _load_app_html(filename).replace(
        _MAP_TILE_PLACEHOLDER, MAP_TILE_HOST if map_tiles else ""
    )
    for slot, content in _map_gl_inlines(map_tiles).items():
        html = html.replace(slot, content)
    return html


@cache
def _html_fingerprint(filename: str, map_tiles: bool) -> str:
    html = _render_app_html(filename, map_tiles)
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class AppSpec:
    """One UI-bound tool: a bundled query rendered by a bundled HTML app."""

    tool_name: str
    query_name: str
    base_uri: str
    html_file: str
    resource_name: str
    resource_title: str
    resource_description: str
    tool_description: str

    def uri_for(self, *, map_tiles: bool = True) -> str:
        """The served `ui://` URI, fingerprinted with the view as served.

        Hosts may cache a view by its URI, so an unchanged URI can keep serving
        a stale copy after a server upgrade or a settings change. A hash of the
        served document in the path gives every changed view a new URI and
        leaves unchanged ones cacheable.
        """
        scheme_host, _, name = self.base_uri.rpartition("/")
        return f"{scheme_host}/{_html_fingerprint(self.html_file, map_tiles)}/{name}"

    @property
    def uri(self) -> str:
        """The URI under default settings."""
        return self.uri_for()


APP_SPECS: tuple[AppSpec, ...] = (
    AppSpec(
        tool_name="show_charging_curve",
        query_name="get_charging_curve",
        base_uri="ui://teslamate/charging-curve.html",
        html_file="charging_curve.html",
        resource_name="charging_curve_chart",
        resource_title="Charging curve chart",
        resource_description=(
            "Interactive battery-level and charging-power chart for one session."
        ),
        tool_description=(
            "Render an interactive charging-curve chart for one charging session, "
            "displayed directly in the conversation (battery level and charging "
            "power over time, with hover readouts and a data table). Returns the "
            "same rows as get_charging_curve, so it also works as a plain data "
            "tool. Prefer this over get_charging_curve when the user wants to SEE "
            "the curve. Find session ids with search_charging_sessions."
        ),
    ),
    AppSpec(
        tool_name="show_battery_degradation",
        query_name="get_battery_degradation_over_time",
        base_uri="ui://teslamate/battery-degradation.html",
        html_file="battery_degradation.html",
        resource_name="battery_degradation_chart",
        resource_title="Battery degradation chart",
        resource_description=("Interactive monthly rated-range trend chart, one line per car."),
        tool_description=(
            "Render an interactive battery-degradation trend chart, displayed "
            "directly in the conversation (monthly average and best rated range "
            "at full charge, one line per car, with hover readouts and a data "
            "table). Returns the same rows as get_battery_degradation_over_time, "
            "so it also works as a plain data tool. Prefer this over "
            "get_battery_degradation_over_time when the user wants to SEE the "
            "trend."
        ),
    ),
    AppSpec(
        tool_name="show_drive_route",
        query_name="get_drive_route",
        base_uri="ui://teslamate/drive-route.html",
        html_file="drive_route.html",
        resource_name="drive_route_map",
        resource_title="Drive route map",
        resource_description=(
            "Interactive GPS route map with speed and battery readouts for one drive."
        ),
        tool_description=(
            "Render an interactive route map for one drive, displayed directly "
            "in the conversation (the GPS track with start/end markers, hover "
            "readouts for time, speed, and battery, and a waypoint table). "
            "Returns the same rows as get_drive_route, so it also works as a "
            "plain data tool. Prefer this over get_drive_route when the user "
            "wants to SEE the route. Find drive ids with search_drives."
        ),
    ),
    AppSpec(
        tool_name="show_trip_route",
        query_name="get_trip_route",
        base_uri="ui://teslamate/trip-route.html",
        html_file="trip_route.html",
        resource_name="trip_route_map",
        resource_title="Trip route map",
        resource_description=(
            "Interactive map of a multi-drive trip with its stops and charging stops."
        ),
        tool_description=(
            "Render an interactive map of a whole trip (several drives with "
            "stops in between), displayed directly in the conversation: the "
            "full GPS track, start/end markers, a marker at every stop with "
            "charging stops highlighted, hover readouts for time, leg, speed, "
            "battery and stop length, and a waypoint table. Returns the same "
            "rows as get_trip_route, so it also works as a plain data tool. "
            "Prefer this over get_trip_route when the user wants to SEE a trip. "
            "Find trip ids with get_trips."
        ),
    ),
    AppSpec(
        tool_name="show_charging_curve_comparison",
        query_name="get_charging_curve_comparison",
        base_uri="ui://teslamate/charging-curve-comparison.html",
        html_file="charging_curve_comparison.html",
        resource_name="charging_curve_comparison_chart",
        resource_title="Charging curve comparison",
        resource_description="Charging power by battery level for several sessions, overlaid.",
        tool_description=(
            "Render several charging sessions' curves overlaid in one interactive "
            "chart, displayed directly in the conversation: charging power against "
            "battery level, one line per session, with the highest peak and best "
            "20-80% average called out, hover readouts, and a data table. Pass "
            "charging_process_ids to compare specific sessions (e.g. a slow "
            "Supercharger visit against a normal one), or leave it out to show the "
            "latest DC sessions matching the filters. Returns the same rows as "
            "get_charging_curve_comparison, so it also works as a plain data tool. "
            "Find session ids with get_fast_charging_sessions."
        ),
    ),
    AppSpec(
        tool_name="show_activity_report",
        query_name="get_activity_report",
        base_uri="ui://teslamate/activity-report.html",
        html_file="activity_report.html",
        resource_name="activity_report_dashboard",
        resource_title="Activity report",
        resource_description="Monthly or yearly dashboard of driving, consumption, and charging.",
        tool_description=(
            "Render a monthly (per day) or yearly (per month) activity dashboard, "
            "displayed directly in the conversation: totals for distance, drives, "
            "driving time, consumption, energy charged, charging cost, and outside "
            "temperature, with bar and line charts per day or month, hover "
            "readouts, and a data table. Defaults to the current month; pass "
            "period='year', year, or month for others. Returns the same rows as "
            "get_activity_report, so it also works as a plain data tool. Prefer "
            "this when the user asks for a monthly or yearly overview or recap."
        ),
    ),
    AppSpec(
        tool_name="show_visited_places",
        query_name="get_visited_places",
        base_uri="ui://teslamate/visited-places.html",
        html_file="visited_places.html",
        resource_name="visited_places_map",
        resource_title="Visited places map",
        resource_description="Map of the places the car parked at, sized by arrivals.",
        tool_description=(
            "Render a map of the places the car parked at, displayed directly in "
            "the conversation: one circle per place sized by the number of "
            "arrivals, places where it charged highlighted, hover readouts for "
            "arrivals, hours parked, and charging, and a table of places. Returns "
            "the same rows as get_visited_places, so it also works as a plain data "
            "tool. Prefer this when the user wants to SEE where the car goes."
        ),
    ),
    AppSpec(
        tool_name="show_efficiency_vs_temperature",
        query_name="get_drive_efficiency_points",
        base_uri="ui://teslamate/efficiency-vs-temperature.html",
        html_file="efficiency_vs_temperature.html",
        resource_name="efficiency_vs_temperature_chart",
        resource_title="Consumption by temperature",
        resource_description="Scatter of each drive's consumption against outside temperature.",
        tool_description=(
            "Render a scatter chart of every drive's consumption (Wh/km) against "
            "outside temperature, displayed directly in the conversation: one dot "
            "per drive sized by distance and colored by car, the distance-weighted "
            "average per 5 °C band, the cold-weather penalty (below 5 °C against "
            "15-25 °C), hover readouts, and a table of bands. Returns the same rows "
            "as get_drive_efficiency_points, so it also works as a plain data tool. "
            "Prefer this when the user wants to SEE how temperature affects range."
        ),
    ),
    AppSpec(
        tool_name="show_recap",
        query_name="get_recap",
        base_uri="ui://teslamate/recap.html",
        html_file="recap.html",
        resource_name="recap_card",
        resource_title="Year or month in review",
        resource_description="A year or a month in review: totals and highlights.",
        tool_description=(
            "Render a year or a month in review ('Wrapped'), displayed directly in "
            "the conversation: the distance with its change against the period "
            "before, driving time, consumption, charging and cost, odometer and "
            "software updates, and highlights (longest drive and where it went, "
            "busiest day, most efficient day or month, favourite destination, "
            "go-to charging spot, top speed, temperature range), with a data "
            "table. Defaults to the current year; pass period='month' (and year, "
            "month) for a month. Returns the same row as get_recap, so it also "
            "works as a plain data tool. Prefer this when the user asks for a "
            "year or month in review, a wrap-up, or 'Wrapped'."
        ),
    ),
    AppSpec(
        tool_name="show_driven_roads",
        query_name="get_driven_roads",
        base_uri="ui://teslamate/driven-roads.html",
        html_file="driven_roads.html",
        resource_name="driven_roads_map",
        resource_title="Driven roads map",
        resource_description="Map of every road the car has driven.",
        tool_description=(
            "Render a map of every road the car has driven, displayed directly in "
            "the conversation: all drive paths drawn as one network, a route "
            "driven many times drawn once (the newest drive between each pair of "
            "places), the number of routes and the distance they cover, and a "
            "table per car. Returns the same rows as get_driven_roads, so it also "
            "works as a plain data tool. Prefer this when the user wants to SEE "
            "where the car has been driven."
        ),
    ),
)

CHARGING_CURVE_APP_URI = APP_SPECS[0].uri

MAP_CSP = ResourceCsp(
    connect_domains=list(MAP_VECTOR_HOSTS),
    resource_domains=[MAP_TILE_HOST, *MAP_VECTOR_HOSTS],
)

# The ext-apps reference SDK (registerAppTool) stamps both `_meta.ui.resourceUri`
# and this deprecated flat key, because hosts that predate the nested form only
# read the flat one. The Python SDK's Apps.tool() writes only the nested form,
# so add the flat key ourselves to match what hosts are tested against.
LEGACY_RESOURCE_URI_META_KEY = "ui/resourceUri"


# History (0.8.0 → 0.9.1): a ResourceLinkedApps subclass used to prepend a
# result-level `resource_link` block as a second rendering signal. It never
# triggered chart rendering, and newer Claude Desktop builds surface a visible
# "Resource links are not currently supported" notice for the block instead of
# ignoring it — so app tools now rely solely on the spec's tool-level
# `_meta.ui.resourceUri` binding. Do not re-add the result-level link.


def build_apps_extension(
    tools: list[PredefinedTool], *, report_timezone: str, map_tiles: bool = True
) -> Apps:
    """Build the Apps extension; pass the result to MCPServer(extensions=[...]).

    Each app tool reuses its backing query via make_query_handler, so the
    chart and the plain `get_*` tool can never drift apart (same params,
    same tz injection, same typed output schema).
    """
    by_name = {t.name: t for t in tools}

    apps = Apps()

    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    for spec in APP_SPECS:
        query = by_name.get(spec.query_name)
        if query is None:  # fail fast, like a missing .toml sidecar
            raise RuntimeError(
                f"MCP Apps: bundled query '{spec.query_name}' not found; "
                f"required by {spec.tool_name} — its .sql/.toml must exist in queries/"
            )
        handler = make_query_handler(query, report_timezone=report_timezone)
        handler.__name__ = spec.tool_name
        handler.__doc__ = spec.tool_description
        uri = spec.uri_for(map_tiles=map_tiles)
        tiles = map_tiles and _uses_map_tiles(spec.html_file)
        apps.tool(
            resource_uri=uri,
            meta={LEGACY_RESOURCE_URI_META_KEY: uri},
            name=spec.tool_name,
            description=spec.tool_description,
            annotations=annotations,
        )(handler)
        apps.add_html_resource(
            uri,
            _render_app_html(spec.html_file, map_tiles),
            name=spec.resource_name,
            title=spec.resource_title,
            description=spec.resource_description,
            # Hosts deny all external loads unless declared: MapLibre fetches the
            # vector basemap; the SVG map loads raster tiles as images.
            csp=MAP_CSP if tiles else None,
            prefers_border=True,
        )
    return apps
