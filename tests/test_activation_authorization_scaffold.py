import json
from pathlib import Path

import pytest

from activation_authorization_dry_run import run_activation_authorization_dry_run
from orchestrator.activation_authorization_interface import (
    ActivationAuthorizationRequestContract,
    authorization_states,
    evaluate_activation_authorization,
    normalize_authorization_request_state,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_activation_authorization_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "activation_authorization_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["activation_authorization_request"]["review_result_state"] == "ready_for_dry_run"
    assert payload["activation_authorization_record"]["authorization_state"] == "authorized_for_dry_run"
    assert payload["activation_authorization_verdict"]["proceed_allowed"] is True
    assert payload["state_transitions"]["authorization_requested+deny"] == "not_authorized"


def test_activation_authorization_request_is_deterministic():
    request = ActivationAuthorizationRequestContract(
        authorization_id="AUTH_001",
        review_id="REV_001",
        activation_id="ACT_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        selected_adapter_id="adapter.testing.future",
        review_decision="approve",
        review_result_state="ready_for_dry_run",
        policy_level="architecture_only",
        dry_run=True,
        authorization_requested_at="2026-03-15T00:00:00Z",
    )

    payload = request.to_payload()
    assert payload["review_result_state"] == "ready_for_dry_run"
    assert payload["dry_run"] is True


def test_activation_authorization_state_transitions_are_deterministic():
    request = ActivationAuthorizationRequestContract(
        authorization_id="AUTH_002",
        review_id="REV_002",
        activation_id="ACT_002",
        request_id="REQ_002",
        execution_id="EXEC_002",
        task_id="TASK_002",
        selected_adapter_id="adapter.testing.future",
        review_decision="approve",
        review_result_state="ready_for_dry_run",
        policy_level="architecture_only",
        dry_run=True,
        authorization_requested_at="2026-03-15T00:00:00Z",
    )
    denied_request = ActivationAuthorizationRequestContract(
        authorization_id="AUTH_003",
        review_id="REV_003",
        activation_id="ACT_003",
        request_id="REQ_003",
        execution_id="EXEC_003",
        task_id="TASK_003",
        selected_adapter_id="adapter.testing.future",
        review_decision="deny",
        review_result_state="denied",
        policy_level="architecture_only",
        dry_run=True,
        authorization_requested_at="2026-03-15T00:00:00Z",
    )
    blocked_request = ActivationAuthorizationRequestContract(
        authorization_id="AUTH_004",
        review_id="REV_004",
        activation_id="ACT_004",
        request_id="REQ_004",
        execution_id="EXEC_004",
        task_id="TASK_004",
        selected_adapter_id="adapter.testing.future",
        review_decision="approve",
        review_result_state="blocked",
        policy_level="architecture_only",
        dry_run=True,
        authorization_requested_at="2026-03-15T00:00:00Z",
    )

    assert normalize_authorization_request_state(request) == "authorization_requested"
    approve_record, approve_verdict = evaluate_activation_authorization(
        request,
        "approve",
        authorized_by="operator_placeholder",
        authorization_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )
    deny_record, deny_verdict = evaluate_activation_authorization(
        request,
        "deny",
        authorized_by="operator_placeholder",
        authorization_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )
    escalate_record, escalate_verdict = evaluate_activation_authorization(
        request,
        "escalate",
        authorized_by="operator_placeholder",
        authorization_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )
    denied_record, denied_verdict = evaluate_activation_authorization(
        denied_request,
        "approve",
        authorized_by="operator_placeholder",
        authorization_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )
    blocked_record, blocked_verdict = evaluate_activation_authorization(
        blocked_request,
        "approve",
        authorized_by="operator_placeholder",
        authorization_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
    )

    assert approve_record.authorization_state == "authorized_for_dry_run"
    assert approve_verdict.authorization_state == "authorized_for_dry_run"
    assert deny_record.authorization_state == "not_authorized"
    assert deny_verdict.authorization_state == "not_authorized"
    assert escalate_record.authorization_state == "requires_additional_review"
    assert escalate_verdict.authorization_state == "requires_additional_review"
    assert denied_record.authorization_state == "not_authorized"
    assert blocked_record.authorization_state == "blocked"
    assert all(state in authorization_states() for state in [
        approve_record.authorization_state,
        deny_record.authorization_state,
        escalate_record.authorization_state,
        denied_record.authorization_state,
        blocked_record.authorization_state,
    ])


def test_activation_authorization_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_activation_authorization_dry_run(tmp_path / "aie_activation_authorization_test")

    authorization_request = json.loads(artifacts.activation_authorization_request_path.read_text(encoding="utf-8"))
    authorization_record = json.loads(artifacts.activation_authorization_record_path.read_text(encoding="utf-8"))
    authorization_verdict = json.loads(artifacts.activation_authorization_verdict_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert authorization_request["activation_authorization_request"]["review_result_state"] == "ready_for_dry_run"
    assert authorization_record["activation_authorization_record"]["authorization_state"] == "authorized_for_dry_run"
    assert authorization_record["activation_authorization_record"]["authorized"] is True
    assert authorization_verdict["activation_authorization_verdict"]["proceed_allowed"] is True
    assert "contract-only boundary" in operator_report
    assert "No live approval engine, no live bounded execution" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report