from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json
from read_only_live_adapter_dry_run import default_read_scope
from validator_engine_dry_run import run_validator_engine_dry_run


SIMULATION_TIMESTAMP = "2026-03-16 04:00:00 -04:00 (Eastern Time — New York)"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_overnight_read_only_rehearsal"
TERMINAL_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_overnight_read_only_rehearsal_terminal"
MIXED_OUTPUT_DIR = Path(__file__).resolve().parent / "runs" / "aie_overnight_read_only_rehearsal_mixed"
OvernightVariant = Literal["retryable_failure", "terminal_failure", "mixed_outcome"]


@dataclass(frozen=True)
class OvernightReadOnlyRehearsalArtifacts:
    output_dir: Path
    rehearsal_request_path: Path
    rehearsal_execution_summary_path: Path
    rehearsal_validator_summary_path: Path
    rehearsal_handoff_summary_path: Path
    operator_report_path: Path


def run_overnight_read_only_rehearsal(
    output_dir: Path | None = None,
    variant: OvernightVariant = "retryable_failure",
) -> OvernightReadOnlyRehearsalArtifacts:
    destination = Path(output_dir) if output_dir else _default_output_dir_for_variant(variant)
    read_scope = default_read_scope().to_payload()
    scenarios = _scenarios_for_variant(variant)

    scenario_results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="aieovernight_") as temp_dir:
        temp_root = Path(temp_dir)
        for scenario in scenarios:
            validator_artifacts = run_validator_engine_dry_run(
                temp_root / str(scenario["scenario"]),
                scenario=str(scenario["scenario"]),
            )
            read_only_response = json.loads(validator_artifacts.read_only_response_path.read_text(encoding="utf-8"))[
                "read_only_response"
            ]
            validator_record = json.loads(validator_artifacts.validator_record_path.read_text(encoding="utf-8"))[
                "validator_record"
            ]
            validator_verdict = json.loads(validator_artifacts.validator_verdict_path.read_text(encoding="utf-8"))[
                "validator_verdict"
            ]
            scenario_results.append(
                {
                    "step_id": scenario["step_id"],
                    "scenario": scenario["scenario"],
                    "purpose": scenario["purpose"],
                    "response_state": read_only_response["response_state"],
                    "validation_class": validator_record["validation_class"],
                    "validation_state": validator_record["validation_state"],
                    "retry_recommended": validator_verdict["retry_recommended"],
                    "operator_attention_required": validator_verdict["operator_attention_required"],
                    "inspected_paths": read_only_response["inspected_paths"],
                    "errors": read_only_response["errors"],
                    "warnings": read_only_response["warnings"],
                    "artifacts_generated": read_only_response["artifacts_generated"],
                }
            )

    execution_summary = {
        "rehearsal_id": _rehearsal_id_for_variant(variant),
        "executed_at": SIMULATION_TIMESTAMP,
        "variant": variant,
        "attempted_scenarios": [result["scenario"] for result in scenario_results],
        "success_count": sum(1 for result in scenario_results if result["response_state"] == "read_completed"),
        "partial_count": sum(1 for result in scenario_results if result["response_state"] == "read_partial"),
        "denied_count": sum(1 for result in scenario_results if result["response_state"] == "read_denied"),
        "failed_count": sum(1 for result in scenario_results if result["response_state"] == "read_failed"),
        "blocked_count": sum(1 for result in scenario_results if result["response_state"] == "read_blocked"),
        "results": scenario_results,
        "read_only_scope": read_scope,
    }
    validator_summary = {
        "rehearsal_id": _rehearsal_id_for_variant(variant),
        "variant": variant,
        "validation_classes_exercised": sorted({str(result["validation_class"]) for result in scenario_results}),
        "retry_recommended_for": [result["scenario"] for result in scenario_results if result["retry_recommended"]],
        "operator_attention_required_for": [
            result["scenario"] for result in scenario_results if result["operator_attention_required"]
        ],
        "terminal_failure_scenarios": [
            result["scenario"] for result in scenario_results if result["validation_class"] == "terminal_failure"
        ],
    }
    handoff_summary = {
        "handoff_id": _handoff_id_for_variant(variant),
        "variant": variant,
        "summary_title": _handoff_title_for_variant(variant),
        "attempted": [result["scenario"] for result in scenario_results],
        "succeeded": [result["scenario"] for result in scenario_results if result["response_state"] == "read_completed"],
        "partial": [result["scenario"] for result in scenario_results if result["response_state"] == "read_partial"],
        "denied": [result["scenario"] for result in scenario_results if result["response_state"] == "read_denied"],
        "failed": [result["scenario"] for result in scenario_results if result["response_state"] == "read_failed"],
        "safe_next_steps": _safe_next_steps_for_variant(variant),
        "operator_attention_level": _operator_attention_level_for_variant(variant),
        "ready_for_additional_bounded_rehearsal": True,
        "ready_for_live_overnight_production": False,
        "overall_overnight_stability": _overnight_stability_for_variant(variant),
    }

    report_text = format_operator_report(
        summary=(
            _summary_for_variant(variant)
        ),
        facts=[
            f"Variant: {variant}",
            f"Attempted scenarios: {', '.join(execution_summary['attempted_scenarios'])}",
            f"Success count: {execution_summary['success_count']}",
            f"Partial count: {execution_summary['partial_count']}",
            f"Denied count: {execution_summary['denied_count']}",
            f"Failed count: {execution_summary['failed_count']}",
            f"Validation classes exercised: {', '.join(validator_summary['validation_classes_exercised'])}",
            f"Overall overnight stability: {handoff_summary['overall_overnight_stability']}",
            f"Ready for additional bounded rehearsal: {handoff_summary['ready_for_additional_bounded_rehearsal']}",
            f"Ready for live overnight production: {handoff_summary['ready_for_live_overnight_production']}",
        ],
        assumptions=[
            "The rehearsal remains strictly bounded to the approved orchestrator root and .py files only.",
            "No write-capable live execution, no Unity invocation, no Blender invocation, and no Babylon gameplay mutation occurred.",
            "The overnight flow is a local rehearsal scaffold and not a live production overnight run.",
        ],
        recommendations=[
            "Continue overnight rehearsal work only within the same bounded read-only scope until additional failure cases are reviewed.",
            "Treat retryable failures as review items for another bounded rehearsal iteration, not as permission for write-capable automation.",
            "Keep runner.py untouched and keep all overnight work disconnected from live runtime integration.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    rehearsal_request_path = destination / "rehearsal_request.json"
    rehearsal_execution_summary_path = destination / "rehearsal_execution_summary.json"
    rehearsal_validator_summary_path = destination / "rehearsal_validator_summary.json"
    rehearsal_handoff_summary_path = destination / "rehearsal_handoff_summary.json"
    operator_report_path = destination / "operator_report.md"

    write_json(
        rehearsal_request_path,
        {
            "rehearsal_request": {
                "rehearsal_id": _rehearsal_id_for_variant(variant),
                "requested_at": SIMULATION_TIMESTAMP,
                "mode": "overnight_read_only_rehearsal",
                "variant": variant,
                "approved_scope": read_scope,
                "scenarios": scenarios,
                "live_production": False,
            }
        },
    )
    write_json(rehearsal_execution_summary_path, {"rehearsal_execution_summary": execution_summary})
    write_json(rehearsal_validator_summary_path, {"rehearsal_validator_summary": validator_summary})
    write_json(rehearsal_handoff_summary_path, {"rehearsal_handoff_summary": handoff_summary})
    safe_write_text(operator_report_path, report_text)

    return OvernightReadOnlyRehearsalArtifacts(
        output_dir=destination,
        rehearsal_request_path=rehearsal_request_path,
        rehearsal_execution_summary_path=rehearsal_execution_summary_path,
        rehearsal_validator_summary_path=rehearsal_validator_summary_path,
        rehearsal_handoff_summary_path=rehearsal_handoff_summary_path,
        operator_report_path=operator_report_path,
    )


def main() -> None:
    artifacts = run_overnight_read_only_rehearsal()
    print(f"rehearsal_request: {artifacts.rehearsal_request_path}")
    print(f"rehearsal_execution_summary: {artifacts.rehearsal_execution_summary_path}")
    print(f"rehearsal_validator_summary: {artifacts.rehearsal_validator_summary_path}")
    print(f"rehearsal_handoff_summary: {artifacts.rehearsal_handoff_summary_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()


def _failure_scenario_for_variant(variant: OvernightVariant) -> str:
    if variant == "terminal_failure":
        return "read_failed_terminal"
    return "read_failed_retryable"


def _scenarios_for_variant(variant: OvernightVariant) -> list[dict[str, str]]:
    if variant == "mixed_outcome":
        return [
            {
                "step_id": "REHEARSAL_STEP_001",
                "scenario": "read_completed",
                "purpose": "baseline_success_probe",
            },
            {
                "step_id": "REHEARSAL_STEP_002",
                "scenario": "read_partial",
                "purpose": "bounded_partial_probe",
            },
            {
                "step_id": "REHEARSAL_STEP_003",
                "scenario": "read_failed_retryable",
                "purpose": "bounded_failure_probe",
            },
        ]
    return [
        {
            "step_id": "REHEARSAL_STEP_001",
            "scenario": "read_completed",
            "purpose": "baseline_success_probe",
        },
        {
            "step_id": "REHEARSAL_STEP_002",
            "scenario": _failure_scenario_for_variant(variant),
            "purpose": "bounded_non_success_probe",
        },
    ]


def _default_output_dir_for_variant(variant: OvernightVariant) -> Path:
    if variant == "mixed_outcome":
        return MIXED_OUTPUT_DIR
    if variant == "terminal_failure":
        return TERMINAL_OUTPUT_DIR
    return DEFAULT_OUTPUT_DIR


def _rehearsal_id_for_variant(variant: OvernightVariant) -> str:
    if variant == "mixed_outcome":
        return "OVERNIGHT_READ_ONLY_REHEARSAL_MIXED_001"
    if variant == "terminal_failure":
        return "OVERNIGHT_READ_ONLY_REHEARSAL_TERMINAL_001"
    return "OVERNIGHT_READ_ONLY_REHEARSAL_001"


def _handoff_id_for_variant(variant: OvernightVariant) -> str:
    if variant == "mixed_outcome":
        return "OVERNIGHT_READ_ONLY_HANDOFF_MIXED_001"
    if variant == "terminal_failure":
        return "OVERNIGHT_READ_ONLY_HANDOFF_TERMINAL_001"
    return "OVERNIGHT_READ_ONLY_HANDOFF_001"


def _handoff_title_for_variant(variant: OvernightVariant) -> str:
    if variant == "mixed_outcome":
        return "Morning handoff for bounded overnight read-only rehearsal mixed variant"
    if variant == "terminal_failure":
        return "Morning handoff for bounded overnight read-only rehearsal terminal variant"
    return "Morning handoff for bounded overnight read-only rehearsal"


def _failure_label_for_variant(variant: OvernightVariant) -> str:
    if variant == "mixed_outcome":
        return "mixed"
    if variant == "terminal_failure":
        return "terminal"
    return "retryable"


def _safe_next_steps_for_variant(variant: OvernightVariant) -> list[str]:
    if variant == "mixed_outcome":
        return [
            "Review the partial outcome before scheduling another bounded overnight rehearsal iteration.",
            "Retry only the retryable failed read within the same approved scope after operator review.",
            "Do not treat this rehearsal as live overnight production.",
        ]
    if variant == "terminal_failure":
        return [
            "Do not retry the same bounded request; review the structural invalidity before any future rehearsal is approved.",
            "Escalate the terminal failure handoff for conservative operator review before changing the bounded request shape.",
            "Do not treat this rehearsal as live overnight production.",
        ]
    return [
        "Repeat retryable failed reads only within the same approved read-only scope after reviewing the recorded failure reason.",
        "Keep the rehearsal disconnected from runner.py and any write-capable runtime path.",
        "Do not treat this rehearsal as live overnight production.",
    ]


def _operator_attention_level_for_variant(variant: OvernightVariant) -> str:
    if variant == "mixed_outcome":
        return "high"
    if variant == "terminal_failure":
        return "high"
    return "medium"


def _overnight_stability_for_variant(variant: OvernightVariant) -> str:
    if variant == "mixed_outcome":
        return "stable_with_partial_and_retryable_failure"
    if variant == "terminal_failure":
        return "stable_with_safe_terminal_halt"
    return "stable_with_retryable_failure"


def _summary_for_variant(variant: OvernightVariant) -> str:
    if variant == "mixed_outcome":
        return (
            "Bounded overnight read-only rehearsal variant mixed_outcome completed deterministically with one successful bounded read, "
            "one partial bounded read, and one retryable read_failed path. This remains a rehearsal only, not live overnight production."
        )
    return (
        f"Bounded overnight read-only rehearsal variant {variant} completed deterministically with one successful bounded read "
        f"and one {_failure_label_for_variant(variant)} read_failed path. This remains a rehearsal only, not live overnight production."
    )