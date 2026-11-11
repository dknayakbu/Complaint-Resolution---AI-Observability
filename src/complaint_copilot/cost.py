"""Cost helpers shared by Phase B's event accounting and Phase C's evaluators."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import overload

from complaint_copilot.contracts import (
    CostObservation,
    RunMode,
    Stage,
    StageUsageEvent,
    TokenUsage,
)

DEFAULT_PRICING_VERSION = "fixture-prices-v1"


class CostError(ValueError):
    """Raised when cost inputs violate the shared cost contract."""


@dataclass(frozen=True)
class PricingRule:
    """Token prices in USD per 1,000 tokens."""

    input_usd_per_1k_tokens: Decimal
    output_usd_per_1k_tokens: Decimal
    cached_input_usd_per_1k_tokens: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if any(
            not value.is_finite() or value < 0
            for value in (
                self.input_usd_per_1k_tokens,
                self.output_usd_per_1k_tokens,
                self.cached_input_usd_per_1k_tokens,
            )
        ):
            raise CostError("token prices must be finite and non-negative")

    def total_for_usage(self, usage: TokenUsage) -> Decimal:
        if not usage.known:
            raise CostError("usage is unknown; cost cannot be calculated as zero")
        if usage.input_tokens is None or usage.output_tokens is None:
            raise CostError("known usage requires input and output token counts")
        input_cost = (
            Decimal(usage.input_tokens) * self.input_usd_per_1k_tokens / Decimal(1000)
        )
        output_cost = (
            Decimal(usage.output_tokens) * self.output_usd_per_1k_tokens / Decimal(1000)
        )
        cached_cost = (
            Decimal(usage.provider_cached_input_tokens or 0)
            * self.cached_input_usd_per_1k_tokens
            / Decimal(1000)
        )
        return input_cost + output_cost + cached_cost


DEFAULT_PRICING: dict[str, PricingRule] = {
    "gpt-4.1-mini": PricingRule(
        input_usd_per_1k_tokens=Decimal("0.00015"),
        output_usd_per_1k_tokens=Decimal("0.00060"),
        cached_input_usd_per_1k_tokens=Decimal("0.000075"),
    ),
    "gpt-4.1": PricingRule(
        input_usd_per_1k_tokens=Decimal("0.0005"),
        output_usd_per_1k_tokens=Decimal("0.0015"),
        cached_input_usd_per_1k_tokens=Decimal("0.00025"),
    ),
    "gpt-4o-mini": PricingRule(
        input_usd_per_1k_tokens=Decimal("0.00015"),
        output_usd_per_1k_tokens=Decimal("0.00060"),
        cached_input_usd_per_1k_tokens=Decimal("0.000075"),
    ),
}

PriceTable = dict[str, PricingRule]
EventInput = StageUsageEvent | Mapping[str, object]


def _coerce_usage(raw_usage: TokenUsage | Mapping[str, object]) -> TokenUsage:
    if isinstance(raw_usage, TokenUsage):
        return raw_usage
    return TokenUsage.from_mapping(raw_usage)


def resolve_pricing(
    model: str,
    *,
    pricing: Mapping[str, PricingRule] | None = None,
) -> PricingRule:
    table = DEFAULT_PRICING if pricing is None else pricing
    try:
        return table[model]
    except KeyError as error:
        raise CostError(f"no pricing configured for model {model!r}") from error


@overload
def calculate_usage_cost(
    usage: TokenUsage | Mapping[str, object],
    *,
    model: str,
    pricing: Mapping[str, PricingRule] | None = None,
    pricing_version: str = DEFAULT_PRICING_VERSION,
) -> CostObservation: ...


@overload
def calculate_usage_cost(
    usage: TokenUsage | Mapping[str, object],
    *,
    input_price_per_1k: Decimal,
    output_price_per_1k: Decimal,
    cached_input_price_per_1k: Decimal = Decimal("0"),
) -> Decimal: ...


def calculate_usage_cost(
    usage: TokenUsage | Mapping[str, object],
    *,
    model: str | None = None,
    pricing: Mapping[str, PricingRule] | None = None,
    pricing_version: str = DEFAULT_PRICING_VERSION,
    input_price_per_1k: Decimal | None = None,
    output_price_per_1k: Decimal | None = None,
    cached_input_price_per_1k: Decimal = Decimal("0"),
) -> CostObservation | Decimal:
    token_usage = _coerce_usage(usage)
    if model is not None:
        if input_price_per_1k is not None or output_price_per_1k is not None:
            raise CostError(
                "select either a model price table or explicit token prices"
            )
        if not token_usage.known:
            return CostObservation(
                amount_usd=None,
                complete=False,
                pricing_version=None,
                unknown_reason=token_usage.unknown_reason or "usage_unknown",
            )
        rule = resolve_pricing(model, pricing=pricing)
        return CostObservation(
            amount_usd=rule.total_for_usage(token_usage),
            complete=True,
            pricing_version=pricing_version,
            unknown_reason=None,
        )

    if input_price_per_1k is None or output_price_per_1k is None:
        raise CostError("model or both explicit token prices are required")
    if not token_usage.known:
        raise CostError("usage is unknown; cost cannot be calculated as zero")
    if token_usage.input_tokens is None or token_usage.output_tokens is None:
        raise CostError("known usage requires input and output token counts")
    rule = PricingRule(
        input_usd_per_1k_tokens=input_price_per_1k,
        output_usd_per_1k_tokens=output_price_per_1k,
        cached_input_usd_per_1k_tokens=cached_input_price_per_1k,
    )
    return rule.total_for_usage(token_usage)


def stage_cost_observation(
    *,
    amount_usd: Decimal | None,
    pricing_version: str,
    complete: bool = True,
    unknown_reason: str | None = None,
) -> CostObservation:
    if complete and amount_usd is None:
        raise CostError("complete cost observations require an amount")
    if not complete and not unknown_reason:
        raise CostError("incomplete cost observations require an unknown reason")
    return CostObservation(
        amount_usd=amount_usd,
        complete=complete,
        pricing_version=pricing_version if complete else None,
        unknown_reason=None if complete else unknown_reason,
    )


def _coerce_event(raw_event: EventInput) -> StageUsageEvent:
    if isinstance(raw_event, StageUsageEvent):
        return raw_event
    return StageUsageEvent.from_mapping(raw_event)


@overload
def aggregate_stage_costs(
    events: Sequence[Mapping[str, object]],
) -> Decimal: ...


@overload
def aggregate_stage_costs(
    events: Iterable[StageUsageEvent],
) -> tuple[Decimal, dict[tuple[Stage, str, RunMode], Decimal]]: ...


def aggregate_stage_costs(
    events: Iterable[StageUsageEvent | Mapping[str, object]],
) -> tuple[Decimal, dict[tuple[Stage, str, RunMode], Decimal]] | Decimal:
    if isinstance(events, Sequence) and events and _is_legacy_cost_record(events[0]):
        return _aggregate_legacy_stage_costs(events)
    return _aggregate_usage_event_costs(events)


def _is_legacy_cost_record(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and "amount_usd" in value
        and "event_id" not in value
        and "cost" not in value
    )


def _aggregate_legacy_stage_costs(
    records: Sequence[Mapping[str, object]],
) -> Decimal:
    total = Decimal("0")
    for record in records:
        amount = record.get("amount_usd")
        if amount is None:
            raise CostError(
                "stage cost aggregation cannot include unknown cost amounts"
            )
        total += Decimal(str(amount))
    return total


def aggregate_by_stage_and_model(
    records: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], Decimal]:
    grouped: defaultdict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for record in records:
        stage = str(record.get("stage", "unknown"))
        model = str(record.get("model", "unknown"))
        amount = record.get("amount_usd")
        if amount is None:
            raise CostError("amount_usd is required for grouped cost aggregation")
        grouped[(stage, model)] += Decimal(str(amount))
    return dict(grouped)


def aggregate_costs(
    events: Iterable[StageUsageEvent | Mapping[str, object]],
) -> dict[tuple[Stage, str, RunMode], Decimal]:
    _, totals = _aggregate_usage_event_costs(events)
    return totals


def _aggregate_usage_event_costs(
    events: Iterable[StageUsageEvent | Mapping[str, object]],
) -> tuple[Decimal, dict[tuple[Stage, str, RunMode], Decimal]]:
    seen_event_ids: set[str] = set()
    totals: dict[tuple[Stage, str, RunMode], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    total_cost = Decimal("0")
    for raw_event in events:
        event = _coerce_event(raw_event)
        if event.event_id in seen_event_ids:
            continue
        seen_event_ids.add(event.event_id)
        if event.cost.amount_usd is not None:
            key = (event.stage, event.requested_model, event.run_mode)
            totals[key] += event.cost.amount_usd
            total_cost += event.cost.amount_usd
    return total_cost, dict(totals)


def detect_anomaly(
    recent_costs: Sequence[Decimal],
    *,
    baseline: Sequence[Decimal],
    multiplier: Decimal = Decimal("3"),
) -> bool:
    return detect_cost_anomaly(
        baseline_costs=baseline,
        current_costs=recent_costs,
        threshold_multiplier=multiplier,
    ).flagged


@dataclass(frozen=True)
class CostAnomaly:
    baseline_mean_usd: Decimal
    current_mean_usd: Decimal
    threshold_multiplier: Decimal
    flagged: bool


def detect_cost_anomaly(
    *,
    baseline_costs: Sequence[Decimal] | Sequence[EventInput],
    current_costs: Sequence[Decimal] | Sequence[EventInput],
    threshold_multiplier: Decimal = Decimal("3"),
) -> CostAnomaly:
    if not threshold_multiplier.is_finite() or threshold_multiplier <= 0:
        raise CostError("anomaly threshold multiplier must be finite and positive")

    def _mean(values: Sequence[Decimal | EventInput]) -> Decimal:
        converted: list[Decimal] = []
        for value in values:
            if isinstance(value, Decimal):
                converted.append(value)
            else:
                event = _coerce_event(value)
                if event.cost.amount_usd is not None:
                    converted.append(event.cost.amount_usd)
        return (
            sum(converted, Decimal("0")) / Decimal(len(converted))
            if converted
            else Decimal("0")
        )

    baseline_mean = _mean(baseline_costs)
    current_mean = _mean(current_costs)
    flagged = bool(
        baseline_mean > 0 and current_mean >= threshold_multiplier * baseline_mean
    )
    return CostAnomaly(
        baseline_mean_usd=baseline_mean,
        current_mean_usd=current_mean,
        threshold_multiplier=threshold_multiplier,
        flagged=flagged,
    )


__all__ = [
    "CostAnomaly",
    "CostError",
    "DEFAULT_PRICING",
    "DEFAULT_PRICING_VERSION",
    "PriceTable",
    "PricingRule",
    "aggregate_by_stage_and_model",
    "aggregate_costs",
    "aggregate_stage_costs",
    "calculate_usage_cost",
    "detect_anomaly",
    "detect_cost_anomaly",
    "resolve_pricing",
    "stage_cost_observation",
]
