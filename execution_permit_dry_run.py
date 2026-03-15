from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from activation_authorization_dry_run import run_activation_authorization_dry_run
from orchestrator.execution_permit_interface import ExecutionPermitRequestContract, evaluate_execution_permit
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json


SIMULATION_TIMESTAMP = "2026-03-15T00:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_execution_permit_test"


@dataclass(frozen=True)
class ExecutionPermitArtifacts:
    output_dir: Path
    execution_permit_request_path: Path
    execution_permit_record_path: Path
    execution_permit_verdict_path: Path
    operator_report_path: Path


def run_execution_permit_dry_run(output_dir: Path | None = None) -> ExecutionPermitArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    authorization_artifacts = run_activation_authorization_dry_run(destination / "activation_authorization_source")
    authorization_request_payload = json.loads(
        authorization_artifacts.activation_authorization_request_path.read_text(encoding="utf-8")
    )
    authorization_record_payload = json.loads(
        authorization_artifacts.activation_authorization_record_path.read_text(encoding="utf-8")
    )

    authorization_request = authorization_request_payload["activation_authorization_request"]
    authorization_record = authorization_record_payload["activation_authorization_record"]

    permit_request = ExecutionPermitRequestContract(
        permit_id=f"PERMIT_{authorization_request['activation_id']}",
        authorization_id=authorization_request["authorization_id"],
        activation_id=authorization_request["activation_id"],
        request_id=authorization_request["request_id"],
        execution_id=authorization_request["execution_id"],
        task_id=authorization_request["task_id"],
        selected_adapter_id=authorization_request["selected_adapter_id"],
        authorization_state=authorization_record["authorization_state"],
        authorized_for=authorization_record["authorized_for"],
        policy_level=authorization_request["policy_level"],
        dry_run=authorization_request["dry_run"],
        permit_requested_at=SIMULATION_TIMESTAMP,
    )

    permit_record, permit_verdict = evaluate_execution_permit(
        permit_request,
        "approve",
        issued_by="operator_placeholder",
        issued_timestamp=SIMULATION_TIMESTAMP,
        expires_at="2026-03-16T00:00:00Z",
        notes="Dry-run permit issues a bounded dry-run ticket only.",
    )

    report_text = format_operator_report(
        summary="Execution permit dry-run completed without any live permit engine or runtime execution.",
        facts=[
            f"Permit ID: {permit_request.permit_id}",
            f"Authorization state: {permit_request.authorization_state}",
            f"Permit state: {permit_record.permit_state}",
            f"Proceed allowed: {permit_verdict.proceed_allowed}",
        ],
        assumptions=[
            "Execution permits remain a contract-only boundary between authorization and any future bounded execution.",
            "No live permit engine, no live bounded execution, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Keep execution permits limited to deterministic dry-run records until a future approved runtime phase exists.",
            "Use permit outputs for contract validation only, not as evidence of live execution infrastructure.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    execution_permit_request_path = destination / "execution_permit_request.json"
    execution_permit_record_path = destination / "execution_permit_record.json"
    execution_permit_verdict_path = destination / "execution_permit_verdict.json"
    operator_report_path = destination / "operator_report.md"

    write_json(execution_permit_request_path, {"execution_permit_request": permit_request.to_payload()})
    write_json(execution_permit_record_path, {"execution_permit_record": permit_record.to_payload()})
    write_json(execution_permit_verdict_path, {"execution_permit_verdict": permit_verdict.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return ExecutionPermitArtifacts(
        output_dir=destination,
        execution_permit_request_path=execution_permit_request_path,
        execution_permit_record_path=execution_permit_record_path,
        execution_permit_verdict_path=execution_permit_verdict_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_execution_permit_dry_run()
    print(f"execution_permit_request: {artifacts.execution_permit_request_path}")
    print(f"execution_permit_record: {artifacts.execution_permit_record_path}")
    print(f"execution_permit_verdict: {artifacts.execution_permit_verdict_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()