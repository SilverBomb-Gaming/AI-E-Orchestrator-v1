from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol

from .operator_handoff_review_interface import HandoffPriorityLevel


OperatorDecision = Literal[
    "approve_retry",
    "approve_next_phase",
    "archive_only",
    "defer",
    "deny",
    "escalate",
]

DecisionResolutionState = Literal[
    "resolved_retry",
    "resolved_archive",
    "resolved_defer",
    "resolved_deny",
    "resolved_escalate",
    "resolved_next_phase",
    "resolution_blocked",
]


@dataclass(frozen=True)
class OperatorDecisionRequestContract:
    """Contract for deterministic operator decision requests."""

    decision_id: str
    handoff_id: str
    session_id: str
    closeout_id: str
    request_id: str
    execution_id: str
    task_id: str
    priority_level: HandoffPriorityLevel
    operator_attention_required: bool
    reviewable_items: List[str] = field(default_factory=list)
    approval_items: List[str] = field(default_factory=list)
    blocked_items: List[str] = field(default_factory=list)
    retry_candidates: List[str] = field(default_factory=list)
    archival_candidates: List[str] = field(default_factory=list)
    decision_requested_at: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "handoff_id": self.handoff_id,
            "session_id": self.session_id,
            "closeout_id": self.closeout_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "priority_level": self.priority_level,
            "operator_attention_required": self.operator_attention_required,
            "reviewable_items": list(self.reviewable_items),
            "approval_items": list(self.approval_items),
            "blocked_items": list(self.blocked_items),
            "retry_candidates": list(self.retry_candidates),
            "archival_candidates": list(self.archival_candidates),
            "decision_requested_at": self.decision_requested_at,
        }


@dataclass(frozen=True)
class OperatorDecisionResponseContract:
    """Contract for deterministic operator decision responses."""

    decision_id: str
    operator_decision: OperatorDecision
    decided_by: str
    decided_at: str
    notes: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "operator_decision": self.operator_decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class OperatorDecisionResolutionRecordContract:
    """Contract for deterministic decision resolution output."""

    decision_id: str
    resolution_state: DecisionResolutionState
    next_action: str
    retry_authorized: bool
    archival_authorized: bool
    escalation_required: bool
    blocked: bool
    blocked_reason: str
    summary: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "resolution_state": self.resolution_state,
            "next_action": self.next_action,
            "retry_authorized": self.retry_authorized,
            "archival_authorized": self.archival_authorized,
            "escalation_required": self.escalation_required,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "summary": self.summary,
        }


def operator_decisions() -> list[str]:
    return ["approve_retry", "approve_next_phase", "archive_only", "defer", "deny", "escalate"]


def decision_resolution_states() -> list[str]:
    return [
        "resolved_retry",
        "resolved_archive",
        "resolved_defer",
        "resolved_deny",
        "resolved_escalate",
        "resolved_next_phase",
        "resolution_blocked",
    ]


def evaluate_operator_decision_resolution(
    request: OperatorDecisionRequestContract,
    response: OperatorDecisionResponseContract,
) -> OperatorDecisionResolutionRecordContract:
    if request.blocked_items:
        return OperatorDecisionResolutionRecordContract(
            decision_id=request.decision_id,
            resolution_state="resolution_blocked",
            next_action="review_blockers",
            retry_authorized=False,
            archival_authorized=False,
            escalation_required=response.operator_decision == "escalate",
            blocked=True,
            blocked_reason="Blocked review items must be resolved before any next-step authorization.",
            summary="Decision resolution remained blocked because the review package still contains blocked items.",
        )

    mapping: Dict[OperatorDecision, tuple[DecisionResolutionState, str, bool, bool, bool, str]] = {
        "approve_retry": (
            "resolved_retry",
            "retry_task",
            True,
            False,
            False,
            "Operator approved a deterministic retry path.",
        ),
        "approve_next_phase": (
            "resolved_next_phase",
            "advance_to_next_phase",
            False,
            False,
            False,
            "Operator approved the next architecture-only phase.",
        ),
        "archive_only": (
            "resolved_archive",
            "archive_package",
            False,
            True,
            False,
            "Operator approved archival only.",
        ),
        "defer": (
            "resolved_defer",
            "defer_for_review",
            False,
            False,
            False,
            "Operator deferred the decision for a later review window.",
        ),
        "deny": (
            "resolved_deny",
            "deny_follow_up",
            False,
            False,
            False,
            "Operator denied follow-up action.",
        ),
        "escalate": (
            "resolved_escalate",
            "escalate_for_review",
            False,
            False,
            True,
            "Operator escalated the package for higher-level review.",
        ),
    }
    resolution_state, next_action, retry_authorized, archival_authorized, escalation_required, summary = mapping[
        response.operator_decision
    ]
    return OperatorDecisionResolutionRecordContract(
        decision_id=request.decision_id,
        resolution_state=resolution_state,
        next_action=next_action,
        retry_authorized=retry_authorized,
        archival_authorized=archival_authorized,
        escalation_required=escalation_required,
        blocked=False,
        blocked_reason="",
        summary=summary,
    )


class OperatorDecisionResolutionInterface(Protocol):
    """Architecture-only boundary for deterministic operator decision resolution."""

    def build_decision_request(self, handoff_id: str) -> OperatorDecisionRequestContract:
        ...

    def resolve_decision(
        self,
        request: OperatorDecisionRequestContract,
        response: OperatorDecisionResponseContract,
    ) -> OperatorDecisionResolutionRecordContract:
        ...


__all__ = [
    "DecisionResolutionState",
    "OperatorDecision",
    "OperatorDecisionRequestContract",
    "OperatorDecisionResolutionInterface",
    "OperatorDecisionResolutionRecordContract",
    "OperatorDecisionResponseContract",
    "decision_resolution_states",
    "evaluate_operator_decision_resolution",
    "operator_decisions",
]