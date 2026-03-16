from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol


ReadOnlyResponseState = Literal[
    "read_requested",
    "read_completed",
    "read_blocked",
    "read_denied",
    "read_failed",
    "read_partial",
]


@dataclass(frozen=True)
class ReadScopeContract:
    """Explicit bounded scope for a read-only local adapter."""

    allowed_roots: List[str] = field(default_factory=list)
    allowed_extensions: List[str] = field(default_factory=list)
    max_file_count: int = 0
    max_total_bytes: int = 0
    recursive_allowed: bool = False
    hidden_files_allowed: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "allowed_roots": list(self.allowed_roots),
            "allowed_extensions": list(self.allowed_extensions),
            "max_file_count": self.max_file_count,
            "max_total_bytes": self.max_total_bytes,
            "recursive_allowed": self.recursive_allowed,
            "hidden_files_allowed": self.hidden_files_allowed,
        }


@dataclass(frozen=True)
class ReadOnlyAdapterRequestContract:
    """Contract for a bounded read-only adapter request."""

    adapter_request_id: str
    session_id: str
    permit_id: str
    authorization_id: str
    request_id: str
    execution_id: str
    task_id: str
    adapter_id: str
    target_paths: List[str] = field(default_factory=list)
    read_scope: ReadScopeContract = field(default_factory=ReadScopeContract)
    dry_run: bool = True
    requested_at: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "adapter_request_id": self.adapter_request_id,
            "session_id": self.session_id,
            "permit_id": self.permit_id,
            "authorization_id": self.authorization_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "adapter_id": self.adapter_id,
            "target_paths": list(self.target_paths),
            "read_scope": self.read_scope.to_payload(),
            "dry_run": self.dry_run,
            "requested_at": self.requested_at,
        }


@dataclass(frozen=True)
class ReadOnlyArtifactContract:
    """Contract for deterministic read-only inspection artifacts."""

    artifact_id: str
    artifact_type: str
    source_path: str
    summary: str
    captured_at: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "source_path": self.source_path,
            "summary": self.summary,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True)
class ReadOnlyAdapterResponseContract:
    """Contract for deterministic read-only adapter responses."""

    adapter_request_id: str
    adapter_id: str
    response_state: ReadOnlyResponseState
    read_completed: bool
    inspected_paths: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    artifacts_generated: List[str] = field(default_factory=list)
    completed_at: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "adapter_request_id": self.adapter_request_id,
            "adapter_id": self.adapter_id,
            "response_state": self.response_state,
            "read_completed": self.read_completed,
            "inspected_paths": list(self.inspected_paths),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "artifacts_generated": list(self.artifacts_generated),
            "completed_at": self.completed_at,
        }


def read_only_response_states() -> list[str]:
    return [
        "read_requested",
        "read_completed",
        "read_blocked",
        "read_denied",
        "read_failed",
        "read_partial",
    ]


class ReadOnlyLiveAdapterInterface(Protocol):
    """Architecture-only boundary for a bounded non-mutating local adapter."""

    def build_request(self, task_id: str) -> ReadOnlyAdapterRequestContract:
        ...

    def inspect(self, request: ReadOnlyAdapterRequestContract) -> ReadOnlyAdapterResponseContract:
        ...


__all__ = [
    "ReadOnlyAdapterRequestContract",
    "ReadOnlyAdapterResponseContract",
    "ReadOnlyArtifactContract",
    "ReadOnlyLiveAdapterInterface",
    "ReadOnlyResponseState",
    "ReadScopeContract",
    "read_only_response_states",
]