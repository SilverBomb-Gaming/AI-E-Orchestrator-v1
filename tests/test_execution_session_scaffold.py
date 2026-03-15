import json
from pathlib import Path

import pytest

from execution_session_dry_run import run_execution_session_dry_run
from orchestrator.execution_session_interface import (
    ExecutionSessionRequestContract,
    evaluate_execution_session,
    normalize_session_request_state,
    session_states,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_execution_session_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "execution_session_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["execution_session_request"]["permit_state"] == "issued_for_dry_run"
    assert payload["execution_session_record"]["session_state"] == "session_open"
    assert payload["execution_session_heartbeat"]["status"] == "open"
    assert payload["execution_session_stop_conditions"]["completed"] is False
    assert payload["state_transitions"]["session_open+cancel"] == "session_cancelled"


def test_execution_session_request_is_deterministic():
    request = ExecutionSessionRequestContract(
        session_id="SESSION_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        activation_id="ACT_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        selected_adapter_id="adapter.testing.future",
        permit_state="issued_for_dry_run",
        issued_for="dry_run",
        policy_level="architecture_only",
        dry_run=True,
        session_requested_at="2026-03-15T00:00:00Z",
    )

    payload = request.to_payload()
    assert payload["permit_state"] == "issued_for_dry_run"
    assert payload["issued_for"] == "dry_run"


def test_execution_session_state_transitions_are_deterministic():
    request = ExecutionSessionRequestContract(
        session_id="SESSION_002",
        permit_id="PERMIT_002",
        authorization_id="AUTH_002",
        activation_id="ACT_002",
        request_id="REQ_002",
        execution_id="EXEC_002",
        task_id="TASK_002",
        selected_adapter_id="adapter.testing.future",
        permit_state="issued_for_dry_run",
        issued_for="dry_run",
        policy_level="architecture_only",
        dry_run=True,
        session_requested_at="2026-03-15T00:00:00Z",
    )
    blocked_request = ExecutionSessionRequestContract(
        session_id="SESSION_003",
        permit_id="PERMIT_003",
        authorization_id="AUTH_003",
        activation_id="ACT_003",
        request_id="REQ_003",
        execution_id="EXEC_003",
        task_id="TASK_003",
        selected_adapter_id="adapter.testing.future",
        permit_state="blocked",
        issued_for="none",
        policy_level="architecture_only",
        dry_run=True,
        session_requested_at="2026-03-15T00:00:00Z",
    )

    assert normalize_session_request_state(request) == "session_requested"
    open_record, open_verdict, open_heartbeat, open_stop = evaluate_execution_session(
        request,
        "approve",
        opened_by="operator_placeholder",
        opened_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
        scope_limit="dry_run_only",
        time_budget_seconds=300,
    )
    complete_record, _, _, complete_stop = evaluate_execution_session(
        request,
        "complete",
        opened_by="operator_placeholder",
        opened_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
        scope_limit="dry_run_only",
        time_budget_seconds=300,
    )
    cancel_record, _, _, cancel_stop = evaluate_execution_session(
        request,
        "cancel",
        opened_by="operator_placeholder",
        opened_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
        scope_limit="dry_run_only",
        time_budget_seconds=300,
    )
    expire_record, _, _, expire_stop = evaluate_execution_session(
        request,
        "expire",
        opened_by="operator_placeholder",
        opened_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
        scope_limit="dry_run_only",
        time_budget_seconds=300,
    )
    fail_record, _, _, fail_stop = evaluate_execution_session(
        request,
        "failure_limit",
        opened_by="operator_placeholder",
        opened_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
        scope_limit="dry_run_only",
        time_budget_seconds=300,
    )
    blocked_record, blocked_verdict, blocked_heartbeat, blocked_stop = evaluate_execution_session(
        blocked_request,
        "approve",
        opened_by="operator_placeholder",
        opened_timestamp="2026-03-15T00:00:00Z",
        expires_at="2026-03-16T00:00:00Z",
        scope_limit="none",
        time_budget_seconds=0,
    )

    assert open_record.session_state == "session_open"
    assert open_verdict.session_state == "session_open"
    assert open_heartbeat.status == "open"
    assert open_stop.stop_reason == "not_triggered"
    assert complete_record.session_state == "session_completed"
    assert complete_stop.completed is True
    assert cancel_record.session_state == "session_cancelled"
    assert cancel_stop.operator_cancelled is True
    assert expire_record.session_state == "session_expired"
    assert expire_stop.time_budget_exceeded is True
    assert fail_record.session_state == "session_failed"
    assert fail_stop.failure_limit_reached is True
    assert blocked_record.session_state == "session_blocked"
    assert blocked_verdict.session_state == "session_blocked"
    assert blocked_heartbeat.status == "blocked"
    assert blocked_stop.policy_blocked is True
    assert all(state in session_states() for state in [
        open_record.session_state,
        complete_record.session_state,
        cancel_record.session_state,
        expire_record.session_state,
        fail_record.session_state,
        blocked_record.session_state,
    ])


def test_execution_session_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_execution_session_dry_run(tmp_path / "aie_execution_session_test")

    session_request = json.loads(artifacts.execution_session_request_path.read_text(encoding="utf-8"))
    session_record = json.loads(artifacts.execution_session_record_path.read_text(encoding="utf-8"))
    session_verdict = json.loads(artifacts.execution_session_verdict_path.read_text(encoding="utf-8"))
    session_heartbeat = json.loads(artifacts.execution_session_heartbeat_path.read_text(encoding="utf-8"))
    stop_conditions = json.loads(artifacts.execution_session_stop_conditions_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert session_request["execution_session_request"]["permit_state"] == "issued_for_dry_run"
    assert session_record["execution_session_record"]["session_state"] == "session_open"
    assert session_verdict["execution_session_verdict"]["proceed_allowed"] is True
    assert session_heartbeat["execution_session_heartbeat"]["status"] == "open"
    assert stop_conditions["execution_session_stop_conditions"]["stop_reason"] == "not_triggered"
    assert "contract-only boundary" in operator_report
    assert "No live session engine, no live bounded execution" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report