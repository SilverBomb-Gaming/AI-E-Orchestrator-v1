import json
from pathlib import Path

import pytest

from orchestrator.post_decision_dispatch_interface import (
    PostDecisionDispatchRequestContract,
    dispatch_states,
    evaluate_post_decision_dispatch,
)
from post_decision_dispatch_dry_run import run_post_decision_dispatch_dry_run


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_post_decision_dispatch_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "post_decision_dispatch_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["post_decision_dispatch_request"]["resolution_state"] == "resolved_archive"
    assert payload["post_decision_dispatch_record"]["dispatch_state"] == "dispatch_archive"
    assert payload["post_decision_dispatch_verdict"]["archival_ready"] is True
    assert payload["dispatch_transitions"]["resolution_blocked"] == "dispatch_blocked"


def test_post_decision_dispatch_transitions_are_deterministic():
    retry_request = PostDecisionDispatchRequestContract(
        dispatch_id="DISPATCH_RETRY",
        decision_id="DECISION_RETRY",
        handoff_id="HANDOFF_RETRY",
        session_id="SESSION_RETRY",
        closeout_id="CLOSEOUT_RETRY",
        request_id="REQ_RETRY",
        execution_id="EXEC_RETRY",
        task_id="TASK_RETRY",
        resolution_state="resolved_retry",
        next_action="retry_task",
        priority_level="urgent",
        dispatch_requested_at="2026-03-16T00:00:00Z",
    )
    archive_request = PostDecisionDispatchRequestContract(
        dispatch_id="DISPATCH_ARCHIVE",
        decision_id="DECISION_ARCHIVE",
        handoff_id="HANDOFF_ARCHIVE",
        session_id="SESSION_ARCHIVE",
        closeout_id="CLOSEOUT_ARCHIVE",
        request_id="REQ_ARCHIVE",
        execution_id="EXEC_ARCHIVE",
        task_id="TASK_ARCHIVE",
        resolution_state="resolved_archive",
        next_action="archive_package",
        priority_level="low",
        dispatch_requested_at="2026-03-16T00:00:00Z",
    )
    blocked_request = PostDecisionDispatchRequestContract(
        dispatch_id="DISPATCH_BLOCKED",
        decision_id="DECISION_BLOCKED",
        handoff_id="HANDOFF_BLOCKED",
        session_id="SESSION_BLOCKED",
        closeout_id="CLOSEOUT_BLOCKED",
        request_id="REQ_BLOCKED",
        execution_id="EXEC_BLOCKED",
        task_id="TASK_BLOCKED",
        resolution_state="resolution_blocked",
        next_action="review_blockers",
        priority_level="high",
        dispatch_requested_at="2026-03-16T00:00:00Z",
    )

    retry_record, retry_verdict = evaluate_post_decision_dispatch(
        retry_request,
        retry_authorized=True,
        archive_authorized=False,
        escalation_required=False,
    )
    archive_record, archive_verdict = evaluate_post_decision_dispatch(
        archive_request,
        retry_authorized=False,
        archive_authorized=True,
        escalation_required=False,
    )
    blocked_record, blocked_verdict = evaluate_post_decision_dispatch(
        blocked_request,
        retry_authorized=False,
        archive_authorized=False,
        escalation_required=False,
    )

    assert retry_record.dispatch_state == "dispatch_retry"
    assert retry_verdict.retry_ready is True
    assert archive_record.dispatch_state == "dispatch_archive"
    assert archive_verdict.archival_ready is True
    assert blocked_record.dispatch_state == "dispatch_blocked"
    assert blocked_verdict.blocked is True
    assert blocked_verdict.requires_operator_review is True
    assert all(
        state in dispatch_states()
        for state in [retry_record.dispatch_state, archive_record.dispatch_state, blocked_record.dispatch_state]
    )


def test_post_decision_dispatch_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_post_decision_dispatch_dry_run(tmp_path / "aie_post_decision_dispatch_test")

    dispatch_request = json.loads(artifacts.post_decision_dispatch_request_path.read_text(encoding="utf-8"))
    dispatch_record = json.loads(artifacts.post_decision_dispatch_record_path.read_text(encoding="utf-8"))
    dispatch_verdict = json.loads(artifacts.post_decision_dispatch_verdict_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert dispatch_request["post_decision_dispatch_request"]["resolution_state"] == "resolved_archive"
    assert dispatch_record["post_decision_dispatch_record"]["dispatch_state"] == "dispatch_archive"
    assert dispatch_verdict["post_decision_dispatch_verdict"]["archival_ready"] is True
    assert dispatch_verdict["post_decision_dispatch_verdict"]["proceed_allowed"] is True
    assert "contract-only" in operator_report
    assert "No live bounded execution, no live dispatch workflow" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report