"""Operational SLI and error-budget helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SLIResult:
    eligible_samples: int
    good: int
    bad: int
    unknown: int
    good_rate: Decimal
    bad_rate: Decimal


def compute_sli(
    *,
    good: int = 0,
    bad: int = 0,
    unknown: int = 0,
    eligible_samples: int | None = None,
) -> SLIResult:
    total = good + bad + unknown
    if eligible_samples is None:
        eligible = total
    else:
        eligible = max(eligible_samples, 0)
    if eligible <= 0:
        zero = Decimal("0")
        return SLIResult(
            eligible_samples=eligible,
            good=good,
            bad=bad,
            unknown=unknown,
            good_rate=zero,
            bad_rate=zero,
        )
    good_rate = Decimal(good) / Decimal(eligible)
    bad_rate = Decimal(bad) / Decimal(eligible)
    return SLIResult(
        eligible_samples=eligible,
        good=good,
        bad=bad,
        unknown=unknown,
        good_rate=good_rate,
        bad_rate=bad_rate,
    )


def error_budget_remaining(
    *,
    target_slo: Decimal | float | int = Decimal("0.99"),
    total_samples: int = 100,
    bad_samples: int = 2,
) -> Decimal:
    target = Decimal(str(target_slo))
    if total_samples <= 0:
        return Decimal("0")
    if target <= 0:
        return Decimal("0")
    if target >= 1:
        return Decimal(max(total_samples - bad_samples, 0))
    allowed_bad = Decimal(total_samples) * (Decimal("1") - target)
    return allowed_bad - Decimal(bad_samples)


__all__ = ["SLIResult", "compute_sli", "error_budget_remaining"]
