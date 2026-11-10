"""Bounded workflow capacity helpers for agent operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapacityReservation:
    workflow: str
    requested: int
    granted: int
    available: int
    overloaded: bool
    reason: str | None = None


class WorkflowCapacity:
    """A simple bounded reservation tracker for two active workflows."""

    def __init__(self, total_capacity: int, *, reserve_per_workflow: int = 1) -> None:
        if total_capacity <= 0:
            raise ValueError("total_capacity must be positive")
        if reserve_per_workflow <= 0:
            raise ValueError("reserve_per_workflow must be positive")
        self.total_capacity = total_capacity
        self.reserve_per_workflow = reserve_per_workflow
        self._in_use: dict[str, int] = {}

    @property
    def in_use(self) -> int:
        return sum(self._in_use.values())

    @property
    def available(self) -> int:
        return max(self.total_capacity - self.in_use, 0)

    def reserve(self, workflow: str, *, requested: int = 1) -> CapacityReservation:
        if not workflow.strip():
            raise ValueError("workflow must be a non-empty string")
        if requested <= 0:
            raise ValueError("requested capacity must be positive")
        current = self._in_use.get(workflow, 0)
        available = self.total_capacity - self.in_use
        if requested > available:
            return CapacityReservation(
                workflow=workflow,
                requested=requested,
                granted=0,
                available=max(available, 0),
                overloaded=True,
                reason="capacity_exceeded",
            )
        self._in_use[workflow] = current + requested
        return CapacityReservation(
            workflow=workflow,
            requested=requested,
            granted=requested,
            available=max(self.total_capacity - self.in_use, 0),
            overloaded=False,
            reason=None,
        )

    def release(self, workflow: str, *, released: int = 1) -> int:
        if not workflow.strip():
            raise ValueError("workflow must be a non-empty string")
        if released <= 0:
            raise ValueError("released capacity must be positive")
        current = self._in_use.get(workflow, 0)
        if current <= 0:
            return 0
        granted = min(released, current)
        self._in_use[workflow] = current - granted
        if self._in_use[workflow] <= 0:
            self._in_use.pop(workflow, None)
        return granted


class TwoWorkflowCapacity(WorkflowCapacity):
    """Convenience wrapper for classification and drafting workflows."""

    def __init__(self, total_capacity: int, *, reserve_per_workflow: int = 1) -> None:
        super().__init__(total_capacity, reserve_per_workflow=reserve_per_workflow)


__all__ = ["CapacityReservation", "TwoWorkflowCapacity", "WorkflowCapacity"]
