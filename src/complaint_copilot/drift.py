"""Distribution drift helpers for Phase C."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence


class DriftIneligibleError(ValueError):
    """Raised when a drift signal cannot be evaluated with the available data."""


def _normalise_distribution(items: Iterable[str]) -> dict[str, float]:
    counter = Counter(items)
    total = sum(counter.values())
    if total == 0:
        raise DriftIneligibleError("feature distribution is empty")
    return {key: count / total for key, count in sorted(counter.items())}


def jensen_shannon_divergence(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    """Compute normalised JSD between distributions."""
    keys = sorted(set(left) | set(right))
    if not keys:
        raise DriftIneligibleError("missing distributions for drift check")
    merged = {key: (left.get(key, 0.0) + right.get(key, 0.0)) / 2.0 for key in keys}
    def entropy(dist: Mapping[str, float]) -> float:
        total = 0.0
        for value in dist.values():
            if value <= 0.0:
                continue
            total -= value * math.log(value, 2)
        return total
    return (entropy(merged) - (entropy(left) + entropy(right)) / 2.0) / math.log(2.0)


def _window_features(rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    if not rows:
        raise DriftIneligibleError("empty baseline or window")
    counter: Counter[str] = Counter()
    for row in rows:
        text = str(row.get("complaint_text", "")).lower()
        counter["length_short" if len(text) < 200 else "length_medium" if len(text) < 600 else "length_long"] += 1
        tokens = re.findall(r"\b\w+\b", text)
        for token in tokens[:5]:
            counter[f"topic:{token}"] += 1
    return _normalise_distribution(counter)


def window_drift_score(baseline: Sequence[Mapping[str, object]], recent_window: Sequence[Mapping[str, object]]) -> float:
    if len(baseline) < 30:
        raise DriftIneligibleError("baseline must contain at least 30 records")
    if len(recent_window) < 10:
        raise DriftIneligibleError("recent window must contain at least 10 records")
    return jensen_shannon_divergence(_window_features(baseline), _window_features(recent_window))


def evaluate_drift_windows(
    baseline: Sequence[Mapping[str, object]],
    windows: Sequence[Sequence[Mapping[str, object]]],
    *,
    threshold: float = 0.10,
) -> dict[str, object]:
    if not baseline:
        return {"eligible": False, "status": "ineligible", "reason": "missing_baseline"}
    if len(baseline) < 30:
        return {"eligible": False, "status": "ineligible", "reason": "baseline_too_small"}
    if not windows:
        return {"eligible": False, "status": "ineligible", "reason": "no_shift_windows"}

    scores: list[float] = []
    for window in windows:
        if not window:
            return {"eligible": False, "status": "ineligible", "reason": "empty_window"}
        if len(window) < 10:
            return {"eligible": False, "status": "ineligible", "reason": "window_too_small"}
        try:
            scores.append(window_drift_score(baseline, window))
        except DriftIneligibleError:
            return {"eligible": False, "status": "ineligible", "reason": "distribution_too_sparse"}

    consecutive = 0
    for score in scores:
        if score > threshold:
            consecutive += 1
        else:
            consecutive = 0
    if consecutive >= 2:
        return {
            "eligible": True,
            "status": "warning",
            "score": max(scores),
            "threshold": threshold,
            "window_scores": scores,
        }
    return {
        "eligible": True,
        "status": "stable",
        "score": max(scores),
        "threshold": threshold,
        "window_scores": scores,
    }
