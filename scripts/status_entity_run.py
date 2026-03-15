from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.config import OrchestratorConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose the latest ENTITY run state.")
    parser.add_argument("--task-id", default="ENTITY_0001", help="Queue task identifier (default: ENTITY_0001)")
    parser.add_argument("--run-id", help="Specific run ID to inspect")
    parser.add_argument(
        "--stale-seconds",
        type=int,
        default=300,
        help="Threshold for considering logs stale (default: 300)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


_ENTITY_STAGE_RANKS: Dict[str, int] = {
    "project_open_end": 10,
    "editor_startup_reached": 20,
    "asset_refresh_begin": 30,
    "asset_refresh_end": 40,
    "script_compile_begin": 50,
    "script_compile_end": 60,
    "workspace_import_in_progress": 65,
    "package_manager_activity_begin": 70,
    "package_manager_activity_end": 80,
    "editor_ready": 90,
    "bootstrap_execute_method_entered": 100,
    "bootstrap_pending_dispatch_set": 105,
    "bootstrap_monitor_registered": 110,
    "bootstrap_waiting_for_editor_ready": 115,
    "bootstrap_dispatch_not_ready": 120,
    "bootstrap_dispatch_ready": 130,
    "bootstrap_dispatch_delaycall_queued": 135,
    "bootstrap_dispatch_immediate_run": 140,
    "bootstrap_dispatch_invoking_run": 145,
    "execute_method_entered": 150,
    "start": 160,
    "source_asset_load_begin": 165,
    "source_asset_load_end": 170,
    "animation_asset_load_begin": 175,
    "animation_asset_load_end": 180,
    "animation_asset_load_skipped": 180,
    "instantiate_begin": 185,
    "instantiate_end": 190,
    "animator_setup_begin": 195,
    "controller_build_begin": 200,
    "controller_build_end": 205,
    "controller_build_skipped": 205,
    "animator_setup_end": 210,
    "prefab_save_begin": 220,
    "prefab_save_end": 230,
    "artifact_write_begin": 240,
    "artifact_write_end": 250,
    "complete": 260,
    "error": 260,
}

_UNITY_BOOT_STAGE_RE = re.compile(r"\[UNITY_BOOT\]\s+([A-Za-z0-9_]+)")
_HEARTBEAT_STAGE_RE = re.compile(r"CREATE_PREFAB_HEARTBEAT .*?startup_stage=([A-Za-z0-9_]+)")


def _stage_rank(stage: str) -> int:
    return _ENTITY_STAGE_RANKS.get((stage or "").strip(), 0)


def _prefer_stage(current: str, candidate: str) -> str:
    candidate = (candidate or "").strip()
    if not candidate:
        return current
    if not current or _stage_rank(candidate) >= _stage_rank(current):
        return candidate
    return current


def load_stage_diagnostic(repo_logs: Path) -> Dict[str, Any]:
    return load_json(repo_logs / "zombie_prefab_creation_diagnostic.json")


def infer_stage_from_diagnostic(diagnostic: Dict[str, Any]) -> str:
    if not diagnostic:
        return ""
    best = ""
    for entry in diagnostic.get("stage_trace", []):
        if isinstance(entry, dict):
            best = _prefer_stage(best, str(entry.get("stage") or ""))
    for key, stage in (
        ("artifact_write_completed", "artifact_write_end"),
        ("prefab_save_completed", "prefab_save_end"),
        ("controller_build_completed", "controller_build_end"),
        ("animator_setup_completed", "animator_setup_end"),
        ("instantiate_completed", "instantiate_end"),
        ("prefab_creation_started", "start"),
        ("execute_method_entered", "execute_method_entered"),
        ("editor_ready_detected", "editor_ready"),
        ("script_compile_completed", "script_compile_end"),
        ("asset_refresh_completed", "asset_refresh_end"),
        ("asset_refresh_detected", "asset_refresh_begin"),
        ("editor_startup_reached", "editor_startup_reached"),
        ("project_open_detected", "project_open_end"),
    ):
        if diagnostic.get(key):
            best = _prefer_stage(best, stage)
    best = _prefer_stage(best, str(diagnostic.get("last_boot_stage") or ""))
    best = _prefer_stage(best, str(diagnostic.get("last_stage") or ""))
    return best


def infer_stage_from_launcher_log(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    best = ""
    for line in text.splitlines():
        heartbeat_match = _HEARTBEAT_STAGE_RE.search(line)
        if heartbeat_match:
            best = _prefer_stage(best, heartbeat_match.group(1))
        stage_match = _UNITY_BOOT_STAGE_RE.search(line)
        if stage_match:
            best = _prefer_stage(best, stage_match.group(1))
    return best


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def find_run_bundle(runs_dir: Path, task_id: str, requested: Optional[str]) -> Tuple[str, Path]:
    if requested:
        candidate = runs_dir / requested
        if not candidate.exists():
            raise FileNotFoundError(f"Run {requested} not found under {runs_dir}")
        return requested, candidate
    normalized_task = task_id.lower()
    candidates: List[Path] = []
    for entry in runs_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.lower().endswith(f"_{normalized_task}"):
            candidates.append(entry)
    if not candidates:
        raise FileNotFoundError(f"No run bundles found for task {task_id}")
    candidates.sort(key=lambda path: path.name)
    chosen = candidates[-1]
    return chosen.name, chosen


def derive_workspace_path(workspaces_dir: Path, task_id: str, run_id: str, run_meta: Dict[str, Any]) -> Path:
    meta_path = run_meta.get("workspace_path")
    if meta_path:
        candidate = Path(meta_path)
        if candidate.exists():
            return candidate
    timestamp_parts = run_id.split("_")
    if len(timestamp_parts) < 2:
        return workspaces_dir / task_id
    timestamp = "_".join(timestamp_parts[:2])
    return workspaces_dir / task_id / timestamp


def collect_log_snapshot(paths: List[Path]) -> Tuple[Optional[float], Optional[str], Optional[float]]:
    candidates: List[float] = []
    for root in paths:
        if not root.exists():
            continue
        for candidate in root.rglob("*.log"):
            try:
                candidates.append(candidate.stat().st_mtime)
            except OSError:
                continue
    if not candidates:
        return None, None, None
    latest = max(candidates)
    iso_value = datetime.fromtimestamp(latest, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    delta = max(0.0, time.time() - latest)
    return latest, iso_value, round(delta, 1)


def detect_unity_process(workspace_path: Path) -> Tuple[Optional[bool], List[Dict[str, str]]]:
    escaped_workspace = str(workspace_path).replace("'", "''")
    command = (
        "$workspace = '{0}'; "
        "$processes = Get-CimInstance Win32_Process -Filter \"Name = 'Unity.exe'\" | "
        "Where-Object {{ $_.CommandLine -and $_.CommandLine -like ('*' + $workspace + '*') }} | "
        "Select-Object ProcessId, Name, CommandLine; "
        "$processes | ConvertTo-Json -Compress"
    ).format(escaped_workspace)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None, []
    output = (completed.stdout or "").strip()
    if not output:
        return False, []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None, []
    if isinstance(payload, dict):
        payload = [payload]
    processes: List[Dict[str, str]] = []
    for entry in payload or []:
        if not isinstance(entry, dict):
            continue
        processes.append(
            {
                "pid": str(entry.get("ProcessId", "")),
                "name": str(entry.get("Name", "Unity.exe")),
                "command_line": str(entry.get("CommandLine", "")),
            }
        )
    return bool(processes), processes


def finalization_check(run_dir: Path, task_id: str) -> Tuple[bool, List[str]]:
    requirements = {
        "command_results": run_dir / "command_results.json",
        "gate_report": run_dir / "gate_report.json",
        "summary": run_dir / "summary.md",
        "run_report": run_dir / "report_last_run.md",
        "run_meta": run_dir / "run_meta.json",
    }
    if task_id.upper().startswith("ENTITY_"):
        requirements["entity_validation"] = run_dir / "entity" / "entity_validation.json"
    failures: List[str] = []
    for label, path in requirements.items():
        if not path.exists():
            failures.append(f"{label} missing ({safe_relative(path, run_dir)})")
            continue
        try:
            if path.stat().st_size <= 0:
                failures.append(f"{label} empty ({safe_relative(path, run_dir)})")
        except OSError:
            failures.append(f"{label} unreadable ({safe_relative(path, run_dir)})")
    return (len(failures) == 0, failures)


def artifact_presence(run_dir: Path, expect_entity: bool) -> Dict[str, bool]:
    payload = {
        "command_results": (run_dir / "command_results.json").exists(),
        "gate_report": (run_dir / "gate_report.json").exists(),
        "summary": (run_dir / "summary.md").exists(),
        "run_report": (run_dir / "report_last_run.md").exists(),
        "run_meta": (run_dir / "run_meta.json").exists(),
        "entity_validation": False,
    }
    if expect_entity:
        payload["entity_validation"] = (run_dir / "entity" / "entity_validation.json").exists()
    return payload


def infer_stage(run_dir: Path, workspace_repo: Path, expect_entity: bool) -> str:
    if not expect_entity:
        return "general"
    repo_logs = workspace_repo / "scripts" / "logs"
    diagnostic_stage = infer_stage_from_diagnostic(load_stage_diagnostic(repo_logs))
    if diagnostic_stage:
        return diagnostic_stage
    launcher_stage = infer_stage_from_launcher_log(repo_logs / "zombie_prefab_creation.log.launcher.log")
    if launcher_stage:
        return launcher_stage
    entity_dir = run_dir / "entity"
    if (entity_dir / "entity_validation.json").exists():
        return "finalization"
    if (entity_dir / "entity_preview.json").exists() or (entity_dir / "entity_preview.png").exists():
        return "preview"
    if (entity_dir / "entity_prefab.json").exists():
        return "prefab"
    if (repo_logs / "zombie_prefab_preview.json").exists():
        return "preview"
    if (repo_logs / "zombie_prefab_creation.json").exists():
        return "prefab"
    return "initialization"


def parse_exit_code_from_log(path: Path) -> Tuple[str, str]:
    if not path.exists():
        return "", "stdout log missing"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", "stdout log unreadable"
    reason = ""
    for line in text.splitlines():
        if line.startswith("UNITY_EXIT_CODE="):
            value = line.partition("=")[2].strip()
            if value:
                return value, reason
            reason = "wrapper emitted blank UNITY_EXIT_CODE"
        elif line.startswith("UNITY_EXIT_REASON=") and not reason:
            reason = line.partition("=")[2].strip()
    if not reason:
        reason = "wrapper did not emit UNITY_EXIT_CODE"
    return "UNKNOWN", reason


def read_wrapper_exit_codes(command_results: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str], List[str]]:
    results: Dict[str, str] = {}
    reasons: Dict[str, str] = {}
    issues: List[str] = []
    for entry in command_results:
        name = str(entry.get("name", "command"))
        unity_exit_code = str(entry.get("unity_exit_code") or "").strip()
        unity_exit_reason = str(entry.get("unity_exit_reason") or "").strip()
        if not unity_exit_code or (unity_exit_code == "UNKNOWN" and not unity_exit_reason):
            stdout_log = Path(str(entry.get("stdout_log") or ""))
            parsed_code, parsed_reason = parse_exit_code_from_log(stdout_log)
            if not unity_exit_code:
                unity_exit_code = parsed_code
            if not unity_exit_reason:
                unity_exit_reason = parsed_reason
        if not unity_exit_code:
            unity_exit_code = "UNKNOWN"
        results[name] = unity_exit_code
        if unity_exit_reason:
            reasons[name] = unity_exit_reason
        command_return = str(entry.get("returncode", "")).strip()
        if unity_exit_code == "UNKNOWN":
            issue = f"{name}: UNITY_EXIT_CODE unresolved"
            if unity_exit_reason:
                issue += f" ({unity_exit_reason})"
            issues.append(issue)
        elif command_return and unity_exit_code != command_return:
            issues.append(
                f"{name}: wrapper Unity exit {unity_exit_code} differs from command returncode {command_return}"
            )
    return results, reasons, issues


def infer_state(
    *,
    unity_running: Optional[bool],
    log_recent: bool,
    finalization_complete: bool,
    gate_status: str,
    entity_status: str,
    latest_ts: Optional[float],
    stale_seconds: int,
    has_any_outputs: bool,
) -> str:
    if unity_running:
        return "RUNNING"
    if log_recent and not finalization_complete:
        return "RUNNING"
    if finalization_complete:
        if entity_status in {"fail", "failed", "error", "internal_error", "unsupported"}:
            return "FAILED"
        if entity_status in {"partial", "warning", "warn"}:
            return "PARTIAL"
        if gate_status == "BLOCK":
            return "FAILED"
        if gate_status == "ASK":
            return "PARTIAL"
        if gate_status == "ALLOW":
            return "COMPLETED"
        return "UNKNOWN"
    stale_logs = latest_ts is not None and (time.time() - latest_ts) > stale_seconds
    if stale_logs and has_any_outputs:
        return "STALLED"
    if has_any_outputs:
        return "PARTIAL"
    return "UNKNOWN"


def write_stuck_diagnostic(run_dir: Path, payload: Dict[str, Any]) -> None:
    try:
        destination = run_dir / "stuck_diagnostic.json"
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    args = parse_args()
    config = OrchestratorConfig.load()
    run_id, run_dir = find_run_bundle(config.runs_dir, args.task_id, args.run_id)
    run_meta = load_json(run_dir / "run_meta.json")
    workspace_path = derive_workspace_path(config.workspaces_dir, args.task_id, run_id, run_meta)
    workspace_logs = workspace_path / "logs"
    workspace_repo = workspace_path / "repo"
    repo_logs = workspace_repo / "scripts" / "logs"
    entity_dir = run_dir / "entity"
    expect_entity = args.task_id.upper().startswith("ENTITY_")

    gate_report = load_json(run_dir / "gate_report.json")
    entity_validation = load_json(entity_dir / "entity_validation.json")
    command_results_payload = load_json(run_dir / "command_results.json")
    command_entries = command_results_payload.get("commands", []) if isinstance(command_results_payload, dict) else []

    latest_ts, latest_iso, latest_delta = collect_log_snapshot([workspace_logs, repo_logs])
    unity_running, unity_processes = detect_unity_process(workspace_path)
    log_recent = latest_ts is not None and (time.time() - latest_ts) <= args.stale_seconds
    finalization_complete, missing_items = finalization_check(run_dir, args.task_id)
    artifact_flags = artifact_presence(run_dir, expect_entity)
    latest_stage = infer_stage(run_dir, workspace_repo, expect_entity)
    gate_status = (gate_report.get("overall_status") or "").upper() if gate_report else ""
    entity_status = (entity_validation.get("status") or "").lower() if entity_validation else ""
    wrapper_exit_codes, wrapper_exit_reasons, wrapper_issues = read_wrapper_exit_codes(command_entries)
    has_any_outputs = any(artifact_flags.values()) or entity_dir.exists() or repo_logs.exists()

    state = infer_state(
        unity_running=unity_running,
        log_recent=log_recent,
        finalization_complete=finalization_complete,
        gate_status=gate_status,
        entity_status=entity_status,
        latest_ts=latest_ts,
        stale_seconds=args.stale_seconds,
        has_any_outputs=has_any_outputs,
    )

    notes: List[str] = []
    if unity_running:
        notes.append("Unity.exe process detected for this workspace")
    elif log_recent and not finalization_complete:
        notes.append("Logs updated within stale window")
    if state == "STALLED":
        notes.extend(missing_items)
    if not finalization_complete and not missing_items:
        notes.append("Finalization incomplete for unknown reasons")
    notes.extend(wrapper_issues)

    result = {
        "task_id": args.task_id,
        "run_id": run_id,
        "workspace_path": str(workspace_path),
        "run_bundle_path": str(run_dir),
        "state": state,
        "latest_stage": latest_stage,
        "latest_log_write_time": latest_iso,
        "seconds_since_last_log_write": latest_delta,
        "unity_process_detected": unity_running,
        "unity_processes": unity_processes,
        "artifact_presence": artifact_flags,
        "finalization_complete": finalization_complete,
        "missing_requirements": missing_items,
        "gate_overall": gate_status or None,
        "entity_status": entity_status or None,
        "wrapper_exit_codes": wrapper_exit_codes,
        "wrapper_exit_reasons": wrapper_exit_reasons,
        "notes": notes,
    }

    if state == "STALLED":
        diag_payload = {
            "run_id": run_id,
            "task_id": args.task_id,
            "workspace_path": str(workspace_path),
            "run_bundle_path": str(run_dir),
            "latest_stage": latest_stage,
            "unity_process_detected": unity_running,
            "latest_log_write_time": latest_iso,
            "seconds_since_last_log_write": latest_delta,
            "command_results_present": artifact_flags["command_results"],
            "entity_validation_present": artifact_flags["entity_validation"],
            "report_present": artifact_flags["run_report"],
            "gate_report_present": artifact_flags["gate_report"],
            "suspected_reason": "; ".join(missing_items) if missing_items else "finalization_incomplete",
            "status": "stalled",
        }
        write_stuck_diagnostic(run_dir, diag_payload)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=== Entity Run Status ===")
        print(f"Run ID: {run_id}")
        print(f"Task ID: {args.task_id}")
        print(f"Workspace: {workspace_path}")
        print(f"Run Bundle: {run_dir}")
        print(f"State: {state}")
        print(f"Latest Stage: {latest_stage}")
        if latest_iso:
            print(f"Last Log Write: {latest_iso} ({latest_delta}s ago)")
        if unity_running is not None:
            print(f"Unity.exe Running: {'yes' if unity_running else 'no'}")
        print("Artifacts:")
        for key, value in artifact_flags.items():
            print(f"- {key}: {'yes' if value else 'no'}")
        if wrapper_exit_codes:
            print("Wrapper Exit Codes:")
            for key, value in wrapper_exit_codes.items():
                print(f"- {key}: {value}")
        if wrapper_exit_reasons:
            print("Wrapper Exit Reasons:")
            for key, value in wrapper_exit_reasons.items():
                print(f"- {key}: {value}")
        if missing_items:
            print("Missing:")
            for item in missing_items:
                print(f"- {item}")
        if notes:
            print("Notes:")
            for note in notes:
                print(f"- {note}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as exc:
        print(f"[status_entity_run] {exc}", file=sys.stderr)
        raise SystemExit(1)
