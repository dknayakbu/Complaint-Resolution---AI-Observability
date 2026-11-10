"""Fixture-tagged telemetry signals for the AgentOps phase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FixtureSignal:
    signal_type: str
    fixture_id: str
    tags: tuple[str, ...]
    payload: dict[str, Any]


def generate_fixture_signals() -> tuple[FixtureSignal, ...]:
    return (
        FixtureSignal(
            signal_type="stage_usage",
            fixture_id="fixture-stage-usage-sample",
            tags=("fixture", "agentops", "stage_usage"),
            payload={
                "stage": "classification",
                "requested_model": "gpt-4.1-mini",
                "input_tokens": 1024,
                "output_tokens": 256,
                "known": True,
            },
        ),
        FixtureSignal(
            signal_type="cost_anomaly",
            fixture_id="fixture-cost-baseline",
            tags=("fixture", "agentops", "cost"),
            payload={
                "annotation": "recent analysis cost is 3x warmup mean",
                "baseline_mean_usd": "0.002",
                "current_mean_usd": "0.006",
            },
        ),
        FixtureSignal(
            signal_type="slo_review",
            fixture_id="fixture-slo-burn",
            tags=("fixture", "agentops", "slo"),
            payload={
                "window": "30d",
                "target": "0.99",
                "bad_samples": 2,
                "total_samples": 100,
            },
        ),
    )


__all__ = ["FixtureSignal", "generate_fixture_signals"]
