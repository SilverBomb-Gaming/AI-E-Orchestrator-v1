import json
from pathlib import Path

import pytest

from orchestrator.execution_bridge_interface import ArtifactRegistrationContract
from orchestrator.real_execution_adapter_interface import (
    AdapterCapabilityDeclaration,
    ApprovalBoundaryContract,
    ExecutionRequestHandoff,
    ExecutionResponseContract,
    FailureClassificationContract,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_adapter_contract_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "execution_adapter_contract_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["adapter_capability"]["dry_run_supported"] is True
    assert payload["adapter_capability"]["live_run_supported"] is False
    assert payload["execution_request_handoff"]["approval_boundary"]["approval_required"] is True
    assert payload["execution_response"]["operator_attention_required"] is True


def test_adapter_capability_contract_is_deterministic():
    capability = AdapterCapabilityDeclaration(
        adapter_id="adapter.git.future",
        adapter_type="git",
        supported_task_types=["repo_edit"],
        supported_runtime_targets=["workspace_copy"],
        allowed_actions=["bounded_patch"],
        denied_actions=["force_reset"],
        requires_approval_for=["live_run"],
        dry_run_supported=True,
        live_run_supported=False,
        notes=["Contract-only scaffold."],
    )

    assert capability.to_payload()["adapter_id"] == "adapter.git.future"
    assert capability.to_payload()["live_run_supported"] is False


def test_execution_request_handoff_is_deterministic():
    approval = ApprovalBoundaryContract(
        approval_required=True,
        approval_reason="Live execution is disabled in this phase.",
        blocked_until_approved=True,
    )
    handoff = ExecutionRequestHandoff(
        execution_id="EXEC_REQ_001",
        request_id="REQ_001",
        task_id="REQ_001_GRAPH",
        adapter_target="unity_editor",
        task_type="task_graph_emission",
        objective="Emit a task graph.",
        policy_level="architecture_only",
        dry_run=True,
        approval_boundary=approval,
        expected_outputs=["task_graph.json"],
        validation_requirements=["validation_status", "validation_notes"],
    )

    payload = handoff.to_payload()
    assert payload["approval_boundary"]["approval_required"] is True
    assert payload["expected_outputs"] == ["task_graph.json"]


def test_execution_response_and_failure_classification_are_deterministic():
    artifact = ArtifactRegistrationContract(
        artifact_id="ART_001",
        artifact_type="structured_report",
        path="runs/test/task_graph.json",
        produced_by="adapter.unity.future",
        related_task_id="REQ_001_GRAPH",
        summary="Placeholder artifact.",
    )
    failure = FailureClassificationContract(
        failure_type="approval_gate",
        failure_scope="adapter_boundary",
        retry_recommended=False,
        retry_reason="Await approval.",
        escalation_required=True,
        blocking=True,
    )
    approval = ApprovalBoundaryContract(
        approval_required=True,
        approval_reason="Live execution disabled.",
        blocked_until_approved=True,
    )
    response = ExecutionResponseContract(
        execution_id="EXEC_REQ_001",
        adapter_id="adapter.unity.future",
        status="approval_required",
        artifacts=[artifact],
        validation_status="pending",
        warnings=["No live execution implemented."],
        errors=[],
        started_at="2026-03-15T00:00:00Z",
        finished_at="2026-03-15T00:00:00Z",
        operator_attention_required=True,
        failure_classification=failure,
        approval_boundary=approval,
    )

    payload = response.to_payload()
    assert payload["status"] == "approval_required"
    assert payload["failure_classification"]["blocking"] is True
    assert payload["approval_boundary"]["blocked_until_approved"] is True


def test_approval_boundary_fields_are_explicit():
    boundary = ApprovalBoundaryContract(
        approval_required=True,
        approval_reason="Operator approval is mandatory for future live work.",
        blocked_until_approved=True,
    )

    assert boundary.to_payload() == {
        "approval_required": True,
        "approval_reason": "Operator approval is mandatory for future live work.",
        "blocked_until_approved": True,
    }