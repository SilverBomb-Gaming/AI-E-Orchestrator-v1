import json
from pathlib import Path

import pytest

from execution_permit_dry_run import run_execution_permit_dry_run
from orchestrator.execution_permit_interface import (
    ExecutionPermitRequestContract,
    evaluate_execution_permit,
    normalize_permit_request_state,
    permit_states,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_execution_permit_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "execution_permit_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["execution_permit_request"]["authorization_state"] == "authorized_for_dry_run"
    assert payload["execution_permit_record"]["permit_state"] == "issued_for_dry_run"
    assert payload["execution_permit_verdict"]["proceed_allowed"] is True
    assert payload["state_transitions"]["permit_requested+deny"] == "not_issued"


def test_execution_permit_request_is_deterministic():
    request = ExecutionPermitRequestContract(
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        activation_id="ACT_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        selected_adapter_id="adapter.testing.future",
        authorization_state="authorized_for_dry_run",
        authorized_for="dry_run",
        policy_level="architecture_only",
        dry_run=True,
        permit_requested_at="2026-03-15T00:00:00Z",
    )

    payload = request.to_payload()
    assert payload["authorization_state"] == "authorized_for_dry_run"
    assert payload["authorized_for"] == "dry_run"


def test_execution_permit_state_transitions_are_deterministic():
    request = ExecutionPermitRequestContract(
        permit_id="PERMIT_002",
        authorization_id="AUTH_002",
        activation_id="ACT_002",
        request_id="REQ_002",
        execution_id="EXEC_002",
        task_id="TASK_002",
        selected_adapter_id="adapter.testing.future",
        authorization_state="authorized_for_dry_run",
        authorized_for="dry_run",
        policy_level="architecture_only",
        dry_run=True,
        permit_requested_at="2026-03-15T00:00:00Z",
    )
    not_authorized_request = ExecutionPermitRequestContract(
        permit_id="PERMIT_003",
        authorization_id="AUTH_003",
        activation_id="ACT_003",
        request_id="REQ_003",
        execution_id="EXEC_003",
        task_id="TASK_003",
        selected_adapter_id="adapter.testing.future",
        authorization_state="not_authorized",
        authorized_for="none",
        policy_level="architecture_only",
        dry_run=True,
        permit_requested_at="2026-03-15T00:00:00Z",
    )
    blocked_request = ExecutionPermitRequestContract(
        permit_id="PERMIT_004",
        authorization_id="AUTH_004",
        activation_id="ACT_004",
        request_id="REQ_004",
        execution_id="EXEC_004",
        task_id="TASK_004",
        selected_adapter_id="adapter.testing.future",
        authorization_state="blocked",
        authorized_for="none",
        policy_level="architecture_only",
        dry_run=True,
        permit_requested_at="2026-03-15T00:00:00Z",
    )

    assert normalize_permit_request_state(request) == "permit_requested"
    approve_record, approve_verdict = evaluate_execution_permit(
        request,
        "approve",
        issued_by="operator_placeholder",
        issued_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )
    deny_record, deny_verdict = evaluate_execution_permit(
        request,
        "deny",
        issued_by="operator_placeholder",
        issued_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )
    escalate_record, escalate_verdict = evaluate_execution_permit(
        request,
        "escalate",
        issued_by="operator_placeholder",
        issued_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )
    not_auth_record, not_auth_verdict = evaluate_execution_permit(
        not_authorized_request,
        "approve",
        issued_by="operator_placeholder",
        issued_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )
    blocked_record, blocked_verdict = evaluate_execution_permit(
        blocked_request,
        "approve",
        issued_by="operator_placeholder",
        issued_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )

    assert approve_record.permit_state == "issued_for_dry_run"
    assert approve_verdict.permit_state == "issued_for_dry_run"
    assert deny_record.permit_state == "not_issued"
    assert deny_verdict.permit_state == "not_issued"
    assert escalate_record.permit_state == "requires_additional_review"
    assert escalate_verdict.permit_state == "requires_additional_review"
    assert not_auth_record.permit_state == "not_issued"
    assert blocked_record.permit_state == "blocked"
    assert all(state in permit_states() for state in [
        approve_record.permit_state,
        deny_record.permit_state,
        escalate_record.permit_state,
        not_auth_record.permit_state,
        blocked_record.permit_state,
    ])


def test_execution_permit_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_execution_permit_dry_run(tmp_path / "aie_execution_permit_test")

    permit_request = json.loads(artifacts.execution_permit_request_path.read_text(encoding="utf-8"))
    permit_record = json.loads(artifacts.execution_permit_record_path.read_text(encoding="utf-8"))
    permit_verdict = json.loads(artifacts.execution_permit_verdict_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert permit_request["execution_permit_request"]["authorization_state"] == "authorized_for_dry_run"
    assert permit_record["execution_permit_record"]["permit_state"] == "issued_for_dry_run"
    assert permit_record["execution_permit_record"]["issued"] is True
    assert permit_verdict["execution_permit_verdict"]["proceed_allowed"] is True
    assert permit_verdict["execution_permit_verdict"]["scope_limit"] == "dry_run_only"
    assert "contract-only boundary" in operator_report
    assert "No live permit engine, no live bounded execution" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report