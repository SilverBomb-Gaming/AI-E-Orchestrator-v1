from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

from .architecture_blueprint import ConversationalRequest, TaskGraph
from .request_schema_loader import load_request_file, validate_request_payload
from .task_graph_emitter import emit_task_graph, infer_request_type


@dataclass(frozen=True)
class PlannerAgentResult:
    request: ConversationalRequest
    request_type: str
    task_graph: TaskGraph

    def to_payload(self) -> Dict[str, Any]:
        return {
            "request": self.request.to_payload(),
            "request_type": self.request_type,
            "task_graph": self.task_graph.to_payload(),
        }


class PlannerAgentStub:
    """Non-runtime planner stub that emits contracts only.

    This class does not execute tasks, mutate queues, invoke providers,
    or interact with the live runner path.
    """

    def plan_from_payload(self, payload: Dict[str, Any]) -> PlannerAgentResult:
        request = validate_request_payload(payload)
        return self.plan(request)

    def plan_from_file(self, path: Path) -> PlannerAgentResult:
        request = load_request_file(path)
        return self.plan(request)

    def plan(self, request: ConversationalRequest) -> PlannerAgentResult:
        request_type = infer_request_type(request)
        task_graph = emit_task_graph(request)
        return PlannerAgentResult(request=request, request_type=request_type, task_graph=task_graph)


__all__ = ["PlannerAgentResult", "PlannerAgentStub"]