import json
from pathlib import Path

import pytest

from activation_review_dry_run import run_activation_review_dry_run
from orchestrator.activation_review_interface import (
    ActivationReviewDecisionContract,
    ActivationReviewRequestContract,
    activation_review_states,
    evaluate_activation_review,
    normalize_activation_review_state,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_activation_review_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "activation_review_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["activation_review_request"]["activation_state"] == "approval_required"
    assert payload["activation_review_decision"]["decision"] == "approve"
    assert payload["activation_verdict"]["result_state"] == "ready_for_dry_run"
    assert payload["state_transitions"]["approval_pending+deny"] == "denied"


def test_activation_review_request_and_decision_are_deterministic():
    request = ActivationReviewRequestContract(
        review_id="REV_001",
        activation_id="ACT_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        selected_adapter_id="adapter.testing.future",
        activation_state="approval_required",
        approval_required=True,
        blocked=True,
        blocked_reason="Awaiting review.",
        policy_level="architecture_only",
        dry_run=True,
    )
    decision = ActivationReviewDecisionContract(
        review_id="REV_001",
        decision="request_changes",
        reviewed_by="operator_placeholder",
        review_timestamp="2026-03-15T00:00:00Z",
        notes="Need tighter activation scope.",
    )

    assert request.to_payload()["activation_state"] == "approval_required"
    assert request.to_payload()["approval_required"] is True
    assert decision.to_payload()["decision"] == "request_changes"


def test_activation_review_state_transitions_are_deterministic():
    pending_request = ActivationReviewRequestContract(
        review_id="REV_002",
        activation_id="ACT_002",
        request_id="REQ_002",
        execution_id="EXEC_002",
        task_id="TASK_002",
        selected_adapter_id="adapter.testing.future",
        activation_state="approval_required",
        approval_required=True,
        blocked=True,
        blocked_reason="Awaiting approval.",
        policy_level="architecture_only",
        dry_run=True,
    )
    blocked_request = ActivationReviewRequestContract(
        review_id="REV_003",
        activation_id="ACT_003",
        request_id="REQ_003",
        execution_id="EXEC_003",
        task_id="TASK_003",
        selected_adapter_id="adapter.testing.future",
        activation_state="blocked",
        approval_required=False,
        blocked=True,
        blocked_reason="Policy blocked the activation.",
        policy_level="architecture_only",
        dry_run=True,
    )

    approve = ActivationReviewDecisionContract(
        review_id="REV_002",
        decision="approve",
        reviewed_by="operator_placeholder",
        review_timestamp="2026-03-15T00:00:00Z",
    )
    deny = ActivationReviewDecisionContract(
        review_id="REV_002",
        decision="deny",
        reviewed_by="operator_placeholder",
        review_timestamp="2026-03-15T00:00:00Z",
    )
    request_changes = ActivationReviewDecisionContract(
        review_id="REV_002",
        decision="request_changes",
        reviewed_by="operator_placeholder",
        review_timestamp="2026-03-15T00:00:00Z",
    )
    escalate = ActivationReviewDecisionContract(
        review_id="REV_002",
        decision="escalate",
        reviewed_by="operator_placeholder",
        review_timestamp="2026-03-15T00:00:00Z",
    )

    assert normalize_activation_review_state(pending_request) == "approval_pending"
    assert evaluate_activation_review(pending_request, approve).result_state == "ready_for_dry_run"
    assert evaluate_activation_review(pending_request, deny).result_state == "denied"
    assert evaluate_activation_review(pending_request, request_changes).result_state == "approval_pending"
    assert evaluate_activation_review(pending_request, escalate).result_state == "escalated"
    assert evaluate_activation_review(blocked_request, approve).result_state == "blocked"
    assert all(state in activation_review_states() for state in [
        evaluate_activation_review(pending_request, approve).result_state,
        evaluate_activation_review(pending_request, deny).result_state,
        evaluate_activation_review(pending_request, request_changes).result_state,
        evaluate_activation_review(pending_request, escalate).result_state,
        evaluate_activation_review(blocked_request, approve).result_state,
    ])


def test_activation_review_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_activation_review_dry_run(tmp_path / "aie_activation_review_test")

    review_request = json.loads(artifacts.activation_review_request_path.read_text(encoding="utf-8"))
    review_decision = json.loads(artifacts.activation_review_decision_path.read_text(encoding="utf-8"))
    review_verdict = json.loads(artifacts.activation_verdict_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert review_request["activation_review_request"]["activation_state"] == "approval_required"
    assert review_decision["activation_review_decision"]["decision"] == "approve"
    assert review_verdict["activation_verdict"]["result_state"] == "ready_for_dry_run"
    assert review_verdict["activation_verdict"]["ready_for_dry_run"] is True
    assert "contract-only boundary" in operator_report
    assert "No live bounded execution" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report