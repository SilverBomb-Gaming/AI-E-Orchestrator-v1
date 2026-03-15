from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Protocol

from .architecture_blueprint import TaskContract, required_response_sections


ExecutionStatus = Literal["planned", "ready", "completed", "failed", "blocked", "simulated_success"]
ValidationStatus = Literal["pending", "passed", "failed", "needs_review"]


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    return value


@dataclass(frozen=True)
class ExecutionInputContract:
    """Normalized executable unit derived from a task graph node.

    This contract is scaffold-only and does not execute the task.
    """

    execution_id: str
    request_id: str
    task_id: str
    task_type: str
    objective: str
    dependencies: List[str] = field(default_factory=list)
    policy_level: str = "architecture_only"
    expected_outputs: List[str] = field(default_factory=list)
    validation_placeholders: List[str] = field(default_factory=list)
    runtime_target_placeholder: str = "unassigned"
    dry_run: bool = True

    def to_payload(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "objective": self.objective,
            "dependencies": sorted(self.dependencies),
            "policy_level": self.policy_level,
            "expected_outputs": list(self.expected_outputs),
            "validation_placeholders": list(self.validation_placeholders),
            "runtime_target_placeholder": self.runtime_target_placeholder,
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True)
class ArtifactRegistrationContract:
    """Description of an artifact for future storage and reporting."""

    artifact_id: str
    artifact_type: str
    path: str
    produced_by: str
    related_task_id: str
    summary: str

    def to_payload(self) -> Dict[str, str]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "produced_by": self.produced_by,
            "related_task_id": self.related_task_id,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ValidationAttachmentContract:
    """Validation outcomes connected to an execution result."""

    validation_status: ValidationStatus
    validation_notes: List[str] = field(default_factory=list)
    blocking_issues: List[str] = field(default_factory=list)
    retry_recommended: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "validation_status": self.validation_status,
            "validation_notes": list(self.validation_notes),
            "blocking_issues": list(self.blocking_issues),
            "retry_recommended": self.retry_recommended,
        }


@dataclass(frozen=True)
class ExecutionResultContract:
    """Bounded result contract for a future tool or agent layer."""

    execution_id: str
    status: ExecutionStatus
    artifacts: List[ArtifactRegistrationContract] = field(default_factory=list)
    validation: ValidationAttachmentContract = field(
        default_factory=lambda: ValidationAttachmentContract(validation_status="pending")
    )
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
            "validation": self.validation.to_payload(),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass(frozen=True)
class ReportHandoffContract:
    """Report-ready payload derived from a bounded execution result."""

    operator_summary: str
    facts_payload: List[str] = field(default_factory=list)
    assumptions_payload: List[str] = field(default_factory=list)
    recommendations_payload: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "operator_summary": self.operator_summary,
            "facts_payload": list(self.facts_payload),
            "assumptions_payload": list(self.assumptions_payload),
            "recommendations_payload": list(self.recommendations_payload),
            "timestamp": self.timestamp,
            "required_report_sections": required_response_sections(),
        }


class ExecutionBridgeInterface(Protocol):
    """Architecture-only bridge between task graphs and future execution layers.

    This bridge defines the bounded handoff contracts from task graph nodes to
    future agent execution, artifact registration, validation attachment, and
    report preparation. It does not execute tasks or interact with runner.py.
    """

    def build_execution_input(self, task: TaskContract) -> ExecutionInputContract:
        ...

    def collect_execution_result(self, execution_id: str) -> ExecutionResultContract:
        ...

    def prepare_report_handoff(self, result: ExecutionResultContract) -> ReportHandoffContract:
        ...


__all__ = [
    "ArtifactRegistrationContract",
    "ExecutionBridgeInterface",
    "ExecutionInputContract",
    "ExecutionResultContract",
    "ExecutionStatus",
    "ReportHandoffContract",
    "ValidationAttachmentContract",
    "ValidationStatus",
]