import json
from pathlib import Path

import pytest

from orchestrator.architecture_blueprint import TaskContract, required_response_sections
from orchestrator.execution_bridge_interface import (
    ArtifactRegistrationContract,
    ExecutionInputContract,
    ExecutionResultContract,
    ReportHandoffContract,
    ValidationAttachmentContract,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_execution_contract_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "execution_contract_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["execution_input"]["dry_run"] is True
    assert payload["execution_result"]["validation"]["validation_status"] == "pending"
    assert payload["report_handoff"]["required_report_sections"] == required_response_sections()


def test_execution_input_contract_is_deterministic():
    contract = ExecutionInputContract(
        execution_id="EXEC_REQ_001_GRAPH",
        request_id="REQ_001",
        task_id="REQ_001_GRAPH",
        task_type="task_graph_emission",
        objective="Emit a task graph.",
        dependencies=["REQ_001_INTAKE"],
        expected_outputs=["task_graph.json"],
        validation_placeholders=["validation_status", "validation_notes"],
        runtime_target_placeholder="future_agent_execution",
        dry_run=True,
    )

    assert contract.to_payload() == {
        "execution_id": "EXEC_REQ_001_GRAPH",
        "request_id": "REQ_001",
        "task_id": "REQ_001_GRAPH",
        "task_type": "task_graph_emission",
        "objective": "Emit a task graph.",
        "dependencies": ["REQ_001_INTAKE"],
        "policy_level": "architecture_only",
        "expected_outputs": ["task_graph.json"],
        "validation_placeholders": ["validation_status", "validation_notes"],
        "runtime_target_placeholder": "future_agent_execution",
        "dry_run": True,
    }


def test_execution_result_and_artifact_registration_are_deterministic():
    artifact = ArtifactRegistrationContract(
        artifact_id="ART_001",
        artifact_type="structured_report",
        path="runs/test/task_graph.json",
        produced_by="ExecutionBridgeScaffold",
        related_task_id="REQ_001_GRAPH",
        summary="Deterministic placeholder artifact.",
    )
    validation = ValidationAttachmentContract(
        validation_status="needs_review",
        validation_notes=["Awaiting future execution adapter approval."],
        blocking_issues=[],
        retry_recommended=False,
    )
    result = ExecutionResultContract(
        execution_id="EXEC_REQ_001_GRAPH",
        status="planned",
        artifacts=[artifact],
        validation=validation,
        warnings=["No runtime adapter attached."],
        errors=[],
        started_at="2026-03-15T00:00:00Z",
        finished_at="2026-03-15T00:00:00Z",
    )

    assert result.to_payload()["artifacts"][0]["artifact_id"] == "ART_001"
    assert result.to_payload()["validation"]["validation_status"] == "needs_review"
    assert result.to_payload()["warnings"] == ["No runtime adapter attached."]


def test_report_handoff_aligns_with_canonical_sections():
    handoff = ReportHandoffContract(
        operator_summary="Execution bridge scaffold remains architecture-only.",
        facts_payload=["No runtime execution occurred."],
        assumptions_payload=["Future agent execution remains unwired."],
        recommendations_payload=["Keep runner integration disabled."],
        timestamp="2026-03-15T00:00:00Z",
    )

    payload = handoff.to_payload()

    assert payload["required_report_sections"] == required_response_sections()
    assert payload["facts_payload"] == ["No runtime execution occurred."]
    assert payload["timestamp"] == "2026-03-15T00:00:00Z"


def test_execution_bridge_contracts_do_not_require_runner_integration():
    task = TaskContract(
        task_id="REQ_001_REPORT",
        request_id="REQ_001",
        task_type="report_contract_preparation",
        objective="Prepare report placeholders.",
    )
    contract = ExecutionInputContract(
        execution_id="EXEC_REQ_001_REPORT",
        request_id=task.request_id,
        task_id=task.task_id,
        task_type=task.task_type,
        objective=task.objective,
        expected_outputs=["report_contract.json"],
        validation_placeholders=["validation_status"],
    )

    assert contract.dry_run is True
    assert contract.policy_level == "architecture_only"