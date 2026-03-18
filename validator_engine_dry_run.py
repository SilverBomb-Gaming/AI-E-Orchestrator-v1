from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json
from orchestrator.validator_engine_interface import ValidationInputContract, evaluate_validation_result
from read_only_live_adapter_dry_run import ReadOnlyScenario, run_read_only_live_adapter_dry_run


SIMULATION_TIMESTAMP = "2026-03-15 20:00:00 -04:00 (Eastern Time — New York)"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_read_only_validation_test"
DEFAULT_FAILED_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_read_only_failed_test"


@dataclass(frozen=True)
class ValidatorEngineArtifacts:
    output_dir: Path
    read_only_request_path: Path
    read_only_response_path: Path
    validator_input_path: Path
    validator_record_path: Path
    validator_verdict_path: Path
    operator_report_path: Path


def run_validator_engine_dry_run(
    output_dir: Path | None = None,
    scenario: ReadOnlyScenario = "read_completed",
) -> ValidatorEngineArtifacts:
    destination = Path(output_dir) if output_dir else _default_output_dir_for_scenario(scenario)
    with tempfile.TemporaryDirectory(prefix="aiev_") as temp_dir:
        adapter_artifacts = run_read_only_live_adapter_dry_run(Path(temp_dir) / "ro", scenario=scenario)
        request_payload = json.loads(adapter_artifacts.read_only_request_path.read_text(encoding="utf-8"))
        response_payload = json.loads(adapter_artifacts.read_only_response_path.read_text(encoding="utf-8"))
        artifact_registry_payload = json.loads(adapter_artifacts.read_only_artifact_registry_path.read_text(encoding="utf-8"))

    request_raw = request_payload["read_only_request"]
    response_raw = response_payload["read_only_response"]
    artifacts_raw = artifact_registry_payload["read_only_artifacts"]

    validation_input = ValidationInputContract(
        validation_id=f"VALIDATION_{request_raw['execution_id']}",
        session_id=request_raw["session_id"],
        request_id=request_raw["request_id"],
        execution_id=request_raw["execution_id"],
        task_id=request_raw["task_id"],
        adapter_id=request_raw["adapter_id"],
        response_state=response_raw["response_state"],
        inspected_paths=response_raw["inspected_paths"],
        artifacts_generated=response_raw["artifacts_generated"],
        warnings=response_raw["warnings"],
        errors=response_raw["errors"],
        validated_at=SIMULATION_TIMESTAMP,
    )
    validation_record, validation_verdict = evaluate_validation_result(validation_input)
    primary_reason = response_raw["errors"][0] if response_raw["errors"] else ""

    report_text = format_operator_report(
        summary=(
            f"Validator engine dry-run classified bounded read-only adapter scenario {scenario} "
            "without any write-capable execution."
        ),
        facts=[
            f"Scenario: {scenario}",
            f"Validation ID: {validation_input.validation_id}",
            f"Response state: {validation_input.response_state}",
            f"Validation class: {validation_record.validation_class}",
            f"Retry recommended: {validation_verdict.retry_recommended}",
            f"Artifacts generated: {len(artifacts_raw)}",
            f"Primary reason: {primary_reason or 'none'}",
        ],
        assumptions=[
            "The validator engine remains classification-only even when consuming real bounded read-only adapter outputs.",
            "No write-capable live execution, no Unity invocation, no Blender invocation, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Use validator output to stabilize bounded read-only results before any future retry or escalation logic is added.",
            "Keep validation disconnected from runner.py and any write-capable runtime path.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    read_only_request_path = destination / "read_only_request.json"
    read_only_response_path = destination / "read_only_response.json"
    validator_input_path = destination / "validator_input.json"
    validator_record_path = destination / "validator_record.json"
    validator_verdict_path = destination / "validator_verdict.json"
    operator_report_path = destination / "operator_report.md"

    write_json(read_only_request_path, request_payload)
    write_json(read_only_response_path, response_payload)
    write_json(validator_input_path, {"validator_input": validation_input.to_payload()})
    write_json(validator_record_path, {"validator_record": validation_record.to_payload()})
    write_json(validator_verdict_path, {"validator_verdict": validation_verdict.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return ValidatorEngineArtifacts(
        output_dir=destination,
        read_only_request_path=read_only_request_path,
        read_only_response_path=read_only_response_path,
        validator_input_path=validator_input_path,
        validator_record_path=validator_record_path,
        validator_verdict_path=validator_verdict_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_validator_engine_dry_run()
    print(f"read_only_request: {artifacts.read_only_request_path}")
    print(f"read_only_response: {artifacts.read_only_response_path}")
    print(f"validator_input: {artifacts.validator_input_path}")
    print(f"validator_record: {artifacts.validator_record_path}")
    print(f"validator_verdict: {artifacts.validator_verdict_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()


def _default_output_dir_for_scenario(scenario: ReadOnlyScenario) -> Path:
    if scenario == "read_failed_retryable":
        return DEFAULT_FAILED_OUTPUT_DIR / "retryable_failure"
    if scenario == "read_failed_terminal":
        return DEFAULT_FAILED_OUTPUT_DIR / "terminal_failure"
    return DEFAULT_OUTPUT_DIR