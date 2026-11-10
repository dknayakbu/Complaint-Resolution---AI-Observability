"""Pure cost attribution helpers for Phase B."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from complaint_copilot.contracts import CostObservation, TokenUsage


class CostError(ValueError):
    """Raised when cost inputs violate Phase B expectations."""


def calculate_usage_cost(
    usage: TokenUsage,
    *,
    input_price_per_1k: Decimal,
    output_price_per_1k: Decimal,
    cached_input_price_per_1k: Decimal = Decimal("0"),
) -> Decimal:
    """Compute a deterministic cost estimate from token usage.

    Unknown usage is intentionally not treated as zero-cost. Instead, callers
    must surface an incomplete observation via the return contract.
    """
    if not usage.known:
        raise CostError("usage is unknown; cost cannot be calculated as zero")
    if usage.input_tokens is None or usage.output_tokens is None:
        raise CostError("known usage requires input and output token counts")

    input_cost = (Decimal(usage.input_tokens) / Decimal(1000)) * input_price_per_1k
    output_cost = (Decimal(usage.output_tokens) / Decimal(1000)) * output_price_per_1k
    cached_cost = Decimal("0")
    if usage.provider_cached_input_tokens is not None:
        cached_cost = (
            Decimal(usage.provider_cached_input_tokens) / Decimal(1000)
        ) * cached_input_price_per_1k
    return input_cost + output_cost + cached_cost


def stage_cost_observation(
    *,
    amount_usd: Decimal | None,
    pricing_version: str,
    complete: bool = True,
    unknown_reason: str | None = None,
) -> CostObservation:
    if amount_usd is None and complete:
        raise CostError("complete cost observations require an amount")
    return CostObservation(
        amount_usd=amount_usd,
        complete=complete,
        pricing_version=pricing_version if complete else None,
        unknown_reason=unknown_reason,
    )


def aggregate_stage_costs(records: Sequence[Mapping[str, object]]) -> Decimal:
    total = Decimal("0")
    for record in records:
        amount = record.get("amount_usd")
        if amount is None:
            raise CostError("stage cost aggregation cannot include unknown cost amounts")
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


def detect_anomaly(
    recent_costs: Sequence[Decimal],
    *,
    baseline: Sequence[Decimal],
    multiplier: Decimal = Decimal("3"),
) -> bool:
    if not baseline:
        return False
    avg_baseline = sum(baseline, Decimal("0")) / Decimal(len(baseline))
    if avg_baseline <= 0:
        return False
    recent_mean = sum(recent_costs, Decimal("0")) / Decimal(len(recent_costs) or 1)
    return recent_mean >= (avg_baseline * multiplier)
