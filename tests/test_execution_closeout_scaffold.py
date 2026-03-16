import json
from pathlib import Path

import pytest

from execution_closeout_dry_run import run_execution_closeout_dry_run
from orchestrator.execution_closeout_interface import (
    ExecutionCloseoutRequestContract,
    closeout_states,
    evaluate_execution_closeout,
    normalize_closeout_request_state,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_execution_closeout_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "execution_closeout_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["execution_closeout_request"]["session_state"] == "session_completed"
    assert payload["execution_closeout_record"]["closeout_state"] == "closed_successfully"
    assert payload["execution_closeout_verdict"]["operator_review_required"] is False
    assert payload["state_transitions"]["closeout_requested+session_failed"] == "closed_failed"


def test_execution_closeout_request_and_state_transitions_are_deterministic():
    completed = ExecutionCloseoutRequestContract(
        closeout_id="CLOSEOUT_001",
        session_id="SESSION_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        session_state="session_completed",
        stop_reason="completed",
        time_budget_seconds=300,
        artifacts_summary_count=1,
        closeout_requested_at="2026-03-15T00:00:00Z",
    )
    failed = ExecutionCloseoutRequestContract(
        closeout_id="CLOSEOUT_002",
        session_id="SESSION_002",
        permit_id="PERMIT_002",
        authorization_id="AUTH_002",
        request_id="REQ_002",
        execution_id="EXEC_002",
        task_id="TASK_002",
        session_state="session_failed",
        stop_reason="failure_limit_reached",
        time_budget_seconds=300,
        artifacts_summary_count=1,
        closeout_requested_at="2026-03-15T00:00:00Z",
    )
    cancelled = ExecutionCloseoutRequestContract(
        closeout_id="CLOSEOUT_003",
        session_id="SESSION_003",
        permit_id="PERMIT_003",
        authorization_id="AUTH_003",
        request_id="REQ_003",
        execution_id="EXEC_003",
        task_id="TASK_003",
        session_state="session_cancelled",
        stop_reason="operator_cancelled",
        time_budget_seconds=300,
        artifacts_summary_count=1,
        closeout_requested_at="2026-03-15T00:00:00Z",
    )
    expired = ExecutionCloseoutRequestContract(
        closeout_id="CLOSEOUT_004",
        session_id="SESSION_004",
        permit_id="PERMIT_004",
        authorization_id="AUTH_004",
        request_id="REQ_004",
        execution_id="EXEC_004",
        task_id="TASK_004",
        session_state="session_expired",
        stop_reason="time_budget_exceeded",
        time_budget_seconds=300,
        artifacts_summary_count=1,
        closeout_requested_at="2026-03-15T00:00:00Z",
    )
    blocked = ExecutionCloseoutRequestContract(
        closeout_id="CLOSEOUT_005",
        session_id="SESSION_005",
        permit_id="PERMIT_005",
        authorization_id="AUTH_005",
        request_id="REQ_005",
        execution_id="EXEC_005",
        task_id="TASK_005",
        session_state="session_blocked",
        stop_reason="policy_blocked",
        time_budget_seconds=0,
        artifacts_summary_count=0,
        closeout_requested_at="2026-03-15T00:00:00Z",
    )

    assert normalize_closeout_request_state(completed) == "closeout_requested"
    completed_record, completed_verdict = evaluate_execution_closeout(
        completed,
        retained_artifacts=["ART_001"],
        discarded_artifacts=[],
        completed_at="2026-03-15T00:00:00Z",
    )
    failed_record, failed_verdict = evaluate_execution_closeout(
        failed,
        retained_artifacts=["ART_002"],
        discarded_artifacts=["ART_TMP_002"],
        completed_at="2026-03-15T00:00:00Z",
    )
    cancelled_record, _ = evaluate_execution_closeout(
        cancelled,
        retained_artifacts=[],
        discarded_artifacts=[],
        completed_at="2026-03-15T00:00:00Z",
    )
    expired_record, expired_verdict = evaluate_execution_closeout(
        expired,
        retained_artifacts=["ART_004"],
        discarded_artifacts=["ART_TMP_004"],
        completed_at="2026-03-15T00:00:00Z",
    )
    blocked_record, _ = evaluate_execution_closeout(
        blocked,
        retained_artifacts=[],
        discarded_artifacts=[],
        completed_at="2026-03-15T00:00:00Z",
    )

    assert completed_record.closeout_state == "closed_successfully"
    assert completed_verdict.closeout_state == "closed_successfully"
    assert failed_record.closeout_state == "closed_failed"
    assert failed_verdict.retry_recommended is True
    assert cancelled_record.closeout_state == "closed_cancelled"
    assert expired_record.closeout_state == "closed_expired"
    assert expired_verdict.escalation_required is True
    assert blocked_record.closeout_state == "closed_blocked"
    assert all(state in closeout_states() for state in [
        completed_record.closeout_state,
        failed_record.closeout_state,
        cancelled_record.closeout_state,
        expired_record.closeout_state,
        blocked_record.closeout_state,
    ])


def test_execution_closeout_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_execution_closeout_dry_run(tmp_path / "aie_execution_closeout_test")

    artifact_record = json.loads(artifacts.execution_artifact_record_path.read_text(encoding="utf-8"))
    artifact_retention = json.loads(artifacts.execution_artifact_retention_path.read_text(encoding="utf-8"))
    closeout_request = json.loads(artifacts.execution_closeout_request_path.read_text(encoding="utf-8"))
    closeout_record = json.loads(artifacts.execution_closeout_record_path.read_text(encoding="utf-8"))
    closeout_verdict = json.loads(artifacts.execution_closeout_verdict_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert artifact_record["execution_artifact_record"]["retention_class"] == "retained_output"
    assert artifact_retention["execution_artifact_retention"]["retained"] is True
    assert closeout_request["execution_closeout_request"]["session_state"] == "session_completed"
    assert closeout_record["execution_closeout_record"]["closeout_state"] == "closed_successfully"
    assert closeout_verdict["execution_closeout_verdict"]["operator_review_required"] is False
    assert "contract-only boundaries" in operator_report or "contract-only boundary" in operator_report
    assert "No live closeout engine, no live bounded execution" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report