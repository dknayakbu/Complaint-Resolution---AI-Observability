from __future__ import annotations

import json
from pathlib import Path

import pytest

from complaint_copilot.contracts import (
    AnalysisResult,
    AnnotationStatus,
    EvaluationStatus,
    SignalReference,
)
from complaint_copilot.drift import (
    DriftIneligibleError,
    evaluate_drift_windows,
    window_drift_score,
)
from complaint_copilot.eval import (
    DatasetValidationError,
    build_quality_report,
    load_labeled_cases,
)
from complaint_copilot.feedback import merge, sort_pending_candidates
from complaint_copilot.online_eval import OnlineRuleEvaluator

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_phase_c_dataset_files_exist_and_are_valid() -> None:
    for family in ("showcase", "baseline", "holdout"):
        complaints_path = DATA_DIR / family / "complaints.jsonl"
        assert complaints_path.exists(), f"Missing {complaints_path}"
        labels_path = DATA_DIR / family / "labels.jsonl"
        assert labels_path.exists(), f"Missing {labels_path}"

    holdout = load_labeled_cases(
        DATA_DIR / "holdout" / "complaints.jsonl", DATA_DIR / "holdout" / "labels.jsonl"
    )
    assert len(holdout) == 30
    assert all("label" in row for row in holdout.values())

    drift_rows = load_labeled_cases(
        DATA_DIR / "drift" / "window_1.jsonl",
        DATA_DIR / "drift" / "window_1_labels.jsonl",
    )
    assert len(drift_rows) == 10


def test_load_labeled_cases_rejects_missing_labels_and_duplicate_ids(
    tmp_path: Path,
) -> None:
    with pytest.raises(DatasetValidationError, match="Labels are missing"):
        load_labeled_cases(
            DATA_DIR / "baseline" / "complaints.jsonl",
            DATA_DIR / "showcase" / "labels.jsonl",
        )

    dup_input = tmp_path / "duplicate-inputs.jsonl"
    dup_input.write_text(
        '{"case_id":"duplicate","complaint_text":"First synthetic complaint"}\n'
        '{"case_id":"duplicate","complaint_text":"Second synthetic complaint"}\n',
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError, match="Duplicate case_id"):
        load_labeled_cases(dup_input, DATA_DIR / "holdout" / "labels.jsonl")


def test_online_rule_evaluator_uses_policy_context_and_unknown_when_no_label() -> None:
    evaluator = OnlineRuleEvaluator()
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "fixtures"
        / "successful-two-stage.json"
    )
    result = AnalysisResult.from_mapping(
        json.loads(fixture_path.read_text(encoding="utf-8"))
    )
    evaluation = evaluator.check(
        result, {"policy_flags": ["fraud_signal"], "rubric_version": "test-rubric"}
    )
    assert evaluation.status is EvaluationStatus.UNKNOWN
    assert evaluation.reason_code == "no_label_available"


def test_drift_monitoring_marks_shift_windows_and_requires_eligible_sample_sizes() -> (
    None
):
    baseline = [
        {
            "complaint_text": (
                "I cannot access my account and I keep getting login loops "
                "after password reset." * 4
            )
        }
        for _ in range(30)
    ]
    shifted = [
        {
            "complaint_text": (
                "A scammer told me to move funds and share my verification "
                "code to unlock my account." * 3
            )
        }
        for _ in range(10)
    ]
    score = window_drift_score(baseline, shifted)
    assert 0.0 <= score <= 1.0

    report = evaluate_drift_windows(baseline, [shifted], threshold=0.10)
    assert report["eligible"] is True

    with pytest.raises(DriftIneligibleError):
        window_drift_score(baseline[:29], shifted)


def test_feedback_merge_keeps_reason_codes_and_priority_order() -> None:
    signal_a = SignalReference(
        source="eval", reference_id="case-a:rev1", reason_code="safety_failure"
    )
    signal_b = SignalReference(
        source="human", reference_id="case-a:rev1", reason_code="quality_feedback"
    )
    pending = merge(None, signal_a)
    merged = merge(pending, signal_b)

    assert merged.priority == "P1"
    assert len(merged.signals) == 2
    assert merged.status is AnnotationStatus.PENDING
    assert merged.evidence_links == ("case-a:rev1",)

    ordered = sort_pending_candidates([merged])
    assert ordered[0].case_id == "case-a"


def test_build_quality_report_preserves_unknown_missing_labels_and_metric_summary() -> (
    None
):
    predictions = {
        "case-1": {
            "category": "fraud_scams",
            "severity": "SEV1",
            "queue": "fraud_scams",
        }
    }
    labels = {
        "case-1": {
            "category": "fraud_scams",
            "severity": "SEV1",
            "queue": "fraud_scams",
        },
        "case-2": {"category": "accounts", "severity": "SEV2", "queue": "accounts"},
    }
    report = build_quality_report(predictions, labels, metric_name="fixture_report")
    assert report["metric_name"] == "fixture_report"
    assert report["coverage"] == 0.5
    assert "missing labels remain unknown" in " ".join(report["findings"])
