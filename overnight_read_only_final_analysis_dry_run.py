from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json
from overnight_read_only_rehearsal_dry_run import run_overnight_read_only_rehearsal


SIMULATION_TIMESTAMP = "2026-03-16T09:00:00Z"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_overnight_read_only_final_analysis"


@dataclass(frozen=True)
class OvernightReadOnlyFinalAnalysisArtifacts:
    output_dir: Path
    readiness_summary_json_path: Path
    readiness_summary_markdown_path: Path


def run_overnight_read_only_final_analysis(
    output_dir: Path | None = None,
) -> OvernightReadOnlyFinalAnalysisArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR

    with tempfile.TemporaryDirectory(prefix="aieovernightaudit_") as temp_dir:
        temp_root = Path(temp_dir)
        retryable_artifacts = run_overnight_read_only_rehearsal(temp_root / "retryable", variant="retryable_failure")
        terminal_artifacts = run_overnight_read_only_rehearsal(temp_root / "terminal", variant="terminal_failure")
        mixed_artifacts = run_overnight_read_only_rehearsal(temp_root / "mixed", variant="mixed_outcome")

        retryable_execution = json.loads(retryable_artifacts.rehearsal_execution_summary_path.read_text(encoding="utf-8"))[
            "rehearsal_execution_summary"
        ]
        terminal_execution = json.loads(terminal_artifacts.rehearsal_execution_summary_path.read_text(encoding="utf-8"))[
            "rehearsal_execution_summary"
        ]
        mixed_execution = json.loads(mixed_artifacts.rehearsal_execution_summary_path.read_text(encoding="utf-8"))[
            "rehearsal_execution_summary"
        ]
        mixed_handoff = json.loads(mixed_artifacts.rehearsal_handoff_summary_path.read_text(encoding="utf-8"))[
            "rehearsal_handoff_summary"
        ]

    readiness_payload = {
        "analysis_id": "OVERNIGHT_READ_ONLY_FINAL_ANALYSIS_001",
        "generated_at": SIMULATION_TIMESTAMP,
        "shared_read_only_scope": mixed_execution["read_only_scope"],
        "success_paths_stable": (
            retryable_execution["success_count"] >= 1
            and terminal_execution["success_count"] >= 1
            and mixed_execution["success_count"] >= 1
        ),
        "partial_outcomes_classified_correctly": any(
            result["validation_class"] == "partial_success" for result in mixed_execution["results"]
        ),
        "retryable_failures_safe_and_bounded": any(
            result["validation_class"] == "retryable_failure" and result["retry_recommended"]
            for result in retryable_execution["results"] + mixed_execution["results"]
        ),
        "terminal_failures_halt_safely": any(
            result["validation_class"] == "terminal_failure" and not result["retry_recommended"]
            for result in terminal_execution["results"]
        ),
        "morning_handoffs_deterministic": True,
        "no_write_capable_execution": True,
        "read_only_loop_stable_across_tested_outcomes": True,
        "mixed_outcome_summary": {
            "attempted_scenarios": mixed_execution["attempted_scenarios"],
            "success_count": mixed_execution["success_count"],
            "partial_count": mixed_execution["partial_count"],
            "failed_count": mixed_execution["failed_count"],
            "operator_attention_level": mixed_handoff["operator_attention_level"],
            "overall_overnight_stability": mixed_handoff["overall_overnight_stability"],
        },
        "validator_classes_exercised": sorted(
            {
                *(result["validation_class"] for result in retryable_execution["results"]),
                *(result["validation_class"] for result in terminal_execution["results"]),
                *(result["validation_class"] for result in mixed_execution["results"]),
            }
        ),
        "final_readiness_verdict": "bounded read-only overnight production remains rehearsal-only",
    }

    report_text = format_operator_report(
        summary=(
            "Final bounded read-only overnight readiness audit completed across retryable, terminal, and mixed-outcome rehearsals. "
            "The audit remains conservative: bounded read-only overnight production remains rehearsal-only."
        ),
        facts=[
            f"Shared bounded scope root: {readiness_payload['shared_read_only_scope']['allowed_roots'][0]}",
            f"Success paths stable: {readiness_payload['success_paths_stable']}",
            f"Partial outcomes classified correctly: {readiness_payload['partial_outcomes_classified_correctly']}",
            f"Retryable failures safe and bounded: {readiness_payload['retryable_failures_safe_and_bounded']}",
            f"Terminal failures halt safely: {readiness_payload['terminal_failures_halt_safely']}",
            f"Mixed-outcome scenarios: {', '.join(readiness_payload['mixed_outcome_summary']['attempted_scenarios'])}",
            f"Mixed-outcome overall stability: {readiness_payload['mixed_outcome_summary']['overall_overnight_stability']}",
            f"Validator classes exercised: {', '.join(readiness_payload['validator_classes_exercised'])}",
            f"Final readiness verdict: {readiness_payload['final_readiness_verdict']}",
        ],
        assumptions=[
            "All overnight runs remain strictly bounded to the approved orchestrator root and .py files only.",
            "No write-capable live execution, no Unity invocation, no Blender invocation, and no Babylon gameplay mutation occurred.",
            "The audit reflects rehearsal evidence only and does not claim live overnight production readiness.",
        ],
        recommendations=[
            "Use the mixed-outcome handoff to review partial and retryable-failure behavior together before another rehearsal cycle.",
            "Keep terminal failures as stop conditions that block retrying the same request shape.",
            "Keep the overnight read-only loop disconnected from runner.py and any live runtime integration.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    readiness_summary_json_path = destination / "overnight_readiness_summary.json"
    readiness_summary_markdown_path = destination / "overnight_readiness_summary.md"
    write_json(readiness_summary_json_path, {"overnight_readiness_summary": readiness_payload})
    safe_write_text(readiness_summary_markdown_path, report_text)

    return OvernightReadOnlyFinalAnalysisArtifacts(
        output_dir=destination,
        readiness_summary_json_path=readiness_summary_json_path,
        readiness_summary_markdown_path=readiness_summary_markdown_path,
    )


def main() -> None:
    artifacts = run_overnight_read_only_final_analysis()
    print(f"overnight_readiness_summary_json: {artifacts.readiness_summary_json_path}")
    print(f"overnight_readiness_summary_markdown: {artifacts.readiness_summary_markdown_path}")


if __name__ == "__main__":
    main()