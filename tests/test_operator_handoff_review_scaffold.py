import json
from pathlib import Path

import pytest

from operator_handoff_review_dry_run import run_operator_handoff_review_dry_run
from orchestrator.operator_handoff_review_interface import (
    OperatorHandoffReviewRequestContract,
    determine_handoff_priority,
    evaluate_operator_handoff_review,
    handoff_priority_levels,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_operator_handoff_review_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "operator_handoff_review_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["operator_handoff_request"]["closeout_state"] == "closed_successfully"
    assert payload["operator_handoff_summary"]["priority_level"] == "low"
    assert payload["operator_handoff_review_targets"]["approval_items"] == ["archive:HANDOFF_SESSION_TASK_001"]
    assert payload["priority_levels"] == ["low", "medium", "high", "urgent"]


def test_operator_handoff_review_contracts_are_deterministic():
    successful_request = OperatorHandoffReviewRequestContract(
        handoff_id="HANDOFF_SUCCESS",
        session_id="SESSION_SUCCESS",
        closeout_id="CLOSEOUT_SUCCESS",
        request_id="REQ_SUCCESS",
        execution_id="EXEC_SUCCESS",
        task_id="TASK_SUCCESS",
        final_outcome="success",
        closeout_state="closed_successfully",
        operator_attention_required=False,
        review_requested_at="2026-03-16T00:00:00Z",
    )
    failed_request = OperatorHandoffReviewRequestContract(
        handoff_id="HANDOFF_FAILED",
        session_id="SESSION_FAILED",
        closeout_id="CLOSEOUT_FAILED",
        request_id="REQ_FAILED",
        execution_id="EXEC_FAILED",
        task_id="TASK_FAILED",
        final_outcome="failed",
        closeout_state="closed_failed",
        operator_attention_required=True,
        review_requested_at="2026-03-16T00:00:00Z",
    )

    success_summary, success_targets = evaluate_operator_handoff_review(
        successful_request,
        retained_artifacts=["ART_SUCCESS"],
        discarded_artifacts=[],
    )
    failed_summary, failed_targets = evaluate_operator_handoff_review(
        failed_request,
        retained_artifacts=["ART_FAILED"],
        discarded_artifacts=["ART_TMP_FAILED"],
    )

    assert determine_handoff_priority(successful_request) == "low"
    assert determine_handoff_priority(failed_request) == "urgent"
    assert success_summary.priority_level == "low"
    assert success_summary.requires_operator_decision is False
    assert success_targets.approval_items == ["archive:HANDOFF_SUCCESS"]
    assert failed_summary.priority_level == "urgent"
    assert failed_summary.requires_operator_decision is True
    assert failed_targets.retry_candidates == ["retry:TASK_FAILED"]
    assert "discarded_artifacts" in failed_targets.reviewable_items
    assert handoff_priority_levels() == ["low", "medium", "high", "urgent"]


def test_operator_handoff_review_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_operator_handoff_review_dry_run(tmp_path / "aie_operator_handoff_review_test")

    handoff_request = json.loads(artifacts.operator_handoff_request_path.read_text(encoding="utf-8"))
    handoff_summary = json.loads(artifacts.operator_handoff_summary_path.read_text(encoding="utf-8"))
    handoff_targets = json.loads(artifacts.operator_handoff_review_targets_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert handoff_request["operator_handoff_request"]["closeout_state"] == "closed_successfully"
    assert handoff_summary["operator_handoff_summary"]["priority_level"] == "low"
    assert handoff_summary["operator_handoff_summary"]["requires_operator_decision"] is False
    assert handoff_targets["operator_handoff_review_targets"]["archival_candidates"]
    assert "contract-only" in operator_report
    assert "No live bounded execution, no live handoff queue" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report