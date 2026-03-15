from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from execution_permit_dry_run import run_execution_permit_dry_run
from orchestrator.execution_session_interface import ExecutionSessionRequestContract, evaluate_execution_session
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json


SIMULATION_TIMESTAMP = "2026-03-15T00:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_execution_session_test"


@dataclass(frozen=True)
class ExecutionSessionArtifacts:
    output_dir: Path
    execution_session_request_path: Path
    execution_session_record_path: Path
    execution_session_verdict_path: Path
    execution_session_heartbeat_path: Path
    execution_session_stop_conditions_path: Path
    operator_report_path: Path


def run_execution_session_dry_run(output_dir: Path | None = None) -> ExecutionSessionArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    permit_artifacts = run_execution_permit_dry_run(destination / "execution_permit_source")
    permit_request_payload = json.loads(permit_artifacts.execution_permit_request_path.read_text(encoding="utf-8"))
    permit_record_payload = json.loads(permit_artifacts.execution_permit_record_path.read_text(encoding="utf-8"))

    permit_request = permit_request_payload["execution_permit_request"]
    permit_record = permit_record_payload["execution_permit_record"]

    session_request = ExecutionSessionRequestContract(
        session_id=f"SESSION_{permit_request['activation_id']}",
        permit_id=permit_request["permit_id"],
        authorization_id=permit_request["authorization_id"],
        activation_id=permit_request["activation_id"],
        request_id=permit_request["request_id"],
        execution_id=permit_request["execution_id"],
        task_id=permit_request["task_id"],
        selected_adapter_id=permit_request["selected_adapter_id"],
        permit_state=permit_record["permit_state"],
        issued_for=permit_record["issued_for"],
        policy_level=permit_request["policy_level"],
        dry_run=permit_request["dry_run"],
        session_requested_at=SIMULATION_TIMESTAMP,
    )

    session_record, session_verdict, session_heartbeat, stop_conditions = evaluate_execution_session(
        session_request,
        "approve",
        opened_by="operator_placeholder",
        opened_timestamp=SIMULATION_TIMESTAMP,
        expires_at="2026-03-16T00:00:00Z",
        scope_limit="dry_run_only",
        time_budget_seconds=300,
        notes="Dry-run session opens a bounded dry-run execution window only.",
    )

    report_text = format_operator_report(
        summary="Execution session dry-run completed without any live session engine or runtime execution.",
        facts=[
            f"Session ID: {session_request.session_id}",
            f"Permit state: {session_request.permit_state}",
            f"Session state: {session_record.session_state}",
            f"Proceed allowed: {session_verdict.proceed_allowed}",
            f"Heartbeat status: {session_heartbeat.status}",
        ],
        assumptions=[
            "Execution sessions remain a contract-only boundary between issued permits and any future bounded execution.",
            "No live session engine, no live bounded execution, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Keep execution sessions limited to deterministic dry-run records until a future approved runtime phase exists.",
            "Use session outputs for contract validation only, not as evidence of live execution infrastructure.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    execution_session_request_path = destination / "execution_session_request.json"
    execution_session_record_path = destination / "execution_session_record.json"
    execution_session_verdict_path = destination / "execution_session_verdict.json"
    execution_session_heartbeat_path = destination / "execution_session_heartbeat.json"
    execution_session_stop_conditions_path = destination / "execution_session_stop_conditions.json"
    operator_report_path = destination / "operator_report.md"

    write_json(execution_session_request_path, {"execution_session_request": session_request.to_payload()})
    write_json(execution_session_record_path, {"execution_session_record": session_record.to_payload()})
    write_json(execution_session_verdict_path, {"execution_session_verdict": session_verdict.to_payload()})
    write_json(execution_session_heartbeat_path, {"execution_session_heartbeat": session_heartbeat.to_payload()})
    write_json(execution_session_stop_conditions_path, {"execution_session_stop_conditions": stop_conditions.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return ExecutionSessionArtifacts(
        output_dir=destination,
        execution_session_request_path=execution_session_request_path,
        execution_session_record_path=execution_session_record_path,
        execution_session_verdict_path=execution_session_verdict_path,
        execution_session_heartbeat_path=execution_session_heartbeat_path,
        execution_session_stop_conditions_path=execution_session_stop_conditions_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_execution_session_dry_run()
    print(f"execution_session_request: {artifacts.execution_session_request_path}")
    print(f"execution_session_record: {artifacts.execution_session_record_path}")
    print(f"execution_session_verdict: {artifacts.execution_session_verdict_path}")
    print(f"execution_session_heartbeat: {artifacts.execution_session_heartbeat_path}")
    print(f"execution_session_stop_conditions: {artifacts.execution_session_stop_conditions_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()