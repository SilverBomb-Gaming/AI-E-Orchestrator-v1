import json
from pathlib import Path

import pytest

from orchestrator.post_dispatch_audit_interface import (
    PostDispatchAuditRequestContract,
    audit_states,
    evaluate_post_dispatch_audit,
)
from post_dispatch_audit_dry_run import run_post_dispatch_audit_dry_run


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_post_dispatch_audit_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "post_dispatch_audit_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["post_dispatch_audit_request"]["dispatch_state"] == "dispatch_archive"
    assert payload["post_dispatch_audit_record"]["audit_state"] == "audit_archived"
    assert payload["post_dispatch_audit_verdict"]["archive_ready"] is True
    assert payload["audit_transitions"]["dispatch_blocked"] == ["audit_blocked"]


def test_post_dispatch_audit_transitions_are_deterministic():
    retry_request = PostDispatchAuditRequestContract(
        audit_id="AUDIT_RETRY",
        dispatch_id="DISPATCH_RETRY",
        decision_id="DECISION_RETRY",
        handoff_id="HANDOFF_RETRY",
        session_id="SESSION_RETRY",
        request_id="REQ_RETRY",
        execution_id="EXEC_RETRY",
        task_id="TASK_RETRY",
        dispatch_state="dispatch_retry",
        dispatch_target="retry_queue_placeholder",
        priority_level="urgent",
        audit_requested_at="2026-03-16T00:00:00Z",
    )
    archive_request = PostDispatchAuditRequestContract(
        audit_id="AUDIT_ARCHIVE",
        dispatch_id="DISPATCH_ARCHIVE",
        decision_id="DECISION_ARCHIVE",
        handoff_id="HANDOFF_ARCHIVE",
        session_id="SESSION_ARCHIVE",
        request_id="REQ_ARCHIVE",
        execution_id="EXEC_ARCHIVE",
        task_id="TASK_ARCHIVE",
        dispatch_state="dispatch_archive",
        dispatch_target="archive_store_placeholder",
        priority_level="low",
        audit_requested_at="2026-03-16T00:00:00Z",
    )
    blocked_request = PostDispatchAuditRequestContract(
        audit_id="AUDIT_BLOCKED",
        dispatch_id="DISPATCH_BLOCKED",
        decision_id="DECISION_BLOCKED",
        handoff_id="HANDOFF_BLOCKED",
        session_id="SESSION_BLOCKED",
        request_id="REQ_BLOCKED",
        execution_id="EXEC_BLOCKED",
        task_id="TASK_BLOCKED",
        dispatch_state="dispatch_blocked",
        dispatch_target="blocked_review_placeholder",
        priority_level="high",
        audit_requested_at="2026-03-16T00:00:00Z",
    )

    retry_record, retry_verdict = evaluate_post_dispatch_audit(retry_request)
    archive_record, archive_verdict = evaluate_post_dispatch_audit(archive_request)
    blocked_record, blocked_verdict = evaluate_post_dispatch_audit(blocked_request)

    assert retry_record.audit_state == "audit_passed"
    assert retry_verdict.retry_ready is True
    assert archive_record.audit_state == "audit_archived"
    assert archive_verdict.archive_ready is True
    assert blocked_record.audit_state == "audit_blocked"
    assert blocked_verdict.blocked is True
    assert blocked_verdict.requires_operator_review is True
    assert all(
        state in audit_states()
        for state in [retry_record.audit_state, archive_record.audit_state, blocked_record.audit_state]
    )


def test_post_dispatch_audit_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_post_dispatch_audit_dry_run(tmp_path / "aie_post_dispatch_audit_test")

    audit_request = json.loads(artifacts.post_dispatch_audit_request_path.read_text(encoding="utf-8"))
    audit_record = json.loads(artifacts.post_dispatch_audit_record_path.read_text(encoding="utf-8"))
    audit_verdict = json.loads(artifacts.post_dispatch_audit_verdict_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert audit_request["post_dispatch_audit_request"]["dispatch_state"] == "dispatch_archive"
    assert audit_record["post_dispatch_audit_record"]["audit_state"] == "audit_archived"
    assert audit_verdict["post_dispatch_audit_verdict"]["archive_ready"] is True
    assert audit_verdict["post_dispatch_audit_verdict"]["proceed_allowed"] is True
    assert "contract-only" in operator_report
    assert "No live bounded execution, no live audit workflow" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report