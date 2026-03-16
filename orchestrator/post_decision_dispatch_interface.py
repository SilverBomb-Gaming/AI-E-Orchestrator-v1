from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Protocol

from .operator_decision_resolution_interface import DecisionResolutionState
from .operator_handoff_review_interface import HandoffPriorityLevel


DispatchState = Literal[
    "dispatch_retry",
    "dispatch_archive",
    "dispatch_next_phase",
    "dispatch_defer",
    "dispatch_deny",
    "dispatch_escalate",
    "dispatch_blocked",
]


@dataclass(frozen=True)
class PostDecisionDispatchRequestContract:
    """Contract for deterministic post-decision dispatch requests."""

    dispatch_id: str
    decision_id: str
    handoff_id: str
    session_id: str
    closeout_id: str
    request_id: str
    execution_id: str
    task_id: str
    resolution_state: DecisionResolutionState
    next_action: str
    priority_level: HandoffPriorityLevel
    dispatch_requested_at: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "decision_id": self.decision_id,
            "handoff_id": self.handoff_id,
            "session_id": self.session_id,
            "closeout_id": self.closeout_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "resolution_state": self.resolution_state,
            "next_action": self.next_action,
            "priority_level": self.priority_level,
            "dispatch_requested_at": self.dispatch_requested_at,
        }


@dataclass(frozen=True)
class PostDecisionDispatchRecordContract:
    """Contract for deterministic dispatch records."""

    dispatch_id: str
    dispatch_state: DispatchState
    dispatch_target: str
    dispatch_reason: str
    retry_authorized: bool
    archive_authorized: bool
    next_phase_authorized: bool
    escalation_required: bool
    deferred: bool
    notes: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "dispatch_state": self.dispatch_state,
            "dispatch_target": self.dispatch_target,
            "dispatch_reason": self.dispatch_reason,
            "retry_authorized": self.retry_authorized,
            "archive_authorized": self.archive_authorized,
            "next_phase_authorized": self.next_phase_authorized,
            "escalation_required": self.escalation_required,
            "deferred": self.deferred,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PostDecisionDispatchVerdictContract:
    """Contract for deterministic dispatch verdicts."""

    dispatch_id: str
    resolution_state: DecisionResolutionState
    dispatch_state: DispatchState
    proceed_allowed: bool
    blocked: bool
    blocked_reason: str
    requires_operator_review: bool
    archival_ready: bool
    retry_ready: bool
    next_phase_ready: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "resolution_state": self.resolution_state,
            "dispatch_state": self.dispatch_state,
            "proceed_allowed": self.proceed_allowed,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "requires_operator_review": self.requires_operator_review,
            "archival_ready": self.archival_ready,
            "retry_ready": self.retry_ready,
            "next_phase_ready": self.next_phase_ready,
        }


def dispatch_states() -> list[str]:
    return [
        "dispatch_retry",
        "dispatch_archive",
        "dispatch_next_phase",
        "dispatch_defer",
        "dispatch_deny",
        "dispatch_escalate",
        "dispatch_blocked",
    ]


def evaluate_post_decision_dispatch(
    request: PostDecisionDispatchRequestContract,
    *,
    retry_authorized: bool,
    archive_authorized: bool,
    escalation_required: bool,
) -> tuple[PostDecisionDispatchRecordContract, PostDecisionDispatchVerdictContract]:
    mapping: Dict[
        DecisionResolutionState,
        tuple[DispatchState, str, str, bool, bool, bool, bool, str],
    ] = {
        "resolved_retry": (
            "dispatch_retry",
            "retry_queue_placeholder",
            "Resolved retry authorization should be packaged for a future bounded retry path.",
            True,
            False,
            True,
            False,
            "Retry dispatch remains contract-only until a future approved runtime phase exists.",
        ),
        "resolved_archive": (
            "dispatch_archive",
            "archive_store_placeholder",
            "Resolved archive authorization should be packaged for archival handling.",
            True,
            True,
            False,
            False,
            "Archive dispatch remains contract-only until a future approved runtime phase exists.",
        ),
        "resolved_next_phase": (
            "dispatch_next_phase",
            "next_phase_placeholder",
            "Resolved next-phase authorization should be packaged for later planning review.",
            True,
            False,
            False,
            True,
            "Next-phase dispatch remains contract-only until a future approved runtime phase exists.",
        ),
        "resolved_defer": (
            "dispatch_defer",
            "deferred_review_placeholder",
            "Resolved defer decision should remain parked for later operator review.",
            False,
            False,
            False,
            False,
            "Deferred dispatch remains contract-only and does not trigger runtime action.",
        ),
        "resolved_deny": (
            "dispatch_deny",
            "denied_follow_up_placeholder",
            "Resolved deny decision should prevent follow-up dispatch.",
            False,
            False,
            False,
            False,
            "Denied dispatch remains contract-only and blocks further action.",
        ),
        "resolved_escalate": (
            "dispatch_escalate",
            "escalation_review_placeholder",
            "Resolved escalation should be packaged for higher-level review.",
            False,
            False,
            False,
            False,
            "Escalation dispatch remains contract-only until a future approved runtime phase exists.",
        ),
        "resolution_blocked": (
            "dispatch_blocked",
            "blocked_review_placeholder",
            "Blocked resolution cannot proceed until review blockers are cleared.",
            False,
            False,
            False,
            False,
            "Blocked dispatch remains contract-only and requires further operator review.",
        ),
    }
    (
        dispatch_state,
        dispatch_target,
        dispatch_reason,
        proceed_allowed,
        archival_ready,
        retry_ready,
        next_phase_ready,
        notes,
    ) = mapping[request.resolution_state]

    deferred = request.resolution_state == "resolved_defer"
    blocked = request.resolution_state == "resolution_blocked"
    requires_operator_review = blocked or request.resolution_state in {"resolved_defer", "resolved_escalate"}
    blocked_reason = "Resolution remains blocked pending operator follow-up." if blocked else ""

    record = PostDecisionDispatchRecordContract(
        dispatch_id=request.dispatch_id,
        dispatch_state=dispatch_state,
        dispatch_target=dispatch_target,
        dispatch_reason=dispatch_reason,
        retry_authorized=retry_authorized,
        archive_authorized=archive_authorized,
        next_phase_authorized=request.resolution_state == "resolved_next_phase",
        escalation_required=escalation_required,
        deferred=deferred,
        notes=notes,
    )
    verdict = PostDecisionDispatchVerdictContract(
        dispatch_id=request.dispatch_id,
        resolution_state=request.resolution_state,
        dispatch_state=dispatch_state,
        proceed_allowed=proceed_allowed,
        blocked=blocked,
        blocked_reason=blocked_reason,
        requires_operator_review=requires_operator_review,
        archival_ready=archival_ready and archive_authorized,
        retry_ready=retry_ready and retry_authorized,
        next_phase_ready=next_phase_ready,
    )
    return record, verdict


class PostDecisionDispatchInterface(Protocol):
    """Architecture-only boundary for deterministic post-decision dispatch packaging."""

    def build_dispatch_request(self, decision_id: str) -> PostDecisionDispatchRequestContract:
        ...

    def prepare_dispatch(
        self,
        request: PostDecisionDispatchRequestContract,
    ) -> tuple[PostDecisionDispatchRecordContract, PostDecisionDispatchVerdictContract]:
        ...


__all__ = [
    "DispatchState",
    "PostDecisionDispatchInterface",
    "PostDecisionDispatchRecordContract",
    "PostDecisionDispatchRequestContract",
    "PostDecisionDispatchVerdictContract",
    "dispatch_states",
    "evaluate_post_decision_dispatch",
]