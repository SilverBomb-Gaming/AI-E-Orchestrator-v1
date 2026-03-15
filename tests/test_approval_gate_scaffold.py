import json
from pathlib import Path

import pytest

from orchestrator.approval_gate_interface import (
    ApprovalDecisionContract,
    ApprovalRequestContract,
    GateVerdictContract,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_approval_gate_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "approval_gate_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["approval_request"]["blocking"] is True
    assert payload["approval_decision"]["decision"] == "deferred"
    assert payload["gate_verdict"]["verdict"] == "approval_pending"


def test_approval_request_contract_is_deterministic():
    contract = ApprovalRequestContract(
        approval_id="APP_001",
        request_id="REQ_001",
        execution_id="EXEC_REQ_001",
        adapter_id="adapter.unity.future",
        approval_reason="Live execution disabled.",
        requested_action="Allow live run.",
        policy_level="architecture_only",
        blocking=True,
        safe_alternative="Remain in dry-run mode.",
    )

    payload = contract.to_payload()
    assert payload["blocking"] is True
    assert payload["safe_alternative"] == "Remain in dry-run mode."


def test_approval_decision_and_gate_verdict_are_deterministic():
    decision = ApprovalDecisionContract(
        approval_id="APP_001",
        decision="denied",
        decided_by="operator_placeholder",
        decided_at="2026-03-15T00:00:00Z",
        notes="Denied during architecture-only phase.",
    )
    verdict = GateVerdictContract(
        verdict="deny",
        proceed_allowed=False,
        blocked_until_approved=False,
        escalation_required=False,
        denial_reason="Live execution disabled.",
    )

    assert decision.to_payload()["decision"] == "denied"
    assert verdict.to_payload()["verdict"] == "deny"
    assert verdict.to_payload()["denial_reason"] == "Live execution disabled."


def test_blocked_pending_and_denied_states_are_explicit():
    pending = GateVerdictContract(
        verdict="approval_pending",
        proceed_allowed=False,
        blocked_until_approved=True,
        escalation_required=True,
        denial_reason="Await operator approval.",
    )
    denied = GateVerdictContract(
        verdict="deny",
        proceed_allowed=False,
        blocked_until_approved=False,
        escalation_required=False,
        denial_reason="Denied by policy.",
    )

    assert pending.to_payload()["blocked_until_approved"] is True
    assert pending.to_payload()["verdict"] == "approval_pending"
    assert denied.to_payload()["verdict"] == "deny"