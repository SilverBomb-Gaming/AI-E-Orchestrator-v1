from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol


@dataclass(frozen=True)
class ArtifactPersistenceRegistration:
    """Contract for registering an artifact for future persistence."""

    artifact_id: str
    artifact_type: str
    artifact_source: str
    produced_by_task: str
    produced_by_adapter: str
    artifact_path: str
    artifact_timestamp: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "artifact_source": self.artifact_source,
            "produced_by_task": self.produced_by_task,
            "produced_by_adapter": self.produced_by_adapter,
            "artifact_path": self.artifact_path,
            "artifact_timestamp": self.artifact_timestamp,
        }


@dataclass(frozen=True)
class ArtifactPersistenceResult:
    """Contract for the future persistence result of an artifact."""

    artifact_id: str
    stored: bool
    storage_location: str
    validation_attached: bool
    retention_policy: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "stored": self.stored,
            "storage_location": self.storage_location,
            "validation_attached": self.validation_attached,
            "retention_policy": self.retention_policy,
        }


class ArtifactPersistenceInterface(Protocol):
    """Architecture-only boundary for future artifact persistence.

    This layer defines artifact registration and persistence result contracts
    without interacting with the filesystem.
    """

    def register_artifact(self, registration: ArtifactPersistenceRegistration) -> Dict[str, Any]:
        ...

    def persist_artifact(self, artifact_id: str) -> ArtifactPersistenceResult:
        ...


__all__ = [
    "ArtifactPersistenceInterface",
    "ArtifactPersistenceRegistration",
    "ArtifactPersistenceResult",
]