from __future__ import annotations

from typing import List

from .architecture_blueprint import ConversationalRequest, RetryPolicy, TaskContract, TaskGraph, ValidationRule, required_response_sections
from .utils import slugify


_TASK_GRAPH_PHASE_ID = "PHASE_3"


def infer_request_type(request: ConversationalRequest) -> str:
    intent = request.intent.strip().lower()
    prompt = request.operator_prompt.strip().lower()
    if intent and intent != "unspecified":
        return intent.replace(" ", "_")
    if "report" in prompt:
        return "report_request"
    if "test" in prompt:
        return "test_request"
    if any(token in prompt for token in ("create", "build", "generate")):
        return "create_request"
    return "general_request"


def emit_task_graph(request: ConversationalRequest) -> TaskGraph:
    request_type = infer_request_type(request)
    tasks: List[TaskContract] = [
        TaskContract(
            task_id=_task_id(request.request_id, "intake"),
            request_id=request.request_id,
            task_type="request_analysis",
            objective=f"Normalize and analyze operator request for {request_type}.",
            inputs={
                "channel": request.channel,
                "request_type": request_type,
                "source_prompt": request.operator_prompt,
            },
            expected_outputs=["request_analysis.json", "planning_notes.md"],
            validation_rules=[
                ValidationRule(
                    rule_id="VR_REQUEST_SCOPE_001",
                    description="Planned work must remain inside approved AI-E architecture scope.",
                    evidence=["request.constraints", "request.context"],
                )
            ],
            retry_policy=RetryPolicy(max_attempts=1, retry_on=[]),
            policy_level="architecture_only",
            risk_level="low",
            assigned_agent="PlannerAgent",
            status="planned",
        ),
        TaskContract(
            task_id=_task_id(request.request_id, "graph"),
            request_id=request.request_id,
            task_type="task_graph_emission",
            objective="Emit a deterministic task-graph contract from the validated conversational request.",
            dependencies=[_task_id(request.request_id, "intake")],
            inputs={
                "request_id": request.request_id,
                "phase_id": _TASK_GRAPH_PHASE_ID,
                "requested_artifacts": list(request.requested_artifacts),
            },
            expected_outputs=["task_graph.json"],
            validation_rules=[
                ValidationRule(
                    rule_id="VR_GRAPH_SHAPE_001",
                    description="Task graph must preserve parent request linkage and explicit dependencies.",
                    evidence=["task_graph.request.request_id", "task_graph.dependency_map"],
                )
            ],
            retry_policy=RetryPolicy(max_attempts=1, retry_on=[]),
            policy_level="architecture_only",
            risk_level="low",
            assigned_agent="PlannerAgent",
            status="planned",
        ),
        TaskContract(
            task_id=_task_id(request.request_id, "report"),
            request_id=request.request_id,
            task_type="report_contract_preparation",
            objective="Prepare operator-facing reporting placeholders for the planned work.",
            dependencies=[_task_id(request.request_id, "graph")],
            inputs={
                "required_sections": required_response_sections(),
                "requested_artifacts": list(request.requested_artifacts),
            },
            expected_outputs=["report_contract.json", "report_outline.md"],
            validation_rules=[
                ValidationRule(
                    rule_id="VR_REPORT_ORDER_001",
                    description="Operator-facing reports must preserve canonical section order.",
                    evidence=["report_contract.required_sections"],
                )
            ],
            retry_policy=RetryPolicy(max_attempts=1, retry_on=[]),
            policy_level="report_contract",
            risk_level="low",
            assigned_agent="ReportAgent",
            status="planned",
        ),
    ]
    return TaskGraph(request=request, tasks=tasks)


def _task_id(request_id: str, suffix: str) -> str:
    return f"{slugify(request_id).replace('-', '_').upper()}_{suffix.upper()}"


__all__ = ["emit_task_graph", "infer_request_type"]