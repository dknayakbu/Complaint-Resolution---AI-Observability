"""Grafana alert adaptation and incident episode handling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from complaint_copilot.contracts import IncidentPriority

RUNBOOKS = {
    "service_access": "https://example.invalid/runbooks/service-access",
    "fraud_scams": "https://example.invalid/runbooks/fraud-scam-response",
    "cards_payments": "https://example.invalid/runbooks/payment-incident",
    "default": "https://example.invalid/runbooks/triage",
}


@dataclass(frozen=True)
class IncidentEpisode:
    incident_id: str
    status: str
    priority: IncidentPriority
    case_ids: tuple[str, ...]
    summary: str
    runbook_url: str
    resolved_at: datetime | None = None
    escalation_count: int = 0


def _normalize_priority(priority: object | None) -> IncidentPriority:
    if isinstance(priority, IncidentPriority):
        return priority
    if isinstance(priority, str):
        normalized = priority.strip().upper()
        if normalized in {"P1", "P2", "P3"}:
            return IncidentPriority(normalized)
        if normalized in {"1", "2", "3"}:
            return IncidentPriority(f"P{normalized}")
        if normalized == "CRITICAL":
            return IncidentPriority.P1
        if normalized == "WARNING":
            return IncidentPriority.P2
        if normalized in {"INFO", "OK", "NORMAL", "NONE"}:
            return IncidentPriority.P3
    if isinstance(priority, int):
        if priority == 1:
            return IncidentPriority.P1
        if priority == 2:
            return IncidentPriority.P2
        if priority == 3:
            return IncidentPriority.P3
    return IncidentPriority.P3


def _case_ids_from_labels(labels: Mapping[str, Any]) -> tuple[str, ...]:
    candidates: list[str] = []
    for key in ("case_id", "case_ids", "affected_case", "affected_cases"):
        value = labels.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                if isinstance(item, str):
                    candidates.append(item)
    return tuple(dict.fromkeys(candidates))


def adapt_grafana_alert(
    payload: Mapping[str, Any],
    *,
    case_id: str | None = None,
) -> IncidentEpisode:
    labels = (
        payload.get("labels", {})
        if isinstance(payload.get("labels", {}), Mapping)
        else {}
    )
    annotations = (
        payload.get("annotations", {})
        if isinstance(payload.get("annotations", {}), Mapping)
        else {}
    )
    status = str(payload.get("status") or payload.get("state") or "active").lower()
    incident_id = str(
        payload.get("id")
        or payload.get("fingerprint")
        or payload.get("title")
        or "incident"
    )
    priority = _normalize_priority(
        labels.get("incident_priority")
        or labels.get("priority")
        or labels.get("severity")
        or payload.get("priority")
        or None
    )
    case_ids = _case_ids_from_labels(labels)
    if case_id is not None:
        case_ids = tuple(dict.fromkeys((case_id, *case_ids)))
    summary = str(payload.get("title") or annotations.get("summary") or "Grafana alert")
    runbook = str(
        labels.get("runbook_url")
        or RUNBOOKS.get(str(labels.get("team") or "default"), RUNBOOKS["default"])
    )
    resolved_at = payload.get("resolvedAt")
    if resolved_at is not None and not isinstance(resolved_at, datetime):
        try:
            resolved_at = datetime.fromisoformat(
                str(resolved_at).replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError:
            resolved_at = None
    return IncidentEpisode(
        incident_id=incident_id,
        status=status,
        priority=priority,
        case_ids=case_ids,
        summary=summary,
        runbook_url=runbook,
        resolved_at=resolved_at,
        escalation_count=1
        if priority in {IncidentPriority.P1, IncidentPriority.P2}
        else 0,
    )


def dedupe_incident_episode(
    episodes: Sequence[IncidentEpisode],
    *,
    seen: set[str] | None = None,
) -> list[IncidentEpisode]:
    observed = set() if seen is None else set(seen)
    unique: list[IncidentEpisode] = []
    for episode in episodes:
        if episode.incident_id in observed:
            continue
        observed.add(episode.incident_id)
        unique.append(episode)
    return unique


def escalate_priority(
    episode: IncidentEpisode,
    *,
    priority: IncidentPriority,
) -> IncidentEpisode:
    return IncidentEpisode(
        incident_id=episode.incident_id,
        status=episode.status,
        priority=priority,
        case_ids=episode.case_ids,
        summary=episode.summary,
        runbook_url=episode.runbook_url,
        resolved_at=episode.resolved_at,
        escalation_count=episode.escalation_count + 1,
    )


def create_postmortem_export(
    title: str,
    *,
    incident: IncidentEpisode,
    action_items: Sequence[str],
    summary: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "incident_id": incident.incident_id,
        "status": incident.status,
        "priority": incident.priority.value,
        "case_ids": list(incident.case_ids),
        "summary": summary,
        "runbook_url": incident.runbook_url,
        "action_items": list(action_items),
    }


__all__ = [
    "IncidentEpisode",
    "RUNBOOKS",
    "adapt_grafana_alert",
    "create_postmortem_export",
    "dedupe_incident_episode",
    "escalate_priority",
]
