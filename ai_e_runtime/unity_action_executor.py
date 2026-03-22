from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from orchestrator.utils import read_json_with_status, slugify, utc_timestamp, write_json


DEFAULT_UNITY_ACTION_TYPE = "create_debug_cube"
MUTATE_EXISTING_OBJECT_ACTION_TYPE = "mutate_existing_object"
DEFAULT_UNITY_SCENE_NAME = "MainMenu"
DEFAULT_UNITY_OBJECT_NAME = "AIE_DebugCube_001"
DEFAULT_MUTATION_TARGET_OBJECT_NAME = "AIE_DebugCube_001"
DEFAULT_MUTATION_PROPERTY_CHANGED = "localScale"
DEFAULT_UNITY_TIMEOUT_SECONDS = 240
DEFAULT_UNITY_PROJECT_PATH = Path(__file__).resolve().parents[2] / "BABYLON VER 2"
DEFAULT_UNITY_EXECUTION_ROOT = Path("runs") / "sample_clip_analysis" / "unity_action"
_POWERSHELL_PREFIX = [
    "powershell.exe",
    "-NoLogo",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
]


def execute_unity_action(request: Dict[str, Any] | Path | str) -> Dict[str, Any]:
    """Execute one approved Unity scene action against the Babylon project.

    The executor only supports a single visible, reversible Babylon scene
    action at a time.
    """

    payload = _coerce_request(request)
    normalized = _normalize_request(payload)
    print(f"[unity_action_executor] Request loaded: {normalized['request_source']}")
    print(f"[unity_action_executor] Action type: {normalized['action_type']}")
    print(f"[unity_action_executor] Scene: {normalized['scene_name']}")

    execution_dir = _resolve_execution_dir(normalized.get("output_dir"))
    execution_id = normalized.get("execution_id") or f"unity_action_{utc_timestamp()}"
    slug = slugify(str(normalized.get("task_id") or execution_id))
    artifact_path = execution_dir / f"{slug}_unity_artifact.json"
    log_path = execution_dir / f"{slug}_unity.log"
    result_path = execution_dir / f"{slug}_execution_result.json"

    validation_issue = _validate_request(normalized)
    if validation_issue is not None:
        result = _build_result(
            execution_id=execution_id,
            task_id=normalized["task_id"],
            action_type=normalized["action_type"],
            status="blocked",
            scene_name=normalized["scene_name"],
            notes=[validation_issue, "No Unity scene changes were applied."],
            output_path=result_path,
            artifact_path=artifact_path,
            log_path=log_path,
            created_object_name=normalized.get("expected_created_object_name"),
            target_object_name=normalized.get("expected_target_object_name"),
            property_changed=normalized.get("expected_property_changed"),
        )
        write_json(result_path, result)
        print(f"[unity_action_executor] Final status: {result['status']}")
        return result

    project_path = Path(str(normalized["project_path"]))
    launcher_path = Path(str(normalized["launcher_path"]))
    command = _build_command(
        launcher_path=launcher_path,
        project_path=project_path,
        scene_name=normalized["scene_name"],
        artifact_path=artifact_path,
        log_path=log_path,
        timeout_seconds=int(normalized["timeout_seconds"]),
        unity_editor_path=normalized.get("unity_editor_path"),
    )
    print(f"[unity_action_executor] Launcher: {launcher_path}")

    running_result = _build_result(
        execution_id=execution_id,
        task_id=normalized["task_id"],
        action_type=normalized["action_type"],
        status="running",
        scene_name=normalized["scene_name"],
        notes=["Unity launcher started; awaiting action artifact confirmation."],
        output_path=result_path,
        artifact_path=artifact_path,
        log_path=log_path,
        command=command,
        created_object_name=normalized.get("expected_created_object_name"),
        target_object_name=normalized.get("expected_target_object_name"),
        property_changed=normalized.get("expected_property_changed"),
    )
    write_json(result_path, running_result)

    try:
        completed = subprocess.run(
            command,
            cwd=str(project_path),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        result = _build_result(
            execution_id=execution_id,
            task_id=normalized["task_id"],
            action_type=normalized["action_type"],
            status="failed",
            scene_name=normalized["scene_name"],
            notes=[f"Failed to start Unity launcher: {exc}", "No Unity scene changes were applied."],
            output_path=result_path,
            artifact_path=artifact_path,
            log_path=log_path,
            command=command,
            returncode=None,
            unity_exit_code="UNKNOWN",
            unity_exit_reason="launcher failed to start",
            created_object_name=normalized.get("expected_created_object_name"),
            target_object_name=normalized.get("expected_target_object_name"),
            property_changed=normalized.get("expected_property_changed"),
        )
        write_json(result_path, result)
        print(f"[unity_action_executor] Final status: {result['status']}")
        return result

    unity_exit_code, unity_exit_reason = _extract_unity_exit_code(completed.stdout, completed.stderr)
    artifact_payload, artifact_issue = read_json_with_status(artifact_path, default={})

    if completed.returncode != 0 or unity_exit_code != "0":
        result = _build_result(
            execution_id=execution_id,
            task_id=normalized["task_id"],
            action_type=normalized["action_type"],
            status="failed",
            scene_name=normalized["scene_name"],
            notes=[
                unity_exit_reason or f"Unity launcher returned code {completed.returncode}.",
                "No additional queue or gameplay systems were modified.",
            ],
            output_path=result_path,
            artifact_path=artifact_path,
            log_path=log_path,
            command=command,
            returncode=completed.returncode,
            unity_exit_code=unity_exit_code,
            unity_exit_reason=unity_exit_reason,
            created_object_name=normalized.get("expected_created_object_name"),
            target_object_name=normalized.get("expected_target_object_name"),
            property_changed=normalized.get("expected_property_changed"),
        )
        write_json(result_path, result)
        print(f"[unity_action_executor] Final status: {result['status']}")
        return result

    artifact_validation = _validate_artifact(
        artifact_payload,
        artifact_issue,
        action_type=normalized["action_type"],
        expected_created_object_name=normalized.get("expected_created_object_name", ""),
        expected_target_object_name=normalized.get("expected_target_object_name", ""),
        expected_property_changed=normalized.get("expected_property_changed", ""),
    )
    if artifact_validation is not None:
        result = _build_result(
            execution_id=execution_id,
            task_id=normalized["task_id"],
            action_type=normalized["action_type"],
            status="failed",
            scene_name=normalized["scene_name"],
            notes=[artifact_validation, "Unity exited without a valid action confirmation artifact."],
            output_path=result_path,
            artifact_path=artifact_path,
            log_path=log_path,
            command=command,
            returncode=completed.returncode,
            unity_exit_code=unity_exit_code,
            unity_exit_reason=unity_exit_reason,
            created_object_name=normalized.get("expected_created_object_name"),
            target_object_name=normalized.get("expected_target_object_name"),
            property_changed=normalized.get("expected_property_changed"),
        )
        write_json(result_path, result)
        print(f"[unity_action_executor] Final status: {result['status']}")
        return result

    artifact_notes = [note for note in artifact_payload.get("notes", []) if isinstance(note, str) and note.strip()]
    result = _build_result(
        execution_id=execution_id,
        task_id=normalized["task_id"],
        action_type=normalized["action_type"],
        status="completed",
        scene_name=str(artifact_payload.get("scene_name") or artifact_payload.get("scene") or normalized["scene_name"]),
        notes=artifact_notes or ["Debug cube action completed."],
        output_path=result_path,
        artifact_path=artifact_path,
        log_path=log_path,
        command=command,
        returncode=completed.returncode,
        unity_exit_code=unity_exit_code,
        unity_exit_reason=unity_exit_reason,
        created_object_name=_resolve_created_object_name(artifact_payload, normalized),
        target_object_name=_resolve_target_object_name(artifact_payload, normalized),
        property_changed=str(artifact_payload.get("property_changed") or normalized.get("expected_property_changed") or ""),
        before_value=artifact_payload.get("before_value"),
        after_value=artifact_payload.get("after_value"),
    )
    write_json(result_path, result)
    print(f"[unity_action_executor] Final status: {result['status']}")
    return result


def _coerce_request(value: Dict[str, Any] | Path | str) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)

    path = Path(value)
    payload, issue = read_json_with_status(path, default={})
    if issue is not None or not isinstance(payload, dict) or not payload:
        return {}
    return payload


def _normalize_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    queue_tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else None
    request_source = "explicit_request"
    queue_status = ""
    queue_source = ""
    base = payload

    if queue_tasks is not None:
        request_source = "sandbox_queue"
        queue_status = str(payload.get("status") or "").strip()
        queue_source = str(payload.get("source") or "").strip()
        if len(queue_tasks) == 1 and isinstance(queue_tasks[0], dict):
            base = dict(queue_tasks[0])
        else:
            base = {"tasks": queue_tasks}
    elif isinstance(payload.get("task"), dict):
        request_source = "task_wrapper"
        base = dict(payload["task"])
    elif isinstance(payload.get("execution_request"), dict):
        request_source = "execution_request"
        base = dict(payload["execution_request"])

    metadata = base.get("metadata") if isinstance(base.get("metadata"), dict) else {}
    parameters = base.get("parameters") if isinstance(base.get("parameters"), dict) else {}
    requested_action = base.get("requested_action") if isinstance(base.get("requested_action"), dict) else {}

    action_type = _first_string(
        base.get("action_type"),
        requested_action.get("action_type"),
        parameters.get("action_type"),
        metadata.get("action_type"),
    ) or str(base.get("task_type") or "").strip().lower()

    project_path = _first_string(
        base.get("project_path"),
        parameters.get("project_path"),
        metadata.get("project_path"),
    ) or str(DEFAULT_UNITY_PROJECT_PATH)

    launcher_path = _first_string(
        base.get("launcher_path"),
        parameters.get("launcher_path"),
        metadata.get("launcher_path"),
    )

    timeout_value = _first_string(
        base.get("timeout_seconds"),
        parameters.get("timeout_seconds"),
        metadata.get("timeout_seconds"),
    )
    try:
        timeout_seconds = int(timeout_value or DEFAULT_UNITY_TIMEOUT_SECONDS)
    except ValueError:
        timeout_seconds = DEFAULT_UNITY_TIMEOUT_SECONDS

    approved = _is_approved(base, request_source=request_source, queue_source=queue_source, queue_status=queue_status)

    normalized = {
        "request_source": request_source,
        "task_id": _first_string(base.get("task_id"), base.get("request_id"), base.get("id")) or "unity_action_task_001",
        "execution_id": _first_string(base.get("execution_id"), base.get("request_id")),
        "action_type": action_type,
        "scene_name": _first_string(
            base.get("scene_name"),
            base.get("target_scene"),
            base.get("scene"),
            parameters.get("scene_name"),
            metadata.get("scene_name"),
        ) or DEFAULT_UNITY_SCENE_NAME,
        "project_path": project_path,
        "launcher_path": launcher_path or _default_launcher_path(project_path, action_type),
        "timeout_seconds": max(30, timeout_seconds),
        "expected_created_object_name": _first_string(
            base.get("expected_created_object_name"),
            parameters.get("expected_created_object_name"),
            metadata.get("expected_created_object_name"),
        ) or (DEFAULT_UNITY_OBJECT_NAME if action_type == DEFAULT_UNITY_ACTION_TYPE else ""),
        "expected_target_object_name": _first_string(
            base.get("expected_target_object_name"),
            parameters.get("expected_target_object_name"),
            metadata.get("expected_target_object_name"),
        ) or (DEFAULT_MUTATION_TARGET_OBJECT_NAME if action_type == MUTATE_EXISTING_OBJECT_ACTION_TYPE else ""),
        "expected_property_changed": _first_string(
            base.get("expected_property_changed"),
            parameters.get("expected_property_changed"),
            metadata.get("expected_property_changed"),
        ) or (DEFAULT_MUTATION_PROPERTY_CHANGED if action_type == MUTATE_EXISTING_OBJECT_ACTION_TYPE else ""),
        "unity_editor_path": _first_string(
            base.get("unity_editor_path"),
            parameters.get("unity_editor_path"),
            metadata.get("unity_editor_path"),
        ),
        "output_dir": _first_string(base.get("output_dir"), parameters.get("output_dir"), metadata.get("output_dir")),
        "approved": approved,
        "task_count": len(queue_tasks) if queue_tasks is not None else 1,
    }
    return normalized


def _validate_request(normalized: Dict[str, Any]) -> str | None:
    if normalized.get("task_count", 0) != 1:
        return "Unity action executor only accepts exactly one task at a time."

    if normalized["action_type"] not in {DEFAULT_UNITY_ACTION_TYPE, MUTATE_EXISTING_OBJECT_ACTION_TYPE}:
        return f"Unsupported Unity action type: {normalized['action_type'] or 'unknown'}"

    if not normalized.get("approved"):
        return "Unity action executor requires one approved sandbox task or an explicit execution request."

    project_path = Path(str(normalized["project_path"]))
    if not project_path.exists():
        return f"Unity project path not found: {project_path}"

    launcher_path = Path(str(normalized["launcher_path"]))
    if not launcher_path.exists():
        return f"Unity launcher not found: {launcher_path}"

    return None


def _resolve_execution_dir(candidate: str | None) -> Path:
    if candidate:
        path = Path(candidate)
    else:
        path = Path(__file__).resolve().parents[1] / DEFAULT_UNITY_EXECUTION_ROOT
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_command(
    *,
    launcher_path: Path,
    project_path: Path,
    scene_name: str,
    artifact_path: Path,
    log_path: Path,
    timeout_seconds: int,
    unity_editor_path: str | None,
) -> List[str]:
    command = [
        *_POWERSHELL_PREFIX,
        "-File",
        str(launcher_path),
        "-ProjectPath",
        str(project_path),
        "-SceneName",
        scene_name,
        "-ArtifactPath",
        str(artifact_path),
        "-LogPath",
        str(log_path),
        "-TimeoutSec",
        str(timeout_seconds),
    ]
    if unity_editor_path:
        command.extend(["-UnityEditorPath", unity_editor_path])
    return command


def _extract_unity_exit_code(stdout_text: str, stderr_text: str) -> tuple[str, str]:
    exit_code = ""
    reason = ""
    for text in (stdout_text or "", stderr_text or ""):
        for line in text.splitlines():
            if line.startswith("UNITY_EXIT_CODE="):
                value = line.partition("=")[2].strip()
                if value:
                    exit_code = value
                elif not reason:
                    reason = "wrapper emitted blank UNITY_EXIT_CODE"
            elif line.startswith("UNITY_EXIT_REASON=") and not reason:
                reason = line.partition("=")[2].strip()
    if exit_code:
        return exit_code, reason
    if not reason:
        reason = "wrapper did not emit UNITY_EXIT_CODE"
    return "UNKNOWN", reason


def _validate_artifact(
    payload: Dict[str, Any],
    issue: str | None,
    *,
    action_type: str,
    expected_created_object_name: str,
    expected_target_object_name: str,
    expected_property_changed: str,
) -> str | None:
    if issue is not None:
        return f"Unity action artifact was {issue}."

    if not isinstance(payload, dict) or not payload:
        return "Unity action artifact was missing or invalid."

    required_keys = ["status", "scene_name", "action_type", "notes"]
    if action_type == DEFAULT_UNITY_ACTION_TYPE:
        required_keys.append("created_object_name")
    elif action_type == MUTATE_EXISTING_OBJECT_ACTION_TYPE:
        required_keys.extend(["target_object_name", "property_changed", "before_value", "after_value"])
    for key in required_keys:
        if key not in payload:
            return f"Unity action artifact missing required field '{key}'."

    if str(payload.get("status") or "").strip().lower() != "success":
        return f"Unity action artifact reported status '{payload.get('status')}'."

    if str(payload.get("action_type") or "").strip() != action_type:
        return f"Unity action artifact reported unsupported action '{payload.get('action_type')}'."

    if action_type == DEFAULT_UNITY_ACTION_TYPE:
        if str(payload.get("created_object_name") or "").strip() != expected_created_object_name:
            return f"Unity action artifact reported unexpected object '{payload.get('created_object_name')}'."
    elif action_type == MUTATE_EXISTING_OBJECT_ACTION_TYPE:
        if str(payload.get("target_object_name") or "").strip() != expected_target_object_name:
            return f"Unity action artifact reported unexpected object '{payload.get('target_object_name')}'."
        if str(payload.get("property_changed") or "").strip() != expected_property_changed:
            return f"Unity action artifact reported unexpected property '{payload.get('property_changed')}'."
        if not isinstance(payload.get("before_value"), list):
            return "Unity action artifact before_value field was not a list."
        if not isinstance(payload.get("after_value"), list):
            return "Unity action artifact after_value field was not a list."

    if not isinstance(payload.get("notes"), list):
        return "Unity action artifact notes field was not a list."

    return None


def _build_result(
    *,
    execution_id: str,
    task_id: str,
    action_type: str,
    status: str,
    scene_name: str,
    notes: List[str],
    output_path: Path,
    artifact_path: Path,
    log_path: Path,
    created_object_name: str | None = None,
    target_object_name: str | None = None,
    property_changed: str | None = None,
    before_value: Any | None = None,
    after_value: Any | None = None,
    command: List[str] | None = None,
    returncode: int | None = None,
    unity_exit_code: str = "",
    unity_exit_reason: str = "",
) -> Dict[str, Any]:
    payload = {
        "execution_id": execution_id,
        "task_id": task_id,
        "action_type": action_type,
        "status": status,
        "scene_name": scene_name,
        "notes": list(notes),
        "output_path": str(output_path),
        "artifact_path": str(artifact_path),
        "log_path": str(log_path),
    }
    if created_object_name:
        payload["created_object_name"] = created_object_name
    if target_object_name:
        payload["target_object_name"] = target_object_name
    if property_changed:
        payload["property_changed"] = property_changed
    if before_value is not None:
        payload["before_value"] = before_value
    if after_value is not None:
        payload["after_value"] = after_value
    if command is not None:
        payload["command"] = list(command)
    if returncode is not None:
        payload["returncode"] = returncode
    if unity_exit_code:
        payload["unity_exit_code"] = unity_exit_code
    if unity_exit_reason:
        payload["unity_exit_reason"] = unity_exit_reason
    return payload


def _is_approved(
    payload: Dict[str, Any],
    *,
    request_source: str,
    queue_source: str,
    queue_status: str,
) -> bool:
    for key in ("approval_status", "decision"):
        value = str(payload.get(key) or "").strip().lower()
        if value in {"approved", "allow", "allowed"}:
            return True

    if request_source == "explicit_request":
        return True

    if queue_source == "sandbox_execution" and queue_status == "ready_for_execution":
        return True

    return False


def _first_string(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _default_launcher_path(project_path: str, action_type: str) -> str:
    tools_dir = Path(project_path) / "Tools"
    if action_type == MUTATE_EXISTING_OBJECT_ACTION_TYPE:
        return str(tools_dir / "run_unity_mutate_debug_cube_001_scale.ps1")
    return str(tools_dir / "run_unity_create_debug_cube.ps1")


def _resolve_created_object_name(payload: Dict[str, Any], normalized: Dict[str, Any]) -> str:
    if normalized["action_type"] != DEFAULT_UNITY_ACTION_TYPE:
        return ""
    return str(payload.get("created_object_name") or normalized.get("expected_created_object_name") or DEFAULT_UNITY_OBJECT_NAME)


def _resolve_target_object_name(payload: Dict[str, Any], normalized: Dict[str, Any]) -> str:
    if normalized["action_type"] != MUTATE_EXISTING_OBJECT_ACTION_TYPE:
        return ""
    return str(payload.get("target_object_name") or normalized.get("expected_target_object_name") or DEFAULT_MUTATION_TARGET_OBJECT_NAME)


__all__ = [
    "DEFAULT_UNITY_ACTION_TYPE",
    "DEFAULT_UNITY_EXECUTION_ROOT",
    "DEFAULT_MUTATION_PROPERTY_CHANGED",
    "DEFAULT_MUTATION_TARGET_OBJECT_NAME",
    "DEFAULT_UNITY_OBJECT_NAME",
    "DEFAULT_UNITY_PROJECT_PATH",
    "DEFAULT_UNITY_SCENE_NAME",
    "DEFAULT_UNITY_TIMEOUT_SECONDS",
    "MUTATE_EXISTING_OBJECT_ACTION_TYPE",
    "execute_unity_action",
]