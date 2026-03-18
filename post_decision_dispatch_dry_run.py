from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from operator_decision_resolution_dry_run import run_operator_decision_resolution_dry_run
from orchestrator.post_decision_dispatch_interface import (
    PostDecisionDispatchRequestContract,
    evaluate_post_decision_dispatch,
)
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json


SIMULATION_TIMESTAMP = "2026-03-15 20:00:00 -04:00 (Eastern Time — New York)"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_post_decision_dispatch_test"


@dataclass(frozen=True)
class PostDecisionDispatchArtifacts:
    output_dir: Path
    post_decision_dispatch_request_path: Path
    post_decision_dispatch_record_path: Path
    post_decision_dispatch_verdict_path: Path
    operator_report_path: Path


def run_post_decision_dispatch_dry_run(output_dir: Path | None = None) -> PostDecisionDispatchArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    with tempfile.TemporaryDirectory(prefix="aiep_") as temp_dir:
        decision_artifacts = run_operator_decision_resolution_dry_run(Path(temp_dir) / "d")
        decision_request_payload = json.loads(decision_artifacts.operator_decision_request_path.read_text(encoding="utf-8"))
        decision_resolution_payload = json.loads(decision_artifacts.operator_decision_resolution_path.read_text(encoding="utf-8"))

    decision_request_raw = decision_request_payload["operator_decision_request"]
    decision_resolution_raw = decision_resolution_payload["operator_decision_resolution"]

    dispatch_request = PostDecisionDispatchRequestContract(
        dispatch_id=f"DISPATCH_{decision_request_raw['decision_id']}",
        decision_id=decision_request_raw["decision_id"],
        handoff_id=decision_request_raw["handoff_id"],
        session_id=decision_request_raw["session_id"],
        closeout_id=decision_request_raw["closeout_id"],
        request_id=decision_request_raw["request_id"],
        execution_id=decision_request_raw["execution_id"],
        task_id=decision_request_raw["task_id"],
        resolution_state=decision_resolution_raw["resolution_state"],
        next_action=decision_resolution_raw["next_action"],
        priority_level=decision_request_raw["priority_level"],
        dispatch_requested_at=SIMULATION_TIMESTAMP,
    )

    dispatch_record, dispatch_verdict = evaluate_post_decision_dispatch(
        dispatch_request,
        retry_authorized=decision_resolution_raw["retry_authorized"],
        archive_authorized=decision_resolution_raw["archival_authorized"],
        escalation_required=decision_resolution_raw["escalation_required"],
    )

    report_text = format_operator_report(
        summary="Post-decision dispatch dry-run completed as a contract-only packaging step without any live dispatch engine or bounded execution runtime.",
        facts=[
            f"Dispatch ID: {dispatch_request.dispatch_id}",
            f"Resolution state: {dispatch_request.resolution_state}",
            f"Dispatch state: {dispatch_record.dispatch_state}",
            f"Proceed allowed: {dispatch_verdict.proceed_allowed}",
            f"Requires operator review: {dispatch_verdict.requires_operator_review}",
        ],
        assumptions=[
            "Post-decision dispatch remains a contract-only layer for deterministic future action packaging.",
            "No live bounded execution, no live dispatch workflow, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Use the dispatch artifacts for contract validation only until a future approved runtime phase exists.",
            "Keep dispatch packaging disconnected from runner.py, queue execution semantics, and live workflows.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    post_decision_dispatch_request_path = destination / "post_decision_dispatch_request.json"
    post_decision_dispatch_record_path = destination / "post_decision_dispatch_record.json"
    post_decision_dispatch_verdict_path = destination / "post_decision_dispatch_verdict.json"
    operator_report_path = destination / "operator_report.md"

    write_json(post_decision_dispatch_request_path, {"post_decision_dispatch_request": dispatch_request.to_payload()})
    write_json(post_decision_dispatch_record_path, {"post_decision_dispatch_record": dispatch_record.to_payload()})
    write_json(post_decision_dispatch_verdict_path, {"post_decision_dispatch_verdict": dispatch_verdict.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return PostDecisionDispatchArtifacts(
        output_dir=destination,
        post_decision_dispatch_request_path=post_decision_dispatch_request_path,
        post_decision_dispatch_record_path=post_decision_dispatch_record_path,
        post_decision_dispatch_verdict_path=post_decision_dispatch_verdict_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_post_decision_dispatch_dry_run()
    print(f"post_decision_dispatch_request: {artifacts.post_decision_dispatch_request_path}")
    print(f"post_decision_dispatch_record: {artifacts.post_decision_dispatch_record_path}")
    print(f"post_decision_dispatch_verdict: {artifacts.post_decision_dispatch_verdict_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()