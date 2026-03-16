import json
from pathlib import Path

import pytest

from orchestrator.validator_engine_interface import ValidationInputContract, evaluate_validation_result, validation_classes
from validator_engine_dry_run import run_validator_engine_dry_run


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_validator_engine_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "validator_engine_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["validator_input"]["response_state"] == "read_completed"
    assert payload["validator_record"]["validation_class"] == "passed"
    assert payload["validator_verdict"]["finalized"] is True
    assert payload["validation_classes"] == [
        "passed",
        "passed_with_warnings",
        "partial_success",
        "retryable_failure",
        "blocked",
        "unsupported",
        "terminal_failure",
    ]


def test_validator_engine_classification_is_deterministic():
    partial_input = ValidationInputContract(
        validation_id="VALIDATION_PARTIAL",
        session_id="SESSION_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        response_state="read_partial",
        inspected_paths=["orchestrator/report_contract.py"],
        artifacts_generated=["RO_ART_001"],
        warnings=[],
        errors=["Target extension is not allowed: .md"],
        validated_at="2026-03-16T00:00:00Z",
    )
    denied_input = ValidationInputContract(
        validation_id="VALIDATION_DENIED",
        session_id="SESSION_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        response_state="read_denied",
        inspected_paths=[],
        artifacts_generated=[],
        warnings=[],
        errors=["Target is outside the approved roots"],
        validated_at="2026-03-16T00:00:00Z",
    )
    retryable_failed_input = ValidationInputContract(
        validation_id="VALIDATION_FAILED_RETRYABLE",
        session_id="SESSION_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        response_state="read_failed",
        inspected_paths=[],
        artifacts_generated=["RO_ART_FAIL_001"],
        warnings=["Retryable failure remained local-only and did not read any target bytes."],
        errors=[
            "RETRYABLE: Simulated transient bounded access issue on an approved target; retry within the same read-only scope may succeed."
        ],
        validated_at="2026-03-16T00:00:00Z",
    )
    terminal_failed_input = ValidationInputContract(
        validation_id="VALIDATION_FAILED_TERMINAL",
        session_id="SESSION_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        response_state="read_failed",
        inspected_paths=[],
        artifacts_generated=["RO_ART_FAIL_001"],
        warnings=[],
        errors=[
            "TERMINAL: Simulated structurally invalid bounded read request; retrying the same request cannot succeed within current policy."
        ],
        validated_at="2026-03-16T00:00:00Z",
    )

    partial_record, partial_verdict = evaluate_validation_result(partial_input)
    denied_record, denied_verdict = evaluate_validation_result(denied_input)
    retryable_record, retryable_verdict = evaluate_validation_result(retryable_failed_input)
    terminal_record, terminal_verdict = evaluate_validation_result(terminal_failed_input)

    assert partial_record.validation_class == "partial_success"
    assert partial_verdict.retry_recommended is True
    assert denied_record.validation_class == "blocked"
    assert denied_record.validation_state == "validation_blocked"
    assert denied_verdict.retry_recommended is False
    assert denied_verdict.operator_attention_required is True
    assert retryable_record.validation_class == "retryable_failure"
    assert retryable_verdict.retry_recommended is True
    assert terminal_record.validation_class == "terminal_failure"
    assert terminal_verdict.retry_recommended is False
    required_classes = {
        "passed",
        "passed_with_warnings",
        "partial_success",
        "blocked",
        "retryable_failure",
        "terminal_failure",
    }
    assert required_classes.issubset(set(validation_classes()))


def test_validator_engine_dry_run_writes_deterministic_outputs(tmp_path):
    artifacts = run_validator_engine_dry_run(tmp_path / "aie_read_only_validation_test")

    read_only_request = json.loads(artifacts.read_only_request_path.read_text(encoding="utf-8"))
    read_only_response = json.loads(artifacts.read_only_response_path.read_text(encoding="utf-8"))
    validator_input = json.loads(artifacts.validator_input_path.read_text(encoding="utf-8"))
    validator_record = json.loads(artifacts.validator_record_path.read_text(encoding="utf-8"))
    validator_verdict = json.loads(artifacts.validator_verdict_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert read_only_request["read_only_request"]["adapter_id"] == "local_read_only_adapter"
    assert read_only_response["read_only_response"]["response_state"] == "read_completed"
    assert validator_input["validator_input"]["response_state"] == "read_completed"
    assert validator_record["validator_record"]["validation_class"] == "passed"
    assert validator_verdict["validator_verdict"]["finalized"] is True
    assert "classification-only" in operator_report
    assert "No write-capable live execution, no Unity invocation" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report


def test_validator_engine_dry_run_partial_scenario_is_deterministic(tmp_path):
    artifacts = run_validator_engine_dry_run(
        tmp_path / "aie_read_only_validation_test_partial",
        scenario="read_partial",
    )

    read_only_response = json.loads(artifacts.read_only_response_path.read_text(encoding="utf-8"))
    validator_input = json.loads(artifacts.validator_input_path.read_text(encoding="utf-8"))
    validator_record = json.loads(artifacts.validator_record_path.read_text(encoding="utf-8"))
    validator_verdict = json.loads(artifacts.validator_verdict_path.read_text(encoding="utf-8"))

    assert read_only_response["read_only_response"]["response_state"] == "read_partial"
    assert validator_input["validator_input"]["response_state"] == "read_partial"
    assert validator_record["validator_record"]["validation_class"] == "partial_success"
    assert validator_verdict["validator_verdict"]["retry_recommended"] is True


def test_validator_engine_dry_run_denied_scenario_is_deterministic(tmp_path):
    artifacts = run_validator_engine_dry_run(
        tmp_path / "aie_read_only_validation_test_denied",
        scenario="read_denied",
    )

    read_only_response = json.loads(artifacts.read_only_response_path.read_text(encoding="utf-8"))
    validator_input = json.loads(artifacts.validator_input_path.read_text(encoding="utf-8"))
    validator_record = json.loads(artifacts.validator_record_path.read_text(encoding="utf-8"))
    validator_verdict = json.loads(artifacts.validator_verdict_path.read_text(encoding="utf-8"))

    assert read_only_response["read_only_response"]["response_state"] == "read_denied"
    assert validator_input["validator_input"]["response_state"] == "read_denied"
    assert validator_record["validator_record"]["validation_class"] == "blocked"
    assert validator_record["validator_record"]["validation_state"] == "validation_blocked"
    assert validator_verdict["validator_verdict"]["retry_recommended"] is False


def test_validator_engine_dry_run_retryable_failed_scenario_is_deterministic(tmp_path):
    artifacts = run_validator_engine_dry_run(
        tmp_path / "aie_read_only_failed_test" / "retryable_failure",
        scenario="read_failed_retryable",
    )

    read_only_response = json.loads(artifacts.read_only_response_path.read_text(encoding="utf-8"))
    validator_record = json.loads(artifacts.validator_record_path.read_text(encoding="utf-8"))
    validator_verdict = json.loads(artifacts.validator_verdict_path.read_text(encoding="utf-8"))

    assert read_only_response["read_only_response"]["response_state"] == "read_failed"
    assert validator_record["validator_record"]["validation_class"] == "retryable_failure"
    assert validator_record["validator_record"]["notes"].startswith("Retryable bounded read failure:")
    assert validator_verdict["validator_verdict"]["retry_recommended"] is True


def test_validator_engine_dry_run_terminal_failed_scenario_is_deterministic(tmp_path):
    artifacts = run_validator_engine_dry_run(
        tmp_path / "aie_read_only_failed_test" / "terminal_failure",
        scenario="read_failed_terminal",
    )

    read_only_response = json.loads(artifacts.read_only_response_path.read_text(encoding="utf-8"))
    validator_record = json.loads(artifacts.validator_record_path.read_text(encoding="utf-8"))
    validator_verdict = json.loads(artifacts.validator_verdict_path.read_text(encoding="utf-8"))

    assert read_only_response["read_only_response"]["response_state"] == "read_failed"
    assert validator_record["validator_record"]["validation_class"] == "terminal_failure"
    assert validator_record["validator_record"]["notes"].startswith("Terminal bounded read failure:")
    assert validator_verdict["validator_verdict"]["retry_recommended"] is False
