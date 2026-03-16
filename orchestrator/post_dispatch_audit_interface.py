from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol

from .operator_handoff_review_interface import HandoffPriorityLevel
from .post_decision_dispatch_interface import DispatchState


AuditState = Literal[
    "audit_pending",
    "audit_passed",
    "audit_warned",
    "audit_blocked",
    "audit_escalated",
    "audit_archived",
]


@dataclass(frozen=True)
class PostDispatchAuditRequestContract:
    """Contract for deterministic post-dispatch audit requests."""

    audit_id: str
    dispatch_id: str
    decision_id: str
    handoff_id: str
    session_id: str
    request_id: str
    execution_id: str
    task_id: str
    dispatch_state: DispatchState
    dispatch_target: str
    priority_level: HandoffPriorityLevel
    audit_requested_at: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "dispatch_id": self.dispatch_id,
            "decision_id": self.decision_id,
            "handoff_id": self.handoff_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "dispatch_state": self.dispatch_state,
            "dispatch_target": self.dispatch_target,
            "priority_level": self.priority_level,
            "audit_requested_at": self.audit_requested_at,
        }


@dataclass(frozen=True)
class PostDispatchAuditRecordContract:
    """Contract for deterministic post-dispatch audit records."""

    audit_id: str
    audit_state: AuditState
    audit_reason: str
    reviewed_dispatch_state: DispatchState
    reviewed_targets: List[str] = field(default_factory=list)
    archival_authorized: bool = False
    retry_followup_authorized: bool = False
    escalation_required: bool = False
    cleanup_required: bool = False
    notes: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "audit_state": self.audit_state,
            "audit_reason": self.audit_reason,
            "reviewed_dispatch_state": self.reviewed_dispatch_state,
            "reviewed_targets": list(self.reviewed_targets),
            "archival_authorized": self.archival_authorized,
            "retry_followup_authorized": self.retry_followup_authorized,
            "escalation_required": self.escalation_required,
            "cleanup_required": self.cleanup_required,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PostDispatchAuditVerdictContract:
    """Contract for deterministic post-dispatch audit verdicts."""

    audit_id: str
    dispatch_id: str
    audit_state: AuditState
    proceed_allowed: bool
    blocked: bool
    blocked_reason: str
    archive_ready: bool
    retry_ready: bool
    next_phase_ready: bool
    requires_operator_review: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "dispatch_id": self.dispatch_id,
            "audit_state": self.audit_state,
            "proceed_allowed": self.proceed_allowed,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "archive_ready": self.archive_ready,
            "retry_ready": self.retry_ready,
            "next_phase_ready": self.next_phase_ready,
            "requires_operator_review": self.requires_operator_review,
        }


def audit_states() -> list[str]:
    return [
        "audit_pending",
        "audit_passed",
        "audit_warned",
        "audit_blocked",
        "audit_escalated",
        "audit_archived",
    ]


def evaluate_post_dispatch_audit(
    request: PostDispatchAuditRequestContract,
) -> tuple[PostDispatchAuditRecordContract, PostDispatchAuditVerdictContract]:
    mapping: Dict[
        DispatchState,
        tuple[AuditState, str, bool, bool, bool, bool, bool, str],
    ] = {
        "dispatch_retry": (
            "audit_passed",
            "Retry dispatch packaged cleanly for future follow-up review.",
            False,
            True,
            False,
            False,
            True,
            "Retry follow-up remains contract-only until a future approved runtime phase exists.",
        ),
        "dispatch_archive": (
            "audit_archived",
            "Archive dispatch packaged cleanly for archival review.",
            True,
            False,
            False,
            False,
            True,
            "Archive audit remains contract-only until a future approved runtime phase exists.",
        ),
        "dispatch_next_phase": (
            "audit_passed",
            "Next-phase dispatch packaged cleanly for future planning review.",
            False,
            False,
            True,
            False,
            True,
            "Next-phase audit remains contract-only until a future approved runtime phase exists.",
        ),
        "dispatch_defer": (
            "audit_warned",
            "Deferred dispatch remains pending later operator attention.",
            False,
            False,
            False,
            False,
            False,
            "Deferred audit remains contract-only and should be reviewed again later.",
        ),
        "dispatch_deny": (
            "audit_warned",
            "Denied dispatch should remain blocked from follow-up action.",
            False,
            False,
            False,
            False,
            False,
            "Denied audit remains contract-only and records the blocked follow-up state.",
        ),
        "dispatch_escalate": (
            "audit_escalated",
            "Escalated dispatch requires higher-level review before future action.",
            False,
            False,
            False,
            True,
            False,
            "Escalated audit remains contract-only until a future approved runtime phase exists.",
        ),
        "dispatch_blocked": (
            "audit_blocked",
            "Blocked dispatch cannot proceed until dispatch blockers are resolved.",
            False,
            False,
            False,
            False,
            False,
            "Blocked audit remains contract-only and requires further operator review.",
        ),
    }
    (
        audit_state,
        audit_reason,
        archive_ready,
        retry_ready,
        next_phase_ready,
        escalation_required,
        proceed_allowed,
        notes,
    ) = mapping[request.dispatch_state]

    blocked = request.dispatch_state == "dispatch_blocked"
    requires_operator_review = request.dispatch_state in {"dispatch_defer", "dispatch_escalate", "dispatch_blocked", "dispatch_deny"}
    blocked_reason = "Dispatch remains blocked pending follow-up review." if blocked else ""
    reviewed_targets = [request.dispatch_target, request.dispatch_state]

    record = PostDispatchAuditRecordContract(
        audit_id=request.audit_id,
        audit_state=audit_state,
        audit_reason=audit_reason,
        reviewed_dispatch_state=request.dispatch_state,
        reviewed_targets=reviewed_targets,
        archival_authorized=archive_ready,
        retry_followup_authorized=retry_ready,
        escalation_required=escalation_required,
        cleanup_required=request.dispatch_state in {"dispatch_archive", "dispatch_deny"},
        notes=notes,
    )
    verdict = PostDispatchAuditVerdictContract(
        audit_id=request.audit_id,
        dispatch_id=request.dispatch_id,
        audit_state=audit_state,
        proceed_allowed=proceed_allowed,
        blocked=blocked,
        blocked_reason=blocked_reason,
        archive_ready=archive_ready,
        retry_ready=retry_ready,
        next_phase_ready=next_phase_ready,
        requires_operator_review=requires_operator_review,
    )
    return record, verdict


class PostDispatchAuditInterface(Protocol):
    """Architecture-only boundary for deterministic post-dispatch audit packaging."""

    def build_audit_request(self, dispatch_id: str) -> PostDispatchAuditRequestContract:
        ...

    def audit_dispatch(
        self,
        request: PostDispatchAuditRequestContract,
    ) -> tuple[PostDispatchAuditRecordContract, PostDispatchAuditVerdictContract]:
        ...


__all__ = [
    "AuditState",
    "PostDispatchAuditInterface",
    "PostDispatchAuditRecordContract",
    "PostDispatchAuditRequestContract",
    "PostDispatchAuditVerdictContract",
    "audit_states",
    "evaluate_post_dispatch_audit",
]