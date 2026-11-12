"""Deterministic replays through Phase B/C logic."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict

from complaint_copilot.classification import ClassificationAgent
from complaint_copilot.contracts import AnalysisRequest, ModelDecision, Stage
from complaint_copilot.cost import detect_cost_anomaly
from complaint_copilot.drift import evaluate_drift_windows, window_drift_score
from complaint_copilot.embedding_drift import MODEL_NAME, embedding_distances
from complaint_copilot.eval import build_quality_report, load_labeled_cases
from complaint_copilot.policy import (
    apply_safeguards,
    queue_for_category,
    validate_classification,
)
from complaint_copilot.provider import FixtureProvider
from complaint_copilot.slo import compute_sli, error_budget_remaining


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    return rows


def replay_drift(data_root: Path) -> dict[str, object]:
    directory = data_root / "drift"
    baseline = _read_jsonl(directory / "baseline.jsonl")
    windows = [
        _read_jsonl(directory / "window_1.jsonl"),
        _read_jsonl(directory / "window_2.jsonl"),
    ]
    report = evaluate_drift_windows(baseline, windows, threshold=0.10)
    scores = [window_drift_score(baseline, window) for window in windows]
    return {
        "mode": "fixture",
        "status": report["status"],
        "eligible": report["eligible"],
        "reference_count": len(baseline),
        "window_counts": [len(window) for window in windows],
        "window_scores_base2_jsd": scores,
        "warning_after_consecutive_windows": report["status"] == "warning",
        "source": "example complaint texts processed by the Phase C extractor",
    }


def measure_embedding_drift(
    data_root: Path, windows: list[list[dict[str, object]]]
) -> dict[str, object]:
    baseline = _read_jsonl(data_root / "drift" / "baseline.jsonl")
    rows = [baseline, *windows]
    texts: list[list[str]] = []
    for group in rows:
        group_texts = []
        for row in group:
            text = row.get("complaint_text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("each complaint must contain non-empty text")
            group_texts.append(text)
        texts.append(group_texts)
    return {
        "model": MODEL_NAME,
        "reference_count": len(baseline),
        "window_counts": [len(window) for window in windows],
        "cosine_distances": embedding_distances(texts[0], texts[1:]),
    }


def replay_embedding_drift(data_root: Path) -> dict[str, object]:
    directory = data_root / "drift"
    return measure_embedding_drift(
        data_root,
        [
            _read_jsonl(directory / "window_1.jsonl"),
            _read_jsonl(directory / "window_2.jsonl"),
        ],
    )


class BatchDriftResult(TypedDict):
    reference_count: int
    complaint_count: int
    score_base2_jsd: float
    threshold: float
    above_threshold: bool


def measure_batch_drift(
    data_root: Path, complaints: list[dict[str, object]]
) -> BatchDriftResult:
    baseline = _read_jsonl(data_root / "drift" / "baseline.jsonl")
    score = window_drift_score(baseline, complaints)
    return {
        "reference_count": len(baseline),
        "complaint_count": len(complaints),
        "score_base2_jsd": score,
        "threshold": 0.10,
        "above_threshold": score > 0.10,
    }


def replay_cost() -> dict[str, object]:
    normal = Decimal("0.004")
    spike = Decimal("0.016")
    history = [normal] * 30
    baseline = history[:15]
    ratios = [Decimal("1")]
    first_crossing: int | None = None
    first_recovery: int | None = None
    flagged = False

    for offset, amount in enumerate([spike] * 8 + [normal] * 8, 1):
        history.append(amount)
        anomaly = detect_cost_anomaly(
            baseline_costs=baseline,
            current_costs=history[-8:],
        )
        ratio = (
            anomaly.current_mean_usd / anomaly.baseline_mean_usd
            if anomaly.baseline_mean_usd
            else Decimal("0")
        )
        ratios.append(ratio)
        if anomaly.flagged and first_crossing is None:
            first_crossing = offset
            flagged = True
        if flagged and not anomaly.flagged and first_recovery is None:
            first_recovery = offset - 8
    total = sum(history[30:], Decimal("0")) + normal * 30
    return {
        "mode": "fixture",
        "baseline_per_analysis_usd": str(normal),
        "spike_per_analysis_usd": str(spike),
        "baseline_count": len(baseline),
        "recent_window_size": 8,
        "ratios_initial_then_each_observation": [str(value) for value in ratios],
        "threshold_crossing_spike_observation": first_crossing,
        "below_threshold_recovery_observation": first_recovery,
        "cumulative_cost_usd": str(total),
        "is_invoice": False,
    }


def replay_quality(data_root: Path) -> dict[str, object]:
    cases = load_labeled_cases(
        data_root / "holdout" / "complaints.jsonl",
        data_root / "holdout" / "labels.jsonl",
    )
    labels: dict[str, dict[str, object]] = {}
    predictions: dict[str, dict[str, object]] = {}
    fixture_classifier = ClassificationAgent(FixtureProvider())
    decision = ModelDecision(
        stage=Stage.CLASSIFICATION,
        model="fixture-evaluation-classifier",
        policy_version="fixture-evaluation-policy-v1",
        reason="credential-free fixture-only evaluation; no model calls",
    )
    for case_id, row in cases.items():
        input_record = row["input"]
        label = row["label"]
        if not isinstance(input_record, dict) or not isinstance(label, dict):
            raise ValueError("holdout input and label records must be loaded")
        complaint_text = input_record.get("complaint_text")
        if not isinstance(complaint_text, str):
            raise ValueError(f"holdout input {case_id} has no complaint text")
        category = str(label["category"])
        severity = f"SEV{int(label['severity'])}"
        queue = str(label["queue"])
        labels[case_id] = {
            "category": category,
            "severity": severity,
            "queue": queue,
        }
        request = AnalysisRequest(
            complaint_text=complaint_text,
            synthetic=True,
            source_sample_id=case_id,
        )
        response = fixture_classifier.run(request, decision)
        classification = validate_classification(response.content, complaint_text)
        effective_severity, _ = apply_safeguards(complaint_text, classification)
        predictions[case_id] = {
            "category": classification.category.value,
            "severity": f"SEV{int(classification.model_severity)}",
            "effective_severity": f"SEV{int(effective_severity)}",
            "queue": queue_for_category(classification.category).value,
        }

    q0 = build_quality_report(
        predictions, labels, metric_name="Q0-scripted-fixture-provider"
    )
    q1_predictions = {
        key: {
            "category": value["category"],
            "severity": value["severity"],
            "effective_severity": value["severity"],
            "queue": value["queue"],
        }
        for key, value in labels.items()
    }
    sev1_cases = [
        case_id for case_id, label in labels.items() if label["severity"] == "SEV1"
    ]
    if len(sev1_cases) != 12:
        raise ValueError("quality replay requires exactly 12 declared SEV1 labels")
    for case_id in sev1_cases[:3]:
        q1_predictions[case_id]["severity"] = "SEV3"
        q1_predictions[case_id]["effective_severity"] = "SEV3"
    for case_id in sev1_cases[:2]:
        q1_predictions[case_id]["effective_severity"] = "SEV1"
    q1 = build_quality_report(
        q1_predictions, labels, metric_name="Q1-controlled-degraded-fixture"
    )
    return {
        "mode": "fixture",
        "label_disclaimer": (
            "Example labels are for arithmetic rehearsal, not independently "
            "adjudicated ground truth or live model results. Q0 uses actual "
            "scripted FixtureProvider outputs; Q1 is a separate controlled "
            "degradation derived from the example labels, not a model comparison."
        ),
        "q0": q0,
        "q1": q1,
    }


def replay_slo() -> dict[str, object]:
    outcomes = [True] * 30
    healthy = _slo_snapshot(outcomes)
    outcomes.append(False)
    degraded = _slo_snapshot(outcomes[-30:])
    outcomes.extend([True] * 30)
    recovered = _slo_snapshot(outcomes[-30:])
    return {
        "mode": "fixture",
        "target": "0.99",
        "healthy": healthy,
        "one_terminal_failure": degraded,
        "after_30_fresh_successes": recovered,
        "burn_rate_after_failure": str((Decimal(1) / Decimal(30)) / Decimal("0.01")),
    }


def _slo_snapshot(outcomes: list[bool]) -> dict[str, Any]:
    good = sum(outcomes)
    bad = len(outcomes) - good
    sli = compute_sli(good=good, bad=bad)
    return {
        "eligible_samples": sli.eligible_samples,
        "good": sli.good,
        "bad": sli.bad,
        "good_rate": str(sli.good_rate),
        "error_budget_remaining": str(
            error_budget_remaining(
                target_slo=Decimal("0.99"),
                total_samples=len(outcomes),
                bad_samples=bad,
            )
        ),
    }
