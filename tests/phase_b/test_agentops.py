from datetime import UTC, datetime
from decimal import Decimal

from complaint_copilot.capacity import TwoWorkflowCapacity
from complaint_copilot.contracts import (
    CostObservation,
    IncidentPriority,
    InputSizeBucket,
    RunMode,
    Stage,
    StageUsageEvent,
    TokenUsage,
)
from complaint_copilot.cost import (
    aggregate_stage_costs,
    calculate_usage_cost,
    detect_cost_anomaly,
)
from complaint_copilot.fixture_signals import generate_fixture_signals
from complaint_copilot.incident_response import (
    adapt_grafana_alert,
    dedupe_incident_episode,
)
from complaint_copilot.model_policy import StageModelPolicy
from complaint_copilot.slo import compute_sli, error_budget_remaining


def test_cost_prices_known_usage_and_aggregates_without_double_counting() -> None:
    usage = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        provider_cached_input_tokens=100,
        known=True,
        unknown_reason=None,
    )
    cost = calculate_usage_cost(usage, model="gpt-4.1-mini")
    assert cost.amount_usd == Decimal("0.0004575")
    assert cost.complete is True

    events = (
        StageUsageEvent(
            schema_version=1,
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
            event_id="evt-1",
            case_id="case-1",
            analysis_id="analysis-1",
            analysis_revision=1,
            stage=Stage.CLASSIFICATION,
            attempt=1,
            run_mode=RunMode.FIXTURE,
            input_size_bucket=InputSizeBucket.SHORT,
            requested_model="gpt-4.1-mini",
            served_model="gpt-4.1-mini",
            prompt_version="p-v1",
            stage_schema_version="s-v1",
            policy_version="policy-v1",
            model_policy_version="model-v1",
            succeeded=True,
            error_category=None,
            duration_ms=123,
            usage=usage,
            cost=cost,
        ),
        StageUsageEvent(
            schema_version=1,
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
            event_id="evt-2",
            case_id="case-1",
            analysis_id="analysis-1",
            analysis_revision=1,
            stage=Stage.CLASSIFICATION,
            attempt=1,
            run_mode=RunMode.FIXTURE,
            input_size_bucket=InputSizeBucket.SHORT,
            requested_model="gpt-4.1-mini",
            served_model="gpt-4.1-mini",
            prompt_version="p-v1",
            stage_schema_version="s-v1",
            policy_version="policy-v1",
            model_policy_version="model-v1",
            succeeded=True,
            error_category=None,
            duration_ms=124,
            usage=usage,
            cost=cost,
        ),
    )
    total, grouped = aggregate_stage_costs(events)
    assert total == cost.amount_usd * 2
    assert (
        grouped[(Stage.CLASSIFICATION, "gpt-4.1-mini", RunMode.FIXTURE)]
        == cost.amount_usd * 2
    )

    duplicate = [*events, events[0]]
    total_dup, grouped_dup = aggregate_stage_costs(duplicate)
    assert total_dup == total
    assert grouped_dup == grouped


def test_model_policy_is_explicit_and_not_severity_routed() -> None:
    policy = StageModelPolicy()
    decision = policy.resolve(Stage.DRAFTING, {})
    assert decision.model == "gpt-4.1-mini"
    assert decision.policy_version == "approved-stage-model-policy-v1"
    assert "severity" in decision.reason.lower()
    assert "not used" in decision.reason.lower()


def test_capacity_reserve_release_and_overload_are_explicit() -> None:
    capacity = TwoWorkflowCapacity(2)
    first = capacity.reserve("classification", requested=1)
    second = capacity.reserve("drafting", requested=1)
    overloaded = capacity.reserve("review", requested=1)

    assert first.granted == 1 and first.overloaded is False
    assert second.granted == 1 and second.overloaded is False
    assert overloaded.granted == 0 and overloaded.overloaded is True
    assert capacity.release("classification") == 1
    assert capacity.available == 1


def test_sli_and_error_budget_handling_cover_unknown_and_no_sample_cases() -> None:
    sli = compute_sli(good=90, bad=2, unknown=8, eligible_samples=100)
    assert sli.good_rate == Decimal("0.90")
    assert sli.bad_rate == Decimal("0.02")
    assert (
        compute_sli(good=1, bad=0, unknown=0, eligible_samples=0).eligible_samples == 0
    )
    assert error_budget_remaining(
        target_slo=0.99, total_samples=100, bad_samples=2
    ) == Decimal("-1")
    assert error_budget_remaining(
        target_slo=1.0, total_samples=100, bad_samples=2
    ) == Decimal("98")


def test_grafana_alerts_adapt_to_incident_episodes_and_are_idempotent() -> None:
    payload = {
        "id": "grafana-123",
        "title": "Payment outage",
        "status": "firing",
        "labels": {"incident_priority": "P1", "team": "cards_payments"},
        "annotations": {"summary": "Cards payment path degraded"},
    }
    episode = adapt_grafana_alert(payload, case_id="case-42")
    assert episode.incident_id == "grafana-123"
    assert episode.priority is IncidentPriority.P1
    assert "case-42" in episode.case_ids
    assert episode.runbook_url.startswith("https://example.invalid/runbooks/")

    deduped = dedupe_incident_episode([episode, episode])
    assert len(deduped) == 1


def test_fixture_signals_and_metric_redaction_use_explicit_fixture_tags() -> None:
    signals = generate_fixture_signals()
    assert len(signals) == 3
    assert all("fixture" in signal.tags for signal in signals)
    first_signal = signals[0]
    assert first_signal.signal_type == "stage_usage"
    assert first_signal.payload["known"] is True

    from complaint_copilot.telemetry import make_metric

    metric = make_metric(
        "complaint.classification.latency",
        1.5,
        labels={"case_id": "abc", "complaint_text": "secret", "team": "ops"},
    )
    assert metric.labels["case_id"] == "<redacted>"
    assert metric.labels["complaint_text"] == "<redacted>"
    assert metric.labels["team"] == "ops"


def test_cost_anomaly_detection_flags_when_recent_cost_is_3x_baseline() -> None:
    anomaly = detect_cost_anomaly(
        baseline_costs=[Decimal("0.010"), Decimal("0.020"), Decimal("0.015")],
        current_costs=[Decimal("0.060"), Decimal("0.070")],
    )
    assert anomaly.flagged is True
    assert anomaly.baseline_mean_usd == Decimal("0.015")
    assert anomaly.current_mean_usd == Decimal("0.065")


def test_unknown_cost_is_not_treated_as_zero() -> None:
    cost = CostObservation(
        amount_usd=None,
        complete=False,
        pricing_version=None,
        unknown_reason="usage_unknown",
    )
    assert cost.amount_usd is None
    assert cost.complete is False
