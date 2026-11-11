"""Observability helpers and redaction rules for AgentOps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_DEFAULT_REDACTED_KEYS = {
    "complaint",
    "complaint_text",
    "draft",
    "prompt",
    "system_prompt",
    "user_prompt",
    "evidence",
    "exception",
    "error_text",
    "trace_id",
    "case_id",
    "analysis_id",
}


@dataclass(frozen=True)
class TelemetryMetric:
    name: str
    value: float | int
    labels: dict[str, str]


def redact_value(value: str | None) -> str:
    if value is None:
        return "<redacted>"
    cleaned = value.strip()
    if not cleaned:
        return "<redacted>"
    lowered = cleaned.lower()
    contains_sensitive = any(
        token in lowered
        for token in (
            "complaint",
            "prompt",
            "draft",
            "api_key",
            "secret",
            "token",
            "exception",
            "trace",
        )
    )
    return "<redacted>" if contains_sensitive else cleaned[:120]


def redact_labels(labels: Mapping[str, Any] | None) -> dict[str, str]:
    if labels is None:
        return {}
    result: dict[str, str] = {}
    for key, value in labels.items():
        if key in _DEFAULT_REDACTED_KEYS:
            result[key] = "<redacted>"
            continue
        if value is None:
            result[key] = "<none>"
            continue
        result[key] = str(redact_value(str(value)))
    return result


def make_metric(
    name: str,
    value: float | int,
    *,
    labels: Mapping[str, Any] | None = None,
) -> TelemetryMetric:
    return TelemetryMetric(name=name, value=value, labels=redact_labels(labels))


def telemetry_record_to_mapping(record: TelemetryMetric) -> dict[str, Any]:
    return {
        "name": record.name,
        "value": record.value,
        "labels": dict(record.labels),
    }


__all__ = [
    "TelemetryMetric",
    "make_metric",
    "redact_labels",
    "redact_value",
    "telemetry_record_to_mapping",
]
