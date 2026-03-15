from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Protocol

from .architecture_blueprint import TaskContract


@dataclass(frozen=True)
class AgentExecutionRequest:
    """Contract for a future tool-agent execution handoff."""

    agent_name: str
    task: TaskContract
    allowed_tools: List[str] = field(default_factory=list)
    working_directory: str = ""
    policy_context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentExecutionResult:
    """Contract for the non-runtime result shape expected from future agents."""

    agent_name: str
    task_id: str
    status: str
    artifact_paths: List[str] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class AgentExecutionInterface(Protocol):
    """Placeholder interface for future tool-facing agents.

    Candidate agents include Unity, Blender, Git, Testing, and asset-pipeline
    roles.

    Responsibilities:
    - execute tool task
    - validate execution results
    - return artifacts

    This module is architecture-only and does not execute any tools.
    """

    def describe_capabilities(self) -> Mapping[str, Any]:
        ...

    def prepare_execution(self, task: TaskContract) -> AgentExecutionRequest:
        ...

    def validate_result(self, result: AgentExecutionResult) -> Mapping[str, Any]:
        ...

    def execute_task(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        ...


__all__ = ["AgentExecutionInterface", "AgentExecutionRequest", "AgentExecutionResult"]