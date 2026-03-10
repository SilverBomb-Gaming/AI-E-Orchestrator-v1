from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Sequence

from orchestrator.config import OrchestratorConfig

Status = Literal["PASS", "FAIL", "WARN"]


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def run_checks(contract_path: Path) -> List[CheckResult]:
    config = OrchestratorConfig.load()
    contract_result, contract_data = _validate_contract(contract_path)
    results: List[CheckResult] = [check_python_version(), check_virtual_env(config), check_core_directories(config)]
    results.append(check_queue_files(config))
    results.append(contract_result)
    if not contract_data:
        return results
    target_repo_result, target_repo_path = check_target_repo(contract_data)
    results.append(target_repo_result)
    if not target_repo_path:
        return results
    results.append(check_repo_assets(target_repo_path, contract_data))
    results.append(check_log_and_output_dirs(target_repo_path, contract_data))
    results.append(check_unity_path(target_repo_path))
    results.append(check_command_allowlist(config, contract_data))
    return results


def check_python_version() -> CheckResult:
    version = sys.version_info
    status: Status = "PASS" if version >= (3, 10) else "FAIL"
    detail = f"Detected Python {platform.python_version()}"
    if status == "FAIL":
        detail += " (requires >= 3.10)"
    return CheckResult("Python runtime", status, detail)


def check_virtual_env(config: OrchestratorConfig) -> CheckResult:
    venv_path = config.root_dir / ".venv-2" / "Scripts" / "python.exe"
    if venv_path.exists():
        detail = f"Found orchestrator venv at {venv_path}"
        return CheckResult(".venv-2 availability", "PASS", detail)
    detail = f"Missing validated interpreter at {venv_path}. Restore or reselect the existing .venv-2 environment."
    return CheckResult(".venv-2 availability", "FAIL", detail)


def check_core_directories(config: OrchestratorConfig) -> CheckResult:
    checks = {
        "runs_dir": config.runs_dir,
        "workspaces_dir": config.workspaces_dir,
        "contracts_dir": config.contracts_dir,
        "queue_contracts_dir": config.queue_contracts_dir,
    }
    missing = [name for name, path in checks.items() if not path.exists()]
    unwritable = [name for name, path in checks.items() if path.exists() and not os.access(path, os.W_OK)]
    if not missing and not unwritable:
        detail = ", ".join(f"{name}={path}" for name, path in checks.items())
        return CheckResult("Core directories", "PASS", detail)
    issues: List[str] = []
    if missing:
        issues.append(f"missing: {', '.join(missing)}")
    if unwritable:
        issues.append(f"read-only: {', '.join(unwritable)}")
    return CheckResult("Core directories", "FAIL", "; ".join(issues))


def check_queue_files(config: OrchestratorConfig) -> CheckResult:
    files = {
        "queue": config.queue_path,
        "approvals": config.approvals_path,
        "command_allowlist": config.command_allowlist_path,
    }
    problems: List[str] = []
    for label, path in files.items():
        if not path.exists():
            problems.append(f"{label} missing ({path})")
            continue
        if not os.access(path, os.R_OK | os.W_OK):
            problems.append(f"{label} not read/write ({path})")
        else:
            try:
                if path.suffix.lower() == ".json":
                    json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - defensive
                problems.append(f"{label} invalid JSON: {exc}")
    if problems:
        return CheckResult("Queue + approvals files", "FAIL", "; ".join(problems))
    detail = ", ".join(f"{label}={path}" for label, path in files.items())
    return CheckResult("Queue + approvals files", "PASS", detail)


def _validate_contract(contract_path: Path) -> tuple[CheckResult, Dict[str, Any] | None]:
    if not contract_path.exists():
        result = CheckResult("Entity contract", "FAIL", f"Missing contract at {contract_path}")
        return result, None
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result = CheckResult("Entity contract", "FAIL", f"Invalid JSON: {exc}")
        return result, None
    contract_type = str(payload.get("type", "")).lower()
    if contract_type != "entity_generation":
        result = CheckResult("Entity contract", "FAIL", f"Expected type 'entity_generation', found '{contract_type}'")
        return result, None
    workflow = payload.get("workflow") or {}
    missing_blocks = [block for block in ("prefab", "preview") if block not in workflow]
    if missing_blocks:
        result = CheckResult("Entity contract", "FAIL", f"Missing workflow blocks: {', '.join(missing_blocks)}")
        return result, None
    prefab = workflow.get("prefab", {})
    preview = workflow.get("preview", {})
    prefab_keys = {"script", "source_asset", "animation_asset", "prefab_output_path", "artifact", "log"}
    preview_keys = {"script", "prefab_path", "preview_png", "artifact", "log"}
    prefab_missing = sorted(key for key in prefab_keys if key not in prefab)
    preview_missing = sorted(key for key in preview_keys if key not in preview)
    missing_messages: List[str] = []
    if prefab_missing:
        missing_messages.append(f"prefab.{', '.join(prefab_missing)}")
    if preview_missing:
        missing_messages.append(f"preview.{', '.join(preview_missing)}")
    if missing_messages:
        result = CheckResult("Entity contract", "FAIL", f"Missing keys: {', '.join(missing_messages)}")
        return result, None
    detail = f"Validated {contract_path.name}"
    return CheckResult("Entity contract", "PASS", detail), payload


def check_target_repo(contract_data: Dict[str, Any]) -> tuple[CheckResult, Path | None]:
    raw_path = contract_data.get("target_repo") or contract_data.get("Target Repo Path")
    if not raw_path:
        return CheckResult("Target repo", "FAIL", "No 'target_repo' declared"), None
    repo_path = Path(raw_path)
    if not repo_path.exists():
        detail = f"Target repo not found at {repo_path}"
        return CheckResult("Target repo", "FAIL", detail), None
    if not repo_path.is_dir():
        detail = f"Target repo is not a directory ({repo_path})"
        return CheckResult("Target repo", "FAIL", detail), None
    if not os.access(repo_path, os.R_OK | os.W_OK):
        detail = f"Insufficient permissions for {repo_path}"
        return CheckResult("Target repo", "FAIL", detail), None
    return CheckResult("Target repo", "PASS", f"Repo resolved to {repo_path}"), repo_path


def check_repo_assets(repo_path: Path, contract_data: Dict[str, Any]) -> CheckResult:
    workflow = contract_data.get("workflow") or {}
    prefab = workflow.get("prefab", {})
    preview = workflow.get("preview", {})
    required_files: List[str] = []
    required_files.append(prefab["script"])
    required_files.append(preview["script"])
    required_files.append(prefab["source_asset"])
    required_files.append(prefab["animation_asset"])
    inputs_missing = _collect_missing(repo_path, required_files)
    if inputs_missing:
        return CheckResult("Unity scripts + inputs", "FAIL", f"Missing: {', '.join(inputs_missing)}")
    detail = ", ".join(sorted(set(required_files)))
    return CheckResult("Unity scripts + inputs", "PASS", f"Present: {detail}")


def check_log_and_output_dirs(repo_path: Path, contract_data: Dict[str, Any]) -> CheckResult:
    workflow = contract_data.get("workflow") or {}
    prefab = workflow.get("prefab", {})
    preview = workflow.get("preview", {})
    paths_to_confirm: List[Path] = []
    paths_to_confirm.append(_resolve_repo_path(repo_path, prefab["prefab_output_path"]).parent)
    paths_to_confirm.append(_resolve_repo_path(repo_path, preview.get("prefab_path", prefab["prefab_output_path"])).parent)
    paths_to_confirm.append(_resolve_repo_path(repo_path, prefab["artifact"]).parent)
    paths_to_confirm.append(_resolve_repo_path(repo_path, prefab["log"]).parent)
    paths_to_confirm.append(_resolve_repo_path(repo_path, preview["artifact"]).parent)
    paths_to_confirm.append(_resolve_repo_path(repo_path, preview["log"]).parent)
    paths_to_confirm.append(_resolve_repo_path(repo_path, preview["preview_png"]).parent)
    issues: List[str] = []
    for path in paths_to_confirm:
        rel = _safe_relpath(path, repo_path)
        if not path.exists():
            issues.append(f"missing {rel}")
        elif not os.access(path, os.W_OK):
            issues.append(f"read-only {rel}")
    if issues:
        return CheckResult("Log/output directories", "FAIL", "; ".join(issues))
    detail = "All artifact/log directories writable"
    return CheckResult("Log/output directories", "PASS", detail)


def check_unity_path(repo_path: Path) -> CheckResult:
    candidates: List[Path] = []
    env_value = os.environ.get("UNITY_EDITOR_EXE")
    if env_value:
        candidates.append(Path(env_value))
    path_file = repo_path / "Tools" / "unity_editor_path.txt"
    if path_file.exists():
        first_line = path_file.read_text(encoding="utf-8").strip()
        if first_line:
            candidates.append(Path(first_line))
    hub_default = Path("D:/Program Files/Unity Hub/Editor/6000.2.8f1/Editor/Unity.exe")
    if hub_default.exists():
        candidates.append(hub_default)
    resolved = next((path for path in candidates if path.exists()), None)
    if resolved:
        return CheckResult("Unity editor path", "PASS", f"Unity.exe located at {resolved}")
    detail = "No UNITY_EDITOR_EXE env var, unity_editor_path.txt entry, or default Hub install"
    return CheckResult("Unity editor path", "FAIL", detail)


def check_command_allowlist(config: OrchestratorConfig, contract_data: Dict[str, Any]) -> CheckResult:
    allowlist_path = config.command_allowlist_path
    if not allowlist_path.exists():
        return CheckResult("Command allowlist", "FAIL", f"Missing {allowlist_path}")
    try:
        allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("Command allowlist", "FAIL", f"Invalid JSON: {exc}")
    entries = [entry.lower() for entry in allowlist.get("exact", [])]
    workflow = contract_data.get("workflow") or {}
    prefab_script = Path(workflow.get("prefab", {}).get("script", "")).name.lower()
    preview_script = Path(workflow.get("preview", {}).get("script", "")).name.lower()
    missing: List[str] = []
    for script_name in (prefab_script, preview_script):
        if not script_name:
            continue
        if not any(script_name in entry for entry in entries):
            missing.append(script_name)
    if missing:
        detail = f"Scripts not present in allowlist 'exact' entries: {', '.join(missing)}"
        return CheckResult("Command allowlist", "FAIL", detail)
    detail = "Prefab + preview scripts present in allowlist"
    return CheckResult("Command allowlist", "PASS", detail)


def _collect_missing(repo_root: Path, relative_paths: Iterable[str]) -> List[str]:
    missing: List[str] = []
    for rel in relative_paths:
        candidate = _resolve_repo_path(repo_root, rel)
        if not candidate.exists():
            missing.append(_safe_relpath(candidate, repo_root))
    return missing


def _resolve_repo_path(repo_root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        return candidate
    normalized = relative_path.replace("\\", "/")
    return repo_root / Path(normalized)


def _safe_relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def format_results(results: Sequence[CheckResult], *, json_mode: bool) -> int:
    failures = [item for item in results if item.status == "FAIL"]
    warnings = [item for item in results if item.status == "WARN"]
    overall = "PASS" if not failures else "FAIL"
    if json_mode:
        payload = {
            "overall": overall,
            "failures": len(failures),
            "warnings": len(warnings),
            "results": [item.as_dict() for item in results],
        }
        print(json.dumps(payload, indent=2))
    else:
        print("=== AI-E Entity Preflight ===")
        for item in results:
            print(f"[{item.status}] {item.name}: {item.detail}")
        print(f"\nOverall: {overall} (fails={len(failures)}, warnings={len(warnings)})")
    return 0 if overall == "PASS" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify ENTITY_0001 prerequisites before queueing work.")
    default_contract = Path("contracts/entities/zombie_basic.json")
    parser.add_argument(
        "--contract",
        type=Path,
        default=default_contract,
        help=f"Path to entity contract (default: {default_contract})",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract_path = args.contract
    if not contract_path.is_absolute():
        contract_path = (OrchestratorConfig.load().root_dir / contract_path).resolve()
    results = run_checks(contract_path)
    return format_results(results, json_mode=args.json)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
