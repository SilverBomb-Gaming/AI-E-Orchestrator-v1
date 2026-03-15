from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Protocol

from .activation_review_interface import ActivationReviewDecision, ActivationReviewState


AuthorizationDecision = Literal["approve", "deny", "escalate"]
AuthorizationState = Literal[
    "authorization_requested",
    "authorized_for_dry_run",
    "authorized_for_live_run",
    "not_authorized",
    "expired",
    "revoked",
    "requires_additional_review",
    "blocked",
]


@dataclass(frozen=True)
class ActivationAuthorizationRequestContract:
    """Contract for requesting formal authorization after activation review."""

    authorization_id: str
    review_id: str
    activation_id: str
    request_id: str
    execution_id: str
    task_id: str
    selected_adapter_id: str
    review_decision: ActivationReviewDecision
    review_result_state: ActivationReviewState
    policy_level: str
    dry_run: bool = True
    authorization_requested_at: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "review_id": self.review_id,
            "activation_id": self.activation_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "selected_adapter_id": self.selected_adapter_id,
            "review_decision": self.review_decision,
            "review_result_state": self.review_result_state,
            "policy_level": self.policy_level,
            "dry_run": self.dry_run,
            "authorization_requested_at": self.authorization_requested_at,
        }


@dataclass(frozen=True)
class ActivationAuthorizationRecordContract:
    """Contract for a deterministic authorization record."""

    authorization_id: str
    authorization_state: AuthorizationState
    authorized: bool
    authorized_for: str
    authorized_by: str
    authorization_timestamp: str
    authorization_reason: str
    expires_at: str
    notes: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "authorization_state": self.authorization_state,
            "authorized": self.authorized,
            "authorized_for": self.authorized_for,
            "authorized_by": self.authorized_by,
            "authorization_timestamp": self.authorization_timestamp,
            "authorization_reason": self.authorization_reason,
            "expires_at": self.expires_at,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ActivationAuthorizationVerdictContract:
    """Contract for deterministic authorization outcomes."""

    authorization_id: str
    activation_id: str
    authorization_state: AuthorizationState
    proceed_allowed: bool
    requires_additional_review: bool
    blocked: bool
    blocked_reason: str
    escalation_required: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "activation_id": self.activation_id,
            "authorization_state": self.authorization_state,
            "proceed_allowed": self.proceed_allowed,
            "requires_additional_review": self.requires_additional_review,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "escalation_required": self.escalation_required,
        }


def authorization_states() -> list[str]:
    return [
        "authorization_requested",
        "authorized_for_dry_run",
        "authorized_for_live_run",
        "not_authorized",
        "expired",
        "revoked",
        "requires_additional_review",
        "blocked",
    ]


def normalize_authorization_request_state(request: ActivationAuthorizationRequestContract) -> AuthorizationState:
    if request.review_result_state == "ready_for_dry_run":
        return "authorization_requested"
    if request.review_result_state == "denied":
        return "not_authorized"
    if request.review_result_state == "blocked":
        return "blocked"
    if request.review_result_state == "escalated":
        return "requires_additional_review"
    return "authorization_requested"


def evaluate_activation_authorization(
    request: ActivationAuthorizationRequestContract,
    decision: AuthorizationDecision,
    *,
    authorized_by: str,
    authorization_timestamp: str,
    expires_at: str,
    notes: str = "",
) -> tuple[ActivationAuthorizationRecordContract, ActivationAuthorizationVerdictContract]:
    initial_state = normalize_authorization_request_state(request)

    if initial_state == "blocked":
        record = ActivationAuthorizationRecordContract(
            authorization_id=request.authorization_id,
            authorization_state="blocked",
            authorized=False,
            authorized_for="none",
            authorized_by=authorized_by,
            authorization_timestamp=authorization_timestamp,
            authorization_reason="Authorization cannot proceed because the reviewed activation is blocked.",
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ActivationAuthorizationVerdictContract(
            authorization_id=request.authorization_id,
            activation_id=request.activation_id,
            authorization_state="blocked",
            proceed_allowed=False,
            requires_additional_review=False,
            blocked=True,
            blocked_reason="Reviewed activation is blocked.",
            escalation_required=False,
        )
        return record, verdict

    if initial_state == "not_authorized":
        record = ActivationAuthorizationRecordContract(
            authorization_id=request.authorization_id,
            authorization_state="not_authorized",
            authorized=False,
            authorized_for="none",
            authorized_by=authorized_by,
            authorization_timestamp=authorization_timestamp,
            authorization_reason="Authorization cannot proceed because activation review denied the request.",
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ActivationAuthorizationVerdictContract(
            authorization_id=request.authorization_id,
            activation_id=request.activation_id,
            authorization_state="not_authorized",
            proceed_allowed=False,
            requires_additional_review=False,
            blocked=True,
            blocked_reason="Activation review denied the request.",
            escalation_required=False,
        )
        return record, verdict

    if decision == "approve":
        record = ActivationAuthorizationRecordContract(
            authorization_id=request.authorization_id,
            authorization_state="authorized_for_dry_run",
            authorized=True,
            authorized_for="dry_run",
            authorized_by=authorized_by,
            authorization_timestamp=authorization_timestamp,
            authorization_reason="Authorization granted for deterministic dry-run activation only.",
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ActivationAuthorizationVerdictContract(
            authorization_id=request.authorization_id,
            activation_id=request.activation_id,
            authorization_state="authorized_for_dry_run",
            proceed_allowed=True,
            requires_additional_review=False,
            blocked=False,
            blocked_reason="",
            escalation_required=False,
        )
        return record, verdict

    if decision == "deny":
        record = ActivationAuthorizationRecordContract(
            authorization_id=request.authorization_id,
            authorization_state="not_authorized",
            authorized=False,
            authorized_for="none",
            authorized_by=authorized_by,
            authorization_timestamp=authorization_timestamp,
            authorization_reason="Authorization denied for the requested activation.",
            expires_at=expires_at,
            notes=notes,
        )
        verdict = ActivationAuthorizationVerdictContract(
            authorization_id=request.authorization_id,
            activation_id=request.activation_id,
            authorization_state="not_authorized",
            proceed_allowed=False,
            requires_additional_review=False,
            blocked=True,
            blocked_reason="Authorization decision denied the request.",
            escalation_required=False,
        )
        return record, verdict

    record = ActivationAuthorizationRecordContract(
        authorization_id=request.authorization_id,
        authorization_state="requires_additional_review",
        authorized=False,
        authorized_for="none",
        authorized_by=authorized_by,
        authorization_timestamp=authorization_timestamp,
        authorization_reason="Authorization requires additional review before any future execution path.",
        expires_at=expires_at,
        notes=notes,
    )
    verdict = ActivationAuthorizationVerdictContract(
        authorization_id=request.authorization_id,
        activation_id=request.activation_id,
        authorization_state="requires_additional_review",
        proceed_allowed=False,
        requires_additional_review=True,
        blocked=True,
        blocked_reason="Authorization requires additional review.",
        escalation_required=True,
    )
    return record, verdict


class ActivationAuthorizationInterface(Protocol):
    """Architecture-only boundary for post-review authorization records."""

    def build_authorization_request(self, review_id: str) -> ActivationAuthorizationRequestContract:
        ...

    def authorize(
        self,
        request: ActivationAuthorizationRequestContract,
        decision: AuthorizationDecision,
    ) -> tuple[ActivationAuthorizationRecordContract, ActivationAuthorizationVerdictContract]:
        ...


__all__ = [
    "ActivationAuthorizationInterface",
    "ActivationAuthorizationRecordContract",
    "ActivationAuthorizationRequestContract",
    "ActivationAuthorizationVerdictContract",
    "AuthorizationDecision",
    "AuthorizationState",
    "authorization_states",
    "evaluate_activation_authorization",
    "normalize_authorization_request_state",
]