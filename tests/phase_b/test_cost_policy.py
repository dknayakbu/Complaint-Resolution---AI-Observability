from decimal import Decimal

import pytest

from complaint_copilot.contracts import TokenUsage
from complaint_copilot.cost import (
    CostError,
    aggregate_by_stage_and_model,
    aggregate_stage_costs,
    calculate_usage_cost,
    detect_anomaly,
    stage_cost_observation,
)


def test_calculate_usage_cost_adds_input_output_and_cached_tokens() -> None:
    usage = TokenUsage(
        input_tokens=1500,
        output_tokens=800,
        provider_cached_input_tokens=300,
        known=True,
        unknown_reason=None,
    )

    total = calculate_usage_cost(
        usage,
        input_price_per_1k=Decimal("0.01"),
        output_price_per_1k=Decimal("0.02"),
        cached_input_price_per_1k=Decimal("0.005"),
    )

    assert total == Decimal("0.0325")


def test_calculate_usage_cost_rejects_unknown_usage() -> None:
    usage = TokenUsage(
        input_tokens=None,
        output_tokens=None,
        provider_cached_input_tokens=None,
        known=False,
        unknown_reason="provider_usage_unavailable",
    )

    with pytest.raises(CostError, match="usage is unknown"):
        calculate_usage_cost(
            usage,
            input_price_per_1k=Decimal("0.01"),
            output_price_per_1k=Decimal("0.02"),
        )


def test_stage_cost_observation_requires_amount_for_complete_observation() -> None:
    with pytest.raises(CostError, match="complete cost observations require an amount"):
        stage_cost_observation(
            amount_usd=None,
            pricing_version="fixture-prices-v1",
            complete=True,
        )

    observation = stage_cost_observation(
        amount_usd=None,
        pricing_version="fixture-prices-v1",
        complete=False,
        unknown_reason="provider_usage_unavailable",
    )

    assert observation.amount_usd is None
    assert observation.complete is False
    assert observation.pricing_version is None
    assert observation.unknown_reason == "provider_usage_unavailable"


def test_aggregate_stage_costs_sums_decimal_amounts() -> None:
    records = [
        {"amount_usd": "1.25"},
        {"amount_usd": "2.00"},
        {"amount_usd": "0.50"},
    ]

    assert aggregate_stage_costs(records) == Decimal("3.75")


def test_aggregate_by_stage_and_model_groups_costs() -> None:
    records = [
        {"stage": "classification", "model": "gpt-4o-mini", "amount_usd": "0.10"},
        {"stage": "classification", "model": "gpt-4o-mini", "amount_usd": "0.20"},
        {"stage": "drafting", "model": "gpt-4o-mini", "amount_usd": "0.35"},
        {"stage": "drafting", "model": "gpt-4o", "amount_usd": "0.75"},
    ]

    result = aggregate_by_stage_and_model(records)

    assert result == {
        ("classification", "gpt-4o-mini"): Decimal("0.30"),
        ("drafting", "gpt-4o-mini"): Decimal("0.35"),
        ("drafting", "gpt-4o"): Decimal("0.75"),
    }


def test_detect_anomaly_flags_cost_spikes_over_baseline() -> None:
    baseline = [Decimal("1.00"), Decimal("2.00"), Decimal("3.00")]
    recent = [Decimal("18.00"), Decimal("20.00")]

    assert detect_anomaly(recent, baseline=baseline, multiplier=Decimal("3")) is True


def test_detect_anomaly_ignores_empty_or_zero_baselines() -> None:
    assert (
        detect_anomaly([Decimal("10")], baseline=[], multiplier=Decimal("3")) is False
    )
    assert (
        detect_anomaly(
            [Decimal("10")],
            baseline=[Decimal("0"), Decimal("0")],
            multiplier=Decimal("3"),
        )
        is False
    )
