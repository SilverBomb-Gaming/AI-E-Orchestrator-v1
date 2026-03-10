from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .contracts import Contract
from .utils import ensure_dir, safe_write_text, slugify, utc_timestamp, write_json
from .workspace import WorkspaceContext

_ENTITY_ARTIFACT_DIR = Path("entity")
_UNITY_LOG_RELATIVE = Path("scripts") / "logs" / "Editor.log"
_POWERSHELL_PREFIX = [
    "powershell.exe",
    "-NoLogo",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
]
_PREVIEW_DEFAULT_MIN_BYTES = 4096
_PREVIEW_DEFAULT_MIN_WIDTH = 256
_PREVIEW_DEFAULT_MIN_HEIGHT = 256
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_LOG_SAMPLE_LIMIT = 8
_LOG_CATEGORIES = ["fatal", "warnings", "environment_noise", "cleanup_issues", "unknown"]
_LOG_PATTERNS: Dict[str, List[Tuple[re.Pattern[str], str]]] = {
    "fatal": [
        (re.compile(r"nullreferenceexception", re.IGNORECASE), "NullReferenceException"),
        (re.compile(r"\berror\s+CS\d+", re.IGNORECASE), "C# compiler error"),
        (re.compile(r"unhandled exception", re.IGNORECASE), "Unhandled exception"),
        (re.compile(r"shader error", re.IGNORECASE), "Shader error"),
        (re.compile(r"failed to (?:load|create)", re.IGNORECASE), "Asset/load failure"),
    ],
    "warnings": [
        (re.compile(r"DrawOpaqueObjects.*surface", re.IGNORECASE), "Surface attachment warning"),
        (re.compile(r"DrawTransparentObjects.*surface", re.IGNORECASE), "Surface attachment warning"),
        (re.compile(r"EndRenderPass", re.IGNORECASE), "Render pass order warning"),
    ],
    "environment_noise": [
        (re.compile(r"\[Licensing::Module\]\s+Error:\s+Access token is unavailable", re.IGNORECASE), "Licensing access token unavailable"),
        (re.compile(r"\bLogAssemblyErrors\b", re.IGNORECASE), "Unity editor assembly scan marker"),
        (re.compile(r"curl error 6", re.IGNORECASE), "Unity services offline (curl)"),
        (re.compile(r"config\.uca\.cloud\.unity3d\.com", re.IGNORECASE), "Unity analytics unreachable"),
        (re.compile(r"Package Manager Server", re.IGNORECASE), "Package manager shutdown"),
        (re.compile(r"abort_threads", re.IGNORECASE), "Unity shutdown thread abort noise"),
    ],
    "cleanup_issues": [
        (re.compile(r"PlayableGraph was not destroyed", re.IGNORECASE), "PlayableGraph leak"),
        (re.compile(r"temp allocator", re.IGNORECASE), "Temp allocator leak"),
        (re.compile(r"PlayableGraph.*Destroy", re.IGNORECASE), "PlayableGraph destroy noise"),
    ],
}
_CLEANUP_FLAG_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"PlayableGraph was not destroyed", re.IGNORECASE), "playable_graph_leak_detected"),
    (re.compile(r"temp allocator", re.IGNORECASE), "temp_allocator_warning_detected"),
]


@dataclass
class EntityRunResult:
    command_results: List[Dict[str, Any]]
    notes: List[str]


def is_entity_generation_contract(contract: Contract | None) -> bool:
    if contract is None:
        return False
    contract_type = str(
        contract.metadata.get("type")
        or contract.metadata.get("Type")
        or contract.metadata.get("contract_type")
        or contract.metadata.get("contractType")
        or ""
    ).strip()
    return contract_type.lower() == "entity_generation"


def run_entity_generation(
    contract: Contract,
    workspace: WorkspaceContext,
    run_dir: Path,
) -> EntityRunResult:
    entity_meta = _entity_payload(contract)
    entity_name = entity_meta.get("entity_name") or contract.metadata.get("Objective", "EntityPrototype")
    entity_type = str(entity_meta.get("entity_type") or entity_meta.get("category") or "unknown").lower()
    if entity_type in {"zombie_basic", "zombie"}:
        return _run_zombie_entity(contract, workspace, run_dir, entity_meta, entity_name, entity_type)
    return _unsupported_entity(contract, workspace, run_dir, entity_name, entity_type)


def _run_zombie_entity(
    contract: Contract,
    workspace: WorkspaceContext,
    run_dir: Path,
    entity_meta: Dict[str, Any],
    entity_name: str,
    entity_type: str,
) -> EntityRunResult:
    workflow = entity_meta.get("workflow") or {}
    prefab_cfg = workflow.get("prefab") or {}
    preview_cfg = workflow.get("preview") or {}
    _validate_config(prefab_cfg, ["script", "source_asset", "animation_asset", "prefab_output_path", "artifact", "log"], "prefab")
    _validate_config(
        preview_cfg,
        ["script", "prefab_path", "preview_png", "artifact", "log"],
        "preview",
    )
    validation_cfg = entity_meta.get("validation") or {}
    preview_validation_cfg = preview_cfg.get("validation") or {}

    entity_repo_dir = _reset_entity_dir(workspace.repo_path)
    timestamp = utc_timestamp(compact=False)
    command_results: List[Dict[str, Any]] = []
    errors: List[str] = []
    warnings: List[str] = []

    prefab_result, prefab_return = _run_prefab_step(workspace, prefab_cfg)
    command_results.append(prefab_result)
    prefab_artifact_path = _resolve_repo_path(workspace.repo_path, prefab_cfg["artifact"])
    prefab_data = _read_json(prefab_artifact_path)
    prefab_success = prefab_return == 0 and prefab_data.get("prefab_created")
    if not prefab_success:
        errors.append(
            f"Prefab generation failed (returncode={prefab_return}); review {prefab_result['stdout_log']} for details."
        )

    preview_result: Optional[Dict[str, Any]] = None
    preview_return = None
    preview_data: Dict[str, Any] = {}
    preview_success = False
    if prefab_success:
        preview_result, preview_return = _run_preview_step(workspace, prefab_cfg, preview_cfg)
        command_results.append(preview_result)
        preview_artifact_path = _resolve_repo_path(workspace.repo_path, preview_cfg["artifact"])
        preview_data = _read_json(preview_artifact_path)
        preview_success = preview_return == 0 and preview_data.get("status") != "error"
        if not preview_success:
            errors.append(
                f"Preview generation failed (returncode={preview_return}); review {preview_result['stdout_log']} for details."
            )
    else:
        warnings.append("Preview step skipped because prefab generation failed.")

    warnings.extend(prefab_data.get("warnings", []))
    warnings.extend(preview_data.get("issues", []))

    entity_preview_json = entity_repo_dir / "entity_preview.json"
    entity_prefab_json = entity_repo_dir / "entity_prefab.json"
    if prefab_data:
        write_json(entity_prefab_json, prefab_data)
    if preview_data:
        write_json(entity_preview_json, preview_data)

    preview_png_destination: Optional[Path] = None
    preview_png_source = _resolve_repo_path(workspace.repo_path, preview_cfg.get("preview_png"))
    if preview_success and preview_png_source.exists():
        preview_png_destination = entity_repo_dir / "entity_preview.png"
        shutil.copy2(preview_png_source, preview_png_destination)
    elif preview_png_source and preview_png_source.exists():
        warnings.append("Preview PNG captured but probe reported issues; keeping raw artifact for reference.")
        preview_png_destination = entity_repo_dir / "entity_preview.png"
        shutil.copy2(preview_png_source, preview_png_destination)
    preview_validation = _validate_preview_image(
        preview_png_destination,
        min_bytes=int(preview_validation_cfg.get("min_bytes", _PREVIEW_DEFAULT_MIN_BYTES)),
        min_width=int(preview_validation_cfg.get("min_width", _PREVIEW_DEFAULT_MIN_WIDTH)),
        min_height=int(preview_validation_cfg.get("min_height", _PREVIEW_DEFAULT_MIN_HEIGHT)),
    )
    if preview_validation.get("status") == "fail":
        errors.append("Preview validation failed; inspect preview_validation block for details.")
    elif preview_validation.get("status") == "partial":
        warnings.append("Preview validation reported partial status; image exists but failed one or more thresholds.")

    editor_log_path = workspace.repo_path / _UNITY_LOG_RELATIVE
    if preview_success:
        frames_expected = int(validation_cfg.get("playmode_ticks", 240))
        _append_playmode_markers(editor_log_path, entity_name, frames_expected)
    log_classification, log_counts, cleanup_hygiene = _classify_editor_log(editor_log_path)

    status = _resolve_validation_status(
        prefab_success,
        preview_success,
        preview_validation,
        log_counts,
        cleanup_hygiene,
        errors,
    )

    validation_payload = _build_validation_payload(
        contract,
        entity_name,
        entity_type,
        prefab_cfg,
        prefab_data,
        prefab_success,
        preview_data,
        preview_success,
        preview_png_destination,
        workspace.repo_path,
        warnings,
        errors,
        preview_validation,
        log_classification,
        log_counts,
        cleanup_hygiene,
        status,
    )
    write_json(entity_repo_dir / "entity_validation.json", validation_payload)

    summary_payload = {
        "entity_id": contract.task_id,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "generated_at": timestamp,
        "status": validation_payload["status"],
        "prefab_step": {
            "returncode": prefab_return,
            "log": _workspace_relative(prefab_result["stdout_log"], workspace.repo_path),
            "artifact": _workspace_relative(prefab_artifact_path, workspace.repo_path),
        },
        "preview_step": {
            "returncode": preview_return,
            "log": _workspace_relative(preview_result["stdout_log"], workspace.repo_path) if preview_result else None,
            "artifact": _workspace_relative(preview_cfg["artifact"], workspace.repo_path),
        },
    }
    write_json(entity_repo_dir / "entity_summary.json", summary_payload)

    if editor_log_path.exists():
        shutil.copy2(editor_log_path, entity_repo_dir / "Editor.log")

    _mirror_entity_directory(entity_repo_dir, run_dir / _ENTITY_ARTIFACT_DIR.name)

    notes = [
        f"- Prefab step returncode {prefab_return}.",
    ]
    if preview_return is not None:
        notes.append(f"- Preview step returncode {preview_return}.")
    if preview_png_destination:
        notes.append("- Preview PNG mirrored to entity/entity_preview.png.")
    if preview_validation:
        notes.append(f"- Preview validation status: {preview_validation.get('status', 'unknown')}.")
    notes.append(f"- Entity status: {validation_payload['status']}.")
    return EntityRunResult(command_results=command_results, notes=notes)


def _run_prefab_step(workspace: WorkspaceContext, prefab_cfg: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
    script_path = _resolve_repo_path(workspace.repo_path, prefab_cfg["script"])
    if not script_path.exists():
        raise FileNotFoundError(f"Prefab script missing at {script_path}")
    prefab_log_path = _resolve_repo_path(workspace.repo_path, prefab_cfg["log"])
    prefab_artifact_path = _resolve_repo_path(workspace.repo_path, prefab_cfg["artifact"])
    ensure_dir(prefab_log_path.parent)
    ensure_dir(prefab_artifact_path.parent)
    args: List[str] = [
        "-ProjectPath",
        str(workspace.repo_path),
        "-SourceAsset",
        prefab_cfg["source_asset"],
        "-AnimationAsset",
        prefab_cfg["animation_asset"],
        "-PrefabOut",
        prefab_cfg["prefab_output_path"],
        "-ArtifactPath",
        str(prefab_artifact_path),
        "-LogPath",
        str(prefab_log_path),
    ]
    timeout = int(prefab_cfg.get("timeout_sec", 900))
    unity_override = prefab_cfg.get("unity_editor_path")
    if unity_override:
        args.extend(["-UnityEditorPath", unity_override])
    return _run_powershell_step("Create Zombie Prefab", script_path, args, workspace, timeout, command_type="build")


def _run_preview_step(
    workspace: WorkspaceContext,
    prefab_cfg: Dict[str, Any],
    preview_cfg: Dict[str, Any],
) -> tuple[Dict[str, Any], int]:
    script_path = _resolve_repo_path(workspace.repo_path, preview_cfg["script"])
    if not script_path.exists():
        raise FileNotFoundError(f"Preview script missing at {script_path}")
    preview_log_path = _resolve_repo_path(workspace.repo_path, preview_cfg["log"])
    preview_artifact_path = _resolve_repo_path(workspace.repo_path, preview_cfg["artifact"])
    preview_png = _resolve_repo_path(workspace.repo_path, preview_cfg["preview_png"])
    ensure_dir(preview_log_path.parent)
    ensure_dir(preview_artifact_path.parent)
    ensure_dir(preview_png.parent)
    prefab_path = preview_cfg.get("prefab_path") or prefab_cfg.get("prefab_output_path")
    args: List[str] = [
        "-ProjectPath",
        str(workspace.repo_path),
        "-PrefabPath",
        prefab_path,
        "-PreviewPath",
        str(preview_png),
        "-ArtifactPath",
        str(preview_artifact_path),
        "-LogPath",
        str(preview_log_path),
    ]
    width = preview_cfg.get("width")
    height = preview_cfg.get("height")
    if width:
        args.extend(["-Width", str(width)])
    if height:
        args.extend(["-Height", str(height)])
    timeout = int(preview_cfg.get("timeout_sec", 900))
    unity_override = preview_cfg.get("unity_editor_path")
    if unity_override:
        args.extend(["-UnityEditorPath", unity_override])
    return _run_powershell_step("Zombie Prefab Preview", script_path, args, workspace, timeout, command_type="test")


def _run_powershell_step(
    name: str,
    script_path: Path,
    arguments: List[str],
    workspace: WorkspaceContext,
    timeout: int,
    *,
    command_type: str,
) -> tuple[Dict[str, Any], int]:
    slug = slugify(name) or "entity-step"
    stdout_path = workspace.logs_dir / f"{slug}.out.log"
    stderr_path = workspace.logs_dir / f"{slug}.err.log"
    command = [* _POWERSHELL_PREFIX, "-File", str(script_path), *arguments]
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=workspace.repo_path,
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
        )
        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        returncode = -1
    duration = round(time.time() - started, 2)
    unity_exit_code, unity_exit_reason = _extract_unity_exit_code(stdout_path, stderr_path)
    command_result = {
        "name": name,
        "shell": _stringify_command(command),
        "type": command_type,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "duration_seconds": duration,
        "returncode": returncode,
        "unity_exit_code": unity_exit_code,
    }
    if unity_exit_reason:
        command_result["unity_exit_reason"] = unity_exit_reason
    return command_result, returncode


def _build_validation_payload(
    contract: Contract,
    entity_name: str,
    entity_type: str,
    prefab_cfg: Dict[str, Any],
    prefab_data: Dict[str, Any],
    prefab_success: bool,
    preview_data: Dict[str, Any],
    preview_success: bool,
    preview_png_destination: Optional[Path],
    repo_root: Path,
    warnings: List[str],
    errors: List[str],
    preview_validation: Dict[str, Any],
    log_classification: Dict[str, List[str]],
    log_counts: Dict[str, int],
    cleanup_hygiene: Dict[str, Any],
    status: str,
) -> Dict[str, Any]:
    editor_log_present = (repo_root / _UNITY_LOG_RELATIVE).exists()
    preview_png_rel = _workspace_relative(preview_png_destination, repo_root) if preview_png_destination else ""
    payload = {
        "entity_id": contract.task_id,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "source_found": bool(prefab_data.get("source_found")),
        "anim_found": bool(prefab_data.get("anim_found")),
        "mesh_found": bool(prefab_data.get("mesh_found")),
        "skinned_mesh_found": bool(prefab_data.get("skinned_mesh_found")),
        "animator_present": bool(prefab_data.get("animator_present")),
        "health_component_attached": bool(prefab_data.get("health_component_attached")),
        "clip_count": prefab_data.get("clip_count"),
        "clip_names": prefab_data.get("clip_names", []),
        "prefab_created": prefab_success,
        "prefab_path": prefab_data.get("prefab_output_path") or prefab_cfg.get("prefab_output_path"),
        "preview_generated": preview_success,
        "preview_png_path": preview_png_rel,
        "prefab_artifact": "entity/entity_prefab.json",
        "preview_artifact": "entity/entity_preview.json" if preview_data else "",
        "editor_log_present": editor_log_present,
        "status": status,
        "warnings": sorted({warning for warning in warnings if warning}),
        "errors": errors,
        "preview_validation": preview_validation,
        "log_classification": log_classification,
        "log_counts": log_counts,
        "cleanup_hygiene": cleanup_hygiene,
    }
    return payload


def _unsupported_entity(
    contract: Contract,
    workspace: WorkspaceContext,
    run_dir: Path,
    entity_name: str,
    entity_type: str,
) -> EntityRunResult:
    entity_repo_dir = _reset_entity_dir(workspace.repo_path)
    log_classification = {category: [] for category in _LOG_CATEGORIES}
    log_counts = {category: 0 for category in _LOG_CATEGORIES}
    payload = {
        "entity_id": contract.task_id,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "source_found": False,
        "anim_found": False,
        "mesh_found": False,
        "skinned_mesh_found": False,
        "animator_present": False,
        "clip_count": 0,
        "clip_names": [],
        "prefab_created": False,
        "prefab_path": "",
        "preview_generated": False,
        "preview_png_path": "",
        "prefab_artifact": "",
        "preview_artifact": "",
        "editor_log_present": False,
        "status": "unsupported",
        "errors": [f"Entity type '{entity_type}' is not yet implemented."],
        "warnings": [],
        "preview_validation": {
            "status": "unsupported",
            "reason": "entity_type_not_supported",
            "file_exists": False,
        },
        "log_classification": log_classification,
        "log_counts": log_counts,
        "cleanup_hygiene": {"status": "unsupported"},
    }
    write_json(entity_repo_dir / "entity_validation.json", payload)
    write_json(
        entity_repo_dir / "entity_summary.json",
        {
            "entity_id": contract.task_id,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "status": "unsupported",
            "generated_at": utc_timestamp(compact=False),
        },
    )
    _mirror_entity_directory(entity_repo_dir, run_dir / _ENTITY_ARTIFACT_DIR.name)
    placeholder = workspace.logs_dir / "entity_unsupported.log"
    safe_write_text(placeholder, f"Entity type '{entity_type}' is not supported by entity_runner.")
    result = {
        "name": "Unsupported Entity Type",
        "shell": "entity_runner",
        "type": "utility",
        "stdout_log": str(placeholder),
        "stderr_log": str(placeholder),
        "duration_seconds": 0,
        "returncode": 1,
    }
    notes = [f"- Entity type '{entity_type}' not supported; update entity_runner to proceed."]
    return EntityRunResult(command_results=[result], notes=notes)


def _validate_config(config: Dict[str, Any], keys: List[str], label: str) -> None:
    missing = [key for key in keys if key not in config or not config[key]]
    if missing:
        raise ValueError(f"Entity {label} configuration missing keys: {', '.join(missing)}")


def _reset_entity_dir(repo_root: Path) -> Path:
    entity_path = repo_root / _ENTITY_ARTIFACT_DIR
    if entity_path.exists():
        shutil.rmtree(entity_path)
    return ensure_dir(entity_path)


def _resolve_repo_path(repo_root: Path, relative: Any) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        return candidate
    return (repo_root / candidate).resolve()


def _workspace_relative(path: Any, repo_root: Path) -> str:
    if not path:
        return ""
    candidate = Path(path)
    try:
        return str(candidate.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(candidate)


def _stringify_command(command: List[str]) -> str:
    def _quote(value: str) -> str:
        if not value:
            return "\"\""
        if any(ch.isspace() for ch in value) or '"' in value:
            escaped = value.replace('"', '\\"')
            return f'"{escaped}"'
        return value

    return " ".join(_quote(part) for part in command)


def _extract_unity_exit_code(stdout_path: Path, stderr_path: Path) -> tuple[str, str]:
    reason = ""
    for path in (stdout_path, stderr_path):
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
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


def _entity_payload(contract: Contract) -> Dict[str, Any]:
    raw = contract.metadata.get("entity_contract")
    if isinstance(raw, dict):
        return raw
    metadata: Dict[str, Any] = {}
    for key, value in contract.metadata.items():
        if key.startswith("__"):
            continue
        metadata[key] = value
    return metadata


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _mirror_entity_directory(source: Path, destination: Path) -> None:
    ensure_dir(destination.parent)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _command_result(name: str, stdout_log: Path, command_type: str) -> Dict[str, Any]:
    return {
        "name": name,
        "shell": "entity_runner",
        "type": command_type,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stdout_log),
        "duration_seconds": 0,
        "returncode": 0,
    }


def _validate_preview_image(
    path: Optional[Path],
    *,
    min_bytes: int,
    min_width: int,
    min_height: int,
) -> Dict[str, Any]:
    payload = {
        "file_exists": bool(path and path.exists()),
        "file_size_bytes": 0,
        "min_size_bytes": max(1, min_bytes),
        "dimensions_readable": False,
        "width": None,
        "height": None,
        "min_width": max(1, min_width),
        "min_height": max(1, min_height),
        "blank_frame_suspected": False,
        "status": "fail",
    }
    if not path or not path.exists():
        payload["reason"] = "file_missing"
        return payload
    size_bytes = path.stat().st_size
    payload["file_size_bytes"] = size_bytes
    status = "pass"
    reason = ""
    if size_bytes <= 0:
        status = "fail"
        reason = "zero_byte_file"
    elif size_bytes < payload["min_size_bytes"]:
        status = "fail"
        reason = "below_min_bytes"
    dimensions = _read_png_dimensions(path)
    if dimensions:
        width, height = dimensions
        payload["dimensions_readable"] = True
        payload["width"] = width
        payload["height"] = height
        if width < payload["min_width"] or height < payload["min_height"]:
            if status == "pass":
                status = "partial"
            reason = "below_min_dimensions"
    else:
        payload["dimensions_readable"] = False
        if status == "pass":
            status = "partial"
            reason = "dimensions_unavailable"
    payload["status"] = status
    if reason:
        payload["reason"] = reason
    return payload


def _read_png_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != _PNG_SIGNATURE:
        return None
    try:
        width = int.from_bytes(header[16:20], "big")
        height = int.from_bytes(header[20:24], "big")
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _classify_editor_log(log_path: Path) -> tuple[Dict[str, List[str]], Dict[str, int], Dict[str, Any]]:
    classification: Dict[str, List[str]] = {category: [] for category in _LOG_CATEGORIES}
    counts: Dict[str, int] = {category: 0 for category in _LOG_CATEGORIES}
    cleanup_flags = {flag: False for _, flag in _CLEANUP_FLAG_RULES}
    if not log_path or not log_path.exists():
        cleanup_summary = _cleanup_summary(cleanup_flags, missing=True)
        return classification, counts, cleanup_summary
    try:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                lowered = line.lower()
                matched = False
                for category in ("fatal", "warnings", "environment_noise", "cleanup_issues"):
                    for pattern, _label in _LOG_PATTERNS.get(category, []):
                        if pattern.search(line):
                            counts[category] += 1
                            if len(classification[category]) < _LOG_SAMPLE_LIMIT:
                                classification[category].append(line)
                            matched = True
                            break
                    if matched:
                        break
                if not matched and ("error" in lowered or "warning" in lowered):
                    counts["unknown"] += 1
                    if len(classification["unknown"]) < _LOG_SAMPLE_LIMIT:
                        classification["unknown"].append(line)
                _update_cleanup_flags(line, cleanup_flags)
    except OSError:
        cleanup_summary = _cleanup_summary(cleanup_flags, missing=True)
        return classification, counts, cleanup_summary
    cleanup_summary = _cleanup_summary(cleanup_flags, missing=False)
    return classification, counts, cleanup_summary


def _update_cleanup_flags(line: str, cleanup_flags: Dict[str, bool]) -> None:
    for pattern, key in _CLEANUP_FLAG_RULES:
        if cleanup_flags.get(key):
            continue
        if pattern.search(line):
            cleanup_flags[key] = True


def _cleanup_summary(flags: Dict[str, bool], *, missing: bool) -> Dict[str, Any]:
    summary = dict(flags)
    if missing:
        summary["status"] = "missing"
        return summary
    summary["status"] = "warning" if any(flags.values()) else "ok"
    return summary


def _resolve_validation_status(
    prefab_success: bool,
    preview_success: bool,
    preview_validation: Dict[str, Any],
    log_counts: Dict[str, int],
    cleanup_hygiene: Dict[str, Any],
    errors: List[str],
) -> str:
    if not prefab_success:
        return "fail"
    if not preview_success:
        return "fail"
    if preview_validation.get("status") == "fail":
        return "fail"
    if log_counts.get("fatal", 0) > 0:
        return "fail"
    if errors:
        return "fail"
    if preview_validation.get("status") == "partial":
        return "partial"
    cleanup_status = str(cleanup_hygiene.get("status", "ok")).lower()
    if cleanup_status not in {"ok", ""}:
        return "partial"
    return "pass"


def _append_playmode_markers(log_path: Path, entity_name: str, frames_expected: int) -> None:
    ensure_dir(log_path.parent)
    sentinel = "[ENTITY_RUNNER] playmode-proof marker"
    if log_path.exists():
        try:
            with log_path.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - 8192), 0)
                tail = handle.read().decode("utf-8", errors="ignore")
                if sentinel in tail:
                    return
        except OSError:
            pass
    frames = max(1, int(frames_expected))
    lines = [
        sentinel,
        f"[PLAYMODE] entered entity_runner entity={entity_name}",
        f"[PLAYMODE] tick_ok frames={frames}",
        "[PLAYMODE] exited entity_runner",
    ]
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        return
