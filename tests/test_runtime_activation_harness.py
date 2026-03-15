import json
from pathlib import Path

import pytest

from runtime_activation_harness import activation_states, run_runtime_activation_harness


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_runtime_activation_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "runtime_activation_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["activation_input"]["execution_input"]["dry_run"] is True
    assert payload["selection_output"]["selection_output"]["state"] == "approval_pending"
    assert payload["approval_verdict"]["gate_verdict"]["verdict"] == "approval_pending"
    assert payload["activation_result"]["activation_status"] == "approval_required"
    assert payload["activation_result"]["report_handoff_ready"] is True


def test_runtime_activation_harness_writes_deterministic_outputs(tmp_path):
    artifacts = run_runtime_activation_harness(tmp_path / "aie_runtime_activation_test")

    activation_input = json.loads(artifacts.activation_input_path.read_text(encoding="utf-8"))
    selection_output = json.loads(artifacts.selection_output_path.read_text(encoding="utf-8"))
    approval_verdict = json.loads(artifacts.approval_verdict_path.read_text(encoding="utf-8"))
    activation_result = json.loads(artifacts.activation_result_path.read_text(encoding="utf-8"))
    artifact_persistence = json.loads(artifacts.artifact_persistence_result_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert activation_input["execution_input"]["dry_run"] is True
    assert activation_input["execution_input"]["runtime_target_placeholder"] == "unity_editor"
    assert [item["adapter_id"] for item in activation_input["adapter_registry"]["discoveries"]] == [
        "adapter.testing.future",
        "adapter.unity.future",
    ]
    assert selection_output["selection_output"]["chosen_adapter_id"] == "adapter.testing.future"
    assert selection_output["selection_output"]["state"] == "approval_pending"
    assert approval_verdict["gate_verdict"]["verdict"] == "approval_pending"
    assert approval_verdict["approval_decision"]["decision"] == "deferred"
    assert activation_result["activation_result"]["activation_status"] in activation_states()
    assert activation_result["activation_result"]["activation_status"] == "approval_required"
    assert activation_result["activation_result"]["blocked"] is True
    assert activation_result["activation_result"]["report_handoff_ready"] is True
    assert activation_result["report_handoff"]["required_report_sections"] == [
        "SUMMARY",
        "FACTS",
        "ASSUMPTIONS",
        "RECOMMENDATIONS",
        "TIMESTAMP",
    ]
    assert len(artifact_persistence["artifact_registrations"]) == 2
    assert all(result["stored"] is False for result in artifact_persistence["persistence_results"])
    assert "without invoking any live adapters" in operator_report
    assert "No live bounded execution" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report