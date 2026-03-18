from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .planner import PlanResult


@dataclass(frozen=True)
class PlanTaskNode:
    task_id: str
    title: str
    task_type: str
    priority: int
    dependencies: List[str]
    target_repo: str
    execution_mode: str
    plan_id: str
    step_index: int

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "task_type": self.task_type,
            "priority": self.priority,
            "dependencies": list(self.dependencies),
            "target_repo": self.target_repo,
            "execution_mode": self.execution_mode,
            "plan_id": self.plan_id,
            "step_index": self.step_index,
        }


@dataclass(frozen=True)
class PlanTaskGraph:
    plan_id: str
    request_id: str
    target_repo: str
    execution_mode: str
    summary_text: str
    nodes: List[PlanTaskNode]

    def to_payload(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "target_repo": self.target_repo,
            "execution_mode": self.execution_mode,
            "summary_text": self.summary_text,
            "nodes": [node.to_payload() for node in self.nodes],
        }


def build_plan_task_graph(plan: PlanResult, *, request_id: str, task_id_prefix: str) -> PlanTaskGraph:
    nodes: List[PlanTaskNode] = []
    previous_task_id: str | None = None
    single_step = len(plan.steps) == 1
    for step in plan.steps:
        task_id = task_id_prefix if single_step else f"{task_id_prefix}__STEP_{step.step_index:02d}"
        dependencies = [previous_task_id] if previous_task_id else []
        nodes.append(
            PlanTaskNode(
                task_id=task_id,
                title=step.title,
                task_type=step.task_type,
                priority=step.priority,
                dependencies=dependencies,
                target_repo=plan.target_repo,
                execution_mode=step.execution_mode,
                plan_id=plan.plan_id,
                step_index=step.step_index,
            )
        )
        previous_task_id = task_id
    return PlanTaskGraph(
        plan_id=plan.plan_id,
        request_id=request_id,
        target_repo=plan.target_repo,
        execution_mode="bounded_read_only",
        summary_text=plan.summary_text(),
        nodes=nodes,
    )


__all__ = ["PlanTaskGraph", "PlanTaskNode", "build_plan_task_graph"]