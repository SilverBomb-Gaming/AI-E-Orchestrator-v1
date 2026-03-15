from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Protocol


ActivationReviewDecision = Literal["approve", "deny", "request_changes", "escalate"]
ActivationReviewState = Literal["ready_for_dry_run", "blocked", "denied", "approval_pending", "escalated"]
ActivationSourceState = Literal[
    "ready_for_dry_run",
    "approval_required",
    "blocked",
    "unsupported",
    "simulated_activated",
]


@dataclass(frozen=True)
class ActivationReviewRequestContract:
    """Contract for operator review of a dry-run activation result."""

    review_id: str
    activation_id: str
    request_id: str
    execution_id: str
    task_id: str
    selected_adapter_id: str
    activation_state: ActivationSourceState
    approval_required: bool
    blocked: bool
    blocked_reason: str
    policy_level: str
    dry_run: bool = True

    def to_payload(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "activation_id": self.activation_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "selected_adapter_id": self.selected_adapter_id,
            "activation_state": self.activation_state,
            "approval_required": self.approval_required,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "policy_level": self.policy_level,
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True)
class ActivationReviewDecisionContract:
    """Contract for a deterministic operator review decision record."""

    review_id: str
    decision: ActivationReviewDecision
    reviewed_by: str
    review_timestamp: str
    notes: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "decision": self.decision,
            "reviewed_by": self.reviewed_by,
            "review_timestamp": self.review_timestamp,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ActivationVerdictContract:
    """Contract for deterministic post-review activation outcomes."""

    activation_id: str
    review_decision: ActivationReviewDecision
    result_state: ActivationReviewState
    result_reason: str
    approved: bool
    blocked: bool
    ready_for_dry_run: bool
    denied: bool
    escalation_required: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "review_decision": self.review_decision,
            "result_state": self.result_state,
            "result_reason": self.result_reason,
            "approved": self.approved,
            "blocked": self.blocked,
            "ready_for_dry_run": self.ready_for_dry_run,
            "denied": self.denied,
            "escalation_required": self.escalation_required,
        }


def activation_review_states() -> list[str]:
    return ["ready_for_dry_run", "blocked", "denied", "approval_pending", "escalated"]


def normalize_activation_review_state(request: ActivationReviewRequestContract) -> ActivationReviewState:
    if request.activation_state == "blocked":
        return "blocked"
    if request.activation_state == "unsupported":
        return "blocked"
    if request.activation_state == "approval_required":
        return "approval_pending"
    if request.activation_state == "ready_for_dry_run":
        return "ready_for_dry_run"
    return "approval_pending"


def evaluate_activation_review(
    request: ActivationReviewRequestContract,
    decision: ActivationReviewDecisionContract,
) -> ActivationVerdictContract:
    initial_state = normalize_activation_review_state(request)

    if initial_state == "blocked":
        return ActivationVerdictContract(
            activation_id=request.activation_id,
            review_decision=decision.decision,
            result_state="blocked",
            result_reason=request.blocked_reason or "Activation remains blocked before review can proceed.",
            approved=False,
            blocked=True,
            ready_for_dry_run=False,
            denied=False,
            escalation_required=False,
        )

    if decision.decision == "approve":
        return ActivationVerdictContract(
            activation_id=request.activation_id,
            review_decision=decision.decision,
            result_state="ready_for_dry_run",
            result_reason="Activation review approved the dry-run path.",
            approved=True,
            blocked=False,
            ready_for_dry_run=True,
            denied=False,
            escalation_required=False,
        )

    if decision.decision == "deny":
        return ActivationVerdictContract(
            activation_id=request.activation_id,
            review_decision=decision.decision,
            result_state="denied",
            result_reason="Activation review denied the requested activation transition.",
            approved=False,
            blocked=True,
            ready_for_dry_run=False,
            denied=True,
            escalation_required=False,
        )

    if decision.decision == "escalate":
        return ActivationVerdictContract(
            activation_id=request.activation_id,
            review_decision=decision.decision,
            result_state="escalated",
            result_reason="Activation review requires escalation before any further transition.",
            approved=False,
            blocked=True,
            ready_for_dry_run=False,
            denied=False,
            escalation_required=True,
        )

    return ActivationVerdictContract(
        activation_id=request.activation_id,
        review_decision=decision.decision,
        result_state="approval_pending",
        result_reason="Activation review requested changes; the activation remains pending review.",
        approved=False,
        blocked=True,
        ready_for_dry_run=False,
        denied=False,
        escalation_required=False,
    )


class ActivationReviewInterface(Protocol):
    """Architecture-only boundary for post-activation operator review."""

    def build_review_request(self, activation_id: str) -> ActivationReviewRequestContract:
        ...

    def evaluate_review(
        self,
        request: ActivationReviewRequestContract,
        decision: ActivationReviewDecisionContract,
    ) -> ActivationVerdictContract:
        ...


__all__ = [
    "ActivationReviewDecision",
    "ActivationReviewDecisionContract",
    "ActivationReviewInterface",
    "ActivationReviewRequestContract",
    "ActivationReviewState",
    "ActivationSourceState",
    "ActivationVerdictContract",
    "activation_review_states",
    "evaluate_activation_review",
    "normalize_activation_review_state",
]