from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Protocol


ArtifactCategory = Literal[
    "logs",
    "generated_assets",
    "validation_results",
    "screenshots",
    "structured_reports",
]


@dataclass(frozen=True)
class ArtifactDescriptor:
    """Contract for a stored artifact recorded by category."""

    artifact_id: str
    request_id: str
    task_id: str
    category: ArtifactCategory
    relative_path: str
    created_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactStoreSummary:
    """Contract for grouped artifact visibility without store implementation."""

    request_id: str
    artifact_counts: Dict[str, int] = field(default_factory=dict)
    categories: List[ArtifactCategory] = field(default_factory=list)


class ArtifactStoreInterface(Protocol):
    """Placeholder interface for future artifact persistence.

    Expected artifact categories include logs, generated assets, validation
    results, screenshots, and structured reports.

    Responsibilities:
    - store logs
    - store generated assets
    - store validation results
    - store structured reports

    This module defines storage contracts only and does not perform any
    filesystem writes.
    """

    def record_artifact(self, descriptor: ArtifactDescriptor) -> Mapping[str, Any]:
        ...

    def list_artifacts(self, request_id: str) -> List[ArtifactDescriptor]:
        ...

    def summarize_request(self, request_id: str) -> ArtifactStoreSummary:
        ...


__all__ = [
    "ArtifactCategory",
    "ArtifactDescriptor",
    "ArtifactStoreInterface",
    "ArtifactStoreSummary",
]