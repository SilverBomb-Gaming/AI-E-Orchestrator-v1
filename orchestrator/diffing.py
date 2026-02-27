from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import read_json


DIFF_POLICY_RISK_THRESHOLD = 0.3
PATCH_LOC_SPIKE_THRESHOLD = 100
FILES_TOUCHED_SPIKE_THRESHOLD = 3
NO_CHANGE_VERDICTS = {"ALLOW", "ASK", "BLOCK"}
DEFAULT_NO_CHANGE_VERDICT = "ALLOW"


@dataclass(frozen=True)
class RegressionGate:
    verdict: str
    reasons: List[str]


def find_previous_run(runs_dir: Path, task_id: str, current_run_id: str) -> Optional[Path]:
    if not runs_dir.exists():
        return None
    suffix = f"_{task_id}"
    candidates = [
        entry
        for entry in runs_dir.iterdir()
        if entry.is_dir() and entry.name.endswith(suffix)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda entry: entry.name)
    previous = [entry for entry in candidates if entry.name < current_run_id]
    if not previous:
        return None
    return previous[-1]


def build_diff_report(
    *,
    current_run_dir: Path,
    previous_run_dir: Path,
    gate_report: Dict[str, any],
    command_results: List[Dict[str, any]],
    current_summary_path: Optional[Path],
    current_classification_path: Optional[Path] = None,
    regression_config: Optional[Dict[str, any]] = None,
) -> Tuple[Dict[str, any], RegressionGate]:
    previous_summary = _load_unity_summary(previous_run_dir)
    current_summary = _load_file(current_summary_path) if current_summary_path else {}
    previous_classification = _load_error_classification(previous_run_dir)
    current_classification = _load_file(current_classification_path)
    previous_gate = read_json(previous_run_dir / "gate_report.json", default={})
    previous_commands_payload = read_json(previous_run_dir / "command_results.json", default={})
    previous_commands = previous_commands_payload.get("commands", [])

    prev_error = int(previous_summary.get("error_count", 0) or 0)
    prev_warning = int(previous_summary.get("warning_count", 0) or 0)
    curr_error = int(current_summary.get("error_count", 0) or 0)
    curr_warning = int(current_summary.get("warning_count", 0) or 0)
    error_delta = curr_error - prev_error
    warning_delta = curr_warning - prev_warning

    prev_signatures = _signature_set(previous_summary, "top_errors")
    curr_signatures = _signature_set(current_summary, "top_errors")
    prev_warning_signatures = _signature_set(previous_summary, "top_warnings")
    curr_warning_signatures = _signature_set(current_summary, "top_warnings")
    new_signatures = sorted(signature for signature in curr_signatures - prev_signatures if signature)
    removed_signatures = sorted(signature for signature in prev_signatures - curr_signatures if signature)
    curr_actionable_signatures, curr_actionable_count, classification_applied = _resolve_actionable_details(
        current_classification,
        curr_signatures,
        curr_error,
    )
    prev_actionable_signatures, prev_actionable_count, _ = _resolve_actionable_details(
        previous_classification,
        prev_signatures,
        prev_error,
    )
    new_actionable_signatures = sorted(
        signature for signature in curr_actionable_signatures - prev_actionable_signatures if signature
    )
    actionable_error_delta = (
        curr_actionable_count - prev_actionable_count
        if curr_actionable_count is not None and prev_actionable_count is not None
        else None
    )

    current_policy = gate_report.get("policy", {})
    previous_policy = previous_gate.get("policy", {})
    current_risk = float(current_policy.get("risk_score", 0.0) or 0.0)
    previous_risk = float(previous_policy.get("risk_score", 0.0) or 0.0)
    policy_risk_delta = round(current_risk - previous_risk, 2)
    current_policy_verdict = str(current_policy.get("verdict", "ALLOW") or "ALLOW").upper()
    previous_policy_verdict = str(previous_policy.get("verdict", "ALLOW") or "ALLOW").upper()
    policy_verdict_static = current_policy_verdict == previous_policy_verdict
    policy_risk_static = policy_risk_delta == 0

    current_patch = gate_report.get("patch_stats", {})
    previous_patch = previous_gate.get("patch_stats", {})
    curr_loc = int(current_patch.get("loc_delta", 0) or 0)
    prev_loc = int(previous_patch.get("loc_delta", 0) or 0)
    patch_loc_delta = curr_loc - prev_loc
    curr_files = int(current_patch.get("files_changed", 0) or 0)
    prev_files = int(previous_patch.get("files_changed", 0) or 0)
    files_touched_delta = curr_files - prev_files
    curr_patch_present = bool(curr_files or curr_loc)
    prev_patch_present = bool(prev_files or prev_loc)
    patch_stats_static = (
        curr_loc == prev_loc
        and curr_files == prev_files
        and curr_patch_present == prev_patch_present
    )

    runtime_delta = _runtime_total(command_results) - _runtime_total(previous_commands)

    report = {
        "previous_bundle_id": previous_run_dir.name,
        "current_bundle_id": current_run_dir.name,
        "error_count_delta": error_delta,
        "warning_count_delta": warning_delta,
        "new_error_signatures": new_signatures,
        "removed_error_signatures": removed_signatures,
        "new_actionable_signatures": new_actionable_signatures,
        "policy_risk_delta": policy_risk_delta,
        "patch_loc_delta": patch_loc_delta,
        "files_touched_delta": files_touched_delta,
        "runtime_delta_seconds": round(runtime_delta, 2),
        "actionable_error_delta": actionable_error_delta,
        "classification_applied": classification_applied,
    }
    report["regression_config"] = regression_config or {"no_change_verdict": DEFAULT_NO_CHANGE_VERDICT}

    no_change_detected = _is_no_change(
        error_counts_static=error_delta == 0,
        warning_counts_static=warning_delta == 0,
        error_signatures_static=curr_signatures == prev_signatures,
        warning_signatures_static=curr_warning_signatures == prev_warning_signatures,
        policy_verdict_static=policy_verdict_static,
        policy_risk_static=policy_risk_static,
        patch_stats_static=patch_stats_static,
    )
    report["no_change_detected"] = no_change_detected
    no_change_pref = _resolve_no_change_preference(regression_config)
    regression_verdict, reasons = _regression_decision(
        report=report,
        new_signatures=new_signatures,
        new_actionable_signatures=new_actionable_signatures,
        policy_risk=current_risk,
        policy_allowed=bool(current_policy.get("allowed", True)),
        policy_verdict=current_policy.get("verdict", "ALLOW"),
        no_change_detected=no_change_detected,
        no_change_preference=no_change_pref,
        actionable_error_delta=actionable_error_delta,
        classification_applied=classification_applied,
    )
    regression_gate = RegressionGate(verdict=regression_verdict, reasons=reasons)
    report["regression_verdict"] = regression_verdict
    report["regression_reasons"] = reasons
    return report, regression_gate


def _runtime_total(command_results: List[Dict[str, any]]) -> float:
    total = 0.0
    for result in command_results or []:
        try:
            total += float(result.get("duration_seconds", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _load_unity_summary(run_dir: Path) -> Dict[str, any]:
    summary_path = run_dir / "artifacts" / "Tools" / "CI" / "unity_log_summary.json"
    return _load_file(summary_path)


def _load_file(path: Path) -> Dict[str, any]:
    if not path or not path.exists():
        return {}
    return read_json(path, default={})


def _regression_decision(
    *,
    report: Dict[str, any],
    new_signatures: List[str],
    new_actionable_signatures: List[str],
    policy_risk: float,
    policy_allowed: bool,
    policy_verdict: str,
    no_change_detected: bool,
    no_change_preference: str,
    actionable_error_delta: Optional[int],
    classification_applied: bool,
) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    status = "ALLOW"
    if no_change_detected:
        if no_change_preference == "ASK":
            return "ASK", ["no_change_detected"]
        if no_change_preference == "BLOCK":
            return "BLOCK", ["no_change_detected"]
        return "ALLOW", ["no_change_stop"]
    if not policy_allowed or (policy_verdict or "").upper() == "BLOCK":
        status = "BLOCK"
        reasons.append("Policy reported hard violations; see policy gate for details.")
        return status, reasons

    actionable_delta = actionable_error_delta if actionable_error_delta is not None else report["error_count_delta"]
    actionable_label = "actionable error" if actionable_error_delta is not None else "error"

    if new_actionable_signatures:
        status = "ASK"
        reasons.append("New actionable error signatures detected: " + ", ".join(new_actionable_signatures[:5]))
    elif not classification_applied and new_signatures:
        status = "ASK"
        reasons.append("New error signatures detected: " + ", ".join(new_signatures[:5]))

    if actionable_delta > 0:
        status = "ASK"
        reasons.append(f"{actionable_label.title()} count increased by {actionable_delta}.")

    if report["policy_risk_delta"] > 0 and policy_risk > DIFF_POLICY_RISK_THRESHOLD:
        status = "ASK"
        reasons.append(
            f"Policy risk increased to {policy_risk:.2f} (delta {report['policy_risk_delta']})."
        )

    if report["patch_loc_delta"] > PATCH_LOC_SPIKE_THRESHOLD or report["files_touched_delta"] > FILES_TOUCHED_SPIKE_THRESHOLD:
        status = "ASK"
        reasons.append(
            f"Patch spike detected (LOC delta {report['patch_loc_delta']}, files delta {report['files_touched_delta']})."
        )

    patch_static = report.get("patch_loc_delta", 0) == 0 and report.get("files_touched_delta", 0) == 0
    signal_static = (
        report.get("error_count_delta", 0) == 0
        and report.get("warning_count_delta", 0) == 0
        and not report.get("removed_error_signatures")
        and not new_signatures
    )
    if patch_static and signal_static:
        status = "ASK"
        reasons.append("No change detected relative to previous bundle; awaiting operator intervention.")

    if not reasons:
        reasons.append("No regressions detected against previous bundle.")
    return status, reasons


def _is_no_change(
    *,
    error_counts_static: bool,
    warning_counts_static: bool,
    error_signatures_static: bool,
    warning_signatures_static: bool,
    policy_verdict_static: bool,
    policy_risk_static: bool,
    patch_stats_static: bool,
) -> bool:
    return all(
        [
            error_counts_static,
            warning_counts_static,
            error_signatures_static,
            warning_signatures_static,
            policy_verdict_static,
            policy_risk_static,
            patch_stats_static,
        ]
    )


def _signature_set(summary: Dict[str, any], key: str) -> set[str]:
    entries = summary.get(key, []) or []
    return {str(item.get("message", "")) for item in entries if item.get("message")}


def _load_error_classification(run_dir: Path) -> Dict[str, any]:
    path = run_dir / "artifacts" / "Tools" / "CI" / "unity_error_classification.json"
    return _load_file(path)


def _resolve_actionable_details(
    classification: Dict[str, any],
    fallback_signatures: set[str],
    fallback_error_count: int,
) -> Tuple[set[str], Optional[int], bool]:
    if classification:
        actionable = set(classification.get("actionable_signatures", []))
        if classification.get("unknown_considered_actionable", True):
            actionable.update(classification.get("unknown_signatures", []) or [])
        count_value = classification.get("actionable_error_count")
        try:
            actionable_count = int(count_value)
        except (TypeError, ValueError):
            actionable_count = fallback_error_count
        return actionable, actionable_count, True
    return set(fallback_signatures), fallback_error_count, False


def _resolve_no_change_preference(regression_config: Optional[Dict[str, any]]) -> str:
    if not regression_config:
        return DEFAULT_NO_CHANGE_VERDICT
    preference = str(regression_config.get("no_change_verdict", DEFAULT_NO_CHANGE_VERDICT)).upper()
    if preference not in NO_CHANGE_VERDICTS:
        return DEFAULT_NO_CHANGE_VERDICT
    return preference
