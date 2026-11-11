"""Feedback and annotation utilities for Phase C."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable

from complaint_copilot.contracts import (
    AnnotationCandidate,
    AnnotationStatus,
    SignalReference,
)


def _priority_for_signal(signal: SignalReference) -> str:
    if (
        "safety" in signal.reason_code.lower()
        or "severity" in signal.reason_code.lower()
    ):
        return "P1"
    if "quality" in signal.reason_code.lower() or "draft" in signal.reason_code.lower():
        return "P2"
    return "P3"


def merge(
    existing_candidate: AnnotationCandidate | None, signal: SignalReference
) -> AnnotationCandidate:
    """Merge a signal into a pending candidate without counting duplicates."""
    signals = list(existing_candidate.signals) if existing_candidate is not None else []
    if signal not in signals:
        signals.append(signal)

    evidence_links = (
        list(existing_candidate.evidence_links)
        if existing_candidate is not None
        else []
    )
    evidence_links.append(signal.reference_id)
    evidence_links = list(OrderedDict.fromkeys(evidence_links))

    if existing_candidate is None:
        case_id = (
            signal.reference_id.split(":", 1)[0]
            if ":" in signal.reference_id
            else "unknown_case"
        )
        analysis_revision = 1
    else:
        case_id = existing_candidate.case_id
        analysis_revision = existing_candidate.analysis_revision

    priority = max(
        (_priority_for_signal(item) for item in signals),
        key=lambda value: {"P1": 3, "P2": 2, "P3": 1}[value],
        default="P3",
    )

    return AnnotationCandidate(
        case_id=case_id,
        analysis_revision=analysis_revision,
        signals=tuple(signals),
        priority=priority,
        evidence_links=tuple(evidence_links),
        status=AnnotationStatus.PENDING,
    )


def sort_pending_candidates(
    candidates: Iterable[AnnotationCandidate],
) -> list[AnnotationCandidate]:
    """Safety-first ordering of candidate annotation items."""
    return sorted(
        candidates,
        key=lambda candidate: (
            {"P1": 0, "P2": 1, "P3": 2}[candidate.priority],
            -candidate.analysis_revision,
            candidate.case_id,
        ),
    )
