from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.planner_stub import PlannerAgentStub
from orchestrator.prompt_gateway_shim import PromptGatewayShim, PromptGatewayShimConfig
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.request_schema_loader import validate_request_payload
from orchestrator.task_graph_emitter import emit_task_graph
from orchestrator.utils import safe_write_text, write_json


PROMPT_TEXT = """AI-E,

Generate a minimal playable FPS sandbox arena for the BABYLON project.

Requirements:

Scene name: MinimalPlayableArena
Arena type: square sandbox arena
Player spawn: center
Enemy spawns: 3 zombie spawn points
Player loadout: Combat Pistol

Execution rules:

1. produce a task graph
2. do not execute tools
3. generate a structured operator report
"""

REQUEST_ID = "REQ_AIE_FIRST_PROMPT_TEST"
SESSION_ID = "SESSION_AIE_FIRST_PROMPT_TEST"
CREATED_AT = "2026-03-15T00:00:00Z"
REPORT_TIMESTAMP = "2026-03-15T00:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_first_prompt_test"
EXPECTED_TASK_TYPES = [
    "request_analysis",
    "task_graph_emission",
    "report_contract_preparation",
]


@dataclass(frozen=True)
class PromptLoopArtifacts:
    output_dir: Path
    prompt_path: Path
    task_graph_path: Path
    operator_report_path: Path


def run_first_prompt_test(output_dir: Path | None = None) -> PromptLoopArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    gateway = PromptGatewayShim(
        PromptGatewayShimConfig(
            request_id=REQUEST_ID,
            session_id=SESSION_ID,
            channel="cli_chat",
            received_at=CREATED_AT,
            intent="create_sandbox",
            context={
                "project": "BABYLON VER 2",
                "scene_name": "MinimalPlayableArena",
                "arena_type": "square sandbox arena",
                "player_spawn": "center",
                "enemy_spawns": 3,
                "player_loadout": "Combat Pistol",
            },
            constraints=[
                "Do not execute tools.",
                "Do not execute runner.py.",
                "Do not modify gameplay systems.",
            ],
            requested_artifacts=[
                "task_graph.json",
                "operator_report.md",
                "prompt.txt",
            ],
            metadata={"source": "architecture_test_harness"},
        )
    )
    planner = PlannerAgentStub()

    envelope = gateway.receive_prompt(PROMPT_TEXT, gateway.session_metadata)
    normalized_request = gateway.normalize_request(envelope)
    raw_payload = gateway.forward_to_schema_loader(normalized_request)
    validated_request = validate_request_payload(raw_payload)
    planner_result = planner.plan(validated_request)
    explicit_graph = emit_task_graph(validated_request)

    planner_graph_payload = planner_result.task_graph.to_payload()
    explicit_graph_payload = explicit_graph.to_payload()
    if planner_graph_payload != explicit_graph_payload:
        raise ValueError("planner stub and task graph emitter produced different task graphs")

    task_types = [task["task_type"] for task in planner_graph_payload["tasks"]]
    if task_types != EXPECTED_TASK_TYPES:
        raise ValueError(f"unexpected scaffold task types: {task_types}")

    report_text = format_operator_report(
        summary="Architecture-only planning loop completed without runtime execution.",
        facts=[
            f"Request ID: {validated_request.request_id}",
            f"Request type: {planner_result.request_type}",
            f"Task graph tasks: {', '.join(task_types)}",
        ],
        assumptions=[
            "The planning loop remains architecture-only and does not execute external tools.",
            "The prompt gateway shim is a deterministic test harness, not a live chat adapter.",
        ],
        recommendations=[
            "Keep runner integration disabled until interface handoff rules are approved.",
            "Use this harness only for scaffold validation and deterministic artifact generation.",
        ],
        timestamp=REPORT_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    prompt_path = destination / "prompt.txt"
    task_graph_path = destination / "task_graph.json"
    operator_report_path = destination / "operator_report.md"
    safe_write_text(prompt_path, PROMPT_TEXT)
    write_json(task_graph_path, planner_graph_payload)
    safe_write_text(operator_report_path, report_text)

    return PromptLoopArtifacts(
        output_dir=destination,
        prompt_path=prompt_path,
        task_graph_path=task_graph_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_first_prompt_test()
    print(f"prompt: {artifacts.prompt_path}")
    print(f"task_graph: {artifacts.task_graph_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()