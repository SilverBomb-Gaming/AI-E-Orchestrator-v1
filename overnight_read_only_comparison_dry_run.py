from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json
from overnight_read_only_rehearsal_dry_run import run_overnight_read_only_rehearsal


SIMULATION_TIMESTAMP = "2026-03-16 04:30:00 -04:00 (Eastern Time — New York)"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_overnight_read_only_comparison"


@dataclass(frozen=True)
class OvernightReadOnlyComparisonArtifacts:
    output_dir: Path
    comparison_json_path: Path
    comparison_markdown_path: Path


def run_overnight_read_only_comparison(
    output_dir: Path | None = None,
) -> OvernightReadOnlyComparisonArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR

    with tempfile.TemporaryDirectory(prefix="aieovernightcompare_") as temp_dir:
        temp_root = Path(temp_dir)
        retryable_artifacts = run_overnight_read_only_rehearsal(
            temp_root / "retryable",
            variant="retryable_failure",
        )
        terminal_artifacts = run_overnight_read_only_rehearsal(
            temp_root / "terminal",
            variant="terminal_failure",
        )

        retryable_execution = json.loads(
            retryable_artifacts.rehearsal_execution_summary_path.read_text(encoding="utf-8")
        )["rehearsal_execution_summary"]
        retryable_handoff = json.loads(
            retryable_artifacts.rehearsal_handoff_summary_path.read_text(encoding="utf-8")
        )["rehearsal_handoff_summary"]
        terminal_execution = json.loads(
            terminal_artifacts.rehearsal_execution_summary_path.read_text(encoding="utf-8")
        )["rehearsal_execution_summary"]
        terminal_handoff = json.loads(
            terminal_artifacts.rehearsal_handoff_summary_path.read_text(encoding="utf-8")
        )["rehearsal_handoff_summary"]

    comparison_payload = {
        "comparison_id": "OVERNIGHT_READ_ONLY_COMPARISON_001",
        "generated_at": SIMULATION_TIMESTAMP,
        "shared_read_only_scope": retryable_execution["read_only_scope"],
        "retryable_variant": {
            "attempted_scenarios": retryable_execution["attempted_scenarios"],
            "success_path_results": retryable_execution["results"][0],
            "failure_path_results": retryable_execution["results"][1],
            "recommended_next_action": retryable_handoff["safe_next_steps"][0],
            "operator_attention_required": retryable_execution["results"][1]["operator_attention_required"],
            "operator_attention_level": retryable_handoff["operator_attention_level"],
        },
        "terminal_variant": {
            "attempted_scenarios": terminal_execution["attempted_scenarios"],
            "success_path_results": terminal_execution["results"][0],
            "failure_path_results": terminal_execution["results"][1],
            "recommended_next_action": terminal_handoff["safe_next_steps"][0],
            "operator_attention_required": terminal_execution["results"][1]["operator_attention_required"],
            "operator_attention_level": terminal_handoff["operator_attention_level"],
        },
        "differences": {
            "retryable_failure_behavior": (
                "Retryable failure recommends another bounded rehearsal iteration within the same approved scope."
            ),
            "terminal_failure_behavior": (
                "Terminal failure records a bounded structural invalidity that does not recommend retrying the same request."
            ),
            "recommended_next_action_difference": {
                "retryable_failure": retryable_handoff["safe_next_steps"][0],
                "terminal_failure": terminal_handoff["safe_next_steps"][0],
            },
            "operator_attention_level_difference": {
                "retryable_failure": retryable_handoff["operator_attention_level"],
                "terminal_failure": terminal_handoff["operator_attention_level"],
            },
        },
        "production_ready": False,
        "readiness_verdict": "bounded read-only overnight production remains rehearsal-only",
    }

    comparison_markdown = format_operator_report(
        summary=(
            "Bounded overnight read-only rehearsal comparison completed across retryable-failure and terminal-failure variants. "
            "The evidence remains conservative: overnight production is still rehearsal-only."
        ),
        facts=[
            f"Shared bounded scope root: {comparison_payload['shared_read_only_scope']['allowed_roots'][0]}",
            f"Shared allowed extension: {comparison_payload['shared_read_only_scope']['allowed_extensions'][0]}",
            f"Retryable variant scenarios: {', '.join(comparison_payload['retryable_variant']['attempted_scenarios'])}",
            f"Terminal variant scenarios: {', '.join(comparison_payload['terminal_variant']['attempted_scenarios'])}",
            f"Retryable validator class: {comparison_payload['retryable_variant']['failure_path_results']['validation_class']}",
            f"Terminal validator class: {comparison_payload['terminal_variant']['failure_path_results']['validation_class']}",
            f"Retryable next action: {comparison_payload['retryable_variant']['recommended_next_action']}",
            f"Terminal next action: {comparison_payload['terminal_variant']['recommended_next_action']}",
            f"Retryable operator attention level: {comparison_payload['retryable_variant']['operator_attention_level']}",
            f"Terminal operator attention level: {comparison_payload['terminal_variant']['operator_attention_level']}",
            f"Production ready: {comparison_payload['production_ready']}",
            f"Readiness verdict: {comparison_payload['readiness_verdict']}",
        ],
        assumptions=[
            "Both rehearsal variants remain strictly bounded to the approved orchestrator root and .py files only.",
            "No write-capable live execution, no Unity invocation, no Blender invocation, and no Babylon gameplay mutation occurred.",
            "The comparison reflects rehearsal evidence only and does not claim live overnight production readiness.",
        ],
        recommendations=[
            "Use the retryable-failure handoff when planning another bounded rehearsal within the same scope.",
            "Treat the terminal-failure handoff as evidence that structural invalid requests still require conservative review rather than production promotion.",
            "Keep the overnight read-only loop disconnected from runner.py and live runtime integration.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(comparison_markdown)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    comparison_json_path = destination / "overnight_rehearsal_comparison.json"
    comparison_markdown_path = destination / "overnight_rehearsal_comparison.md"
    write_json(comparison_json_path, {"overnight_rehearsal_comparison": comparison_payload})
    safe_write_text(comparison_markdown_path, comparison_markdown)

    return OvernightReadOnlyComparisonArtifacts(
        output_dir=destination,
        comparison_json_path=comparison_json_path,
        comparison_markdown_path=comparison_markdown_path,
    )


def main() -> None:
    artifacts = run_overnight_read_only_comparison()
    print(f"overnight_rehearsal_comparison_json: {artifacts.comparison_json_path}")
    print(f"overnight_rehearsal_comparison_markdown: {artifacts.comparison_markdown_path}")


if __name__ == "__main__":
    main()