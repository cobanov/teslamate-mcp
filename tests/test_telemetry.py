"""Tests for optional OpenTelemetry export wiring."""

from __future__ import annotations

from teslamate_mcp.telemetry import configure_telemetry


def test_noop_without_endpoint(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert configure_telemetry() is False


def test_provider_installed_with_endpoint(monkeypatch) -> None:
    # Swap the network exporter for an in-memory one: the provider is process-
    # global, so a real OTLP exporter would spam export retries from every
    # span the remaining tests create.
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
        lambda: InMemorySpanExporter(),
    )
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.test:4318")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "teslamate-mcp-test")
    assert configure_telemetry() is True

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    attrs = provider.resource.attributes
    assert attrs["service.name"] == "teslamate-mcp-test"
