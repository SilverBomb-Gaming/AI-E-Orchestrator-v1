from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .report_contract import format_operator_report, validate_operator_report
from .utils import ensure_dir, safe_write_text, slugify, write_json
from .validator_engine_interface import ValidationInputContract, evaluate_validation_result
from read_only_live_adapter_dry_run import ReadOnlyScenario, run_read_only_live_adapter_dry_run


SIMULATION_TIMESTAMP = "2026-03-16 06:00:00 -04:00 (Eastern Time — New York)"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "runs" / "aie_live_read_only_session"
ALLOWED_SCENARIOS = {
    "read_completed",
    "read_partial",
    "read_denied",
    "read_failed_retryable",
    "read_failed_terminal",
}


@dataclass(frozen=True)
class RunnerReadOnlyBridgeResult:
    output_dir: Path
    session_bundle_dir: Path
    execution_request_path: Path
    execution_response_path: Path
    validator_summary_path: Path
    session_execution_summary_path: Path
    operator_handoff_report_path: Path
    response_state: str
    validation_class: str
    gate_report: dict[str, Any]
    summary_payload: dict[str, Any]
    operator_report_text: str


def execute_read_only_session(
    request: Mapping[str, Any] | None = None,
    *,
    output_dir: Path | None = None,
) -> RunnerReadOnlyBridgeResult:
    payload = dict(request or {})
    scenario = _normalize_scenario(payload)
    session_id = _session_id(payload, scenario)
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    ensure_dir(destination)
    session_bundle_dir = ensure_dir(destination / "session_bundles" / slugify(session_id))

    adapter_artifacts = run_read_only_live_adapter_dry_run(session_bundle_dir / "adapter", scenario=scenario)
    request_payload = json.loads(adapter_artifacts.read_only_request_path.read_text(encoding="utf-8"))["read_only_request"]
    response_payload = json.loads(adapter_artifacts.read_only_response_path.read_text(encoding="utf-8"))["read_only_response"]
    artifact_registry = json.loads(adapter_artifacts.read_only_artifact_registry_path.read_text(encoding="utf-8"))["read_only_artifacts"]

    validation_input = ValidationInputContract(
        validation_id=f"VALIDATION_{request_payload['execution_id']}",
        session_id=request_payload["session_id"],
        request_id=request_payload["request_id"],
        execution_id=request_payload["execution_id"],
        task_id=request_payload["task_id"],
        adapter_id=request_payload["adapter_id"],
        response_state=response_payload["response_state"],
        inspected_paths=response_payload["inspected_paths"],
        artifacts_generated=response_payload["artifacts_generated"],
        warnings=response_payload["warnings"],
        errors=response_payload["errors"],
        validated_at=SIMULATION_TIMESTAMP,
    )
    validation_record, validation_verdict = evaluate_validation_result(validation_input)
    gate_report = _build_gate_report(validation_record.validation_class, validation_record.notes)

    summary_payload = {
        "session_id": session_id,
        "scenario": scenario,
        "response_state": response_payload["response_state"],
        "validation_class": validation_record.validation_class,
        "validation_state": validation_record.validation_state,
        "retry_recommended": validation_verdict.retry_recommended,
        "operator_attention_required": validation_verdict.operator_attention_required,
        "artifacts_generated": response_payload["artifacts_generated"],
        "no_write_capable_execution": True,
        "scope_enforced": True,
        "gate_overall": gate_report["overall_status"],
    }

    operator_report_text = format_operator_report(
        summary=(
            f"Runner bridge executed bounded read-only scenario {scenario} through the adapter and validator pipeline "
            "without any write-capable execution."
        ),
        facts=[
            f"Session ID: {session_id}",
            f"Scenario: {scenario}",
            f"Response state: {response_payload['response_state']}",
            f"Validation class: {validation_record.validation_class}",
            f"Retry recommended: {validation_verdict.retry_recommended}",
            f"Artifacts generated: {len(response_payload['artifacts_generated'])}",
            f"Gate overall: {gate_report['overall_status']}",
        ],
        assumptions=[
            "The runner bridge remains strictly bounded to the existing orchestrator read-only scope and .py files only.",
            "No write-capable execution, no Unity invocation, no Blender invocation, and no Babylon gameplay mutation occurred.",
        ],
        recommendations=[
            _next_action_for_validation_class(validation_record.validation_class),
            "Keep runner read-only capability execution disconnected from any write-capable runtime path.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(operator_report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    validator_summary_payload = {
        "validator_input": validation_input.to_payload(),
        "validator_record": validation_record.to_payload(),
        "validator_verdict": validation_verdict.to_payload(),
    }
    execution_request_payload = {
        "execution_request": {
            "contract_type": "read_only_capability",
            "session_id": session_id,
            "scenario": scenario,
            "source_request": payload,
            "read_only_request": request_payload,
        }
    }
    execution_response_payload = {
        "execution_response": {
            "session_id": session_id,
            "scenario": scenario,
            "read_only_response": response_payload,
            "read_only_artifacts": artifact_registry,
        }
    }
    session_execution_payload = {"session_execution_summary": summary_payload}

    execution_request_path = destination / "execution_request.json"
    execution_response_path = destination / "execution_response.json"
    validator_summary_path = destination / "validator_summary.json"
    session_execution_summary_path = destination / "session_execution_summary.json"
    operator_handoff_report_path = destination / "operator_handoff_report.md"

    _write_dual_json(destination, session_bundle_dir, "execution_request.json", execution_request_payload)
    _write_dual_json(destination, session_bundle_dir, "execution_response.json", execution_response_payload)
    _write_dual_json(destination, session_bundle_dir, "validator_summary.json", validator_summary_payload)
    _write_dual_json(destination, session_bundle_dir, "session_execution_summary.json", session_execution_payload)
    _write_dual_text(destination, session_bundle_dir, "operator_handoff_report.md", operator_report_text)

    return RunnerReadOnlyBridgeResult(
        output_dir=destination,
        session_bundle_dir=session_bundle_dir,
        execution_request_path=execution_request_path,
        execution_response_path=execution_response_path,
        validator_summary_path=validator_summary_path,
        session_execution_summary_path=session_execution_summary_path,
        operator_handoff_report_path=operator_handoff_report_path,
        response_state=response_payload["response_state"],
        validation_class=validation_record.validation_class,
        gate_report=gate_report,
        summary_payload=summary_payload,
        operator_report_text=operator_report_text,
    )


def _normalize_scenario(request: Mapping[str, Any]) -> ReadOnlyScenario:
    candidates = [
        request.get("scenario"),
        request.get("read_only_scenario"),
        request.get("readOnlyScenario"),
        request.get("metadata", {}).get("read_only_scenario") if isinstance(request.get("metadata"), Mapping) else None,
    ]
    for value in candidates:
        if not value:
            continue
        candidate = str(value).strip().lower()
        if candidate in ALLOWED_SCENARIOS:
            return candidate  # type: ignore[return-value]
    return "read_completed"


def _session_id(request: Mapping[str, Any], scenario: str) -> str:
    explicit = request.get("session_id") or request.get("run_id")
    if explicit:
        return str(explicit)
    return f"LIVE_READ_ONLY_{scenario.upper()}"


def _build_gate_report(validation_class: str, notes: str) -> dict[str, Any]:
    if validation_class in {"passed", "passed_with_warnings"}:
        overall = "ALLOW"
        score = 1.0
    elif validation_class in {"partial_success", "retryable_failure"}:
        overall = "ASK"
        score = 0.5
    else:
        overall = "BLOCK"
        score = 0.0
    reason = f"Read-only runner bridge classified the session as {validation_class}. {notes}".strip()
    return {
        "overall_status": overall,
        "overall_score": score,
        "gates": [
            {
                "name": "read_only_bridge",
                "status": overall,
                "score": score,
                "reasons": [reason],
            }
        ],
        "patch_stats": {
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
            "touched_files": [],
            "loc_delta": 0,
        },
        "artifacts": [],
        "policy": {
            "allowed": overall != "BLOCK",
            "violations": [] if overall == "ALLOW" else [
                {
                    "rule": "read_only_validation_review",
                    "detail": reason,
                    "evidence": validation_class,
                    "severity": "soft" if overall == "ASK" else "hard",
                }
            ],
            "risk_score": 0.0 if overall == "ALLOW" else 0.5 if overall == "ASK" else 1.0,
            "verdict": overall,
        },
    }


def _next_action_for_validation_class(validation_class: str) -> str:
    if validation_class == "partial_success":
        return "Review the partial bounded read outcome before another runner session is scheduled."
    if validation_class == "retryable_failure":
        return "Retry only the bounded read-only session within the same approved scope after operator review."
    if validation_class == "terminal_failure":
        return "Do not retry the same bounded request shape; review the structural invalidity first."
    return "Keep the live read-only session within the current bounded scope."


def _write_dual_json(root: Path, session_bundle_dir: Path, filename: str, payload: dict[str, Any]) -> None:
    write_json(root / filename, payload)
    write_json(session_bundle_dir / filename, payload)


def _write_dual_text(root: Path, session_bundle_dir: Path, filename: str, content: str) -> None:
    safe_write_text(root / filename, content)
    safe_write_text(session_bundle_dir / filename, content)


__all__ = ["RunnerReadOnlyBridgeResult", "execute_read_only_session"]