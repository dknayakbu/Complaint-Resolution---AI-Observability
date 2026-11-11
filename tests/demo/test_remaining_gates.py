from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from complaint_copilot.api import create_app
from complaint_copilot.provider import FixtureProvider, OpenAIProvider
from complaint_copilot.repository import SQLiteRepository
from complaint_copilot.settings import AppSettings


def _client(tmp_path: Path) -> TestClient:
    settings = AppSettings(
        mode="fixture",
        database_path=tmp_path / "demo.sqlite3",
        model="fixture-default",
        classification_model="fixture-classifier",
        drafting_model="fixture-drafter",
        evaluation_model="fixture-evaluator",
    )
    return TestClient(
        create_app(
            settings,
            repository=SQLiteRepository(tmp_path / "demo.sqlite3"),
            provider=FixtureProvider(),
        )
    )


def test_live_mode_requires_explicit_bounded_approval() -> None:
    with pytest.raises(ValueError, match="LIVE_MODEL_APPROVED"):
        AppSettings(
            mode="live",
            openai_api_key="not-used",
            reviewer_token="reviewer",
            internal_token="internal",
            short_input_max=100,
            medium_input_max=500,
        )

    approved = AppSettings(
        mode="live",
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
        live_model_approved=True,
        live_approval_id="facilitator-approval-1",
        live_max_requests=2,
        live_max_calls=6,
        live_max_tokens=100_000,
        live_max_cost_usd=Decimal("100"),
        live_max_output_tokens=128,
        live_max_usd_per_1k_tokens=Decimal("1"),
    )
    assert approved.live_model_approved is True
    assert approved.live_max_requests == 2
    assert approved.live_max_calls == 6
    assert approved.live_max_tokens == 100_000
    assert approved.live_max_cost_usd == Decimal("100")


def test_live_approval_request_limit_persists_and_blocks_before_provider_call(
    tmp_path: Path,
) -> None:
    settings = AppSettings(
        mode="live",
        database_path=tmp_path / "live.sqlite3",
        model="fixture-default",
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
        live_model_approved=True,
        live_approval_id="facilitator-approval-1",
        live_max_requests=1,
        live_max_calls=2,
        live_max_tokens=100_000,
        live_max_cost_usd=Decimal("100"),
        live_max_output_tokens=128,
        live_max_usd_per_1k_tokens=Decimal("1"),
    )
    repository = SQLiteRepository(tmp_path / "live.sqlite3")
    provider = FixtureProvider()
    app = create_app(settings, repository=repository, provider=provider)
    with TestClient(app) as client:
        first = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "live-approved-request"},
            json={"complaint_text": "Synthetic account access complaint."},
        )
        blocked = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "live-over-budget-request"},
            json={"complaint_text": "Synthetic payment complaint."},
        )

    restarted = create_app(
        settings,
        repository=SQLiteRepository(tmp_path / "live.sqlite3"),
        provider=provider,
    )
    with TestClient(restarted) as client:
        after_restart = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "live-after-restart"},
            json={"complaint_text": "Synthetic card complaint."},
        )

    assert first.status_code == 201
    assert blocked.status_code == 429
    assert after_restart.status_code == 429
    assert len(provider.calls) == 2


def test_live_call_limit_stops_generation_before_provider_call(tmp_path: Path) -> None:
    settings = AppSettings(
        mode="live",
        database_path=tmp_path / "live-call-budget.sqlite3",
        model="fixture-default",
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
        live_model_approved=True,
        live_approval_id="call-budget-approval",
        live_max_requests=1,
        live_max_calls=1,
        live_max_tokens=100_000,
        live_max_cost_usd=Decimal("100"),
        live_max_output_tokens=128,
        live_max_usd_per_1k_tokens=Decimal("1"),
    )
    provider = FixtureProvider()
    with TestClient(
        create_app(
            settings,
            repository=SQLiteRepository(settings.database_path),
            provider=provider,
        )
    ) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "bounded-live-workflow"},
            json={"complaint_text": "Synthetic account access complaint."},
        )

    assert response.status_code == 201
    case = response.json()
    assert case["state"] == "manual_required"
    assert case["analyses"][0]["result"]["draft"] is None
    assert case["analyses"][0]["result"]["drafting_stage"]["failure_code"] == (
        "live_budget_exhausted"
    )
    assert len(provider.calls) == 1


def test_live_call_budget_persists_across_restart(tmp_path: Path) -> None:
    settings = AppSettings(
        mode="live",
        database_path=tmp_path / "live-call-budget-restart.sqlite3",
        model="fixture-default",
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
        live_model_approved=True,
        live_approval_id="persistent-call-budget",
        live_max_requests=2,
        live_max_calls=1,
        live_max_tokens=100_000,
        live_max_cost_usd=Decimal("100"),
        live_max_output_tokens=128,
        live_max_usd_per_1k_tokens=Decimal("1"),
    )
    repository = SQLiteRepository(settings.database_path)
    provider = FixtureProvider()
    with TestClient(
        create_app(settings, repository=repository, provider=provider)
    ) as client:
        first = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "first-live-run"},
            json={"complaint_text": "Synthetic account access complaint."},
        )
    assert first.status_code == 201
    assert len(provider.calls) == 1

    restarted = create_app(
        settings,
        repository=SQLiteRepository(settings.database_path),
        provider=provider,
    )
    with TestClient(restarted) as client:
        second = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "second-live-run"},
            json={"complaint_text": "Another synthetic account complaint."},
        )

    assert second.status_code == 201
    assert second.json()["state"] == "manual_required"
    assert "live_budget_exhausted" in str(second.json())
    assert len(provider.calls) == 1


def test_live_baseline_uses_the_same_call_and_cost_budget(tmp_path: Path) -> None:
    settings = AppSettings(
        mode="live",
        database_path=tmp_path / "live-baseline-budget.sqlite3",
        model="fixture-default",
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
        live_model_approved=True,
        live_approval_id="baseline-budget-approval",
        live_max_requests=1,
        live_max_calls=1,
        live_max_tokens=100_000,
        live_max_cost_usd=Decimal("100"),
        live_max_output_tokens=128,
        live_max_usd_per_1k_tokens=Decimal("1"),
    )
    provider = FixtureProvider()
    with TestClient(
        create_app(
            settings,
            repository=SQLiteRepository(settings.database_path),
            provider=provider,
        )
    ) as client:
        response = client.post(
            "/api/baseline",
            json={"complaint_text": "Synthetic account access complaint."},
        )

    assert response.status_code == 200
    assert len(provider.calls) == 1


def test_live_token_limit_blocks_provider_before_call(tmp_path: Path) -> None:
    settings = AppSettings(
        mode="live",
        database_path=tmp_path / "live-token-budget.sqlite3",
        model="fixture-default",
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
        live_model_approved=True,
        live_approval_id="token-budget-approval",
        live_max_requests=1,
        live_max_calls=2,
        live_max_tokens=1,
        live_max_cost_usd=Decimal("100"),
        live_max_output_tokens=128,
        live_max_usd_per_1k_tokens=Decimal("1"),
    )
    provider = FixtureProvider()
    with TestClient(
        create_app(
            settings,
            repository=SQLiteRepository(settings.database_path),
            provider=provider,
        )
    ) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "under-token-budget"},
            json={"complaint_text": "Synthetic account access complaint."},
        )

    assert response.status_code == 201
    assert response.json()["state"] == "manual_required"
    assert "live_budget_exhausted" in str(response.json())
    assert provider.calls == []


def test_openai_provider_applies_approved_output_token_limit() -> None:
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
        model="gpt-4o-mini",
        usage=None,
    )
    provider = OpenAIProvider("not-used", 5, client=client, max_output_tokens=37)

    provider.generate(None, "gpt-4o-mini", "system", "user")

    assert (
        client.chat.completions.create.call_args.kwargs["max_completion_tokens"] == 37
    )


def test_live_cost_limit_blocks_provider_before_call(tmp_path: Path) -> None:
    settings = AppSettings(
        mode="live",
        database_path=tmp_path / "live-cost-budget.sqlite3",
        model="fixture-default",
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
        live_model_approved=True,
        live_approval_id="cost-budget-approval",
        live_max_requests=1,
        live_max_calls=2,
        live_max_tokens=100_000,
        live_max_cost_usd=Decimal("0.000001"),
        live_max_output_tokens=128,
        live_max_usd_per_1k_tokens=Decimal("1"),
    )
    provider = FixtureProvider()
    with TestClient(
        create_app(
            settings,
            repository=SQLiteRepository(settings.database_path),
            provider=provider,
        )
    ) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "under-cost-budget"},
            json={"complaint_text": "Synthetic account access complaint."},
        )

    assert response.status_code == 201
    assert response.json()["state"] == "manual_required"
    assert "live_budget_exhausted" in str(response.json())
    assert provider.calls == []


def test_model_policy_exposes_explicit_stage_assignments(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/model-policy")

    assert response.status_code == 200
    assert response.json() == {
        "policy_version": "approved-stage-model-policy-v1",
        "mode": "fixture",
        "stage_models": {
            "classification": "fixture-classifier",
            "drafting": "fixture-drafter",
            "evaluation": "fixture-evaluator",
        },
        "routing_basis": "stage_only",
        "severity_based_routing": False,
    }


def test_operations_slo_reports_persisted_outcomes_and_sample_eligibility(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        complaint = "Synthetic complaint: the replacement debit card arrived late."
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "slo-case-1"},
            json={"complaint_text": complaint},
        )
        assert response.status_code == 201

        slo = client.get("/api/operations/slo")

    assert slo.status_code == 200
    assert slo.json() == {
        "status": "insufficient_sample",
        "target": "0.99",
        "window_size": 30,
        "eligible_samples": 1,
        "good": 1,
        "bad": 0,
        "unknown": 0,
        "good_rate": "1",
        "bad_rate": "0",
        "error_budget_remaining": "0.01",
    }


def test_operations_slo_counts_terminal_fixture_failure_as_bad(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "slo-failure-case"},
            json={
                "complaint_text": "Synthetic complaint for a controlled timeout.",
                "source_sample_id": "synthetic-provider-timeout",
            },
        )
        assert response.status_code == 201
        slo = client.get("/api/operations/slo").json()

    assert slo["good"] == 0
    assert slo["bad"] == 1
    assert slo["eligible_samples"] == 1
    assert slo["status"] == "insufficient_sample"


def test_operations_slo_keeps_fixture_and_live_mode_windows_separate(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "demo.sqlite3"
    repository = SQLiteRepository(database_path)
    with TestClient(
        create_app(
            AppSettings(mode="fixture", database_path=database_path),
            repository=repository,
            provider=FixtureProvider(),
        )
    ) as fixture_client:
        completed = fixture_client.post(
            "/api/cases",
            headers={"Idempotency-Key": "fixture-only-slo-event"},
            json={"complaint_text": "Synthetic account access complaint."},
        )
        assert completed.status_code == 201

    live_settings = AppSettings(
        mode="live",
        database_path=database_path,
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
        live_model_approved=True,
        live_approval_id="slo-window-test",
        live_max_requests=1,
        live_max_calls=1,
        live_max_tokens=100_000,
        live_max_cost_usd=Decimal("100"),
        live_max_output_tokens=128,
        live_max_usd_per_1k_tokens=Decimal("1"),
    )
    with TestClient(
        create_app(
            live_settings,
            repository=SQLiteRepository(database_path),
            provider=FixtureProvider(),
        )
    ) as live_client:
        slo = live_client.get("/api/operations/slo").json()

    assert slo["status"] == "insufficient_sample"
    assert slo["eligible_samples"] == 0


def test_alert_inbox_accepts_firing_and_resolved_for_one_fingerprint(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        headers = {"X-Internal-Token": "fixture-internal-token"}
        firing = {
            "fingerprint": "episode-1",
            "status": "firing",
            "title": "Synthetic provider failure",
            "labels": {"incident_priority": "P1"},
        }
        resolved = {**firing, "status": "resolved"}

        first = client.post("/internal/alerts", headers=headers, json=firing)
        duplicate = client.post("/internal/alerts", headers=headers, json=firing)
        recovery = client.post("/internal/alerts", headers=headers, json=resolved)
        events = client.get("/api/alerts").json()

    assert first.json() == {"accepted": True, "duplicate": False}
    assert duplicate.json() == {"accepted": True, "duplicate": True}
    assert recovery.status_code == 200
    assert recovery.json() == {"accepted": True, "duplicate": False}
    assert {event["status"] for event in events} == {"firing", "resolved"}


def test_grafana_webhook_payload_is_accepted_with_bounded_labels(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        payload = {
            "status": "firing",
            "commonLabels": {
                "alertname": "Synthetic provider failure",
                "incident_priority": "P1",
            },
            "alerts": [
                {"fingerprint": "grafana-fingerprint-1", "labels": {}},
            ],
        }
        response = client.post(
            "/internal/alerts",
            auth=("grafana-alerting", "fixture-internal-token"),
            json=payload,
        )
        events = client.get("/api/alerts").json()

    assert response.status_code == 200
    event = events[0]
    assert event["priority"] == "P1"
    assert event["name"] == "Synthetic provider failure"
    assert event["payload"] == {
        "name": "Synthetic provider failure",
        "priority": "P1",
        "status": "firing",
    }


def test_grafana_repeat_episode_after_resolution_is_not_deduplicated(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        payload = {
            "status": "firing",
            "commonLabels": {"alertname": "Synthetic provider failure"},
            "alerts": [
                {
                    "fingerprint": "stable-rule-fingerprint",
                    "startsAt": "2026-11-11T10:00:00Z",
                    "labels": {},
                },
            ],
        }
        firing = client.post(
            "/internal/alerts",
            auth=("grafana-alerting", "fixture-internal-token"),
            json=payload,
        )
        duplicate = client.post(
            "/internal/alerts",
            auth=("grafana-alerting", "fixture-internal-token"),
            json=payload,
        )
        resolved = client.post(
            "/internal/alerts",
            auth=("grafana-alerting", "fixture-internal-token"),
            json={**payload, "status": "resolved"},
        )
        next_episode = client.post(
            "/internal/alerts",
            auth=("grafana-alerting", "fixture-internal-token"),
            json={
                **payload,
                "alerts": [
                    {
                        "fingerprint": "stable-rule-fingerprint",
                        "startsAt": "2026-11-11T11:00:00Z",
                        "labels": {},
                    },
                ],
            },
        )
        events = client.get("/api/alerts").json()

    assert firing.json()["duplicate"] is False
    assert duplicate.json()["duplicate"] is True
    assert resolved.json()["duplicate"] is False
    assert next_episode.json()["duplicate"] is False
    assert len(events) == 3


def test_fixture_quality_replay_uses_provider_outputs_not_answer_key_as_predictions(
    tmp_path: Path,
) -> None:
    del tmp_path
    from complaint_copilot.demo_replay import replay_quality

    report = replay_quality(Path(__file__).resolve().parents[2] / "data")
    q0 = report["q0"]
    assert isinstance(q0, dict)
    assert q0["metric_name"] == "Q0-scripted-fixture-provider"
    assert q0["severity_accuracy"] < 1
