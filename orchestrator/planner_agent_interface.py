from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol

from .architecture_blueprint import ConversationalRequest, TaskGraph


@dataclass(frozen=True)
class PlanningStrategyContract:
    """Contract for the future planner's bounded strategy output."""

    request_id: str
    request_type: str
    planning_phase_id: str = "PHASE_2"
    goals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    requested_artifacts: List[str] = field(default_factory=list)
    planning_notes: List[str] = field(default_factory=list)


class PlannerAgentInterface(Protocol):
    """Placeholder interface for future planning behavior.

    Responsibilities:
    - receive validated request
    - generate task planning strategy
    - produce task graph contracts

    This module is architecture-only. It defines the expected planner boundary
    without executing tasks or mutating runtime state.
    """

    def plan_request(self, request: ConversationalRequest) -> PlanningStrategyContract:
        ...

    def emit_task_graph(self, strategy: PlanningStrategyContract) -> TaskGraph:
        ...


__all__ = ["PlannerAgentInterface", "PlanningStrategyContract"]