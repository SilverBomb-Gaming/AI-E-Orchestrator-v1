from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol

from .execution_session_interface import SessionState


CloseoutState = Literal[
    "closeout_requested",
    "closed_successfully",
    "closed_with_warnings",
    "closed_blocked",
    "closed_failed",
    "closed_cancelled",
    "closed_expired",
]


@dataclass(frozen=True)
class ExecutionCloseoutRequestContract:
    """Contract for requesting deterministic session closeout."""

    closeout_id: str
    session_id: str
    permit_id: str
    authorization_id: str
    request_id: str
    execution_id: str
    task_id: str
    session_state: SessionState
    stop_reason: str
    time_budget_seconds: int
    artifacts_summary_count: int
    closeout_requested_at: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "closeout_id": self.closeout_id,
            "session_id": self.session_id,
            "permit_id": self.permit_id,
            "authorization_id": self.authorization_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "session_state": self.session_state,
            "stop_reason": self.stop_reason,
            "time_budget_seconds": self.time_budget_seconds,
            "artifacts_summary_count": self.artifacts_summary_count,
            "closeout_requested_at": self.closeout_requested_at,
        }


@dataclass(frozen=True)
class ExecutionCloseoutRecordContract:
    """Contract for deterministic closeout summaries."""

    closeout_id: str
    closeout_state: CloseoutState
    completed: bool
    completed_at: str
    final_outcome: str
    final_summary: str
    retained_artifacts: List[str] = field(default_factory=list)
    discarded_artifacts: List[str] = field(default_factory=list)
    cleanup_required: bool = False
    cleanup_notes: str = ""
    operator_attention_required: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "closeout_id": self.closeout_id,
            "closeout_state": self.closeout_state,
            "completed": self.completed,
            "completed_at": self.completed_at,
            "final_outcome": self.final_outcome,
            "final_summary": self.final_summary,
            "retained_artifacts": list(self.retained_artifacts),
            "discarded_artifacts": list(self.discarded_artifacts),
            "cleanup_required": self.cleanup_required,
            "cleanup_notes": self.cleanup_notes,
            "operator_attention_required": self.operator_attention_required,
        }


@dataclass(frozen=True)
class ExecutionCloseoutVerdictContract:
    """Contract for deterministic closeout verdicts."""

    closeout_id: str
    session_id: str
    closeout_state: CloseoutState
    operator_review_required: bool
    cleanup_required: bool
    retry_recommended: bool
    retry_reason: str
    escalation_required: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "closeout_id": self.closeout_id,
            "session_id": self.session_id,
            "closeout_state": self.closeout_state,
            "operator_review_required": self.operator_review_required,
            "cleanup_required": self.cleanup_required,
            "retry_recommended": self.retry_recommended,
            "retry_reason": self.retry_reason,
            "escalation_required": self.escalation_required,
        }


def closeout_states() -> list[str]:
    return [
        "closeout_requested",
        "closed_successfully",
        "closed_with_warnings",
        "closed_blocked",
        "closed_failed",
        "closed_cancelled",
        "closed_expired",
    ]


def normalize_closeout_request_state(request: ExecutionCloseoutRequestContract) -> CloseoutState:
    if request.session_state in {"session_completed", "session_failed", "session_cancelled", "session_expired", "session_blocked"}:
        return "closeout_requested"
    return "closed_with_warnings"


def evaluate_execution_closeout(
    request: ExecutionCloseoutRequestContract,
    *,
    retained_artifacts: List[str],
    discarded_artifacts: List[str],
    completed_at: str,
) -> tuple[ExecutionCloseoutRecordContract, ExecutionCloseoutVerdictContract]:
    initial_state = normalize_closeout_request_state(request)
    if initial_state != "closeout_requested":
        record = ExecutionCloseoutRecordContract(
            closeout_id=request.closeout_id,
            closeout_state="closed_with_warnings",
            completed=True,
            completed_at=completed_at,
            final_outcome="warning",
            final_summary="Session closeout ran before the session reached a terminal state.",
            retained_artifacts=list(retained_artifacts),
            discarded_artifacts=list(discarded_artifacts),
            cleanup_required=False,
            cleanup_notes="No cleanup actions were required.",
            operator_attention_required=True,
        )
        verdict = ExecutionCloseoutVerdictContract(
            closeout_id=request.closeout_id,
            session_id=request.session_id,
            closeout_state="closed_with_warnings",
            operator_review_required=True,
            cleanup_required=False,
            retry_recommended=False,
            retry_reason="",
            escalation_required=False,
        )
        return record, verdict

    mapping: Dict[SessionState, tuple[CloseoutState, str, bool, bool, bool, str]] = {
        "session_completed": ("closed_successfully", "success", False, False, False, ""),
        "session_failed": ("closed_failed", "failed", True, True, True, "Session failed within the bounded window."),
        "session_cancelled": ("closed_cancelled", "cancelled", True, False, False, ""),
        "session_expired": ("closed_expired", "expired", True, True, True, "Session expired before completion."),
        "session_blocked": ("closed_blocked", "blocked", True, False, False, ""),
        "session_requested": ("closed_with_warnings", "warning", True, False, False, ""),
        "session_open": ("closed_with_warnings", "warning", True, False, False, ""),
        "requires_additional_review": ("closed_with_warnings", "warning", True, False, True, "Additional review is still required."),
    }
    close_state, outcome, attention, retry, escalate, retry_reason = mapping[request.session_state]
    cleanup_required = bool(discarded_artifacts)
    record = ExecutionCloseoutRecordContract(
        closeout_id=request.closeout_id,
        closeout_state=close_state,
        completed=True,
        completed_at=completed_at,
        final_outcome=outcome,
        final_summary=f"Session {request.session_state} closed as {close_state}.",
        retained_artifacts=list(retained_artifacts),
        discarded_artifacts=list(discarded_artifacts),
        cleanup_required=cleanup_required,
        cleanup_notes="Retained and discarded artifact sets were summarized deterministically.",
        operator_attention_required=attention,
    )
    verdict = ExecutionCloseoutVerdictContract(
        closeout_id=request.closeout_id,
        session_id=request.session_id,
        closeout_state=close_state,
        operator_review_required=attention,
        cleanup_required=cleanup_required,
        retry_recommended=retry,
        retry_reason=retry_reason,
        escalation_required=escalate,
    )
    return record, verdict


class ExecutionCloseoutInterface(Protocol):
    """Architecture-only boundary for post-session closeout."""

    def build_closeout_request(self, session_id: str) -> ExecutionCloseoutRequestContract:
        ...

    def close_session(self, request: ExecutionCloseoutRequestContract) -> tuple[ExecutionCloseoutRecordContract, ExecutionCloseoutVerdictContract]:
        ...


__all__ = [
    "CloseoutState",
    "ExecutionCloseoutInterface",
    "ExecutionCloseoutRecordContract",
    "ExecutionCloseoutRequestContract",
    "ExecutionCloseoutVerdictContract",
    "closeout_states",
    "evaluate_execution_closeout",
    "normalize_closeout_request_state",
]