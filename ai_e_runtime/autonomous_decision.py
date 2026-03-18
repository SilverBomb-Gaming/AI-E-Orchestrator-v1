from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class DecisionRuntimeContext:
    session_phase: str | None = None
    waiting_reason: str | None = None
    blocked_reason: str | None = None
    current_task_id: str | None = None
    queue_remaining: int = 0

    def to_payload(self) -> Dict[str, Any]:
        return {
            "session_phase": self.session_phase,
            "waiting_reason": self.waiting_reason,
            "blocked_reason": self.blocked_reason,
            "current_task_id": self.current_task_id,
            "queue_remaining": self.queue_remaining,
        }


@dataclass(frozen=True)
class AutonomousDecision:
    decision: str
    decision_reason: str
    decision_summary: str
    auto_execute: bool
    approval_required: bool
    sandbox_first: bool
    review_required: bool
    blocked: bool
    missing_evidence: List[str]
    content_policy_block: bool
    capability_supported: bool
    promotion_basis: str | None
    fail_closed_reason: str | None
    runtime_context: DecisionRuntimeContext

    def to_payload(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "decision_summary": self.decision_summary,
            "auto_execute": self.auto_execute,
            "approval_required": self.approval_required,
            "sandbox_first": self.sandbox_first,
            "review_required": self.review_required,
            "blocked": self.blocked,
            "missing_evidence": list(self.missing_evidence),
            "content_policy_block": self.content_policy_block,
            "capability_supported": self.capability_supported,
            "promotion_basis": self.promotion_basis,
            "fail_closed_reason": self.fail_closed_reason,
            "runtime_context": self.runtime_context.to_payload(),
        }


def evaluate_autonomous_decision(
    *,
    requested_intent: str,
    resolved_intent: str,
    mutation_capable: bool,
    capability_supported: bool,
    eligible_for_auto: bool,
    approval_required_by_capability: bool,
    intelligence_execution_decision: str | None,
    intelligence_summary: str | None,
    auto_execution_reason: str | None,
    missing_evidence: List[str] | None,
    content_policy_decision: str | None,
    content_policy_summary: str | None,
    rating_locked: bool,
    runtime_context: DecisionRuntimeContext | None = None,
) -> AutonomousDecision:
    context = runtime_context or DecisionRuntimeContext()
    evidence_gaps = list(missing_evidence or [])
    is_mutation_path = requested_intent == "mutate" or mutation_capable

    if is_mutation_path and not capability_supported:
        summary = "Decision: block - capability unsupported for write-capable execution."
        return AutonomousDecision(
            decision="block",
            decision_reason="capability_unsupported",
            decision_summary=summary,
            auto_execute=False,
            approval_required=False,
            sandbox_first=False,
            review_required=False,
            blocked=True,
            missing_evidence=evidence_gaps,
            content_policy_block=False,
            capability_supported=False,
            promotion_basis=None,
            fail_closed_reason="No supported write-capable capability matched the request.",
            runtime_context=context,
        )

    if is_mutation_path and content_policy_decision == "blocked" and rating_locked:
        summary = content_policy_summary or "Decision: block - content policy is incompatible with the locked project rating."
        return AutonomousDecision(
            decision="block",
            decision_reason="content_policy_blocked",
            decision_summary=summary,
            auto_execute=False,
            approval_required=False,
            sandbox_first=False,
            review_required=False,
            blocked=True,
            missing_evidence=evidence_gaps,
            content_policy_block=True,
            capability_supported=capability_supported,
            promotion_basis=None,
            fail_closed_reason="Locked rating profile blocks this task.",
            runtime_context=context,
        )

    if is_mutation_path and content_policy_decision == "requires_review":
        summary = content_policy_summary or "Decision: require_review - task exceeds the current unlocked rating target."
        return AutonomousDecision(
            decision="require_review",
            decision_reason="content_policy_review_required",
            decision_summary=summary,
            auto_execute=False,
            approval_required=True,
            sandbox_first=False,
            review_required=True,
            blocked=False,
            missing_evidence=evidence_gaps,
            content_policy_block=False,
            capability_supported=capability_supported,
            promotion_basis=None,
            fail_closed_reason=None,
            runtime_context=context,
        )

    if is_mutation_path and intelligence_execution_decision == "auto_execute" and eligible_for_auto:
        summary = intelligence_summary or "Decision: auto_execute - capability is proven, compatible, and auto-eligible."
        return AutonomousDecision(
            decision="auto_execute",
            decision_reason="promotion_eligible",
            decision_summary=summary,
            auto_execute=True,
            approval_required=False,
            sandbox_first=False,
            review_required=False,
            blocked=False,
            missing_evidence=evidence_gaps,
            content_policy_block=False,
            capability_supported=capability_supported,
            promotion_basis=auto_execution_reason,
            fail_closed_reason=None,
            runtime_context=context,
        )

    if is_mutation_path and (intelligence_execution_decision == "sandbox_first" or not capability_supported or bool(evidence_gaps)):
        summary = intelligence_summary or "Decision: sandbox_first - insufficient proof for real-target execution."
        return AutonomousDecision(
            decision="sandbox_first",
            decision_reason="insufficient_evidence",
            decision_summary=summary,
            auto_execute=False,
            approval_required=True,
            sandbox_first=True,
            review_required=False,
            blocked=False,
            missing_evidence=evidence_gaps,
            content_policy_block=False,
            capability_supported=capability_supported,
            promotion_basis=None,
            fail_closed_reason="Mutation path is fail-closed until stronger evidence exists.",
            runtime_context=context,
        )

    if is_mutation_path and (intelligence_execution_decision == "approval_required" or approval_required_by_capability):
        summary = intelligence_summary or "Decision: require_approval - capability is supported but not auto-eligible."
        return AutonomousDecision(
            decision="require_approval",
            decision_reason="approval_gated",
            decision_summary=summary,
            auto_execute=False,
            approval_required=True,
            sandbox_first=False,
            review_required=False,
            blocked=False,
            missing_evidence=evidence_gaps,
            content_policy_block=False,
            capability_supported=capability_supported,
            promotion_basis=None,
            fail_closed_reason=None,
            runtime_context=context,
        )

    summary = "Decision: auto_execute - bounded non-mutation path may proceed without operator approval."
    if resolved_intent != "inspect":
        summary = intelligence_summary or summary
    return AutonomousDecision(
        decision="auto_execute",
        decision_reason="bounded_non_mutation",
        decision_summary=summary,
        auto_execute=True,
        approval_required=False,
        sandbox_first=False,
        review_required=False,
        blocked=False,
        missing_evidence=evidence_gaps,
        content_policy_block=False,
        capability_supported=capability_supported,
        promotion_basis=None,
        fail_closed_reason=None,
        runtime_context=context,
    )


__all__ = ["AutonomousDecision", "DecisionRuntimeContext", "evaluate_autonomous_decision"]