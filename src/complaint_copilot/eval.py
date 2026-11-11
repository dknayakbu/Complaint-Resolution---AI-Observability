"""Offline evaluation helpers for the Phase C data workstream."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from complaint_copilot.contracts import (
    Category,
    EvaluationResult,
    EvaluationScore,
    EvaluationSource,
    EvaluationStatus,
    QueueKey,
    Severity,
)


class DatasetValidationError(ValueError):
    """Raised when a label/input dataset is invalid."""


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(
                f"Invalid JSON on line {line_number} of {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise DatasetValidationError(
                f"Line {line_number} of {path} must decode to an object"
            )
        records.append(payload)
    return records


def _normalise_case_id(
    record: Mapping[str, object], *, field_name: str = "case_id"
) -> str:
    case_id = record.get(field_name)
    if not isinstance(case_id, str) or not case_id.strip():
        raise DatasetValidationError(
            f"{field_name} is required and must be a non-empty string"
        )
    return case_id


def _validate_label_record(
    record: Mapping[str, object],
) -> tuple[str, Category, Severity, QueueKey]:
    case_id = _normalise_case_id(record)
    if "category" not in record or "severity" not in record or "queue" not in record:
        raise DatasetValidationError(
            f"Label for {case_id} is missing category/severity/queue"
        )
    try:
        raw_category = record["category"]
        if not isinstance(raw_category, str):
            raise ValueError
        category = Category(raw_category)
    except ValueError as exc:  # pragma: no cover - exercised via tests
        raise DatasetValidationError(
            f"Label for {case_id} has invalid category"
        ) from exc
    try:
        raw_severity = record["severity"]
        if isinstance(raw_severity, str) and raw_severity in Severity.__members__:
            severity = Severity[raw_severity]
        elif type(raw_severity) is int:
            severity = Severity(raw_severity)
        else:
            raise ValueError
    except ValueError as exc:  # pragma: no cover - exercised via tests
        raise DatasetValidationError(
            f"Label for {case_id} has invalid severity"
        ) from exc
    try:
        raw_queue = record["queue"]
        if not isinstance(raw_queue, str):
            raise ValueError
        queue = QueueKey(raw_queue)
    except ValueError as exc:  # pragma: no cover - exercised via tests
        raise DatasetValidationError(f"Label for {case_id} has invalid queue") from exc
    return case_id, category, severity, queue


def load_labeled_cases(
    input_path: str | Path, label_path: str | Path
) -> dict[str, dict[str, object]]:
    """Load inputs and labels, reject duplicate IDs and split leakage."""
    input_records = _read_jsonl(input_path)
    label_records = _read_jsonl(label_path)

    seen: dict[str, set[str]] = {"input": set(), "label": set()}
    for kind, payload in {"input": input_records, "label": label_records}.items():
        for record in payload:
            case_id = _normalise_case_id(record)
            if case_id in seen[kind]:
                raise DatasetValidationError(
                    f"Duplicate case_id found in {kind} data: {case_id}"
                )
            seen[kind].add(case_id)

    input_ids = seen["input"]
    label_ids = seen["label"]
    missing = sorted(input_ids - label_ids)
    extra = sorted(label_ids - input_ids)
    if missing:
        raise DatasetValidationError(
            f"Labels are missing for case_ids: {', '.join(missing)}"
        )
    if extra:
        raise DatasetValidationError(
            f"Input data is missing for case_ids: {', '.join(extra)}"
        )

    output: dict[str, dict[str, object]] = {}
    for record in input_records:
        case_id = _normalise_case_id(record)
        prohibited = {
            key
            for key in record
            if key in {"expected", "ground_truth", "label"}
            or key.startswith(("expected_", "ground_truth_", "label_"))
        }
        if prohibited:
            prohibited_fields = ", ".join(sorted(prohibited))
            raise DatasetValidationError(
                f"Input record {case_id} contains forbidden expected-label fields: "
                f"{prohibited_fields}"
            )
        output[case_id] = {"input": record}

    for record in label_records:
        case_id, category, severity, queue = _validate_label_record(record)
        output[case_id]["label"] = {
            "category": category,
            "severity": severity,
            "queue": queue,
        }

    return output


def serialize_model_input(record: Mapping[str, object]) -> dict[str, object]:
    """Serialize a complaint record for a model call while rejecting labels."""
    payload = dict(record)
    prohibited = {
        key
        for key in payload
        if key in {"expected", "ground_truth", "label"}
        or key.startswith(("expected_", "ground_truth_", "label_"))
    }
    if prohibited:
        raise DatasetValidationError(
            "ground-truth fields are forbidden in model input: "
            + ", ".join(sorted(prohibited))
        )
    if "complaint_text" not in payload:
        raise DatasetValidationError("Model input must contain complaint_text")
    return payload


def build_confusion_matrix(
    predictions: Mapping[str, str],
    labels: Mapping[str, str],
    ordered_labels: Sequence[str],
) -> dict[str, dict[str, int]]:
    matrix = {
        label: {predicted: 0 for predicted in ordered_labels}
        for label in ordered_labels
    }
    for case_id, actual in labels.items():
        predicted = predictions.get(case_id)
        if predicted is None:
            raise DatasetValidationError(f"No prediction for case_id {case_id}")
        if actual not in matrix:
            raise DatasetValidationError(f"Unknown actual label {actual!r}")
        if predicted not in matrix[actual]:
            matrix[actual][predicted] = 0
        matrix[actual][predicted] += 1
    return matrix


def _coerce_string(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _case_field_map(
    payload: Mapping[str, Mapping[str, object]], *, field_name: str
) -> dict[str, str]:
    result: dict[str, str] = {}
    for case_id, record in payload.items():
        value = record.get(field_name)
        if value is not None:
            result[str(case_id)] = str(value)
    return result


def accuracy(predictions: Mapping[str, str], labels: Mapping[str, str]) -> float:
    if not labels:
        return 0.0
    matched = 0
    for case_id, expected in labels.items():
        if predictions.get(case_id) == expected:
            matched += 1
    return matched / len(labels)


def coverage(predictions: Mapping[str, str], labels: Mapping[str, str]) -> float:
    if not labels:
        return 0.0
    return min(len(predictions), len(labels)) / len(labels)


def _recall_for_threshold(
    predictions: Mapping[str, str],
    labels: Mapping[str, str],
    *,
    expected_value: str,
) -> tuple[float, int]:
    relevant = {
        case_id: value for case_id, value in labels.items() if value == expected_value
    }
    if not relevant:
        return 0.0, 0
    matched = sum(
        1
        for case_id, expected in relevant.items()
        if predictions.get(case_id) == expected
    )
    return matched / len(relevant), len(relevant)


def sev1_recall(predictions: Mapping[str, str], labels: Mapping[str, str]) -> float:
    recall, _ = _recall_for_threshold(predictions, labels, expected_value="SEV1")
    return recall


def effective_sev1_recall(
    predictions: Mapping[str, dict[str, object]],
    labels: Mapping[str, dict[str, object]],
) -> tuple[float, int]:
    prediction_values: dict[str, str] = {}
    label_values: dict[str, str] = {}
    for case_id, record in predictions.items():
        value = record.get("effective_severity")
        if value is None:
            value = record.get("severity")
        if value is not None:
            prediction_values[str(case_id)] = str(value)
    for case_id, record in labels.items():
        value = record.get("effective_severity")
        if value is None:
            value = record.get("severity")
        if value is not None:
            label_values[str(case_id)] = str(value)
    return _recall_for_threshold(prediction_values, label_values, expected_value="SEV1")


def queue_accuracy(predictions: Mapping[str, str], labels: Mapping[str, str]) -> float:
    return accuracy(predictions, labels)


def build_quality_report(
    predictions: Mapping[str, dict[str, object]],
    labels: Mapping[str, dict[str, object]],
    *,
    metric_name: str,
) -> dict[str, object]:
    category_predictions = _case_field_map(predictions, field_name="category")
    category_labels = _case_field_map(labels, field_name="category")
    queue_predictions = _case_field_map(predictions, field_name="queue")
    queue_labels = _case_field_map(labels, field_name="queue")
    severity_predictions = _case_field_map(predictions, field_name="severity")
    severity_labels = _case_field_map(labels, field_name="severity")

    missing_predictions = sorted(set(severity_labels) - set(severity_predictions))
    extra_predictions = sorted(set(severity_predictions) - set(severity_labels))
    eligible_samples = len(severity_labels)
    unknown_samples = len(missing_predictions)
    pred_total = len(severity_predictions)

    raw_recall, raw_denominator = _recall_for_threshold(
        severity_predictions, severity_labels, expected_value="SEV1"
    )
    effective_recall, effective_denominator = effective_sev1_recall(predictions, labels)

    report: dict[str, object] = {
        "metric_name": metric_name,
        "category_accuracy": accuracy(category_predictions, category_labels),
        "queue_accuracy": accuracy(queue_predictions, queue_labels),
        "severity_accuracy": accuracy(severity_predictions, severity_labels),
        "raw_sev1_recall": raw_recall,
        "effective_sev1_recall": effective_recall,
        "coverage": coverage(severity_predictions, severity_labels),
        "denominators": {
            "labels": eligible_samples,
            "predictions": pred_total,
            "eligible_samples": eligible_samples,
            "unknown_samples": unknown_samples,
            "raw_sev1": raw_denominator,
            "effective_sev1": effective_denominator,
            "missing_predictions": len(missing_predictions),
        },
        "missing_predictions": missing_predictions,
        "extra_predictions": extra_predictions,
        "findings": [
            "metric_name generated from the provided evaluation labels",
            "missing labels remain unknown and do not count as pass",
            "coverage is capped at 100% and excludes unknown predictions",
        ],
    }
    return report


def _score_value(
    value: Decimal | int | float | str | None,
) -> Decimal | None:  # pragma: no cover - used by typed call sites
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def offline_rule_result(
    *,
    case_id: str,
    analysis_id: str,
    analysis_revision: int,
    rubric_version: str,
    findings: Sequence[str] = (),
    scores: Sequence[EvaluationScore] = (),
    **kwargs: Any,
) -> EvaluationResult:
    """Create a typed evaluation result for offline rule checks."""
    del kwargs
    return EvaluationResult(
        schema_version=1,
        case_id=case_id,
        analysis_id=analysis_id,
        analysis_revision=analysis_revision,
        evaluator_version="offline-eval-v1",
        rubric_version=rubric_version,
        source=EvaluationSource.ONLINE_RULE,
        status=EvaluationStatus.UNKNOWN,
        findings=tuple(str(item) for item in findings),
        scores=tuple(scores),
        reason_code="missing_label_or_ambiguous_rule",
    )
