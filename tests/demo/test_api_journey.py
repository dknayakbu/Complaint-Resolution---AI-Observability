from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from complaint_copilot.api import create_app
from complaint_copilot.contracts import Stage
from complaint_copilot.provider import (
    FixtureProvider,
    ProviderFailure,
    ProviderResponse,
)
from complaint_copilot.repository import SQLiteRepository
from complaint_copilot.settings import AppSettings


def _provider(
    complaint: str,
    *,
    category: str = "cards_payments",
    severity: int = 3,
    drafting: ProviderResponse | ProviderFailure | None = None,
) -> FixtureProvider:
    classification = ProviderResponse(
        json.dumps(
            {
                "category": category,
                "model_severity": severity,
                "evidence": [{"start": 0, "end": len(complaint), "quote": complaint}],
                "decision_summary": "Controlled synthetic test result.",
            }
        ),
        "fixture-model",
        10,
        4,
    )
    responses: dict[Stage, list[ProviderResponse | ProviderFailure]] = {
        Stage.CLASSIFICATION: [classification],
    }
    if drafting is not None:
        responses[Stage.DRAFTING] = [drafting]
    else:
        responses[Stage.DRAFTING] = [
            ProviderResponse(
                json.dumps({"draft": "Thank you for explaining the card issue."}),
                "fixture-model",
                12,
                5,
            )
        ]
    return FixtureProvider(responses)


def _client(tmp_path: Path, provider: FixtureProvider) -> TestClient:
    settings = AppSettings(
        mode="fixture",
        database_path=tmp_path / "demo.sqlite3",
        model="fixture-model",
    )
    app = create_app(
        settings,
        repository=SQLiteRepository(tmp_path / "demo.sqlite3"),
        provider=provider,
    )
    return TestClient(app)


def test_fixture_two_stage_review_journey_and_duplicate_approval(
    tmp_path: Path,
) -> None:
    complaint = "Synthetic complaint: duplicate debit left rent money short."
    provider = _provider(complaint)
    with _client(tmp_path, provider) as client:
        assert client.get("/api/mode").json()["mode"] == "fixture"
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "scene-1"},
            json={"complaint_text": complaint, "synthetic": True},
        )
        assert response.status_code == 201
        case = response.json()
        assert case["state"] == "awaiting_review"
        result = case["analyses"][0]["result"]
        assert result["draft"].endswith(
            "not a substantive response or confirmation that your concern "
            "has been resolved."
        )
        assert [call[0] for call in provider.calls] == [
            Stage.CLASSIFICATION,
            Stage.DRAFTING,
        ]
        assert len(case["audit"]) >= 4
        assert client.get("/api/queue").json() == []

        review_body = {
            "expected_case_version": case["version"],
            "analysis_revision": case["current_revision"],
            "reason": "Synthetic reviewer approval.",
            "category": "cards_payments",
            "queue": "cards_payments",
        }
        denied = client.post(f"/api/cases/{case['case_id']}/review", json=review_body)
        assert denied.status_code == 403
        approved = client.post(
            f"/api/cases/{case['case_id']}/review",
            headers={"Authorization": "Bearer fixture-reviewer-token"},
            json=review_body,
        )
        assert approved.status_code == 200
        assert len(client.get("/api/queue").json()) == 1
        duplicate = client.post(
            f"/api/cases/{case['case_id']}/review",
            headers={"Authorization": "Bearer fixture-reviewer-token"},
            json=review_body,
        )
        assert duplicate.status_code == 409
        assert len(client.get("/api/queue").json()) == 1


def test_fixture_draft_reflects_the_replacement_card_issue(tmp_path: Path) -> None:
    complaint = (
        "My replacement debit card arrived late, but my existing card still works."
    )
    with _client(tmp_path, FixtureProvider()) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "personalized-fixture-draft"},
            json={"complaint_text": complaint},
        )

    draft = response.json()["analyses"][0]["result"]["draft"].casefold()
    assert "replacement debit card" in draft
    assert "current card works" in draft


def test_safeguard_promotes_severity_but_preserves_model_prediction(
    tmp_path: Path,
) -> None:
    complaint = (
        "Your system debited the same card purchase twice for GBP 85. "
        "The duplicate debit has left me short of the money needed for my rent."
    )
    provider = _provider(complaint, category="other", severity=3)
    with _client(tmp_path, provider) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "scene-2"},
            json={"complaint_text": complaint},
        )
    result = response.json()["analyses"][0]["result"]
    assert result["classification"]["model_severity"] == 3
    assert result["effective_severity"] == 1


def test_controlled_raw_miss_fixture_records_model_and_effective_severity(
    tmp_path: Path,
) -> None:
    complaint = (
        "Your system debited the same card purchase twice for GBP 85. "
        "The duplicate debit has left me short of the money needed for my rent."
    )
    with _client(tmp_path, FixtureProvider()) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "scene-2-controlled-miss"},
            json={
                "complaint_text": complaint,
                "source_sample_id": "scene-2-controlled-raw-miss",
            },
        )

    case = response.json()
    analysis = case["analyses"][0]
    result = analysis["result"]
    assert result["classification"]["category"] == "other"
    assert result["classification"]["model_severity"] == 3
    assert result["effective_severity"] == 1
    assert analysis["policy_flags"]


def test_invalid_input_and_invalid_classification_have_no_drafting_call(
    tmp_path: Path,
) -> None:
    complaint = "Synthetic complaint with unsupported output."
    provider = FixtureProvider(
        {
            Stage.CLASSIFICATION: [
                ProviderResponse('{"category":"unknown"}', "fixture-model")
            ]
        }
    )
    with _client(tmp_path, provider) as client:
        invalid = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "empty"},
            json={"complaint_text": "   "},
        )
        assert invalid.status_code == 422
        assert provider.calls == []

        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "bad-classifier"},
            json={"complaint_text": complaint},
        )
    case = response.json()
    assert case["state"] == "manual_required"
    assert len(provider.calls) == 1
    result = case["analyses"][0]["result"]
    assert result["classification_stage"]["status"] == "failed"
    assert result["drafting_stage"]["status"] == "skipped"


def test_drafting_failure_retains_classification_and_urgency(
    tmp_path: Path,
) -> None:
    complaint = "Synthetic duplicate debit left money missing."
    provider = _provider(
        complaint,
        drafting=ProviderFailure("provider_timeout", retryable=False),
    )
    with _client(tmp_path, provider) as client:
        response = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "draft-timeout"},
            json={"complaint_text": complaint},
        )
    case = response.json()
    result = case["analyses"][0]["result"]
    assert case["state"] == "manual_required"
    assert result["classification"] is not None
    assert result["effective_severity"] == 1
    assert result["draft"] is None
    assert result["drafting_stage"]["status"] == "failed"
    assert result["cost"]["complete"] is False
    assert len(provider.calls) == 2


def test_revision_linked_feedback_merges_with_safety_signal_and_adjudicates(
    tmp_path: Path,
) -> None:
    complaint = (
        "Your system debited the same card purchase twice for GBP 85. "
        "The duplicate debit has left me short of the money needed for my rent."
    )
    provider = _provider(complaint, category="other", severity=3)
    with _client(tmp_path, provider) as client:
        case = client.post(
            "/api/cases",
            headers={"Idempotency-Key": "scene-annotation"},
            json={"complaint_text": complaint},
        ).json()
        annotations = client.get("/api/cases").json()
        assert annotations
        feedback = client.post(
            f"/api/cases/{case['case_id']}/feedback",
            headers={"Authorization": "Bearer fixture-reviewer-token"},
            json={
                "analysis_revision": case["current_revision"],
                "rating": "down",
                "note": "Urgent payment complaint needs specialist correction.",
            },
        )
        assert feedback.status_code == 200
        candidates = client.get("/api/annotations")
        assert candidates.status_code == 200
        candidate = candidates.json()[0]
        assert len(candidate["candidate"]["signals"]) == 2
        adjudicated = client.post(
            f"/api/annotations/{candidate['annotation_id']}/adjudicate",
            headers={"Authorization": "Bearer fixture-reviewer-token"},
            json={
                "expected_case_version": case["version"],
                "analysis_revision": case["current_revision"],
                "case_id": case["case_id"],
                "category": "cards_payments",
                "severity": 1,
                "queue": "cards_payments",
                "draft_rubric_assessment": "Acknowledgement stays non-committal.",
                "reason": "Synthetic adjudication for rehearsal.",
            },
        )
        assert adjudicated.status_code == 200
        assert adjudicated.json()["label"]["category"] == "cards_payments"
        assert len(client.get("/api/queue").json()) == 0


def test_internal_alerts_are_authenticated_and_idempotent(tmp_path: Path) -> None:
    with _client(tmp_path, FixtureProvider()) as client:
        payload = {
            "fingerprint": "synthetic-alert-1",
            "status": "firing",
            "title": "Synthetic safety rule",
            "labels": {"incident_priority": "P1"},
        }
        denied = client.post("/internal/alerts", json=payload)
        assert denied.status_code == 401
        headers = {"X-Internal-Token": "fixture-internal-token"}
        first = client.post("/internal/alerts", headers=headers, json=payload)
        second = client.post("/internal/alerts", headers=headers, json=payload)
        assert first.json() == {"accepted": True, "duplicate": False}
        assert second.json() == {"accepted": True, "duplicate": True}
        assert len(client.get("/api/alerts").json()) == 1


def test_replay_route_persists_idempotency_and_returns_real_cost_computation(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, FixtureProvider()) as client:
        headers = {
            "X-Internal-Token": "fixture-internal-token",
            "Idempotency-Key": "cost-replay-1",
        }
        first = client.post("/internal/demo/replay/cost", headers=headers)
        second = client.post("/internal/demo/replay/cost", headers=headers)
        assert first.status_code == 200
        assert first.json()["threshold_crossing_spike_observation"] == 6
        assert first.json()["cumulative_cost_usd"] == "0.280"
        assert first.json()["duplicate"] is False
        assert second.json()["duplicate"] is True
