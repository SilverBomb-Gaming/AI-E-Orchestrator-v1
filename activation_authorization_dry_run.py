from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from activation_review_dry_run import run_activation_review_dry_run
from orchestrator.activation_authorization_interface import (
    ActivationAuthorizationRequestContract,
    evaluate_activation_authorization,
)
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json


SIMULATION_TIMESTAMP = "2026-03-15T00:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_activation_authorization_test"


@dataclass(frozen=True)
class ActivationAuthorizationArtifacts:
    output_dir: Path
    activation_authorization_request_path: Path
    activation_authorization_record_path: Path
    activation_authorization_verdict_path: Path
    operator_report_path: Path


def run_activation_authorization_dry_run(output_dir: Path | None = None) -> ActivationAuthorizationArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    review_artifacts = run_activation_review_dry_run(destination / "activation_review_source")
    review_request_payload = json.loads(review_artifacts.activation_review_request_path.read_text(encoding="utf-8"))
    review_decision_payload = json.loads(review_artifacts.activation_review_decision_path.read_text(encoding="utf-8"))
    review_verdict_payload = json.loads(review_artifacts.activation_verdict_path.read_text(encoding="utf-8"))

    review_request = review_request_payload["activation_review_request"]
    review_decision = review_decision_payload["activation_review_decision"]
    review_verdict = review_verdict_payload["activation_verdict"]

    authorization_request = ActivationAuthorizationRequestContract(
        authorization_id=f"AUTH_{review_verdict['activation_id']}",
        review_id=review_request["review_id"],
        activation_id=review_verdict["activation_id"],
        request_id=review_request["request_id"],
        execution_id=review_request["execution_id"],
        task_id=review_request["task_id"],
        selected_adapter_id=review_request["selected_adapter_id"],
        review_decision=review_decision["decision"],
        review_result_state=review_verdict["result_state"],
        policy_level=review_request["policy_level"],
        dry_run=review_request["dry_run"],
        authorization_requested_at=SIMULATION_TIMESTAMP,
    )

    authorization_record, authorization_verdict = evaluate_activation_authorization(
        authorization_request,
        "approve",
        authorized_by="operator_placeholder",
        authorization_timestamp=SIMULATION_TIMESTAMP,
        expires_at="2026-03-16T00:00:00Z",
        notes="Dry-run authorization permits deterministic activation only.",
    )

    report_text = format_operator_report(
        summary="Activation authorization dry-run completed without any live authorization engine or runtime execution.",
        facts=[
            f"Authorization ID: {authorization_request.authorization_id}",
            f"Review result state: {authorization_request.review_result_state}",
            f"Authorization state: {authorization_record.authorization_state}",
            f"Proceed allowed: {authorization_verdict.proceed_allowed}",
        ],
        assumptions=[
            "Activation authorization remains a contract-only boundary after review and before any future bounded execution.",
            "No live approval engine, no live bounded execution, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Keep authorization limited to deterministic dry-run records until a future approved runtime phase exists.",
            "Use authorization outputs for contract validation only, not as evidence of live authorization infrastructure.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    activation_authorization_request_path = destination / "activation_authorization_request.json"
    activation_authorization_record_path = destination / "activation_authorization_record.json"
    activation_authorization_verdict_path = destination / "activation_authorization_verdict.json"
    operator_report_path = destination / "operator_report.md"

    write_json(activation_authorization_request_path, {"activation_authorization_request": authorization_request.to_payload()})
    write_json(activation_authorization_record_path, {"activation_authorization_record": authorization_record.to_payload()})
    write_json(activation_authorization_verdict_path, {"activation_authorization_verdict": authorization_verdict.to_payload()})
    safe_write_text(operator_report_path, report_text)

    return ActivationAuthorizationArtifacts(
        output_dir=destination,
        activation_authorization_request_path=activation_authorization_request_path,
        activation_authorization_record_path=activation_authorization_record_path,
        activation_authorization_verdict_path=activation_authorization_verdict_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_activation_authorization_dry_run()
    print(f"activation_authorization_request: {artifacts.activation_authorization_request_path}")
    print(f"activation_authorization_record: {artifacts.activation_authorization_record_path}")
    print(f"activation_authorization_verdict: {artifacts.activation_authorization_verdict_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()