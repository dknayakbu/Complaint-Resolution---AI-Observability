"""Low-cardinality OpenTelemetry metrics and trace setup for the demo API."""

from __future__ import annotations

import os
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


@dataclass(frozen=True)
class DemoInstruments:
    requests: metrics.Counter
    analyses: metrics.Counter
    stage_calls: metrics.Counter
    stage_duration: metrics.Histogram
    tokens: metrics.Counter
    estimated_cost: metrics.Counter
    cost_unknown: metrics.Counter
    safety_promotions: metrics.Counter
    review_backlog: metrics.UpDownCounter
    reviews: metrics.Counter
    drift_scores: metrics.Histogram
    drift_warnings: metrics.Counter
    cost_ratios: metrics.Histogram
    cost_anomalies: metrics.Counter
    quality_recall: metrics.Histogram
    slo_outcomes: metrics.Counter
    incident_events: metrics.Counter


def _otlp_endpoint(signal: str) -> str | None:
    base = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
    if not base:
        return None
    return f"{base}/v1/{signal}"


def _create_instruments() -> tuple[trace.Tracer, DemoInstruments]:
    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "complaint-copilot-api")}
    )
    trace_provider = TracerProvider(resource=resource)
    trace_endpoint = _otlp_endpoint("traces")
    if trace_endpoint is not None:
        trace_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=trace_endpoint))
        )
    trace.set_tracer_provider(trace_provider)

    metric_readers = []
    metric_endpoint = _otlp_endpoint("metrics")
    if metric_endpoint is not None:
        interval = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "15000"))
        if interval < 1000:
            raise ValueError("OTEL_METRIC_EXPORT_INTERVAL_MS must be at least 1000")
        metric_readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=metric_endpoint),
                export_interval_millis=interval,
            )
        )
    meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter("complaint_copilot.demo", "0.1.0")
    return trace.get_tracer("complaint_copilot.workflow", "0.1.0"), DemoInstruments(
        requests=meter.create_counter("complaint_requests"),
        analyses=meter.create_counter("complaint_analysis"),
        stage_calls=meter.create_counter("llm_calls"),
        stage_duration=meter.create_histogram("llm_call_duration_seconds", unit="s"),
        tokens=meter.create_counter("llm_tokens"),
        estimated_cost=meter.create_counter("llm_estimated_cost_usd", unit="USD"),
        cost_unknown=meter.create_counter("llm_cost_unknown"),
        safety_promotions=meter.create_counter("complaint_safety_promotions"),
        review_backlog=meter.create_up_down_counter("complaint_review_backlog"),
        reviews=meter.create_counter("complaint_reviews"),
        drift_scores=meter.create_histogram("complaint_drift_js_divergence", unit="1"),
        drift_warnings=meter.create_counter("complaint_drift_warnings"),
        cost_ratios=meter.create_histogram("complaint_cost_anomaly_ratio", unit="1"),
        cost_anomalies=meter.create_counter("complaint_cost_anomaly_events"),
        quality_recall=meter.create_histogram("evaluation_sev1_recall", unit="1"),
        slo_outcomes=meter.create_counter("complaint_slo_outcomes"),
        incident_events=meter.create_counter("complaint_incident_events"),
    )


tracer, instruments = _create_instruments()


def flush_telemetry() -> None:
    trace_provider = trace.get_tracer_provider()
    if isinstance(trace_provider, TracerProvider):
        trace_provider.force_flush(timeout_millis=5000)
    meter_provider = metrics.get_meter_provider()
    if isinstance(meter_provider, MeterProvider):
        meter_provider.force_flush(timeout_millis=5000)
