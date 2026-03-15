from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from aie_prompt_test import PROMPT_TEXT
from orchestrator.execution_bridge_interface import (
    ArtifactRegistrationContract,
    ExecutionInputContract,
    ExecutionResultContract,
    ReportHandoffContract,
    ValidationAttachmentContract,
)
from orchestrator.planner_stub import PlannerAgentStub
from orchestrator.prompt_gateway_shim import PromptGatewayShim, PromptGatewayShimConfig
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.request_schema_loader import validate_request_payload
from orchestrator.utils import safe_write_text, write_json


REQUEST_ID = "REQ_AIE_DRY_RUN_EXECUTION_TEST"
SESSION_ID = "SESSION_AIE_DRY_RUN_EXECUTION_TEST"
CREATED_AT = "2026-03-15T00:00:00Z"
SIMULATION_TIMESTAMP = "2026-03-15T00:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_dry_run_execution_test"


@dataclass(frozen=True)
class DryRunExecutionArtifacts:
    output_dir: Path
    prompt_path: Path
    task_graph_path: Path
    execution_results_path: Path
    artifact_registry_path: Path
    validation_results_path: Path
    operator_report_path: Path


def run_dry_run_execution_test(output_dir: Path | None = None) -> DryRunExecutionArtifacts:
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
                "prompt.txt",
                "task_graph.json",
                "execution_results.json",
                "artifact_registry.json",
                "validation_results.json",
                "operator_report.md",
            ],
            metadata={"source": "dry_run_execution_harness"},
        )
    )
    planner = PlannerAgentStub()

    envelope = gateway.receive_prompt(PROMPT_TEXT, gateway.session_metadata)
    normalized_request = gateway.normalize_request(envelope)
    validated_request = validate_request_payload(gateway.forward_to_schema_loader(normalized_request))
    planner_result = planner.plan(validated_request)
    task_graph_payload = planner_result.task_graph.to_payload()

    execution_inputs = [_build_execution_input(task) for task in planner_result.task_graph.tasks]
    execution_results = [_simulate_execution_result(contract, destination) for contract in execution_inputs]
    artifact_registry = [artifact.to_payload() for result in execution_results for artifact in result.artifacts]
    validation_results = [
        {
            "execution_id": result.execution_id,
            "validation": result.validation.to_payload(),
        }
        for result in execution_results
    ]

    if any(result.status != "simulated_success" for result in execution_results):
        raise ValueError("dry-run loop produced a non-simulated execution status")

    report_handoff = _build_report_handoff(planner_result.request_type, execution_results)
    report_payload = report_handoff.to_payload()
    report_text = format_operator_report(
        summary=report_payload["operator_summary"],
        facts=report_payload["facts_payload"],
        assumptions=report_payload["assumptions_payload"],
        recommendations=report_payload["recommendations_payload"],
        timestamp=report_payload["timestamp"],
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    prompt_path = destination / "prompt.txt"
    task_graph_path = destination / "task_graph.json"
    execution_results_path = destination / "execution_results.json"
    artifact_registry_path = destination / "artifact_registry.json"
    validation_results_path = destination / "validation_results.json"
    operator_report_path = destination / "operator_report.md"

    safe_write_text(prompt_path, PROMPT_TEXT)
    write_json(task_graph_path, task_graph_payload)
    write_json(execution_results_path, {"execution_results": [result.to_payload() for result in execution_results]})
    write_json(artifact_registry_path, {"artifacts": artifact_registry})
    write_json(validation_results_path, {"validation_results": validation_results})
    safe_write_text(operator_report_path, report_text)

    return DryRunExecutionArtifacts(
        output_dir=destination,
        prompt_path=prompt_path,
        task_graph_path=task_graph_path,
        execution_results_path=execution_results_path,
        artifact_registry_path=artifact_registry_path,
        validation_results_path=validation_results_path,
        operator_report_path=operator_report_path,
    )


def _build_execution_input(task) -> ExecutionInputContract:
    return ExecutionInputContract(
        execution_id=f"EXEC_{task.task_id}",
        request_id=task.request_id,
        task_id=task.task_id,
        task_type=task.task_type,
        objective=task.objective,
        dependencies=list(task.dependencies),
        policy_level=task.policy_level,
        expected_outputs=list(task.expected_outputs),
        validation_placeholders=["validation_status", "validation_notes", "blocking_issues"],
        runtime_target_placeholder="dry_run_simulation",
        dry_run=True,
    )


def _simulate_execution_result(contract: ExecutionInputContract, destination: Path) -> ExecutionResultContract:
    artifact = ArtifactRegistrationContract(
        artifact_id=f"ART_{contract.task_id}_001",
        artifact_type="simulated_output",
        path=str((destination / f"{contract.task_id.lower()}_artifact.json").as_posix()),
        produced_by=contract.task_id,
        related_task_id=contract.task_id,
        summary=f"Simulated artifact registration for {contract.task_type}.",
    )
    validation = ValidationAttachmentContract(
        validation_status="passed",
        validation_notes=[f"Dry-run simulation completed for {contract.task_type}."],
        blocking_issues=[],
        retry_recommended=False,
    )
    return ExecutionResultContract(
        execution_id=contract.execution_id,
        status="simulated_success",
        artifacts=[artifact],
        validation=validation,
        warnings=["Dry-run scaffold only; no runtime adapter invoked."],
        errors=[],
        started_at=SIMULATION_TIMESTAMP,
        finished_at=SIMULATION_TIMESTAMP,
    )


def _build_report_handoff(request_type: str, execution_results: List[ExecutionResultContract]) -> ReportHandoffContract:
    task_ids = [result.execution_id for result in execution_results]
    return ReportHandoffContract(
        operator_summary="Dry-run execution loop completed with simulated results only.",
        facts_payload=[
            f"Request type: {request_type}",
            f"Execution results: {len(execution_results)} simulated_success entries.",
            f"Execution IDs: {', '.join(task_ids)}",
        ],
        assumptions_payload=[
            "The execution bridge remains architecture-only and does not execute tasks.",
            "Artifact and validation records are deterministic dry-run simulations.",
        ],
        recommendations_payload=[
            "Keep runner integration disabled until runtime handoff rules are approved.",
            "Use dry-run results only for contract validation, not execution evidence.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )


def main() -> None:
    artifacts = run_dry_run_execution_test()
    print(f"prompt: {artifacts.prompt_path}")
    print(f"task_graph: {artifacts.task_graph_path}")
    print(f"execution_results: {artifacts.execution_results_path}")
    print(f"artifact_registry: {artifacts.artifact_registry_path}")
    print(f"validation_results: {artifacts.validation_results_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()