from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Protocol


ApprovalDecisionState = Literal["approved", "denied", "deferred"]
GateVerdictState = Literal["allow", "approval_pending", "deny", "escalate"]


@dataclass(frozen=True)
class ApprovalRequestContract:
    """Contract for requesting operator approval before future live work."""

    approval_id: str
    request_id: str
    execution_id: str
    adapter_id: str
    approval_reason: str
    requested_action: str
    policy_level: str
    blocking: bool = True
    safe_alternative: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "adapter_id": self.adapter_id,
            "approval_reason": self.approval_reason,
            "requested_action": self.requested_action,
            "policy_level": self.policy_level,
            "blocking": self.blocking,
            "safe_alternative": self.safe_alternative,
        }


@dataclass(frozen=True)
class ApprovalDecisionContract:
    """Contract for a future approval decision record."""

    approval_id: str
    decision: ApprovalDecisionState
    decided_by: str
    decided_at: str
    notes: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class GateVerdictContract:
    """Contract for gate outcomes before any future live action."""

    verdict: GateVerdictState
    proceed_allowed: bool
    blocked_until_approved: bool
    escalation_required: bool
    denial_reason: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "proceed_allowed": self.proceed_allowed,
            "blocked_until_approved": self.blocked_until_approved,
            "escalation_required": self.escalation_required,
            "denial_reason": self.denial_reason,
        }


class ApprovalGateInterface(Protocol):
    """Architecture-only boundary for future approval gating.

    This layer defines approval requests, decisions, and gate verdicts without
    approving or blocking work at runtime.
    """

    def build_approval_request(self, execution_id: str) -> ApprovalRequestContract:
        ...

    def evaluate_gate(self, decision: ApprovalDecisionContract) -> GateVerdictContract:
        ...


__all__ = [
    "ApprovalDecisionContract",
    "ApprovalDecisionState",
    "ApprovalGateInterface",
    "ApprovalRequestContract",
    "GateVerdictContract",
    "GateVerdictState",
]