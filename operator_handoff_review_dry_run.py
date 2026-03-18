from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from execution_closeout_dry_run import run_execution_closeout_dry_run
from orchestrator.operator_handoff_review_interface import (
    OperatorHandoffReviewRequestContract,
    evaluate_operator_handoff_review,
)
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json


SIMULATION_TIMESTAMP = "2026-03-15 20:00:00 -04:00 (Eastern Time — New York)"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_operator_handoff_review_test"


@dataclass(frozen=True)
class OperatorHandoffReviewArtifacts:
    output_dir: Path
    operator_handoff_request_path: Path
    operator_handoff_summary_path: Path
    operator_handoff_review_targets_path: Path
    operator_report_path: Path


def run_operator_handoff_review_dry_run(output_dir: Path | None = None) -> OperatorHandoffReviewArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    with tempfile.TemporaryDirectory(prefix="aieh_") as temp_dir:
        closeout_artifacts = run_execution_closeout_dry_run(Path(temp_dir) / "c")
        closeout_request_payload = json.loads(closeout_artifacts.execution_closeout_request_path.read_text(encoding="utf-8"))
        closeout_record_payload = json.loads(closeout_artifacts.execution_closeout_record_path.read_text(encoding="utf-8"))
        artifact_record_payload = json.loads(closeout_artifacts.execution_artifact_record_path.read_text(encoding="utf-8"))

    closeout_request_raw = closeout_request_payload["execution_closeout_request"]
    closeout_record_raw = closeout_record_payload["execution_closeout_record"]
    artifact_record_raw = artifact_record_payload["execution_artifact_record"]

    handoff_request = OperatorHandoffReviewRequestContract(
        handoff_id=f"HANDOFF_{closeout_request_raw['session_id']}",
        session_id=closeout_request_raw["session_id"],
        closeout_id=closeout_request_raw["closeout_id"],
        request_id=closeout_request_raw["request_id"],
        execution_id=closeout_request_raw["execution_id"],
        task_id=closeout_request_raw["task_id"],
        final_outcome=closeout_record_raw["final_outcome"],
        closeout_state=closeout_record_raw["closeout_state"],
        operator_attention_required=closeout_record_raw["operator_attention_required"],
        review_requested_at=SIMULATION_TIMESTAMP,
    )
    handoff_summary, handoff_targets = evaluate_operator_handoff_review(
        handoff_request,
        retained_artifacts=[artifact_record_raw["artifact_id"]],
        discarded_artifacts=closeout_record_raw["discarded_artifacts"],
    )

    report_text = format_operator_report(
        summary="Operator handoff review dry-run completed as a contract-only packaging step without any live handoff infrastructure.",
        facts=[
            f"Handoff ID: {handoff_request.handoff_id}",
            f"Closeout state: {handoff_request.closeout_state}",
            f"Priority level: {handoff_summary.priority_level}",
            f"Requires operator decision: {handoff_summary.requires_operator_decision}",
            f"Archival candidates: {len(handoff_targets.archival_candidates)}",
        ],
        assumptions=[
            "Operator handoff review remains a contract-only layer for deterministic morning review packaging.",
            "No live bounded execution, no live handoff queue, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Use the handoff package for architecture validation only until a future approved runtime phase exists.",
            "Keep operator review packaging disconnected from runner.py and any execution semantics.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    operator_handoff_request_path = destination / "operator_handoff_request.json"
    operator_handoff_summary_path = destination / "operator_handoff_summary.json"
    operator_handoff_review_targets_path = destination / "operator_handoff_review_targets.json"
    operator_report_path = destination / "operator_report.md"

    write_json(operator_handoff_request_path, {"operator_handoff_request": handoff_request.to_payload()})
    write_json(operator_handoff_summary_path, {"operator_handoff_summary": handoff_summary.to_payload()})
    write_json(operator_handoff_review_targets_path, {"operator_handoff_review_targets": handoff_targets.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return OperatorHandoffReviewArtifacts(
        output_dir=destination,
        operator_handoff_request_path=operator_handoff_request_path,
        operator_handoff_summary_path=operator_handoff_summary_path,
        operator_handoff_review_targets_path=operator_handoff_review_targets_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_operator_handoff_review_dry_run()
    print(f"operator_handoff_request: {artifacts.operator_handoff_request_path}")
    print(f"operator_handoff_summary: {artifacts.operator_handoff_summary_path}")
    print(f"operator_handoff_review_targets: {artifacts.operator_handoff_review_targets_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()