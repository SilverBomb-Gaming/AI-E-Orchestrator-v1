from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from orchestrator.activation_review_interface import (
    ActivationReviewDecisionContract,
    ActivationReviewRequestContract,
    ActivationVerdictContract,
    evaluate_activation_review,
)
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json
from runtime_activation_harness import run_runtime_activation_harness


SIMULATION_TIMESTAMP = "2026-03-15T00:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_activation_review_test"


@dataclass(frozen=True)
class ActivationReviewArtifacts:
    output_dir: Path
    activation_review_request_path: Path
    activation_review_decision_path: Path
    activation_verdict_path: Path
    operator_report_path: Path


def run_activation_review_dry_run(output_dir: Path | None = None) -> ActivationReviewArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    activation_artifacts = run_runtime_activation_harness(destination / "activation_runtime_source")
    activation_payload = json.loads(activation_artifacts.activation_result_path.read_text(encoding="utf-8"))
    activation_result = activation_payload["activation_result"]

    review_request = ActivationReviewRequestContract(
        review_id=f"REV_{activation_result['activation_id']}",
        activation_id=activation_result["activation_id"],
        request_id=activation_result["request_id"],
        execution_id=activation_result["execution_id"],
        task_id=activation_result["task_id"],
        selected_adapter_id=activation_result["chosen_adapter_id"],
        activation_state=activation_result["activation_status"],
        approval_required=activation_result["activation_status"] == "approval_required",
        blocked=activation_result["blocked"],
        blocked_reason=activation_result["blocked_reason"],
        policy_level="architecture_only",
        dry_run=activation_result["dry_run"],
    )
    review_decision = ActivationReviewDecisionContract(
        review_id=review_request.review_id,
        decision="approve",
        reviewed_by="operator_placeholder",
        review_timestamp=SIMULATION_TIMESTAMP,
        notes="Dry-run activation review approves transition to ready_for_dry_run only.",
    )
    activation_verdict = evaluate_activation_review(review_request, review_decision)
    report_text = _build_operator_report(review_request, review_decision, activation_verdict)
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    activation_review_request_path = destination / "activation_review_request.json"
    activation_review_decision_path = destination / "activation_review_decision.json"
    activation_verdict_path = destination / "activation_verdict.json"
    operator_report_path = destination / "operator_report.md"

    write_json(activation_review_request_path, {"activation_review_request": review_request.to_payload()})
    write_json(activation_review_decision_path, {"activation_review_decision": review_decision.to_payload()})
    write_json(activation_verdict_path, {"activation_verdict": activation_verdict.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return ActivationReviewArtifacts(
        output_dir=destination,
        activation_review_request_path=activation_review_request_path,
        activation_review_decision_path=activation_review_decision_path,
        activation_verdict_path=activation_verdict_path,
        operator_report_path=operator_report_path,
    )


def _build_operator_report(
    review_request: ActivationReviewRequestContract,
    review_decision: ActivationReviewDecisionContract,
    activation_verdict: ActivationVerdictContract,
) -> str:
    return format_operator_report(
        summary="Activation review dry-run completed without any live approval infrastructure or runtime execution.",
        facts=[
            f"Activation ID: {review_request.activation_id}",
            f"Incoming activation state: {review_request.activation_state}",
            f"Review decision: {review_decision.decision}",
            f"Result state: {activation_verdict.result_state}",
        ],
        assumptions=[
            "Activation review remains a contract-only boundary between automated activation analysis and human approval review.",
            "No live bounded execution, no live operator workflow, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Keep activation review limited to deterministic dry-run transitions until a future approved runtime phase exists.",
            "Use review verdicts for contract validation only, not as evidence of live approval infrastructure.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )


def main() -> None:
    artifacts = run_activation_review_dry_run()
    print(f"activation_review_request: {artifacts.activation_review_request_path}")
    print(f"activation_review_decision: {artifacts.activation_review_decision_path}")
    print(f"activation_verdict: {artifacts.activation_verdict_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()