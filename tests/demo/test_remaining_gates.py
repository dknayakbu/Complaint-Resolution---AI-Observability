from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from complaint_copilot.api import create_app
from complaint_copilot.provider import (
    FixtureProvider,
    OpenAIProvider,
    ProviderFailure,
    ProviderResponse,
    RetryingProvider,
)
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


def test_live_calls_have_no_local_spending_caps_across_restart(tmp_path: Path) -> None:
    settings = AppSettings(
        mode="live",
        database_path=tmp_path / "live.sqlite3",
        openai_api_key="not-used",
        reviewer_token="reviewer",
        internal_token="internal",
        short_input_max=100,
        medium_input_max=500,
    )
    provider = FixtureProvider()
    for batch in range(2):
        with TestClient(create_app(settings, provider=provider)) as client:
            assert "live_max_requests" not in client.get("/api/mode").json()
            assert (
                client.post(
                    "/api/baseline", json={"complaint_text": "Synthetic complaint."}
                ).status_code
                == 200
            )
            for index in range(6):
                response = client.post(
                    "/api/cases",
                    headers={"Idempotency-Key": f"case-{batch}-{index}"},
                    json={"complaint_text": "Synthetic account complaint."},
                )
                assert response.status_code == 201
                assert response.json()["state"] == "awaiting_review"
    assert len(provider.calls) == 26


def test_legacy_budget_tables_are_not_required_or_modified(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    SQLiteRepository(path)
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "live_run_budgets" not in tables
        connection.execute("CREATE TABLE live_run_budgets (marker TEXT)")
        connection.execute("INSERT INTO live_run_budgets VALUES ('legacy')")
        connection.executemany(
            "INSERT INTO schema_migrations VALUES (?, 'previously-applied')",
            [(3,), (4,)],
        )
    SQLiteRepository(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT marker FROM live_run_budgets").fetchone() == (
            "legacy",
        )


def test_openai_request_does_not_set_an_output_token_cap() -> None:
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
        model="gpt-4o-mini",
        usage=None,
    )
    OpenAIProvider("not-used", 5, client=client).generate(
        None, "gpt-4o-mini", "system", "user"
    )
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "max_completion_tokens" not in kwargs


def test_baseline_invalid_provider_output_is_reported(tmp_path: Path) -> None:
    provider = FixtureProvider(
        {
            None: [
                ProviderResponse(
                    '{"category":"Card Services","severity":3,"draft":"x"}', "model"
                )
            ]
        }
    )
    with TestClient(
        create_app(
            AppSettings(database_path=tmp_path / "demo.sqlite3"), provider=provider
        )
    ) as client:
        response = client.post(
            "/api/baseline", json={"complaint_text": "Synthetic complaint."}
        )
    assert response.status_code == 502


def test_empty_stage_model_environment_values_use_the_shared_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "")
    monkeypatch.setenv("DRAFTING_MODEL", " ")
    monkeypatch.setenv("EVALUATION_MODEL", "")

    settings = AppSettings.from_env()

    assert settings.classification_model is None
    assert settings.drafting_model is None
    assert settings.evaluation_model is None


def test_retrying_provider_reports_attempts_without_multiplying_model_responses() -> (
    None
):
    provider = Mock()
    provider.generate.side_effect = [
        ProviderFailure("provider_timeout", retryable=True),
        ProviderResponse(
            '{"result":"ok"}',
            "recording-model",
            input_tokens=10,
            output_tokens=5,
        ),
    ]
    retrying = RetryingProvider(provider, max_attempts=2, sleeper=lambda _: None)

    response = retrying.generate(None, "recording-model", "system", "user")

    assert response.attempts == 2
    assert provider.generate.call_count == 2


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


@pytest.mark.parametrize(
    "fixture_id", ["test-provider-timeout", "synthetic-provider-timeout"]
)
def test_operations_slo_counts_terminal_fixture_failure_as_bad(
    tmp_path: Path, fixture_id: str
) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "slo-failure-case"},
            json={
                "complaint_text": "Synthetic complaint for a controlled timeout.",
                "source_sample_id": fixture_id,
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
