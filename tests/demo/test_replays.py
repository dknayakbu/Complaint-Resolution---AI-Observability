from __future__ import annotations

from pathlib import Path

from complaint_copilot.demo_replay import (
    replay_cost,
    replay_drift,
    replay_quality,
    replay_slo,
)

ROOT = Path(__file__).resolve().parents[2]


def test_drift_replay_uses_raw_text_and_observed_actual_scores() -> None:
    report = replay_drift(ROOT / "data")
    assert report["mode"] == "fixture"
    assert report["eligible"] is True
    assert report["status"] == "warning"
    assert report["reference_count"] == 30
    assert report["window_counts"] == [10, 10]
    scores = report["window_scores_base2_jsd"]
    assert isinstance(scores, list)
    assert all(0 <= score <= 1 for score in scores)


def test_cost_replay_crosses_and_recovers_at_declared_positions() -> None:
    report = replay_cost()
    assert report["threshold_crossing_spike_observation"] == 6
    assert report["below_threshold_recovery_observation"] == 3
    assert report["cumulative_cost_usd"] == "0.280"
    assert report["is_invoice"] is False


def test_quality_replay_evaluates_fixture_outputs_and_separates_controlled_q1() -> None:
    report = replay_quality(ROOT / "data")
    q0 = report["q0"]
    q1 = report["q1"]
    assert isinstance(q0, dict)
    assert isinstance(q1, dict)
    assert q0["metric_name"] == "Q0-scripted-fixture-provider"
    assert q0["raw_sev1_recall"] == 0
    assert q0["effective_sev1_recall"] == 0.5
    assert q0["category_accuracy"] == 0.5
    assert q1["raw_sev1_recall"] == 0.75
    assert q1["effective_sev1_recall"] == 11 / 12
    assert q1["denominators"]["raw_sev1"] == 12
    assert "not a model comparison" in report["label_disclaimer"]


def test_slo_recovery_requires_replacing_the_failed_window_member() -> None:
    report = replay_slo()
    degraded = report["one_terminal_failure"]
    recovered = report["after_30_fresh_successes"]
    assert isinstance(degraded, dict)
    assert isinstance(recovered, dict)
    assert degraded["good"] == 29
    assert degraded["bad"] == 1
    assert degraded["error_budget_remaining"] == "-0.70"
    assert recovered["good"] == 30
    assert recovered["bad"] == 0
