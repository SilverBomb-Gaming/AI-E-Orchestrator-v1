from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol

from .execution_closeout_interface import CloseoutState


HandoffPriorityLevel = Literal["low", "medium", "high", "urgent"]


@dataclass(frozen=True)
class OperatorHandoffReviewRequestContract:
    """Contract for requesting deterministic operator handoff review packaging."""

    handoff_id: str
    session_id: str
    closeout_id: str
    request_id: str
    execution_id: str
    task_id: str
    final_outcome: str
    closeout_state: CloseoutState
    operator_attention_required: bool
    review_requested_at: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "session_id": self.session_id,
            "closeout_id": self.closeout_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "final_outcome": self.final_outcome,
            "closeout_state": self.closeout_state,
            "operator_attention_required": self.operator_attention_required,
            "review_requested_at": self.review_requested_at,
        }


@dataclass(frozen=True)
class OperatorHandoffReviewSummaryContract:
    """Contract for deterministic operator handoff summary content."""

    handoff_id: str
    summary_title: str
    summary_text: str
    key_facts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommended_next_actions: List[str] = field(default_factory=list)
    priority_level: HandoffPriorityLevel = "low"
    requires_operator_decision: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "summary_title": self.summary_title,
            "summary_text": self.summary_text,
            "key_facts": list(self.key_facts),
            "warnings": list(self.warnings),
            "recommended_next_actions": list(self.recommended_next_actions),
            "priority_level": self.priority_level,
            "requires_operator_decision": self.requires_operator_decision,
        }


@dataclass(frozen=True)
class OperatorHandoffReviewTargetsContract:
    """Contract for deterministic review target packaging."""

    handoff_id: str
    reviewable_items: List[str] = field(default_factory=list)
    approval_items: List[str] = field(default_factory=list)
    blocked_items: List[str] = field(default_factory=list)
    retry_candidates: List[str] = field(default_factory=list)
    archival_candidates: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "reviewable_items": list(self.reviewable_items),
            "approval_items": list(self.approval_items),
            "blocked_items": list(self.blocked_items),
            "retry_candidates": list(self.retry_candidates),
            "archival_candidates": list(self.archival_candidates),
        }


def handoff_priority_levels() -> list[str]:
    return ["low", "medium", "high", "urgent"]


def determine_handoff_priority(request: OperatorHandoffReviewRequestContract) -> HandoffPriorityLevel:
    if request.closeout_state in {"closed_failed", "closed_expired"}:
        return "urgent"
    if request.closeout_state in {"closed_blocked", "closed_cancelled"}:
        return "high"
    if request.operator_attention_required or request.closeout_state == "closed_with_warnings":
        return "medium"
    return "low"


def evaluate_operator_handoff_review(
    request: OperatorHandoffReviewRequestContract,
    *,
    retained_artifacts: List[str],
    discarded_artifacts: List[str],
) -> tuple[OperatorHandoffReviewSummaryContract, OperatorHandoffReviewTargetsContract]:
    priority = determine_handoff_priority(request)
    warnings: List[str] = []
    recommended_next_actions: List[str] = []
    reviewable_items = [
        f"closeout:{request.closeout_id}",
        f"session:{request.session_id}",
    ]
    approval_items: List[str] = []
    blocked_items: List[str] = []
    retry_candidates: List[str] = []
    archival_candidates = list(retained_artifacts)
    requires_operator_decision = False

    if request.closeout_state == "closed_successfully":
        approval_items.append(f"archive:{request.handoff_id}")
        recommended_next_actions.append("Archive the deterministic closeout package for morning review.")
    elif request.closeout_state == "closed_with_warnings":
        warnings.append("Closeout completed with warnings and needs operator review.")
        recommended_next_actions.append("Review warning details before archiving the handoff package.")
        requires_operator_decision = True
    elif request.closeout_state == "closed_blocked":
        warnings.append("The session was blocked before a clean closeout path was achieved.")
        blocked_items.append(f"blocked:{request.execution_id}")
        recommended_next_actions.append("Review the blocking condition before any future bounded session is considered.")
        requires_operator_decision = True
    elif request.closeout_state in {"closed_failed", "closed_expired"}:
        warnings.append("The session did not finish cleanly and requires escalation-oriented review.")
        retry_candidates.append(f"retry:{request.task_id}")
        reviewable_items.append(f"failure:{request.execution_id}")
        recommended_next_actions.append("Review failure and retry candidates before approving any follow-up work.")
        requires_operator_decision = True
    elif request.closeout_state == "closed_cancelled":
        warnings.append("The session was cancelled and should be reviewed before any restart is considered.")
        blocked_items.append(f"cancelled:{request.session_id}")
        recommended_next_actions.append("Confirm whether cancellation should remain final or move into a new review cycle.")
        requires_operator_decision = True

    if discarded_artifacts:
        warnings.append("Discarded artifacts were summarized and should be reviewed for retention policy compliance.")
        reviewable_items.append("discarded_artifacts")

    if request.operator_attention_required and "Closeout completed with warnings and needs operator review." not in warnings:
        warnings.append("Operator attention is explicitly required by the closeout layer.")
        requires_operator_decision = True

    summary = OperatorHandoffReviewSummaryContract(
        handoff_id=request.handoff_id,
        summary_title=f"Operator handoff review for {request.task_id}",
        summary_text=(
            "Deterministic handoff packaging completed for operator review without any live handoff system or runtime integration."
        ),
        key_facts=[
            f"Final outcome: {request.final_outcome}",
            f"Closeout state: {request.closeout_state}",
            f"Retained artifacts: {len(retained_artifacts)}",
            f"Discarded artifacts: {len(discarded_artifacts)}",
        ],
        warnings=warnings,
        recommended_next_actions=recommended_next_actions,
        priority_level=priority,
        requires_operator_decision=requires_operator_decision,
    )
    targets = OperatorHandoffReviewTargetsContract(
        handoff_id=request.handoff_id,
        reviewable_items=reviewable_items,
        approval_items=approval_items,
        blocked_items=blocked_items,
        retry_candidates=retry_candidates,
        archival_candidates=archival_candidates,
    )
    return summary, targets


class OperatorHandoffReviewInterface(Protocol):
    """Architecture-only boundary for deterministic operator handoff review packaging."""

    def build_handoff_request(self, closeout_id: str) -> OperatorHandoffReviewRequestContract:
        ...

    def prepare_review_package(
        self,
        request: OperatorHandoffReviewRequestContract,
    ) -> tuple[OperatorHandoffReviewSummaryContract, OperatorHandoffReviewTargetsContract]:
        ...


__all__ = [
    "HandoffPriorityLevel",
    "OperatorHandoffReviewInterface",
    "OperatorHandoffReviewRequestContract",
    "OperatorHandoffReviewSummaryContract",
    "OperatorHandoffReviewTargetsContract",
    "determine_handoff_priority",
    "evaluate_operator_handoff_review",
    "handoff_priority_levels",
]