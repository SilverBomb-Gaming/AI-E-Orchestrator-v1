from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol


SelectionState = Literal["selectable", "blocked", "approval_pending", "denied", "unsupported"]


@dataclass(frozen=True)
class SelectionInputContract:
    """Contract for matching an execution request to an approved adapter."""

    selection_id: str
    request_id: str
    execution_id: str
    task_id: str
    task_type: str
    runtime_target: str
    policy_level: str
    dry_run: bool = True
    approval_required: bool = False
    expected_outputs: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "selection_id": self.selection_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "runtime_target": self.runtime_target,
            "policy_level": self.policy_level,
            "dry_run": self.dry_run,
            "approval_required": self.approval_required,
            "expected_outputs": list(self.expected_outputs),
        }


@dataclass(frozen=True)
class SelectionOutputContract:
    """Contract for deterministic adapter-selection outcomes."""

    selection_id: str
    chosen_adapter_id: str
    candidate_adapters: List[str] = field(default_factory=list)
    selection_reason: str = ""
    blocked: bool = False
    blocked_reason: str = ""
    approval_required: bool = False
    escalation_required: bool = False
    state: SelectionState = "selectable"

    def to_payload(self) -> Dict[str, Any]:
        return {
            "selection_id": self.selection_id,
            "chosen_adapter_id": self.chosen_adapter_id,
            "candidate_adapters": list(self.candidate_adapters),
            "selection_reason": self.selection_reason,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "approval_required": self.approval_required,
            "escalation_required": self.escalation_required,
            "state": self.state,
        }


class AdapterSelectionInterface(Protocol):
    """Architecture-only boundary for future adapter selection.

    This layer describes how a future execution request would be matched to an
    approved adapter. It does not select or invoke adapters at runtime.
    """

    def build_selection_input(self, execution_id: str) -> SelectionInputContract:
        ...

    def select_adapter(self, selection_input: SelectionInputContract) -> SelectionOutputContract:
        ...


__all__ = [
    "AdapterSelectionInterface",
    "SelectionInputContract",
    "SelectionOutputContract",
    "SelectionState",
]