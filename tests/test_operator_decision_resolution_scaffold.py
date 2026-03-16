import json
from pathlib import Path

import pytest

from operator_decision_resolution_dry_run import run_operator_decision_resolution_dry_run
from orchestrator.operator_decision_resolution_interface import (
    OperatorDecisionRequestContract,
    OperatorDecisionResponseContract,
    decision_resolution_states,
    evaluate_operator_decision_resolution,
    operator_decisions,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_operator_decision_resolution_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "operator_decision_resolution_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["operator_decision_request"]["priority_level"] == "low"
    assert payload["operator_decision_response"]["operator_decision"] == "archive_only"
    assert payload["operator_decision_resolution"]["resolution_state"] == "resolved_archive"
    assert payload["decision_transitions"]["blocked_review_package"] == "resolution_blocked"


def test_operator_decision_resolution_transitions_are_deterministic():
    retry_request = OperatorDecisionRequestContract(
        decision_id="DECISION_RETRY",
        handoff_id="HANDOFF_RETRY",
        session_id="SESSION_RETRY",
        closeout_id="CLOSEOUT_RETRY",
        request_id="REQ_RETRY",
        execution_id="EXEC_RETRY",
        task_id="TASK_RETRY",
        priority_level="urgent",
        operator_attention_required=True,
        reviewable_items=["failure:EXEC_RETRY"],
        approval_items=[],
        blocked_items=[],
        retry_candidates=["retry:TASK_RETRY"],
        archival_candidates=[],
        decision_requested_at="2026-03-16T00:00:00Z",
    )
    retry_response = OperatorDecisionResponseContract(
        decision_id="DECISION_RETRY",
        operator_decision="approve_retry",
        decided_by="operator_placeholder",
        decided_at="2026-03-16T00:00:00Z",
        notes="Retry approved.",
    )
    archive_request = OperatorDecisionRequestContract(
        decision_id="DECISION_ARCHIVE",
        handoff_id="HANDOFF_ARCHIVE",
        session_id="SESSION_ARCHIVE",
        closeout_id="CLOSEOUT_ARCHIVE",
        request_id="REQ_ARCHIVE",
        execution_id="EXEC_ARCHIVE",
        task_id="TASK_ARCHIVE",
        priority_level="low",
        operator_attention_required=False,
        reviewable_items=["session:SESSION_ARCHIVE"],
        approval_items=["archive:HANDOFF_ARCHIVE"],
        blocked_items=[],
        retry_candidates=[],
        archival_candidates=["ART_ARCHIVE"],
        decision_requested_at="2026-03-16T00:00:00Z",
    )
    archive_response = OperatorDecisionResponseContract(
        decision_id="DECISION_ARCHIVE",
        operator_decision="archive_only",
        decided_by="operator_placeholder",
        decided_at="2026-03-16T00:00:00Z",
        notes="Archive approved.",
    )
    blocked_request = OperatorDecisionRequestContract(
        decision_id="DECISION_BLOCKED",
        handoff_id="HANDOFF_BLOCKED",
        session_id="SESSION_BLOCKED",
        closeout_id="CLOSEOUT_BLOCKED",
        request_id="REQ_BLOCKED",
        execution_id="EXEC_BLOCKED",
        task_id="TASK_BLOCKED",
        priority_level="high",
        operator_attention_required=True,
        reviewable_items=["blocked:EXEC_BLOCKED"],
        approval_items=[],
        blocked_items=["blocked:EXEC_BLOCKED"],
        retry_candidates=[],
        archival_candidates=[],
        decision_requested_at="2026-03-16T00:00:00Z",
    )
    blocked_response = OperatorDecisionResponseContract(
        decision_id="DECISION_BLOCKED",
        operator_decision="escalate",
        decided_by="operator_placeholder",
        decided_at="2026-03-16T00:00:00Z",
        notes="Blocked package escalated.",
    )

    retry_resolution = evaluate_operator_decision_resolution(retry_request, retry_response)
    archive_resolution = evaluate_operator_decision_resolution(archive_request, archive_response)
    blocked_resolution = evaluate_operator_decision_resolution(blocked_request, blocked_response)

    assert retry_resolution.resolution_state == "resolved_retry"
    assert retry_resolution.retry_authorized is True
    assert archive_resolution.resolution_state == "resolved_archive"
    assert archive_resolution.archival_authorized is True
    assert blocked_resolution.resolution_state == "resolution_blocked"
    assert blocked_resolution.blocked is True
    assert blocked_resolution.escalation_required is True
    assert "archive_only" in operator_decisions()
    assert all(
        state in decision_resolution_states()
        for state in [retry_resolution.resolution_state, archive_resolution.resolution_state, blocked_resolution.resolution_state]
    )


def test_operator_decision_resolution_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_operator_decision_resolution_dry_run(tmp_path / "aie_operator_decision_resolution_test")

    decision_request = json.loads(artifacts.operator_decision_request_path.read_text(encoding="utf-8"))
    decision_response = json.loads(artifacts.operator_decision_response_path.read_text(encoding="utf-8"))
    decision_resolution = json.loads(artifacts.operator_decision_resolution_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert decision_request["operator_decision_request"]["priority_level"] == "low"
    assert decision_response["operator_decision_response"]["operator_decision"] == "archive_only"
    assert decision_resolution["operator_decision_resolution"]["resolution_state"] == "resolved_archive"
    assert decision_resolution["operator_decision_resolution"]["archival_authorized"] is True
    assert "contract-only" in operator_report
    assert "No live bounded execution, no live operator workflow engine" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report