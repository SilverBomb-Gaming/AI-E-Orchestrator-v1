from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .capability_registry import CapabilityEvidenceStore, RuntimeCapability


_SCENE_ROOTS_MARKER = "--- !u!1660057539 &9223372036854775807\nSceneRoots:\n"
_GRASS_PATCH_PREFIX = "AIE_LEVEL_0001_GrassPatch_"


@dataclass(frozen=True)
class GrassMutationResult:
    scene_text: str
    patch_name: str
    before_marker_count: int
    after_marker_count: int
    before_root_count: int
    after_root_count: int


def run_level_0001_grass_mutation(task: Dict[str, Any]) -> Dict[str, Any]:
    capability = RuntimeCapability(
        capability_id=str(task.get("capability_id") or "level_0001_add_grass"),
        title=str(task.get("capability_title") or "LEVEL_0001 add grass"),
        intent="mutate",
        target_level=str(task.get("target_level") or "LEVEL_0001"),
        target_scene=str(task.get("target_scene") or "Assets/AI_E_TestScenes/MinimalPlayableArena.unity"),
        requested_execution_lane=str(task.get("requested_execution_lane") or "approval_required_mutation"),
        handler_name=str(task.get("handler_name") or "level_0001_grass_handler"),
        agent_type=str(task.get("agent_type") or "level_0001_grass_mutation_agent"),
        approval_required=bool(task.get("approval_required", True)),
        eligible_for_auto=bool(task.get("eligible_for_auto", False)),
        evidence_state=str(task.get("evidence_state") or "experimental"),
        safety_class=str(task.get("safety_class") or "approval_gated_automation"),
        match_terms=[],
        match_verbs=[],
    )
    evidence_store = CapabilityEvidenceStore(Path(str(task.get("capability_evidence_path"))))
    evidence_store.ensure_entry(capability)

    approval_state = str(task.get("approval_state") or "awaiting_approval")
    execution_decision = str(task.get("execution_decision") or "approval_required")
    auto_execution_enabled = bool(task.get("auto_execution_enabled", False))
    auto_execution_reason = str(task.get("auto_execution_reason") or "")
    if capability.approval_required and approval_state != "approved":
        evidence_store.record_result(
            capability,
            passed=False,
            validation_state="approval_missing",
            artifact_requirements_met=False,
            notes="Mutation execution was denied because approval metadata was missing.",
        )
        return {
            "status": "blocked",
            "summary": f"{capability.handler_name} blocked mutation for {capability.target_level}",
            "error": "Mutation execution requires explicit operator approval.",
            "details": {
                "capability_id": capability.capability_id,
                "handler_name": capability.handler_name,
                "approval_state": approval_state,
            },
        }

    scene_path = _resolve_scene_path(task)
    if not scene_path.exists():
        evidence_store.record_result(
            capability,
            passed=False,
            validation_state="scene_missing",
            artifact_requirements_met=False,
            notes=f"Target scene was missing: {scene_path}",
        )
        return {
            "status": "blocked",
            "summary": f"{capability.handler_name} could not find the target scene",
            "error": f"Target scene does not exist: {scene_path}",
            "details": {
                "capability_id": capability.capability_id,
                "target_scene": str(scene_path),
            },
        }

    original_text = scene_path.read_text(encoding="utf-8")
    before_hash = hashlib.sha1(original_text.encode("utf-8")).hexdigest()
    operation = _resolve_mutation_operation(capability.capability_id, capability.handler_name)

    try:
        mutation = _apply_grass_patch(original_text) if operation == "add" else _remove_grass_patch(original_text)
    except ValueError as exc:
        evidence_store.record_result(
            capability,
            passed=False,
            validation_state="mutation_failed",
            artifact_requirements_met=False,
            notes=str(exc),
        )
        return {
            "status": "blocked",
            "summary": f"{capability.handler_name} failed to mutate {capability.target_level}",
            "error": str(exc),
            "details": {
                "capability_id": capability.capability_id,
                "handler_name": capability.handler_name,
                "target_scene": str(scene_path),
            },
        }

    scene_path.write_text(mutation.scene_text, encoding="utf-8")
    updated_text = scene_path.read_text(encoding="utf-8")
    after_hash = hashlib.sha1(updated_text.encode("utf-8")).hexdigest()
    if operation == "add":
        validation_passed = (
            mutation.patch_name in updated_text
            and _count_marker_names(updated_text) == mutation.after_marker_count
            and _count_scene_roots(updated_text) == mutation.after_root_count
            and after_hash != before_hash
        )
        mutation_summary = "grass patch added"
        object_field = "added_object_name"
        validation_check = "marker_present_and_scene_root_count_increased"
        success_summary = f"{capability.handler_name} added grass patch {mutation.patch_name} to {capability.target_level}"
        evidence_note = f"Bounded grass mutation validated successfully with marker {mutation.patch_name}."
    else:
        validation_passed = (
            mutation.patch_name not in updated_text
            and _count_marker_names(updated_text) == mutation.after_marker_count
            and _count_scene_roots(updated_text) == mutation.after_root_count
            and after_hash != before_hash
        )
        mutation_summary = "grass patch removed"
        object_field = "removed_object_name"
        validation_check = "marker_absent_and_scene_root_count_decreased"
        success_summary = f"{capability.handler_name} removed grass patch {mutation.patch_name} from {capability.target_level}"
        evidence_note = f"Bounded grass removal validated successfully for marker {mutation.patch_name}."
    if not validation_passed:
        scene_path.write_text(original_text, encoding="utf-8")
        evidence_store.record_result(
            capability,
            passed=False,
            validation_state="validation_failed",
            artifact_requirements_met=False,
            notes="Grass mutation did not pass marker validation and the scene was reverted.",
        )
        return {
            "status": "blocked",
            "summary": f"{capability.handler_name} failed validation for {capability.target_level}",
            "error": "Mutation validation failed; scene reverted.",
            "details": {
                "capability_id": capability.capability_id,
                "handler_name": capability.handler_name,
                "target_scene": str(scene_path),
                "patch_name": mutation.patch_name,
            },
        }

    evidence_snapshot = evidence_store.record_result(
        capability,
        passed=True,
        validation_state="passed",
        artifact_requirements_met=True,
        notes=evidence_note,
    )
    mutation_details = {
        "capability_id": capability.capability_id,
        "capability_title": capability.title,
        "handler_name": capability.handler_name,
        "target_level": capability.target_level,
        "target_scene": str(scene_path),
        "approval_state": approval_state,
        "execution_decision": execution_decision,
        "auto_execution_enabled": auto_execution_enabled,
        "auto_execution_reason": auto_execution_reason,
        "approved_by": task.get("approved_by"),
        "approved_at": task.get("approved_at"),
        "approval_notes": task.get("approval_notes", ""),
        "mutation_summary": mutation_summary,
        "files_changed": [str(scene_path)],
        object_field: mutation.patch_name,
        "before_marker_count": mutation.before_marker_count,
        "after_marker_count": mutation.after_marker_count,
        "before_root_count": mutation.before_root_count,
        "after_root_count": mutation.after_root_count,
        "before_scene_sha1": before_hash,
        "after_scene_sha1": after_hash,
        "validation": {
            "status": "passed",
            "check": validation_check,
        },
        "evidence": evidence_snapshot,
    }
    return {
        "status": "completed",
        "summary": success_summary,
        "details": mutation_details,
        "artifacts": [
            str(scene_path),
            str(task.get("capability_evidence_path") or ""),
        ],
    }


def _resolve_scene_path(task: Dict[str, Any]) -> Path:
    target_repo = Path(str(task.get("target_repo") or ""))
    scene_relative = str(task.get("target_scene") or "Assets/AI_E_TestScenes/MinimalPlayableArena.unity")
    parts = [part for part in scene_relative.replace("\\", "/").split("/") if part]
    return target_repo.joinpath(*parts)


def _apply_grass_patch(scene_text: str) -> GrassMutationResult:
    if _SCENE_ROOTS_MARKER not in scene_text:
        raise ValueError("MinimalPlayableArena scene is missing a SceneRoots block.")
    before_marker_count = _count_marker_names(scene_text)
    before_root_count = _count_scene_roots(scene_text)
    next_index = _next_patch_index(scene_text)
    patch_name = f"{_GRASS_PATCH_PREFIX}{next_index:03d}"
    max_id = _next_file_id_seed(scene_text)
    game_object_id = max_id + 11
    transform_id = max_id + 12
    x_position = round(-8.0 + ((next_index - 1) % 4) * 4.0, 2)
    z_position = round(8.0 - ((next_index - 1) // 4) * 4.0, 2)
    object_block = (
        f"--- !u!1 &{game_object_id}\n"
        "GameObject:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  serializedVersion: 6\n"
        "  m_Component:\n"
        f"  - component: {{fileID: {transform_id}}}\n"
        "  m_Layer: 0\n"
        f"  m_Name: {patch_name}\n"
        "  m_TagString: Untagged\n"
        "  m_Icon: {fileID: 0}\n"
        "  m_NavMeshLayer: 0\n"
        "  m_StaticEditorFlags: 0\n"
        "  m_IsActive: 1\n"
        f"--- !u!4 &{transform_id}\n"
        "Transform:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        f"  m_GameObject: {{fileID: {game_object_id}}}\n"
        "  serializedVersion: 2\n"
        "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}\n"
        f"  m_LocalPosition: {{x: {x_position}, y: 0.1, z: {z_position}}}\n"
        "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
        "  m_ConstrainProportionsScale: 0\n"
        "  m_Children: []\n"
        "  m_Father: {fileID: 0}\n"
        "  m_LocalEulerAnglesHint: {x: 0, y: 0, z: 0}\n"
    )
    scene_roots_index = scene_text.index(_SCENE_ROOTS_MARKER)
    with_object = scene_text[:scene_roots_index] + object_block + scene_text[scene_roots_index:]
    updated_scene = re.sub(
        r"(?ms)(--- !u!1660057539 &9223372036854775807\nSceneRoots:\n  m_ObjectHideFlags: 0\n  m_Roots:\n)((?:  - \{fileID: \d+\}\n)*)",
        lambda match: match.group(1) + match.group(2) + f"  - {{fileID: {transform_id}}}\n",
        with_object,
        count=1,
    )
    return GrassMutationResult(
        scene_text=updated_scene,
        patch_name=patch_name,
        before_marker_count=before_marker_count,
        after_marker_count=before_marker_count + 1,
        before_root_count=before_root_count,
        after_root_count=before_root_count + 1,
    )


def _remove_grass_patch(scene_text: str) -> GrassMutationResult:
    if _SCENE_ROOTS_MARKER not in scene_text:
        raise ValueError("MinimalPlayableArena scene is missing a SceneRoots block.")
    before_marker_count = _count_marker_names(scene_text)
    before_root_count = _count_scene_roots(scene_text)
    if before_marker_count <= 0:
        raise ValueError("MinimalPlayableArena scene does not contain a bounded grass patch to remove.")

    patch_records = _find_patch_records(scene_text)
    if not patch_records:
        raise ValueError("MinimalPlayableArena scene does not contain a removable bounded grass patch.")
    latest_patch = patch_records[-1]

    without_game_object = scene_text.replace(str(latest_patch["game_object_block"]), "", 1)
    without_transform = without_game_object.replace(str(latest_patch["transform_block"]), "", 1)
    updated_scene, root_replacements = re.subn(
        rf"(?m)^  - \{{fileID: {int(latest_patch['transform_id'])}\}}\n",
        "",
        without_transform,
        count=1,
    )
    if root_replacements != 1:
        raise ValueError("Bounded grass patch was missing its SceneRoots entry; removal aborted.")

    return GrassMutationResult(
        scene_text=updated_scene,
        patch_name=str(latest_patch["patch_name"]),
        before_marker_count=before_marker_count,
        after_marker_count=before_marker_count - 1,
        before_root_count=before_root_count,
        after_root_count=before_root_count - 1,
    )


def _count_marker_names(scene_text: str) -> int:
    return len(re.findall(rf"m_Name: {_GRASS_PATCH_PREFIX}\d{{3}}", scene_text))


def _count_scene_roots(scene_text: str) -> int:
    match = re.search(
        r"(?ms)--- !u!1660057539 &9223372036854775807\nSceneRoots:\n  m_ObjectHideFlags: 0\n  m_Roots:\n((?:  - \{fileID: \d+\}\n)*)",
        scene_text,
    )
    if not match:
        return 0
    return len(re.findall(r"  - \{fileID: \d+\}", match.group(1)))


def _next_patch_index(scene_text: str) -> int:
    indexes = [int(match) for match in re.findall(rf"{_GRASS_PATCH_PREFIX}(\d{{3}})", scene_text)]
    return max(indexes, default=0) + 1


def _next_file_id_seed(scene_text: str) -> int:
    ids = [
        int(match)
        for match in re.findall(r"&(\d+)", scene_text)
        if match != "9223372036854775807"
    ]
    return max(ids, default=1000000)


def _find_patch_records(scene_text: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for match in re.finditer(r"(?ms)^--- !u!1 &(?P<game_object_id>\d+)\nGameObject:\n(?P<body>.*?)(?=^--- !u!|\Z)", scene_text):
        body = str(match.group("body"))
        patch_match = re.search(rf"(?m)^  m_Name: (?P<patch_name>{_GRASS_PATCH_PREFIX}\d{{3}})\n", body)
        if patch_match is None:
            continue
        transform_match = re.search(r"(?m)^  - component: \{fileID: (?P<transform_id>\d+)\}\n", body)
        if transform_match is None:
            raise ValueError("Bounded grass patch is missing its Transform component reference.")
        transform_id = int(transform_match.group("transform_id"))
        transform_block_match = re.search(
            rf"(?ms)^--- !u!4 &{transform_id}\nTransform:\n.*?(?=^--- !u!|\Z)",
            scene_text,
        )
        if transform_block_match is None:
            raise ValueError(f"Bounded grass patch Transform block is missing for fileID {transform_id}.")
        patch_name = str(patch_match.group("patch_name"))
        records.append(
            {
                "patch_name": patch_name,
                "patch_index": int(patch_name.rsplit("_", 1)[1]),
                "game_object_id": int(match.group("game_object_id")),
                "transform_id": transform_id,
                "game_object_block": match.group(0),
                "transform_block": transform_block_match.group(0),
            }
        )
    records.sort(key=lambda record: int(record["patch_index"]))
    return records


def _resolve_mutation_operation(capability_id: str, handler_name: str) -> str:
    if capability_id == "level_0001_remove_grass" or "remove" in handler_name.lower():
        return "remove"
    return "add"


__all__ = ["run_level_0001_grass_mutation"]