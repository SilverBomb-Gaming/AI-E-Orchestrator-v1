from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal

from aie_prompt_test import PROMPT_TEXT
from orchestrator.adapter_registry_interface import AdapterDiscoveryOutput, AdapterRegistrationContract
from orchestrator.adapter_selection_interface import SelectionInputContract, SelectionOutputContract
from orchestrator.approval_gate_interface import (
    ApprovalDecisionContract,
    ApprovalRequestContract,
    GateVerdictContract,
)
from orchestrator.architecture_blueprint import TaskContract
from orchestrator.artifact_persistence_interface import (
    ArtifactPersistenceRegistration,
    ArtifactPersistenceResult,
)
from orchestrator.execution_bridge_interface import ExecutionInputContract, ReportHandoffContract
from orchestrator.planner_stub import PlannerAgentStub
from orchestrator.prompt_gateway_shim import PromptGatewayShim, PromptGatewayShimConfig
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.request_schema_loader import validate_request_payload
from orchestrator.utils import safe_write_text, write_json


ActivationStatus = Literal[
    "ready_for_dry_run",
    "approval_required",
    "blocked",
    "unsupported",
    "simulated_activated",
]

REQUEST_ID = "REQ_AIE_RUNTIME_ACTIVATION_TEST"
SESSION_ID = "SESSION_AIE_RUNTIME_ACTIVATION_TEST"
CREATED_AT = "2026-03-14 20:00:00 -04:00 (Eastern Time — New York)"
SIMULATION_TIMESTAMP = "2026-03-14 20:00:00 -04:00 (Eastern Time — New York)"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_runtime_activation_test"


@dataclass(frozen=True)
class RuntimeActivationArtifacts:
    output_dir: Path
    activation_input_path: Path
    selection_output_path: Path
    approval_verdict_path: Path
    activation_result_path: Path
    artifact_persistence_result_path: Path
    operator_report_path: Path


@dataclass(frozen=True)
class RuntimeActivationResult:
    activation_id: str
    request_id: str
    execution_id: str
    task_id: str
    chosen_adapter_id: str
    candidate_adapters: List[str]
    selection_status: str
    approval_verdict: str
    activation_status: ActivationStatus
    blocked: bool
    blocked_reason: str
    dry_run: bool
    artifacts_registered: int
    report_handoff_ready: bool
    timestamp: str

    def to_payload(self) -> dict[str, object]:
        return {
            "activation_id": self.activation_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "chosen_adapter_id": self.chosen_adapter_id,
            "candidate_adapters": list(self.candidate_adapters),
            "selection_status": self.selection_status,
            "approval_verdict": self.approval_verdict,
            "activation_status": self.activation_status,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "dry_run": self.dry_run,
            "artifacts_registered": self.artifacts_registered,
            "report_handoff_ready": self.report_handoff_ready,
            "timestamp": self.timestamp,
        }


def activation_states() -> List[str]:
    return [
        "ready_for_dry_run",
        "approval_required",
        "blocked",
        "unsupported",
        "simulated_activated",
    ]


def run_runtime_activation_harness(output_dir: Path | None = None) -> RuntimeActivationArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    planner = PlannerAgentStub()
    gateway = PromptGatewayShim(
        PromptGatewayShimConfig(
            request_id=REQUEST_ID,
            session_id=SESSION_ID,
            channel="cli_chat",
            received_at=CREATED_AT,
            intent="runtime_activation_dry_run",
            context={
                "project": "BABYLON VER 2",
                "runtime_target": "unity_editor",
                "activation_mode": "dry_run_only",
            },
            constraints=[
                "Do not execute runner.py.",
                "Do not invoke live adapters.",
                "Do not modify Babylon gameplay systems.",
            ],
            requested_artifacts=[
                "activation_input.json",
                "selection_output.json",
                "approval_verdict.json",
                "activation_result.json",
                "artifact_persistence_result.json",
                "operator_report.md",
            ],
            metadata={"source": "runtime_activation_harness"},
        )
    )

    envelope = gateway.receive_prompt(PROMPT_TEXT, gateway.session_metadata)
    normalized_request = gateway.normalize_request(envelope)
    validated_request = validate_request_payload(gateway.forward_to_schema_loader(normalized_request))
    planner_result = planner.plan(validated_request)
    selected_task = _select_task_for_activation(planner_result.task_graph.tasks)
    execution_input = _build_execution_input(selected_task)
    registrations, discoveries = _build_adapter_registry_snapshot()
    selection_input = _build_selection_input(execution_input)
    selection_output = _build_selection_output(selection_input, discoveries)
    approval_request = _build_approval_request(selection_input, selection_output)
    approval_decision = _build_approval_decision(approval_request)
    gate_verdict = _build_gate_verdict(approval_decision)
    artifact_registrations, persistence_results = _build_artifact_persistence(selection_output, execution_input, destination)
    activation_result = _build_activation_result(
        execution_input=execution_input,
        selection_output=selection_output,
        gate_verdict=gate_verdict,
        artifacts_registered=len(artifact_registrations),
    )
    report_handoff = _build_report_handoff(
        selected_task=selected_task,
        selection_output=selection_output,
        gate_verdict=gate_verdict,
        activation_result=activation_result,
        persistence_results=persistence_results,
    )
    report_text = format_operator_report(
        summary=report_handoff.operator_summary,
        facts=report_handoff.facts_payload,
        assumptions=report_handoff.assumptions_payload,
        recommendations=report_handoff.recommendations_payload,
        timestamp=report_handoff.timestamp,
    )
    validation = validate_operator_report(report_text)
    if not validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(validation.errors))

    activation_input_path = destination / "activation_input.json"
    selection_output_path = destination / "selection_output.json"
    approval_verdict_path = destination / "approval_verdict.json"
    activation_result_path = destination / "activation_result.json"
    artifact_persistence_result_path = destination / "artifact_persistence_result.json"
    operator_report_path = destination / "operator_report.md"

    write_json(
        activation_input_path,
        {
            "task_graph_node": selected_task.to_payload(),
            "execution_input": execution_input.to_payload(),
            "adapter_registry": {
                "registrations": [registration.to_payload() for registration in registrations],
                "discoveries": [discovery.to_payload() for discovery in discoveries],
            },
        },
    )
    write_json(
        selection_output_path,
        {
            "selection_input": selection_input.to_payload(),
            "selection_output": selection_output.to_payload(),
        },
    )
    write_json(
        approval_verdict_path,
        {
            "approval_request": approval_request.to_payload(),
            "approval_decision": approval_decision.to_payload(),
            "gate_verdict": gate_verdict.to_payload(),
        },
    )
    write_json(
        activation_result_path,
        {
            "activation_result": activation_result.to_payload(),
            "report_handoff": report_handoff.to_payload(),
        },
    )
    write_json(
        artifact_persistence_result_path,
        {
            "artifact_registrations": [registration.to_payload() for registration in artifact_registrations],
            "persistence_results": [result.to_payload() for result in persistence_results],
        },
    )
    safe_write_text(operator_report_path, report_text)

    return RuntimeActivationArtifacts(
        output_dir=destination,
        activation_input_path=activation_input_path,
        selection_output_path=selection_output_path,
        approval_verdict_path=approval_verdict_path,
        activation_result_path=activation_result_path,
        artifact_persistence_result_path=artifact_persistence_result_path,
        operator_report_path=operator_report_path,
    )


def _select_task_for_activation(tasks: List[TaskContract]) -> TaskContract:
    for task in tasks:
        if task.task_type == "task_graph_emission":
            return task
    raise ValueError("runtime activation harness requires a task_graph_emission node")


def _build_execution_input(task: TaskContract) -> ExecutionInputContract:
    return ExecutionInputContract(
        execution_id=f"EXEC_{task.task_id}_ACTIVATION",
        request_id=task.request_id,
        task_id=task.task_id,
        task_type=task.task_type,
        objective=task.objective,
        dependencies=list(task.dependencies),
        policy_level="architecture_only",
        expected_outputs=["selection_output.json", "approval_verdict.json", "operator_report.md"],
        validation_placeholders=["selection_status", "approval_verdict", "activation_status"],
        runtime_target_placeholder="unity_editor",
        dry_run=True,
    )


def _build_adapter_registry_snapshot() -> tuple[List[AdapterRegistrationContract], List[AdapterDiscoveryOutput]]:
    registrations = [
        AdapterRegistrationContract(
            adapter_id="adapter.testing.future",
            adapter_type="testing",
            supported_task_types=["task_graph_emission", "report_contract_preparation"],
            supported_targets=["workspace_copy", "unity_editor"],
            allowed_actions=["bounded_contract_validation"],
            requires_approval=["live_run"],
            dry_run_supported=True,
            live_run_supported=False,
        ),
        AdapterRegistrationContract(
            adapter_id="adapter.unity.future",
            adapter_type="unity",
            supported_task_types=["scene_edit", "playmode_validation"],
            supported_targets=["unity_editor"],
            allowed_actions=["bounded_scene_edit", "bounded_validation"],
            requires_approval=["live_run"],
            dry_run_supported=True,
            live_run_supported=False,
        ),
    ]
    discoveries = [
        AdapterDiscoveryOutput(
            adapter_id="adapter.testing.future",
            adapter_status="registered",
            capabilities={
                "dry_run_supported": True,
                "live_run_supported": False,
                "supported_targets": ["workspace_copy", "unity_editor"],
                "supported_task_types": ["task_graph_emission", "report_contract_preparation"],
            },
            priority=20,
            availability="available",
        ),
        AdapterDiscoveryOutput(
            adapter_id="adapter.unity.future",
            adapter_status="registered",
            capabilities={
                "dry_run_supported": True,
                "live_run_supported": False,
                "supported_targets": ["unity_editor"],
                "supported_task_types": ["scene_edit", "playmode_validation"],
            },
            priority=10,
            availability="planned",
        ),
    ]
    return registrations, discoveries


def _build_selection_input(execution_input: ExecutionInputContract) -> SelectionInputContract:
    return SelectionInputContract(
        selection_id=f"SEL_{execution_input.task_id}_ACTIVATION",
        request_id=execution_input.request_id,
        execution_id=execution_input.execution_id,
        task_id=execution_input.task_id,
        task_type=execution_input.task_type,
        runtime_target=execution_input.runtime_target_placeholder,
        policy_level=execution_input.policy_level,
        dry_run=execution_input.dry_run,
        approval_required=True,
        expected_outputs=list(execution_input.expected_outputs),
    )


def _build_selection_output(
    selection_input: SelectionInputContract,
    discoveries: List[AdapterDiscoveryOutput],
) -> SelectionOutputContract:
    candidate_adapters = [item.adapter_id for item in sorted(discoveries, key=lambda item: (-item.priority, item.adapter_id))]
    chosen_adapter_id = candidate_adapters[0] if candidate_adapters else ""
    state = "approval_pending" if chosen_adapter_id else "unsupported"
    blocked_reason = (
        "Future live runtime activation remains disabled until an approved runtime phase exists."
        if chosen_adapter_id
        else "No dry-run adapter candidates support the activation request."
    )
    return SelectionOutputContract(
        selection_id=selection_input.selection_id,
        chosen_adapter_id=chosen_adapter_id,
        candidate_adapters=candidate_adapters,
        selection_reason="Deterministic dry-run adapter match selected from the registry snapshot.",
        blocked=True,
        blocked_reason=blocked_reason,
        approval_required=True,
        escalation_required=True,
        state=state,
    )


def _build_approval_request(
    selection_input: SelectionInputContract,
    selection_output: SelectionOutputContract,
) -> ApprovalRequestContract:
    return ApprovalRequestContract(
        approval_id=f"APP_{selection_input.task_id}_ACTIVATION",
        request_id=selection_input.request_id,
        execution_id=selection_input.execution_id,
        adapter_id=selection_output.chosen_adapter_id,
        approval_reason="Live bounded runtime activation is not enabled in this phase.",
        requested_action="Allow a future live activation through a bounded adapter.",
        policy_level=selection_input.policy_level,
        blocking=True,
        safe_alternative="Remain in deterministic dry-run activation mode.",
    )


def _build_approval_decision(approval_request: ApprovalRequestContract) -> ApprovalDecisionContract:
    return ApprovalDecisionContract(
        approval_id=approval_request.approval_id,
        decision="deferred",
        decided_by="operator_placeholder",
        decided_at=SIMULATION_TIMESTAMP,
        notes="Architecture-only scaffold; no live activation approval path is active.",
    )


def _build_gate_verdict(decision: ApprovalDecisionContract) -> GateVerdictContract:
    if decision.decision == "approved":
        return GateVerdictContract(
            verdict="allow",
            proceed_allowed=True,
            blocked_until_approved=False,
            escalation_required=False,
            denial_reason="",
        )
    if decision.decision == "denied":
        return GateVerdictContract(
            verdict="deny",
            proceed_allowed=False,
            blocked_until_approved=False,
            escalation_required=False,
            denial_reason="Live runtime activation remains denied in this architecture-only phase.",
        )
    return GateVerdictContract(
        verdict="approval_pending",
        proceed_allowed=False,
        blocked_until_approved=True,
        escalation_required=True,
        denial_reason="Future live runtime activation remains blocked pending explicit approval.",
    )


def _build_artifact_persistence(
    selection_output: SelectionOutputContract,
    execution_input: ExecutionInputContract,
    destination: Path,
) -> tuple[List[ArtifactPersistenceRegistration], List[ArtifactPersistenceResult]]:
    registrations = [
        ArtifactPersistenceRegistration(
            artifact_id=f"ART_{execution_input.task_id}_ACTIVATION_001",
            artifact_type="runtime_activation_result",
            artifact_source="runtime_activation_harness",
            produced_by_task=execution_input.task_id,
            produced_by_adapter=selection_output.chosen_adapter_id,
            artifact_path=str((destination / "activation_result.json").as_posix()),
            artifact_timestamp=SIMULATION_TIMESTAMP,
        ),
        ArtifactPersistenceRegistration(
            artifact_id=f"ART_{execution_input.task_id}_ACTIVATION_002",
            artifact_type="operator_report",
            artifact_source="runtime_activation_harness",
            produced_by_task=execution_input.task_id,
            produced_by_adapter=selection_output.chosen_adapter_id,
            artifact_path=str((destination / "operator_report.md").as_posix()),
            artifact_timestamp=SIMULATION_TIMESTAMP,
        ),
    ]
    results = [
        ArtifactPersistenceResult(
            artifact_id=registration.artifact_id,
            stored=False,
            storage_location="contract_only",
            validation_attached=True,
            retention_policy="architecture_scaffold_only",
        )
        for registration in registrations
    ]
    return registrations, results


def _build_activation_result(
    *,
    execution_input: ExecutionInputContract,
    selection_output: SelectionOutputContract,
    gate_verdict: GateVerdictContract,
    artifacts_registered: int,
) -> RuntimeActivationResult:
    if selection_output.state == "unsupported":
        activation_status: ActivationStatus = "unsupported"
    elif gate_verdict.verdict == "allow":
        activation_status = "ready_for_dry_run"
    elif gate_verdict.verdict == "approval_pending":
        activation_status = "approval_required"
    else:
        activation_status = "blocked"
    return RuntimeActivationResult(
        activation_id=f"ACT_{execution_input.task_id}_ACTIVATION",
        request_id=execution_input.request_id,
        execution_id=execution_input.execution_id,
        task_id=execution_input.task_id,
        chosen_adapter_id=selection_output.chosen_adapter_id,
        candidate_adapters=list(selection_output.candidate_adapters),
        selection_status=selection_output.state,
        approval_verdict=gate_verdict.verdict,
        activation_status=activation_status,
        blocked=activation_status != "ready_for_dry_run",
        blocked_reason=gate_verdict.denial_reason or selection_output.blocked_reason,
        dry_run=execution_input.dry_run,
        artifacts_registered=artifacts_registered,
        report_handoff_ready=True,
        timestamp=SIMULATION_TIMESTAMP,
    )


def _build_report_handoff(
    *,
    selected_task: TaskContract,
    selection_output: SelectionOutputContract,
    gate_verdict: GateVerdictContract,
    activation_result: RuntimeActivationResult,
    persistence_results: List[ArtifactPersistenceResult],
) -> ReportHandoffContract:
    return ReportHandoffContract(
        operator_summary="Runtime activation harness completed a deterministic dry-run decision flow without invoking any live adapters.",
        facts_payload=[
            f"Task node: {selected_task.task_id} ({selected_task.task_type})",
            f"Chosen adapter: {selection_output.chosen_adapter_id}",
            f"Candidate adapters: {', '.join(selection_output.candidate_adapters)}",
            f"Approval verdict: {gate_verdict.verdict}",
            f"Activation status: {activation_result.activation_status}",
            f"Artifact persistence handoffs: {len(persistence_results)} contract-only entries.",
        ],
        assumptions_payload=[
            "Adapter discovery, selection, approval, and persistence remain architecture-only contracts.",
            "No live bounded execution, Unity execution, Blender execution, or gameplay mutation occurred.",
        ],
        recommendations_payload=[
            "Keep runtime activation limited to dry-run decision scaffolds until a future approved runtime phase exists.",
            "Use these outputs for contract review only, not as evidence of real adapter execution.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )


def main() -> None:
    artifacts = run_runtime_activation_harness()
    print(f"activation_input: {artifacts.activation_input_path}")
    print(f"selection_output: {artifacts.selection_output_path}")
    print(f"approval_verdict: {artifacts.approval_verdict_path}")
    print(f"activation_result: {artifacts.activation_result_path}")
    print(f"artifact_persistence_result: {artifacts.artifact_persistence_result_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()