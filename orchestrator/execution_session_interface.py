from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol

from .execution_permit_interface import PermitState


SessionDecision = Literal["approve", "cancel", "expire", "block", "failure_limit", "complete"]
SessionState = Literal[
    "session_requested",
    "session_open",
    "session_completed",
    "session_cancelled",
    "session_expired",
    "session_blocked",
    "session_failed",
    "requires_additional_review",
]
HeartbeatStatus = Literal["planned", "open", "completed", "cancelled", "expired", "blocked", "failed"]


@dataclass(frozen=True)
class ExecutionSessionRequestContract:
    """Contract for requesting a bounded execution session from an issued permit."""

    session_id: str
    permit_id: str
    authorization_id: str
    activation_id: str
    request_id: str
    execution_id: str
    task_id: str
    selected_adapter_id: str
    permit_state: PermitState
    issued_for: str
    policy_level: str
    dry_run: bool = True
    session_requested_at: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "permit_id": self.permit_id,
            "authorization_id": self.authorization_id,
            "activation_id": self.activation_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "selected_adapter_id": self.selected_adapter_id,
            "permit_state": self.permit_state,
            "issued_for": self.issued_for,
            "policy_level": self.policy_level,
            "dry_run": self.dry_run,
            "session_requested_at": self.session_requested_at,
        }


@dataclass(frozen=True)
class ExecutionSessionRecordContract:
    """Contract for a deterministic execution session record."""

    session_id: str
    session_state: SessionState
    opened: bool
    opened_by: str
    opened_timestamp: str
    session_reason: str
    scope_limit: str
    time_budget_seconds: int
    expires_at: str
    cancelled: bool = False
    cancelled_at: str = ""
    cancellation_reason: str = ""
    notes: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_state": self.session_state,
            "opened": self.opened,
            "opened_by": self.opened_by,
            "opened_timestamp": self.opened_timestamp,
            "session_reason": self.session_reason,
            "scope_limit": self.scope_limit,
            "time_budget_seconds": self.time_budget_seconds,
            "expires_at": self.expires_at,
            "cancelled": self.cancelled,
            "cancelled_at": self.cancelled_at,
            "cancellation_reason": self.cancellation_reason,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExecutionSessionVerdictContract:
    """Contract for deterministic execution-session outcomes."""

    session_id: str
    permit_id: str
    session_state: SessionState
    proceed_allowed: bool
    blocked: bool
    blocked_reason: str
    scope_limit: str
    time_budget_seconds: int
    requires_additional_review: bool
    escalation_required: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "permit_id": self.permit_id,
            "session_state": self.session_state,
            "proceed_allowed": self.proceed_allowed,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "scope_limit": self.scope_limit,
            "time_budget_seconds": self.time_budget_seconds,
            "requires_additional_review": self.requires_additional_review,
            "escalation_required": self.escalation_required,
        }


@dataclass(frozen=True)
class ExecutionSessionHeartbeatContract:
    session_id: str
    heartbeat_timestamp: str
    status: HeartbeatStatus
    active_task_id: str
    progress_note: str
    warnings: List[str] = field(default_factory=list)
    operator_attention_required: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "heartbeat_timestamp": self.heartbeat_timestamp,
            "status": self.status,
            "active_task_id": self.active_task_id,
            "progress_note": self.progress_note,
            "warnings": list(self.warnings),
            "operator_attention_required": self.operator_attention_required,
        }


@dataclass(frozen=True)
class ExecutionStopConditionsContract:
    session_id: str
    stop_reason: str
    time_budget_exceeded: bool
    scope_exceeded: bool
    operator_cancelled: bool
    policy_blocked: bool
    failure_limit_reached: bool
    completed: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "stop_reason": self.stop_reason,
            "time_budget_exceeded": self.time_budget_exceeded,
            "scope_exceeded": self.scope_exceeded,
            "operator_cancelled": self.operator_cancelled,
            "policy_blocked": self.policy_blocked,
            "failure_limit_reached": self.failure_limit_reached,
            "completed": self.completed,
        }


def session_states() -> list[str]:
    return [
        "session_requested",
        "session_open",
        "session_completed",
        "session_cancelled",
        "session_expired",
        "session_blocked",
        "session_failed",
        "requires_additional_review",
    ]


def normalize_session_request_state(request: ExecutionSessionRequestContract) -> SessionState:
    if request.permit_state in {"issued_for_dry_run", "issued_for_live_run"}:
        return "session_requested"
    if request.permit_state == "blocked":
        return "session_blocked"
    if request.permit_state == "requires_additional_review":
        return "requires_additional_review"
    return "session_requested"


def evaluate_execution_session(
    request: ExecutionSessionRequestContract,
    decision: SessionDecision,
    *,
    opened_by: str,
    opened_timestamp: str,
    expires_at: str,
    scope_limit: str,
    time_budget_seconds: int,
    notes: str = "",
) -> tuple[
    ExecutionSessionRecordContract,
    ExecutionSessionVerdictContract,
    ExecutionSessionHeartbeatContract,
    ExecutionStopConditionsContract,
]:
    initial_state = normalize_session_request_state(request)

    if initial_state == "session_blocked":
        return _blocked_session(
            request=request,
            opened_by=opened_by,
            opened_timestamp=opened_timestamp,
            expires_at=expires_at,
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            notes=notes,
            reason="Permit is blocked.",
        )

    if initial_state == "requires_additional_review":
        record = ExecutionSessionRecordContract(
            session_id=request.session_id,
            session_state="requires_additional_review",
            opened=False,
            opened_by=opened_by,
            opened_timestamp=opened_timestamp,
            session_reason="Session opening requires additional review.",
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ExecutionSessionVerdictContract(
            session_id=request.session_id,
            permit_id=request.permit_id,
            session_state="requires_additional_review",
            proceed_allowed=False,
            blocked=True,
            blocked_reason="Session opening requires additional review.",
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            requires_additional_review=True,
            escalation_required=True,
        )
        heartbeat = ExecutionSessionHeartbeatContract(
            session_id=request.session_id,
            heartbeat_timestamp=opened_timestamp,
            status="blocked",
            active_task_id=request.task_id,
            progress_note="Session opening paused for additional review.",
            warnings=["No live session engine is active."],
            operator_attention_required=True,
        )
        stop = ExecutionStopConditionsContract(
            session_id=request.session_id,
            stop_reason="requires_additional_review",
            time_budget_exceeded=False,
            scope_exceeded=False,
            operator_cancelled=False,
            policy_blocked=False,
            failure_limit_reached=False,
            completed=False,
        )
        return record, verdict, heartbeat, stop

    if decision == "approve":
        record = ExecutionSessionRecordContract(
            session_id=request.session_id,
            session_state="session_open",
            opened=True,
            opened_by=opened_by,
            opened_timestamp=opened_timestamp,
            session_reason="Session opened from an issued execution permit.",
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ExecutionSessionVerdictContract(
            session_id=request.session_id,
            permit_id=request.permit_id,
            session_state="session_open",
            proceed_allowed=True,
            blocked=False,
            blocked_reason="",
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            requires_additional_review=False,
            escalation_required=False,
        )
        heartbeat = ExecutionSessionHeartbeatContract(
            session_id=request.session_id,
            heartbeat_timestamp=opened_timestamp,
            status="open",
            active_task_id=request.task_id,
            progress_note="Dry-run session opened within the bounded permit scope.",
            warnings=["Simulation-only session; no live engine started."],
            operator_attention_required=False,
        )
        stop = ExecutionStopConditionsContract(
            session_id=request.session_id,
            stop_reason="not_triggered",
            time_budget_exceeded=False,
            scope_exceeded=False,
            operator_cancelled=False,
            policy_blocked=False,
            failure_limit_reached=False,
            completed=False,
        )
        return record, verdict, heartbeat, stop

    if decision == "complete":
        return _terminal_session(
            request=request,
            opened_by=opened_by,
            opened_timestamp=opened_timestamp,
            expires_at=expires_at,
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            notes=notes,
            state="session_completed",
            stop_reason="completed",
            heartbeat_status="completed",
            blocked=False,
        )

    if decision == "cancel":
        return _terminal_session(
            request=request,
            opened_by=opened_by,
            opened_timestamp=opened_timestamp,
            expires_at=expires_at,
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            notes=notes,
            state="session_cancelled",
            stop_reason="operator_cancelled",
            heartbeat_status="cancelled",
            blocked=True,
        )

    if decision == "expire":
        return _terminal_session(
            request=request,
            opened_by=opened_by,
            opened_timestamp=opened_timestamp,
            expires_at=expires_at,
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            notes=notes,
            state="session_expired",
            stop_reason="time_budget_exceeded",
            heartbeat_status="expired",
            blocked=True,
        )

    if decision == "block":
        return _terminal_session(
            request=request,
            opened_by=opened_by,
            opened_timestamp=opened_timestamp,
            expires_at=expires_at,
            scope_limit=scope_limit,
            time_budget_seconds=time_budget_seconds,
            notes=notes,
            state="session_blocked",
            stop_reason="policy_blocked",
            heartbeat_status="blocked",
            blocked=True,
        )

    return _terminal_session(
        request=request,
        opened_by=opened_by,
        opened_timestamp=opened_timestamp,
        expires_at=expires_at,
        scope_limit=scope_limit,
        time_budget_seconds=time_budget_seconds,
        notes=notes,
        state="session_failed",
        stop_reason="failure_limit_reached",
        heartbeat_status="failed",
        blocked=True,
    )


def _blocked_session(
    *,
    request: ExecutionSessionRequestContract,
    opened_by: str,
    opened_timestamp: str,
    expires_at: str,
    scope_limit: str,
    time_budget_seconds: int,
    notes: str,
    reason: str,
) -> tuple[
    ExecutionSessionRecordContract,
    ExecutionSessionVerdictContract,
    ExecutionSessionHeartbeatContract,
    ExecutionStopConditionsContract,
]:
    record = ExecutionSessionRecordContract(
        session_id=request.session_id,
        session_state="session_blocked",
        opened=False,
        opened_by=opened_by,
        opened_timestamp=opened_timestamp,
        session_reason=reason,
        scope_limit=scope_limit,
        time_budget_seconds=time_budget_seconds,
        expires_at=expires_at,
        notes=notes,
    )
    verdict = ExecutionSessionVerdictContract(
        session_id=request.session_id,
        permit_id=request.permit_id,
        session_state="session_blocked",
        proceed_allowed=False,
        blocked=True,
        blocked_reason=reason,
        scope_limit=scope_limit,
        time_budget_seconds=time_budget_seconds,
        requires_additional_review=False,
        escalation_required=False,
    )
    heartbeat = ExecutionSessionHeartbeatContract(
        session_id=request.session_id,
        heartbeat_timestamp=opened_timestamp,
        status="blocked",
        active_task_id=request.task_id,
        progress_note="Session is blocked before opening.",
        warnings=["No live session engine is active."],
        operator_attention_required=True,
    )
    stop = ExecutionStopConditionsContract(
        session_id=request.session_id,
        stop_reason="policy_blocked",
        time_budget_exceeded=False,
        scope_exceeded=False,
        operator_cancelled=False,
        policy_blocked=True,
        failure_limit_reached=False,
        completed=False,
    )
    return record, verdict, heartbeat, stop


def _terminal_session(
    *,
    request: ExecutionSessionRequestContract,
    opened_by: str,
    opened_timestamp: str,
    expires_at: str,
    scope_limit: str,
    time_budget_seconds: int,
    notes: str,
    state: SessionState,
    stop_reason: str,
    heartbeat_status: HeartbeatStatus,
    blocked: bool,
) -> tuple[
    ExecutionSessionRecordContract,
    ExecutionSessionVerdictContract,
    ExecutionSessionHeartbeatContract,
    ExecutionStopConditionsContract,
]:
    cancelled = state == "session_cancelled"
    record = ExecutionSessionRecordContract(
        session_id=request.session_id,
        session_state=state,
        opened=state in {"session_completed", "session_cancelled", "session_expired", "session_blocked", "session_failed"},
        opened_by=opened_by,
        opened_timestamp=opened_timestamp,
        session_reason=f"Session transitioned to {state}.",
        scope_limit=scope_limit,
        time_budget_seconds=time_budget_seconds,
        expires_at=expires_at,
        cancelled=cancelled,
        cancelled_at=opened_timestamp if cancelled else "",
        cancellation_reason="Operator cancelled the session." if cancelled else "",
        notes=notes,
    )
    verdict = ExecutionSessionVerdictContract(
        session_id=request.session_id,
        permit_id=request.permit_id,
        session_state=state,
        proceed_allowed=state in {"session_open", "session_completed"},
        blocked=blocked,
        blocked_reason="" if not blocked else f"Session reached terminal state: {state}.",
        scope_limit=scope_limit,
        time_budget_seconds=time_budget_seconds,
        requires_additional_review=False,
        escalation_required=False,
    )
    heartbeat = ExecutionSessionHeartbeatContract(
        session_id=request.session_id,
        heartbeat_timestamp=opened_timestamp,
        status=heartbeat_status,
        active_task_id=request.task_id,
        progress_note=f"Session state is {state}.",
        warnings=["Simulation-only session; no live engine started."],
        operator_attention_required=blocked,
    )
    stop = ExecutionStopConditionsContract(
        session_id=request.session_id,
        stop_reason=stop_reason,
        time_budget_exceeded=state == "session_expired",
        scope_exceeded=False,
        operator_cancelled=state == "session_cancelled",
        policy_blocked=state == "session_blocked",
        failure_limit_reached=state == "session_failed",
        completed=state == "session_completed",
    )
    return record, verdict, heartbeat, stop


class ExecutionSessionInterface(Protocol):
    """Architecture-only boundary for post-permit execution sessions."""

    def build_session_request(self, permit_id: str) -> ExecutionSessionRequestContract:
        ...

    def open_session(
        self,
        request: ExecutionSessionRequestContract,
        decision: SessionDecision,
    ) -> tuple[
        ExecutionSessionRecordContract,
        ExecutionSessionVerdictContract,
        ExecutionSessionHeartbeatContract,
        ExecutionStopConditionsContract,
    ]:
        ...


__all__ = [
    "ExecutionSessionHeartbeatContract",
    "ExecutionSessionInterface",
    "ExecutionSessionRecordContract",
    "ExecutionSessionRequestContract",
    "ExecutionSessionVerdictContract",
    "ExecutionStopConditionsContract",
    "HeartbeatStatus",
    "SessionDecision",
    "SessionState",
    "evaluate_execution_session",
    "normalize_session_request_state",
    "session_states",
]