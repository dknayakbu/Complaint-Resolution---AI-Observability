from __future__ import annotations

from pathlib import Path

import pytest

from complaint_copilot.drift import evaluate_drift_windows, window_drift_score
from complaint_copilot.eval import DatasetValidationError, build_quality_report, load_labeled_cases
from complaint_copilot.feedback import merge, sort_pending_candidates
from complaint_copilot.online_eval import OnlineRuleEvaluator
from complaint_copilot.contracts import (
    AnalysisOutcome,
    AnalysisResult,
    AnnotationStatus,
    EvaluationStatus,
    SignalReference,
    StageOutcomeRecord,
    StageStatus,
    Severity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_phase_c_dataset_files_exist_and_are_valid() -> None:
    for family in ("showcase", "baseline", "holdout", "drift"):
        complaints_path = DATA_DIR / family / "complaints.jsonl"
        assert complaints_path.exists(), f"Missing {complaints_path}"
        if family != "drift":
            labels_path = DATA_DIR / family / "labels.jsonl"
            assert labels_path.exists(), f"Missing {labels_path}"

    holdout = load_labeled_cases(DATA_DIR / "holdout" / "complaints.jsonl", DATA_DIR / "holdout" / "labels.jsonl")
    assert len(holdout) == 30
    assert set(row["category"] for row in (DATA_DIR / "holdout" / "labels.jsonl").read_text(encoding="utf-8").splitlines() if row.strip())

    drift_rows = load_labeled_cases(DATA_DIR / "drift" / "window_1.jsonl", DATA_DIR / "drift" / "window_1_labels.jsonl")
    assert len(drift_rows) == 10


def test_load_labeled_cases_rejects_missing_labels_and_duplicate_ids() -> None:
    with pytest.raises(DatasetValidationError, match="Labels are missing"):
        load_labeled_cases(DATA_DIR / "baseline" / "complaints.jsonl", DATA_DIR / "showcase" / "labels.jsonl")

    dup_input = DATA_DIR / "holdout" / "complaints.jsonl"
    with pytest.raises(DatasetValidationError, match="Duplicate case_id"):
        load_labeled_cases(dup_input, dup_input)


def test_online_rule_evaluator_uses_policy_context_and_unknown_when_no_label() -> None:
    evaluator = OnlineRuleEvaluator()
    result = AnalysisResult(
        schema_version=1,
        case_id="case-42",
        analysis_id="analysis-42",
        request_id="req-42",
        analysis_revision=1,
        run_mode="demo",
        analysis_outcome=AnalysisOutcome.COMPLETE,
        case_state="awaiting_review",
        trace_id="trace-42",
        policy_version="policy-v1",
        model_policy_version="model-v1",
        classification_prompt_version="prompt-v1",
        classification_schema_version="schema-v1",
        drafting_prompt_version="draft-prompt-v1",
        drafting_schema_version="draft-schema-v1",
        classification=None,
        effective_severity=None,
        draft="draft text",
        classification_stage=StageOutcomeRecord(status=StageStatus.SKIPPED, failure_code=None),
        drafting_stage=StageOutcomeRecord(status=StageStatus.SUCCEEDED, failure_code=None),
        cost={"known_subtotal_usd": "0.00", "complete": True, "unknown_reason": None},
    )
    evaluation = evaluator.check(result, {"policy_flags": ["fraud_signal"], "expected_category": "fraud_scams"})
    assert evaluation.status is EvaluationStatus.UNKNOWN
    assert evaluation.reason_code == "no_label_available"


def test_drift_monitoring_marks_shift_windows_and_requires_eligible_sample_sizes() -> None:
    baseline = [
        {"complaint_text": ("I cannot access my account and I keep getting login loops after password reset." * 4)}
        for _ in range(30)
    ]
    shifted = [
        {"complaint_text": ("A scammer told me to move funds and share my verification code to unlock my account." * 3)}
        for _ in range(10)
    ]
    score = window_drift_score(baseline, shifted)
    assert 0.0 <= score <= 1.0

    report = evaluate_drift_windows(baseline, [shifted], threshold=0.10)
    assert report["eligible"] is True

    with pytest.raises(Exception):
        window_drift_score(baseline[:29], shifted)


def test_feedback_merge_keeps_reason_codes_and_priority_order() -> None:
    signal_a = SignalReference(source="eval", reference_id="case-a:rev1", reason_code="safety_failure")
    signal_b = SignalReference(source="human", reference_id="case-a:rev1", reason_code="quality_feedback")
    pending = merge(None, signal_a)
    merged = merge(pending, signal_b)

    assert merged.priority == "P1"
    assert len(merged.signals) == 2
    assert merged.status is AnnotationStatus.PENDING
    assert merged.evidence_links == ("case-a:rev1",)

    ordered = sort_pending_candidates([merged])
    assert ordered[0].case_id == "case-a"


def test_build_quality_report_preserves_unknown_missing_labels_and_metric_summary() -> None:
    predictions = {"case-1": {"category": "fraud_scams", "severity": "SEV1", "queue": "fraud_scams"}}
    labels = {"case-1": {"category": "fraud_scams", "severity": "SEV1", "queue": "fraud_scams"}, "case-2": {"category": "accounts", "severity": "SEV2", "queue": "accounts"}}
    report = build_quality_report(predictions, labels, metric_name="fixture_report")
    assert report["metric_name"] == "fixture_report"
    assert report["coverage"] == 0.5
    assert "missing labels remain unknown" in " ".join(report["findings"])
