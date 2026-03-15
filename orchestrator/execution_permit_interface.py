from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Protocol

from .activation_authorization_interface import AuthorizationState


PermitDecision = Literal["approve", "deny", "escalate"]
PermitState = Literal[
    "permit_requested",
    "issued_for_dry_run",
    "issued_for_live_run",
    "not_issued",
    "expired",
    "revoked",
    "blocked",
    "requires_additional_review",
]


@dataclass(frozen=True)
class ExecutionPermitRequestContract:
    """Contract for requesting an execution permit after authorization."""

    permit_id: str
    authorization_id: str
    activation_id: str
    request_id: str
    execution_id: str
    task_id: str
    selected_adapter_id: str
    authorization_state: AuthorizationState
    authorized_for: str
    policy_level: str
    dry_run: bool = True
    permit_requested_at: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "permit_id": self.permit_id,
            "authorization_id": self.authorization_id,
            "activation_id": self.activation_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "selected_adapter_id": self.selected_adapter_id,
            "authorization_state": self.authorization_state,
            "authorized_for": self.authorized_for,
            "policy_level": self.policy_level,
            "dry_run": self.dry_run,
            "permit_requested_at": self.permit_requested_at,
        }


@dataclass(frozen=True)
class ExecutionPermitRecordContract:
    """Contract for a deterministic execution permit record."""

    permit_id: str
    permit_state: PermitState
    issued: bool
    issued_for: str
    issued_by: str
    issued_timestamp: str
    permit_reason: str
    scope_limit: str
    expires_at: str
    notes: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "permit_id": self.permit_id,
            "permit_state": self.permit_state,
            "issued": self.issued,
            "issued_for": self.issued_for,
            "issued_by": self.issued_by,
            "issued_timestamp": self.issued_timestamp,
            "permit_reason": self.permit_reason,
            "scope_limit": self.scope_limit,
            "expires_at": self.expires_at,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExecutionPermitVerdictContract:
    """Contract for deterministic execution-permit outcomes."""

    permit_id: str
    activation_id: str
    permit_state: PermitState
    proceed_allowed: bool
    blocked: bool
    blocked_reason: str
    scope_limit: str
    requires_additional_review: bool
    escalation_required: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "permit_id": self.permit_id,
            "activation_id": self.activation_id,
            "permit_state": self.permit_state,
            "proceed_allowed": self.proceed_allowed,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "scope_limit": self.scope_limit,
            "requires_additional_review": self.requires_additional_review,
            "escalation_required": self.escalation_required,
        }


def permit_states() -> list[str]:
    return [
        "permit_requested",
        "issued_for_dry_run",
        "issued_for_live_run",
        "not_issued",
        "expired",
        "revoked",
        "blocked",
        "requires_additional_review",
    ]


def normalize_permit_request_state(request: ExecutionPermitRequestContract) -> PermitState:
    if request.authorization_state == "authorized_for_dry_run":
        return "permit_requested"
    if request.authorization_state == "authorized_for_live_run":
        return "permit_requested"
    if request.authorization_state == "not_authorized":
        return "not_issued"
    if request.authorization_state == "blocked":
        return "blocked"
    if request.authorization_state == "requires_additional_review":
        return "requires_additional_review"
    return "permit_requested"


def evaluate_execution_permit(
    request: ExecutionPermitRequestContract,
    decision: PermitDecision,
    *,
    issued_by: str,
    issued_timestamp: str,
    expires_at: str,
    notes: str = "",
) -> tuple[ExecutionPermitRecordContract, ExecutionPermitVerdictContract]:
    initial_state = normalize_permit_request_state(request)

    if initial_state == "blocked":
        record = ExecutionPermitRecordContract(
            permit_id=request.permit_id,
            permit_state="blocked",
            issued=False,
            issued_for="none",
            issued_by=issued_by,
            issued_timestamp=issued_timestamp,
            permit_reason="Permit cannot be issued because the authorization is blocked.",
            scope_limit="none",
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ExecutionPermitVerdictContract(
            permit_id=request.permit_id,
            activation_id=request.activation_id,
            permit_state="blocked",
            proceed_allowed=False,
            blocked=True,
            blocked_reason="Authorization is blocked.",
            scope_limit="none",
            requires_additional_review=False,
            escalation_required=False,
        )
        return record, verdict

    if initial_state == "not_issued":
        record = ExecutionPermitRecordContract(
            permit_id=request.permit_id,
            permit_state="not_issued",
            issued=False,
            issued_for="none",
            issued_by=issued_by,
            issued_timestamp=issued_timestamp,
            permit_reason="Permit cannot be issued because authorization was not granted.",
            scope_limit="none",
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ExecutionPermitVerdictContract(
            permit_id=request.permit_id,
            activation_id=request.activation_id,
            permit_state="not_issued",
            proceed_allowed=False,
            blocked=True,
            blocked_reason="Authorization was not granted.",
            scope_limit="none",
            requires_additional_review=False,
            escalation_required=False,
        )
        return record, verdict

    if decision == "approve":
        issued_state: PermitState = "issued_for_dry_run" if request.authorized_for == "dry_run" else "issued_for_live_run"
        scope_limit = "dry_run_only" if request.authorized_for == "dry_run" else "bounded_live_run"
        record = ExecutionPermitRecordContract(
            permit_id=request.permit_id,
            permit_state=issued_state,
            issued=True,
            issued_for=request.authorized_for,
            issued_by=issued_by,
            issued_timestamp=issued_timestamp,
            permit_reason="Permit issued according to the bounded authorization record.",
            scope_limit=scope_limit,
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ExecutionPermitVerdictContract(
            permit_id=request.permit_id,
            activation_id=request.activation_id,
            permit_state=issued_state,
            proceed_allowed=True,
            blocked=False,
            blocked_reason="",
            scope_limit=scope_limit,
            requires_additional_review=False,
            escalation_required=False,
        )
        return record, verdict

    if decision == "deny":
        record = ExecutionPermitRecordContract(
            permit_id=request.permit_id,
            permit_state="not_issued",
            issued=False,
            issued_for="none",
            issued_by=issued_by,
            issued_timestamp=issued_timestamp,
            permit_reason="Permit issuance denied for the requested execution path.",
            scope_limit="none",
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ExecutionPermitVerdictContract(
            permit_id=request.permit_id,
            activation_id=request.activation_id,
            permit_state="not_issued",
            proceed_allowed=False,
            blocked=True,
            blocked_reason="Permit issuance denied.",
            scope_limit="none",
            requires_additional_review=False,
            escalation_required=False,
        )
        return record, verdict

    record = ExecutionPermitRecordContract(
        permit_id=request.permit_id,
        permit_state="requires_additional_review",
        issued=False,
        issued_for="none",
        issued_by=issued_by,
        issued_timestamp=issued_timestamp,
        permit_reason="Permit issuance requires additional review before any future execution path.",
        scope_limit="none",
        expires_at=expires_at,
        notes=notes,
    )
    verdict = ExecutionPermitVerdictContract(
        permit_id=request.permit_id,
        activation_id=request.activation_id,
        permit_state="requires_additional_review",
        proceed_allowed=False,
        blocked=True,
        blocked_reason="Permit issuance requires additional review.",
        scope_limit="none",
        requires_additional_review=True,
        escalation_required=True,
    )
    return record, verdict


class ExecutionPermitInterface(Protocol):
    """Architecture-only boundary for post-authorization execution permits."""

    def build_permit_request(self, authorization_id: str) -> ExecutionPermitRequestContract:
        ...

    def issue_permit(
        self,
        request: ExecutionPermitRequestContract,
        decision: PermitDecision,
    ) -> tuple[ExecutionPermitRecordContract, ExecutionPermitVerdictContract]:
        ...


__all__ = [
    "ExecutionPermitInterface",
    "ExecutionPermitRecordContract",
    "ExecutionPermitRequestContract",
    "ExecutionPermitVerdictContract",
    "PermitDecision",
    "PermitState",
    "evaluate_execution_permit",
    "normalize_permit_request_state",
    "permit_states",
]