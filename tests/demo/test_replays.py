from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import Mock, call, patch

from fastapi.testclient import TestClient

from complaint_copilot.api import _record_replay_metrics, create_app
from complaint_copilot.contracts import RunMode
from complaint_copilot.demo_replay import (
    measure_batch_drift,
    replay_cost,
    replay_drift,
    replay_quality,
    replay_slo,
)
from complaint_copilot.repository import RecordNotFound, SQLiteRepository
from complaint_copilot.settings import AppSettings

ROOT = Path(__file__).resolve().parents[2]
COMPLAINTS = runpy.run_path(str(ROOT / "make_complaints.py"))["COMPLAINTS"]


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


def test_drift_replay_metrics_keep_windows_separate() -> None:
    instruments = Mock()
    with patch("complaint_copilot.api.instruments", instruments):
        _record_replay_metrics(
            "drift",
            {"window_scores_base2_jsd": [0.2, 0.6]},
            run_mode=RunMode.DEMO,
        )
    assert instruments.drift_scores.record.call_args_list == [
        call(0.2, {"run_mode": "demo", "replay": "drift", "window": "1"}),
        call(0.6, {"run_mode": "demo", "replay": "drift", "window": "2"}),
    ]


def test_complaint_burst_shows_shift_against_reference() -> None:
    report = measure_batch_drift(
        ROOT / "data", [{"complaint_text": text} for text in COMPLAINTS]
    )
    assert report["reference_count"] == 30
    assert report["complaint_count"] == 10
    assert report["score_base2_jsd"] > report["threshold"]


def test_batch_drift_is_authorized_unique_and_recorded_once(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "batch.sqlite3")
    app = create_app(
        AppSettings(mode="fixture", database_path=tmp_path / "batch.sqlite3"),
        repository=repository,
    )
    ids = [f"case-{index}" for index in range(10)]
    cases = dict(zip(ids, COMPLAINTS, strict=True))
    cases["case-10"] = "A different invented complaint."

    def get_case(case_id: str) -> dict[str, str]:
        if case_id not in cases:
            raise RecordNotFound(case_id)
        return {"complaint_text": cases[case_id]}

    headers = {
        "X-Internal-Token": "fixture-internal-token",
        "Idempotency-Key": "batch-1",
    }
    with (
        patch.object(
            repository,
            "get_case",
            side_effect=get_case,
        ),
        patch("complaint_copilot.api.instruments") as instruments,
        patch("complaint_copilot.api.flush_telemetry"),
        TestClient(app) as client,
    ):
        denied = client.post(
            "/internal/demo/batch-drift",
            json={"case_ids": ids},
            headers={"Idempotency-Key": "batch-1"},
        )
        assert denied.status_code == 401
        repeated_ids = client.post(
            "/internal/demo/batch-drift",
            json={"case_ids": [ids[0]] * 10},
            headers=headers,
        )
        assert repeated_ids.status_code == 422
        too_few = client.post(
            "/internal/demo/batch-drift",
            json={"case_ids": ids[:5]},
            headers=headers,
        )
        assert too_few.status_code == 422
        response = client.post(
            "/internal/demo/batch-drift", json={"case_ids": ids}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["above_threshold"] is True
        again = client.post(
            "/internal/demo/batch-drift", json={"case_ids": ids}, headers=headers
        )
        assert again.json()["duplicate"] is True
        instruments.drift_scores.record.assert_called_once()
        conflict = client.post(
            "/internal/demo/batch-drift",
            json={"case_ids": ids[:-1] + ["case-10"]},
            headers=headers,
        )
        assert conflict.status_code == 409
        other_batch = client.post(
            "/internal/demo/batch-drift",
            json={"case_ids": list(reversed(ids[:-1])) + ["case-99"]},
            headers=headers,
        )
        assert other_batch.status_code == 404


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
