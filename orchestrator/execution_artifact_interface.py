from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Protocol


ArtifactClass = Literal["report", "log", "validation", "evidence", "intermediate", "discardable", "retained_output"]


@dataclass(frozen=True)
class ExecutionArtifactRecordContract:
    """Contract for a deterministic execution artifact record."""

    artifact_id: str
    session_id: str
    execution_id: str
    task_id: str
    artifact_type: str
    artifact_source: str
    artifact_path: str
    produced_by_adapter: str
    produced_timestamp: str
    retention_class: ArtifactClass
    cleanup_required: bool
    summary: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "artifact_type": self.artifact_type,
            "artifact_source": self.artifact_source,
            "artifact_path": self.artifact_path,
            "produced_by_adapter": self.produced_by_adapter,
            "produced_timestamp": self.produced_timestamp,
            "retention_class": self.retention_class,
            "cleanup_required": self.cleanup_required,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ArtifactRetentionRecordContract:
    """Contract for deterministic retention and cleanup handling."""

    artifact_id: str
    retained: bool
    retention_reason: str
    retention_policy: str
    expires_at: str
    cleanup_required: bool
    cleanup_reason: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "retained": self.retained,
            "retention_reason": self.retention_reason,
            "retention_policy": self.retention_policy,
            "expires_at": self.expires_at,
            "cleanup_required": self.cleanup_required,
            "cleanup_reason": self.cleanup_reason,
        }


def artifact_classes() -> list[str]:
    return ["report", "log", "validation", "evidence", "intermediate", "discardable", "retained_output"]


class ExecutionArtifactInterface(Protocol):
    """Architecture-only boundary for summarizing execution artifacts."""

    def record_artifact(self, artifact_id: str) -> ExecutionArtifactRecordContract:
        ...

    def classify_retention(self, artifact_id: str) -> ArtifactRetentionRecordContract:
        ...


__all__ = [
    "ArtifactClass",
    "ArtifactRetentionRecordContract",
    "ExecutionArtifactInterface",
    "ExecutionArtifactRecordContract",
    "artifact_classes",
]