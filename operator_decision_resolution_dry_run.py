from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from operator_handoff_review_dry_run import run_operator_handoff_review_dry_run
from orchestrator.operator_decision_resolution_interface import (
    OperatorDecisionRequestContract,
    OperatorDecisionResponseContract,
    evaluate_operator_decision_resolution,
)
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json


SIMULATION_TIMESTAMP = "2026-03-16T00:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_operator_decision_resolution_test"


@dataclass(frozen=True)
class OperatorDecisionResolutionArtifacts:
    output_dir: Path
    operator_decision_request_path: Path
    operator_decision_response_path: Path
    operator_decision_resolution_path: Path
    operator_report_path: Path


def run_operator_decision_resolution_dry_run(output_dir: Path | None = None) -> OperatorDecisionResolutionArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    with tempfile.TemporaryDirectory(prefix="aied_") as temp_dir:
        handoff_artifacts = run_operator_handoff_review_dry_run(Path(temp_dir) / "h")
        handoff_request_payload = json.loads(handoff_artifacts.operator_handoff_request_path.read_text(encoding="utf-8"))
        handoff_summary_payload = json.loads(handoff_artifacts.operator_handoff_summary_path.read_text(encoding="utf-8"))
        handoff_targets_payload = json.loads(handoff_artifacts.operator_handoff_review_targets_path.read_text(encoding="utf-8"))

    handoff_request_raw = handoff_request_payload["operator_handoff_request"]
    handoff_summary_raw = handoff_summary_payload["operator_handoff_summary"]
    handoff_targets_raw = handoff_targets_payload["operator_handoff_review_targets"]

    decision_request = OperatorDecisionRequestContract(
        decision_id=f"DECISION_{handoff_request_raw['handoff_id']}",
        handoff_id=handoff_request_raw["handoff_id"],
        session_id=handoff_request_raw["session_id"],
        closeout_id=handoff_request_raw["closeout_id"],
        request_id=handoff_request_raw["request_id"],
        execution_id=handoff_request_raw["execution_id"],
        task_id=handoff_request_raw["task_id"],
        priority_level=handoff_summary_raw["priority_level"],
        operator_attention_required=handoff_request_raw["operator_attention_required"],
        reviewable_items=handoff_targets_raw["reviewable_items"],
        approval_items=handoff_targets_raw["approval_items"],
        blocked_items=handoff_targets_raw["blocked_items"],
        retry_candidates=handoff_targets_raw["retry_candidates"],
        archival_candidates=handoff_targets_raw["archival_candidates"],
        decision_requested_at=SIMULATION_TIMESTAMP,
    )

    selected_decision = "archive_only"
    if decision_request.blocked_items:
        selected_decision = "escalate"
    elif decision_request.retry_candidates:
        selected_decision = "approve_retry"
    elif decision_request.approval_items and "archive:" not in " ".join(decision_request.approval_items):
        selected_decision = "approve_next_phase"

    decision_response = OperatorDecisionResponseContract(
        decision_id=decision_request.decision_id,
        operator_decision=selected_decision,
        decided_by="operator_placeholder",
        decided_at=SIMULATION_TIMESTAMP,
        notes="Deterministic dry-run operator decision for architecture-only validation.",
    )
    decision_resolution = evaluate_operator_decision_resolution(decision_request, decision_response)

    report_text = format_operator_report(
        summary="Operator decision resolution dry-run completed as a contract-only step without any live operator workflow or bounded execution runtime.",
        facts=[
            f"Decision ID: {decision_request.decision_id}",
            f"Priority level: {decision_request.priority_level}",
            f"Operator decision: {decision_response.operator_decision}",
            f"Resolution state: {decision_resolution.resolution_state}",
            f"Blocked: {decision_resolution.blocked}",
        ],
        assumptions=[
            "Operator decision resolution remains a contract-only layer for deterministic next-step packaging.",
            "No live bounded execution, no live operator workflow engine, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Use the decision artifacts for contract validation only until a future approved runtime phase exists.",
            "Keep decision resolution disconnected from runner.py, queue execution semantics, and live workflows.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    operator_decision_request_path = destination / "operator_decision_request.json"
    operator_decision_response_path = destination / "operator_decision_response.json"
    operator_decision_resolution_path = destination / "operator_decision_resolution.json"
    operator_report_path = destination / "operator_report.md"

    write_json(operator_decision_request_path, {"operator_decision_request": decision_request.to_payload()})
    write_json(operator_decision_response_path, {"operator_decision_response": decision_response.to_payload()})
    write_json(operator_decision_resolution_path, {"operator_decision_resolution": decision_resolution.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return OperatorDecisionResolutionArtifacts(
        output_dir=destination,
        operator_decision_request_path=operator_decision_request_path,
        operator_decision_response_path=operator_decision_response_path,
        operator_decision_resolution_path=operator_decision_resolution_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_operator_decision_resolution_dry_run()
    print(f"operator_decision_request: {artifacts.operator_decision_request_path}")
    print(f"operator_decision_response: {artifacts.operator_decision_response_path}")
    print(f"operator_decision_resolution: {artifacts.operator_decision_resolution_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()