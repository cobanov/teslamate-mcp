"""Optional OpenTelemetry export.

The MCP SDK v2 emits OTel spans for every request out of the box, but without
a configured provider they are no-ops. This wires a real OTLP/HTTP exporter
when (and only when) the standard OTEL_EXPORTER_OTLP_ENDPOINT (or the
traces-specific variant) is set — so the default deployment carries zero
telemetry overhead and no code changes are needed to turn tracing on.
"""

from __future__ import annotations

import logging
import os

from . import __version__

logger = logging.getLogger(__name__)


def configure_telemetry() -> bool:
    """Install an OTLP span exporter if an endpoint is configured. Idempotent-ish:
    call once at process start, before the server handles requests."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    if not endpoint:
        return False

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME", "teslamate-mcp"),
            "service.version": __version__,
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry tracing enabled (exporting to %s)", endpoint)
    return True
