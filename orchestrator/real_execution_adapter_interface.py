from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Protocol

from .execution_bridge_interface import ArtifactRegistrationContract


AdapterResponseStatus = Literal["planned", "approval_required", "ready", "blocked", "failed"]


@dataclass(frozen=True)
class ApprovalBoundaryContract:
    """Explicit approval boundary for future live execution adapters."""

    approval_required: bool
    approval_reason: str = ""
    blocked_until_approved: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "approval_required": self.approval_required,
            "approval_reason": self.approval_reason,
            "blocked_until_approved": self.blocked_until_approved,
        }


@dataclass(frozen=True)
class AdapterCapabilityDeclaration:
    """Declared capabilities and limits for a future live execution adapter."""

    adapter_id: str
    adapter_type: str
    supported_task_types: List[str] = field(default_factory=list)
    supported_runtime_targets: List[str] = field(default_factory=list)
    allowed_actions: List[str] = field(default_factory=list)
    denied_actions: List[str] = field(default_factory=list)
    requires_approval_for: List[str] = field(default_factory=list)
    dry_run_supported: bool = True
    live_run_supported: bool = False
    notes: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_type": self.adapter_type,
            "supported_task_types": list(self.supported_task_types),
            "supported_runtime_targets": list(self.supported_runtime_targets),
            "allowed_actions": list(self.allowed_actions),
            "denied_actions": list(self.denied_actions),
            "requires_approval_for": list(self.requires_approval_for),
            "dry_run_supported": self.dry_run_supported,
            "live_run_supported": self.live_run_supported,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ExecutionRequestHandoff:
    """Bounded handoff from execution unit to a future real adapter."""

    execution_id: str
    request_id: str
    task_id: str
    adapter_target: str
    task_type: str
    objective: str
    policy_level: str
    dry_run: bool = True
    approval_boundary: ApprovalBoundaryContract = field(
        default_factory=lambda: ApprovalBoundaryContract(approval_required=False)
    )
    expected_outputs: List[str] = field(default_factory=list)
    validation_requirements: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "adapter_target": self.adapter_target,
            "task_type": self.task_type,
            "objective": self.objective,
            "policy_level": self.policy_level,
            "dry_run": self.dry_run,
            "approval_boundary": self.approval_boundary.to_payload(),
            "expected_outputs": list(self.expected_outputs),
            "validation_requirements": list(self.validation_requirements),
        }


@dataclass(frozen=True)
class FailureClassificationContract:
    """Failure classification contract for future recovery logic."""

    failure_type: str
    failure_scope: str
    retry_recommended: bool = False
    retry_reason: str = ""
    escalation_required: bool = False
    blocking: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "failure_type": self.failure_type,
            "failure_scope": self.failure_scope,
            "retry_recommended": self.retry_recommended,
            "retry_reason": self.retry_reason,
            "escalation_required": self.escalation_required,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class ExecutionResponseContract:
    """Bounded response shape from a future real execution adapter."""

    execution_id: str
    adapter_id: str
    status: AdapterResponseStatus
    artifacts: List[ArtifactRegistrationContract] = field(default_factory=list)
    validation_status: str = "pending"
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    operator_attention_required: bool = False
    failure_classification: FailureClassificationContract | None = None
    approval_boundary: ApprovalBoundaryContract = field(
        default_factory=lambda: ApprovalBoundaryContract(approval_required=False)
    )

    def to_payload(self) -> Dict[str, Any]:
        payload = {
            "execution_id": self.execution_id,
            "adapter_id": self.adapter_id,
            "status": self.status,
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
            "validation_status": self.validation_status,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "operator_attention_required": self.operator_attention_required,
            "approval_boundary": self.approval_boundary.to_payload(),
        }
        if self.failure_classification is not None:
            payload["failure_classification"] = self.failure_classification.to_payload()
        return payload


class RealExecutionAdapterInterface(Protocol):
    """Architecture-only future boundary for bounded live execution adapters.

    This contract layer defines how adapters would declare capabilities, accept
    bounded execution requests, and report structured responses. It does not
    execute any actions or integrate with runner.py.
    """

    def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        ...

    def accept_execution_request(self, request: ExecutionRequestHandoff) -> Mapping[str, Any]:
        ...

    def report_execution_response(self, execution_id: str) -> ExecutionResponseContract:
        ...


__all__ = [
    "AdapterCapabilityDeclaration",
    "AdapterResponseStatus",
    "ApprovalBoundaryContract",
    "ExecutionRequestHandoff",
    "ExecutionResponseContract",
    "FailureClassificationContract",
    "RealExecutionAdapterInterface",
]