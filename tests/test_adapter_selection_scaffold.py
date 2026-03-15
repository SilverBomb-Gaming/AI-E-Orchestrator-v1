import json
from pathlib import Path

import pytest

from orchestrator.adapter_selection_interface import SelectionInputContract, SelectionOutputContract


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_adapter_selection_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "adapter_selection_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["selection_input"]["dry_run"] is True
    assert payload["selection_output"]["state"] == "approval_pending"


def test_selection_input_contract_is_deterministic():
    contract = SelectionInputContract(
        selection_id="SEL_REQ_001",
        request_id="REQ_001",
        execution_id="EXEC_REQ_001",
        task_id="REQ_001_GRAPH",
        task_type="task_graph_emission",
        runtime_target="unity_editor",
        policy_level="architecture_only",
        dry_run=True,
        approval_required=True,
        expected_outputs=["task_graph.json"],
    )

    assert contract.to_payload()["selection_id"] == "SEL_REQ_001"
    assert contract.to_payload()["approval_required"] is True


def test_selection_output_contract_is_deterministic_and_explicit():
    contract = SelectionOutputContract(
        selection_id="SEL_REQ_001",
        chosen_adapter_id="adapter.unity.future",
        candidate_adapters=["adapter.unity.future", "adapter.testing.future"],
        selection_reason="Unity adapter best matches target.",
        blocked=True,
        blocked_reason="Live execution disabled.",
        approval_required=True,
        escalation_required=True,
        state="approval_pending",
    )

    payload = contract.to_payload()
    assert payload["blocked"] is True
    assert payload["state"] == "approval_pending"
    assert payload["escalation_required"] is True


def test_selection_states_cover_blocked_pending_denied():
    blocked = SelectionOutputContract(selection_id="SEL_1", chosen_adapter_id="", blocked=True, blocked_reason="blocked", state="blocked")
    pending = SelectionOutputContract(selection_id="SEL_2", chosen_adapter_id="adapter.unity.future", approval_required=True, state="approval_pending")
    denied = SelectionOutputContract(selection_id="SEL_3", chosen_adapter_id="", blocked=True, blocked_reason="denied", escalation_required=False, state="denied")

    assert blocked.to_payload()["state"] == "blocked"
    assert pending.to_payload()["state"] == "approval_pending"
    assert denied.to_payload()["state"] == "denied"