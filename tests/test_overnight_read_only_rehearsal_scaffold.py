import json
from pathlib import Path

import pytest

from overnight_read_only_rehearsal_dry_run import run_overnight_read_only_rehearsal


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_overnight_read_only_rehearsal_writes_deterministic_outputs(tmp_path):
    artifacts = run_overnight_read_only_rehearsal(tmp_path / "aie_overnight_read_only_rehearsal")

    rehearsal_request = json.loads(artifacts.rehearsal_request_path.read_text(encoding="utf-8"))["rehearsal_request"]
    execution_summary = json.loads(artifacts.rehearsal_execution_summary_path.read_text(encoding="utf-8"))[
        "rehearsal_execution_summary"
    ]
    validator_summary = json.loads(artifacts.rehearsal_validator_summary_path.read_text(encoding="utf-8"))[
        "rehearsal_validator_summary"
    ]
    handoff_summary = json.loads(artifacts.rehearsal_handoff_summary_path.read_text(encoding="utf-8"))[
        "rehearsal_handoff_summary"
    ]
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert rehearsal_request["mode"] == "overnight_read_only_rehearsal"
    assert rehearsal_request["variant"] == "retryable_failure"
    assert rehearsal_request["approved_scope"]["allowed_extensions"] == [".py"]
    assert rehearsal_request["approved_scope"]["max_file_count"] == 2
    assert rehearsal_request["scenarios"][0]["scenario"] == "read_completed"
    assert rehearsal_request["scenarios"][1]["scenario"] == "read_failed_retryable"
    assert rehearsal_request["live_production"] is False

    assert execution_summary["success_count"] == 1
    assert execution_summary["partial_count"] == 0
    assert execution_summary["denied_count"] == 0
    assert execution_summary["failed_count"] == 1
    assert execution_summary["blocked_count"] == 0
    assert execution_summary["results"][1]["validation_class"] == "retryable_failure"

    assert validator_summary["validation_classes_exercised"] == ["passed", "retryable_failure"]
    assert validator_summary["retry_recommended_for"] == ["read_failed_retryable"]
    assert validator_summary["terminal_failure_scenarios"] == []

    assert handoff_summary["succeeded"] == ["read_completed"]
    assert handoff_summary["failed"] == ["read_failed_retryable"]
    assert handoff_summary["partial"] == []
    assert handoff_summary["denied"] == []
    assert handoff_summary["operator_attention_level"] == "medium"
    assert handoff_summary["safe_next_steps"][0].startswith("Repeat retryable failed reads")
    assert handoff_summary["ready_for_additional_bounded_rehearsal"] is True
    assert handoff_summary["ready_for_live_overnight_production"] is False

    assert "rehearsal only, not live overnight production" in operator_report
    assert "Ready for live overnight production: False" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report


def test_overnight_read_only_rehearsal_terminal_variant_writes_deterministic_outputs(tmp_path):
    artifacts = run_overnight_read_only_rehearsal(
        tmp_path / "aie_overnight_read_only_rehearsal_terminal",
        variant="terminal_failure",
    )

    rehearsal_request = json.loads(artifacts.rehearsal_request_path.read_text(encoding="utf-8"))["rehearsal_request"]
    execution_summary = json.loads(artifacts.rehearsal_execution_summary_path.read_text(encoding="utf-8"))[
        "rehearsal_execution_summary"
    ]
    validator_summary = json.loads(artifacts.rehearsal_validator_summary_path.read_text(encoding="utf-8"))[
        "rehearsal_validator_summary"
    ]
    handoff_summary = json.loads(artifacts.rehearsal_handoff_summary_path.read_text(encoding="utf-8"))[
        "rehearsal_handoff_summary"
    ]
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert rehearsal_request["variant"] == "terminal_failure"
    assert rehearsal_request["scenarios"][1]["scenario"] == "read_failed_terminal"

    assert execution_summary["variant"] == "terminal_failure"
    assert execution_summary["results"][1]["validation_class"] == "terminal_failure"
    assert execution_summary["results"][1]["retry_recommended"] is False

    assert validator_summary["variant"] == "terminal_failure"
    assert validator_summary["validation_classes_exercised"] == ["passed", "terminal_failure"]
    assert validator_summary["retry_recommended_for"] == []
    assert validator_summary["terminal_failure_scenarios"] == ["read_failed_terminal"]

    assert handoff_summary["variant"] == "terminal_failure"
    assert handoff_summary["failed"] == ["read_failed_terminal"]
    assert handoff_summary["operator_attention_level"] == "high"
    assert handoff_summary["safe_next_steps"][0].startswith("Do not retry the same bounded request")
    assert handoff_summary["ready_for_additional_bounded_rehearsal"] is True
    assert handoff_summary["ready_for_live_overnight_production"] is False

    assert "variant terminal_failure" in operator_report
    assert "Ready for live overnight production: False" in operator_report