from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from execution_session_dry_run import run_execution_session_dry_run
from orchestrator.execution_artifact_interface import ArtifactRetentionRecordContract, ExecutionArtifactRecordContract
from orchestrator.execution_closeout_interface import ExecutionCloseoutRequestContract, evaluate_execution_closeout
from orchestrator.execution_session_interface import ExecutionSessionRequestContract, evaluate_execution_session
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json


SIMULATION_TIMESTAMP = "2026-03-14 20:00:00 -04:00 (Eastern Time — New York)"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_execution_closeout_test"


@dataclass(frozen=True)
class ExecutionCloseoutArtifacts:
    output_dir: Path
    execution_artifact_record_path: Path
    execution_artifact_retention_path: Path
    execution_closeout_request_path: Path
    execution_closeout_record_path: Path
    execution_closeout_verdict_path: Path
    operator_report_path: Path


def run_execution_closeout_dry_run(output_dir: Path | None = None) -> ExecutionCloseoutArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    with tempfile.TemporaryDirectory(prefix="aiec_") as temp_dir:
        session_artifacts = run_execution_session_dry_run(Path(temp_dir) / "s")
        session_request_payload = json.loads(session_artifacts.execution_session_request_path.read_text(encoding="utf-8"))
        session_request_raw = session_request_payload["execution_session_request"]

        session_request = ExecutionSessionRequestContract(
            session_id=session_request_raw["session_id"],
            permit_id=session_request_raw["permit_id"],
            authorization_id=session_request_raw["authorization_id"],
            activation_id=session_request_raw["activation_id"],
            request_id=session_request_raw["request_id"],
            execution_id=session_request_raw["execution_id"],
            task_id=session_request_raw["task_id"],
            selected_adapter_id=session_request_raw["selected_adapter_id"],
            permit_state=session_request_raw["permit_state"],
            issued_for=session_request_raw["issued_for"],
            policy_level=session_request_raw["policy_level"],
            dry_run=session_request_raw["dry_run"],
            session_requested_at=session_request_raw["session_requested_at"],
        )

        session_record, _, _, stop_conditions = evaluate_execution_session(
            session_request,
            "complete",
            opened_by="operator_placeholder",
            opened_timestamp=SIMULATION_TIMESTAMP,
            expires_at="2026-03-15 20:00:00 -04:00 (Eastern Time — New York)",
            scope_limit="dry_run_only",
            time_budget_seconds=300,
            notes="Dry-run session completed for deterministic closeout review.",
        )

    artifact_record = ExecutionArtifactRecordContract(
        artifact_id=f"ART_{session_request.task_id}_CLOSEOUT_001",
        session_id=session_request.session_id,
        execution_id=session_request.execution_id,
        task_id=session_request.task_id,
        artifact_type="operator_report",
        artifact_source="execution_closeout_dry_run",
        artifact_path=str((destination / "operator_report.md").as_posix()),
        produced_by_adapter=session_request.selected_adapter_id,
        produced_timestamp=SIMULATION_TIMESTAMP,
        retention_class="retained_output",
        cleanup_required=False,
        summary="Deterministic final operator report artifact for closeout review.",
    )
    artifact_retention = ArtifactRetentionRecordContract(
        artifact_id=artifact_record.artifact_id,
        retained=True,
        retention_reason="Final operator-facing closeout artifact should be retained for review.",
        retention_policy="closeout_record_retention",
        expires_at="2026-03-21 20:00:00 -04:00 (Eastern Time — New York)",
        cleanup_required=False,
        cleanup_reason="",
    )

    closeout_request = ExecutionCloseoutRequestContract(
        closeout_id=f"CLOSEOUT_{session_request.session_id}",
        session_id=session_request.session_id,
        permit_id=session_request.permit_id,
        authorization_id=session_request.authorization_id,
        request_id=session_request.request_id,
        execution_id=session_request.execution_id,
        task_id=session_request.task_id,
        session_state=session_record.session_state,
        stop_reason=stop_conditions.stop_reason,
        time_budget_seconds=session_record.time_budget_seconds,
        artifacts_summary_count=1,
        closeout_requested_at=SIMULATION_TIMESTAMP,
    )
    closeout_record, closeout_verdict = evaluate_execution_closeout(
        closeout_request,
        retained_artifacts=[artifact_record.artifact_id],
        discarded_artifacts=[],
        completed_at=SIMULATION_TIMESTAMP,
    )

    report_text = format_operator_report(
        summary="Execution closeout dry-run completed without any live closeout engine or runtime execution.",
        facts=[
            f"Session ID: {closeout_request.session_id}",
            f"Session state: {closeout_request.session_state}",
            f"Closeout state: {closeout_record.closeout_state}",
            f"Retained artifacts: {len(closeout_record.retained_artifacts)}",
            f"Cleanup required: {closeout_record.cleanup_required}",
        ],
        assumptions=[
            "Execution artifacts and session closeout remain contract-only boundaries after a bounded session ends.",
            "No live closeout engine, no live bounded execution, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Keep closeout limited to deterministic dry-run records until a future approved runtime phase exists.",
            "Use closeout outputs for contract validation only, not as evidence of live execution infrastructure.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    execution_artifact_record_path = destination / "execution_artifact_record.json"
    execution_artifact_retention_path = destination / "execution_artifact_retention.json"
    execution_closeout_request_path = destination / "execution_closeout_request.json"
    execution_closeout_record_path = destination / "execution_closeout_record.json"
    execution_closeout_verdict_path = destination / "execution_closeout_verdict.json"
    operator_report_path = destination / "operator_report.md"

    write_json(execution_artifact_record_path, {"execution_artifact_record": artifact_record.to_payload()})
    write_json(execution_artifact_retention_path, {"execution_artifact_retention": artifact_retention.to_payload()})
    write_json(execution_closeout_request_path, {"execution_closeout_request": closeout_request.to_payload()})
    write_json(execution_closeout_record_path, {"execution_closeout_record": closeout_record.to_payload()})
    write_json(execution_closeout_verdict_path, {"execution_closeout_verdict": closeout_verdict.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return ExecutionCloseoutArtifacts(
        output_dir=destination,
        execution_artifact_record_path=execution_artifact_record_path,
        execution_artifact_retention_path=execution_artifact_retention_path,
        execution_closeout_request_path=execution_closeout_request_path,
        execution_closeout_record_path=execution_closeout_record_path,
        execution_closeout_verdict_path=execution_closeout_verdict_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_execution_closeout_dry_run()
    print(f"execution_artifact_record: {artifacts.execution_artifact_record_path}")
    print(f"execution_artifact_retention: {artifacts.execution_artifact_retention_path}")
    print(f"execution_closeout_request: {artifacts.execution_closeout_request_path}")
    print(f"execution_closeout_record: {artifacts.execution_closeout_record_path}")
    print(f"execution_closeout_verdict: {artifacts.execution_closeout_verdict_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()