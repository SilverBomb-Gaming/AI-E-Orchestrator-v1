from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.post_dispatch_audit_interface import (
    PostDispatchAuditRequestContract,
    evaluate_post_dispatch_audit,
)
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json
from post_decision_dispatch_dry_run import run_post_decision_dispatch_dry_run


SIMULATION_TIMESTAMP = "2026-03-16T00:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_post_dispatch_audit_test"


@dataclass(frozen=True)
class PostDispatchAuditArtifacts:
    output_dir: Path
    post_dispatch_audit_request_path: Path
    post_dispatch_audit_record_path: Path
    post_dispatch_audit_verdict_path: Path
    operator_report_path: Path


def run_post_dispatch_audit_dry_run(output_dir: Path | None = None) -> PostDispatchAuditArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    with tempfile.TemporaryDirectory(prefix="aiea_") as temp_dir:
        dispatch_artifacts = run_post_decision_dispatch_dry_run(Path(temp_dir) / "p")
        dispatch_request_payload = json.loads(dispatch_artifacts.post_decision_dispatch_request_path.read_text(encoding="utf-8"))
        dispatch_record_payload = json.loads(dispatch_artifacts.post_decision_dispatch_record_path.read_text(encoding="utf-8"))

    dispatch_request_raw = dispatch_request_payload["post_decision_dispatch_request"]
    dispatch_record_raw = dispatch_record_payload["post_decision_dispatch_record"]

    audit_request = PostDispatchAuditRequestContract(
        audit_id=f"AUDIT_{dispatch_request_raw['dispatch_id']}",
        dispatch_id=dispatch_request_raw["dispatch_id"],
        decision_id=dispatch_request_raw["decision_id"],
        handoff_id=dispatch_request_raw["handoff_id"],
        session_id=dispatch_request_raw["session_id"],
        request_id=dispatch_request_raw["request_id"],
        execution_id=dispatch_request_raw["execution_id"],
        task_id=dispatch_request_raw["task_id"],
        dispatch_state=dispatch_record_raw["dispatch_state"],
        dispatch_target=dispatch_record_raw["dispatch_target"],
        priority_level=dispatch_request_raw["priority_level"],
        audit_requested_at=SIMULATION_TIMESTAMP,
    )
    audit_record, audit_verdict = evaluate_post_dispatch_audit(audit_request)

    report_text = format_operator_report(
        summary="Post-dispatch audit dry-run completed as a contract-only review step without any live audit or bounded execution infrastructure.",
        facts=[
            f"Audit ID: {audit_request.audit_id}",
            f"Dispatch state: {audit_request.dispatch_state}",
            f"Audit state: {audit_record.audit_state}",
            f"Proceed allowed: {audit_verdict.proceed_allowed}",
            f"Requires operator review: {audit_verdict.requires_operator_review}",
        ],
        assumptions=[
            "Post-dispatch audit remains a contract-only layer for deterministic review before future action.",
            "No live bounded execution, no live audit workflow, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Use the audit artifacts for contract validation only until a future approved runtime phase exists.",
            "Keep audit packaging disconnected from runner.py, queue execution semantics, and live workflows.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    post_dispatch_audit_request_path = destination / "post_dispatch_audit_request.json"
    post_dispatch_audit_record_path = destination / "post_dispatch_audit_record.json"
    post_dispatch_audit_verdict_path = destination / "post_dispatch_audit_verdict.json"
    operator_report_path = destination / "operator_report.md"

    write_json(post_dispatch_audit_request_path, {"post_dispatch_audit_request": audit_request.to_payload()})
    write_json(post_dispatch_audit_record_path, {"post_dispatch_audit_record": audit_record.to_payload()})
    write_json(post_dispatch_audit_verdict_path, {"post_dispatch_audit_verdict": audit_verdict.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return PostDispatchAuditArtifacts(
        output_dir=destination,
        post_dispatch_audit_request_path=post_dispatch_audit_request_path,
        post_dispatch_audit_record_path=post_dispatch_audit_record_path,
        post_dispatch_audit_verdict_path=post_dispatch_audit_verdict_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_post_dispatch_audit_dry_run()
    print(f"post_dispatch_audit_request: {artifacts.post_dispatch_audit_request_path}")
    print(f"post_dispatch_audit_record: {artifacts.post_dispatch_audit_record_path}")
    print(f"post_dispatch_audit_verdict: {artifacts.post_dispatch_audit_verdict_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()