from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .capability_registry import CapabilityRegistry, RuntimeCapability
from orchestrator.config import OrchestratorConfig
from orchestrator.utils import ensure_dir, read_json, safe_write_text, utc_timestamp, write_json


PROOF_SESSION_ID = "live_real_grass_validation_20260317"
PROOF_TASK_ID = "INTAKE_EE04F913D280"
EXPECTED_CAPABILITY_ID = "level_0001_add_grass"
EXPECTED_MARKER = "AIE_LEVEL_0001_GrassPatch_001"
EXPECTED_TARGET_REPO = Path(r"E:\AI projects 2025\BABYLON VER 2")
EXPECTED_TARGET_SCENE = EXPECTED_TARGET_REPO / "Assets" / "AI_E_TestScenes" / "MinimalPlayableArena.unity"
EXPECTED_PRE_SHA1 = "f76f7de9f74d839e0c439760052ea297a055283c"
KNOWN_CONSTRAINT = (
    "Task intake currently assumes contract and artifact paths stay under config.root_dir when deriving "
    "relative paths; sandbox configs should remain beneath the orchestrator repo root unless path handling "
    "is generalized."
)


@dataclass(frozen=True)
class RealTargetRollbackResult:
    session_id: str
    status: str
    restored: bool
    report_path: Path
    rollback_dir: Path
    target_scene: Path
    backup_path: Path
    restored_sha1: str | None
    marker_present_after: bool
    message: str


def rollback_first_real_target_grass_proof(
    config: OrchestratorConfig,
    *,
    expected_pre_sha1: str | None = None,
) -> RealTargetRollbackResult:
    effective_expected_pre_sha1 = str(expected_pre_sha1 or EXPECTED_PRE_SHA1)
    run_dir = config.runs_dir / PROOF_SESSION_ID
    rollback_dir = ensure_dir(run_dir / "rollback")
    report_path = rollback_dir / "rollback_validation_report.json"
    findings_path = rollback_dir / "rollback_findings.json"
    rollback_baseline_path = rollback_dir / "rollback_baseline.json"
    rollback_pre_diff_path = rollback_dir / "rollback_pre_restore.diff.txt"
    rollback_post_diff_path = rollback_dir / "rollback_post_restore.diff.txt"
    target_scene = EXPECTED_TARGET_SCENE
    validation_report_path = run_dir / "post_mutation" / "real_target_validation_report.json"
    backup_path = run_dir / "pre_mutation" / "MinimalPlayableArena.pre_mutation.unity"
    pre_mutation_state_path = run_dir / "pre_mutation" / "pre_mutation_state.json"
    capability = _resolve_reference_capability(config)
    evidence_store = CapabilityRegistry(config).evidence_store()

    baseline = _capture_rollback_baseline(
        session_id=PROOF_SESSION_ID,
        target_scene=target_scene,
        backup_path=backup_path,
        validation_report_path=validation_report_path,
        pre_mutation_state_path=pre_mutation_state_path,
    )
    write_json(rollback_baseline_path, baseline)

    validation_report = baseline.get("validation_report", {})
    pre_mutation_state = baseline.get("pre_mutation_state", {})
    already_restored = (
        not bool(baseline.get("current_marker_present"))
        and str(baseline.get("current_scene_sha1") or "") == effective_expected_pre_sha1
        and str(baseline.get("backup_sha1") or "") == effective_expected_pre_sha1
        and str(validation_report.get("session_id") or "") == PROOF_SESSION_ID
        and str(validation_report.get("task_id") or "") == PROOF_TASK_ID
        and str(validation_report.get("capability_id") or "") == EXPECTED_CAPABILITY_ID
        and str(validation_report.get("expected_marker") or "") == EXPECTED_MARKER
        and bool(validation_report.get("expected_marker_present"))
        and str(validation_report.get("scene_sha1_before") or "") == effective_expected_pre_sha1
        and Path(str(validation_report.get("target_scene") or "")) == EXPECTED_TARGET_SCENE
        and str(pre_mutation_state.get("scene_sha1_before") or "") == effective_expected_pre_sha1
        and Path(str(pre_mutation_state.get("target_scene") or "")) == EXPECTED_TARGET_SCENE
        and str(pre_mutation_state.get("expected_marker") or "") == EXPECTED_MARKER
    )
    if already_restored:
        safe_write_text(rollback_pre_diff_path, "")
        safe_write_text(rollback_post_diff_path, "")
        report = {
            "session_id": PROOF_SESSION_ID,
            "task_id": PROOF_TASK_ID,
            "capability_id": EXPECTED_CAPABILITY_ID,
            "target_scene": str(target_scene),
            "backup_source_path": str(backup_path),
            "validation_report_path": str(validation_report_path),
            "pre_mutation_state_path": str(pre_mutation_state_path),
            "rollback_baseline_path": str(rollback_baseline_path),
            "rollback_pre_restore_diff_path": str(rollback_pre_diff_path),
            "rollback_post_restore_diff_path": str(rollback_post_diff_path),
            "rollback_started_at": baseline.get("captured_at"),
            "rollback_completed_at": utc_timestamp(compact=False),
            "rollback_status": "completed",
            "rollback_stop_reason": "already_restored",
            "session_final_state": "complete",
            "rollback_action_summary": "target scene already matched captured pre-mutation backup for the fixed proof session",
            "current_state_sha1_before_rollback": baseline.get("current_scene_sha1"),
            "restored_scene_sha1": baseline.get("current_scene_sha1"),
            "expected_pre_mutation_sha1": effective_expected_pre_sha1,
            "backup_sha1": baseline.get("backup_sha1"),
            "source_backup_identity_confirmed": str(baseline.get("backup_sha1") or "") == EXPECTED_PRE_SHA1,
            "marker_expected_removed": EXPECTED_MARKER,
            "marker_present_before_rollback": baseline.get("current_marker_present"),
            "marker_count_before_rollback": baseline.get("current_marker_count"),
            "marker_present_after_rollback": False,
            "marker_count_after_rollback": 0,
            "restored_scene_matches_backup": True,
            "restored_scene_matches_expected_sha1": True,
            "rollback_validation_result": "passed",
            "rollback_validation_check": (
                "marker absent after restore, restored scene equals captured backup, restored SHA1 matches known pre-mutation SHA1"
            ),
            "known_constraint": KNOWN_CONSTRAINT,
        }
        write_json(report_path, report)
        evidence_store.record_rollback_result(
            capability,
            passed=True,
            rollback_state="passed",
            notes="Real-target rollback validated from captured backup; live scene already matched the byte-accurate pre-mutation state.",
        )
        return RealTargetRollbackResult(
            session_id=PROOF_SESSION_ID,
            status="completed",
            restored=True,
            report_path=report_path,
            rollback_dir=rollback_dir,
            target_scene=target_scene,
            backup_path=backup_path,
            restored_sha1=str(baseline.get("current_scene_sha1") or ""),
            marker_present_after=False,
            message="rollback already satisfied",
        )

    failure = _validate_context(baseline, expected_pre_sha1=effective_expected_pre_sha1)
    if failure is not None:
        findings = _build_failure_findings(baseline, failure)
        write_json(findings_path, findings)
        write_json(report_path, findings)
        evidence_store.record_rollback_result(
            capability,
            passed=False,
            rollback_state="failed_closed",
            notes=f"Real-target rollback failed closed: {failure}",
        )
        return RealTargetRollbackResult(
            session_id=PROOF_SESSION_ID,
            status="failed_closed",
            restored=False,
            report_path=report_path,
            rollback_dir=rollback_dir,
            target_scene=target_scene,
            backup_path=backup_path,
            restored_sha1=None,
            marker_present_after=bool(baseline.get("current_marker_present")),
            message=failure,
        )

    current_scene_text = target_scene.read_text(encoding="utf-8")
    backup_text = backup_path.read_text(encoding="utf-8")
    safe_write_text(rollback_pre_diff_path, _build_diff_text(current_scene_text, backup_text, target_scene, backup_path))

    shutil.copy2(backup_path, target_scene)

    restored_text = target_scene.read_text(encoding="utf-8")
    restored_bytes = target_scene.read_bytes()
    backup_bytes = backup_path.read_bytes()
    restored_sha1 = _sha1_path(target_scene)
    marker_present_after = EXPECTED_MARKER in restored_text
    backup_sha1 = _sha1_path(backup_path)
    restored_matches_backup = restored_bytes == backup_bytes
    restored_matches_expected_sha1 = restored_sha1 == effective_expected_pre_sha1
    safe_write_text(rollback_post_diff_path, _build_diff_text(restored_text, backup_text, target_scene, backup_path))

    validation_passed = (
        not marker_present_after
        and restored_matches_backup
        and restored_matches_expected_sha1
        and backup_sha1 == effective_expected_pre_sha1
    )
    report = {
        "session_id": PROOF_SESSION_ID,
        "task_id": PROOF_TASK_ID,
        "capability_id": EXPECTED_CAPABILITY_ID,
        "target_scene": str(target_scene),
        "backup_source_path": str(backup_path),
        "validation_report_path": str(validation_report_path),
        "pre_mutation_state_path": str(pre_mutation_state_path),
        "rollback_baseline_path": str(rollback_baseline_path),
        "rollback_pre_restore_diff_path": str(rollback_pre_diff_path),
        "rollback_post_restore_diff_path": str(rollback_post_diff_path),
        "rollback_started_at": baseline.get("captured_at"),
        "rollback_completed_at": utc_timestamp(compact=False),
        "rollback_status": "completed" if validation_passed else "failed_closed",
        "rollback_stop_reason": "rollback_complete" if validation_passed else "rollback_validation_failed",
        "session_final_state": "complete" if validation_passed else "failed_closed",
        "rollback_action_summary": "restored target scene from captured pre-mutation backup for the fixed proof session only",
        "current_state_sha1_before_rollback": baseline.get("current_scene_sha1"),
        "restored_scene_sha1": restored_sha1,
        "expected_pre_mutation_sha1": effective_expected_pre_sha1,
        "backup_sha1": backup_sha1,
        "source_backup_identity_confirmed": backup_sha1 == EXPECTED_PRE_SHA1,
        "marker_expected_removed": EXPECTED_MARKER,
        "marker_present_before_rollback": baseline.get("current_marker_present"),
        "marker_count_before_rollback": baseline.get("current_marker_count"),
        "marker_present_after_rollback": marker_present_after,
        "marker_count_after_rollback": restored_text.count(EXPECTED_MARKER),
        "restored_scene_matches_backup": restored_matches_backup,
        "restored_scene_matches_expected_sha1": restored_matches_expected_sha1,
        "rollback_validation_result": "passed" if validation_passed else "failed",
        "rollback_validation_check": (
            "marker absent after restore, restored scene equals captured backup, restored SHA1 matches known pre-mutation SHA1"
        ),
        "known_constraint": KNOWN_CONSTRAINT,
    }
    write_json(report_path, report)
    evidence_store.record_rollback_result(
        capability,
        passed=bool(validation_passed),
        rollback_state="passed" if validation_passed else "failed",
        notes=(
            "Real-target rollback restored the captured pre-mutation backup and passed byte-level validation."
            if validation_passed
            else "Real-target rollback restored the captured pre-mutation backup but post-restore validation failed."
        ),
    )
    return RealTargetRollbackResult(
        session_id=PROOF_SESSION_ID,
        status=str(report["rollback_status"]),
        restored=bool(validation_passed),
        report_path=report_path,
        rollback_dir=rollback_dir,
        target_scene=target_scene,
        backup_path=backup_path,
        restored_sha1=restored_sha1,
        marker_present_after=marker_present_after,
        message="rollback validation passed" if validation_passed else "rollback validation failed after restore",
    )


def _capture_rollback_baseline(
    *,
    session_id: str,
    target_scene: Path,
    backup_path: Path,
    validation_report_path: Path,
    pre_mutation_state_path: Path,
) -> Dict[str, Any]:
    validation_report = read_json(validation_report_path, default={})
    pre_mutation_state = read_json(pre_mutation_state_path, default={})
    current_scene_text = target_scene.read_text(encoding="utf-8") if target_scene.exists() else ""
    return {
        "session_id": session_id,
        "captured_at": utc_timestamp(compact=False),
        "target_scene": str(target_scene),
        "backup_path": str(backup_path),
        "validation_report_path": str(validation_report_path),
        "pre_mutation_state_path": str(pre_mutation_state_path),
        "current_scene_exists": target_scene.exists(),
        "backup_exists": backup_path.exists(),
        "validation_report_exists": validation_report_path.exists(),
        "pre_mutation_state_exists": pre_mutation_state_path.exists(),
        "current_scene_sha1": _sha1_path(target_scene) if target_scene.exists() else None,
        "backup_sha1": _sha1_path(backup_path) if backup_path.exists() else None,
        "current_scene_size_bytes": target_scene.stat().st_size if target_scene.exists() else None,
        "backup_size_bytes": backup_path.stat().st_size if backup_path.exists() else None,
        "current_marker_present": EXPECTED_MARKER in current_scene_text,
        "current_marker_count": current_scene_text.count(EXPECTED_MARKER),
        "validation_report": validation_report,
        "pre_mutation_state": pre_mutation_state,
    }


def _validate_context(baseline: Dict[str, Any], *, expected_pre_sha1: str) -> str | None:
    if not baseline.get("backup_exists"):
        return "Expected pre-mutation backup is missing for the fixed proof session."
    if not baseline.get("current_scene_exists"):
        return "Expected real target scene is missing for the fixed proof session."
    if not baseline.get("validation_report_exists"):
        return "Expected real-target validation report is missing for the fixed proof session."
    if not baseline.get("pre_mutation_state_exists"):
        return "Expected pre-mutation state artifact is missing for the fixed proof session."

    validation_report = baseline.get("validation_report", {})
    pre_mutation_state = baseline.get("pre_mutation_state", {})

    if str(validation_report.get("session_id") or "") != PROOF_SESSION_ID:
        return "Validation report session id does not match the fixed rollback session."
    if str(validation_report.get("task_id") or "") != PROOF_TASK_ID:
        return "Validation report task id does not match the fixed rollback task."
    if str(validation_report.get("capability_id") or "") != EXPECTED_CAPABILITY_ID:
        return "Validation report capability id does not match the fixed rollback capability."
    if Path(str(validation_report.get("target_scene") or "")) != EXPECTED_TARGET_SCENE:
        return "Validation report target scene does not match the fixed rollback scene."
    if Path(str(validation_report.get("backup_path") or "")) != Path(str(baseline.get("backup_path") or "")):
        return "Validation report backup path does not match the fixed rollback backup."
    if str(validation_report.get("expected_marker") or "") != EXPECTED_MARKER:
        return "Validation report expected marker does not match the fixed rollback marker."
    if str(validation_report.get("scene_sha1_before") or "") != expected_pre_sha1:
        return "Validation report pre-mutation SHA1 does not match the fixed rollback SHA1."
    if not bool(validation_report.get("expected_marker_present")):
        return "Validation report does not confirm the marker was present after mutation."
    if not bool(baseline.get("current_marker_present")):
        return "Current target scene does not contain the expected marker; rollback would be ambiguous."
    if int(baseline.get("current_marker_count") or 0) != 1:
        return "Current target scene does not contain exactly one expected marker; rollback would be ambiguous."
    if str(pre_mutation_state.get("scene_sha1_before") or "") != expected_pre_sha1:
        return "Pre-mutation state artifact SHA1 does not match the fixed rollback SHA1."
    if Path(str(pre_mutation_state.get("target_scene") or "")) != EXPECTED_TARGET_SCENE:
        return "Pre-mutation state target scene does not match the fixed rollback scene."
    if str(pre_mutation_state.get("expected_marker") or "") != EXPECTED_MARKER:
        return "Pre-mutation state expected marker does not match the fixed rollback marker."
    if str(baseline.get("backup_sha1") or "") != expected_pre_sha1:
        return "Backup SHA1 does not match the known pre-mutation SHA1; refusing restore."
    return None


def _build_failure_findings(baseline: Dict[str, Any], failure: str) -> Dict[str, Any]:
    return {
        "session_id": PROOF_SESSION_ID,
        "task_id": PROOF_TASK_ID,
        "capability_id": EXPECTED_CAPABILITY_ID,
        "rollback_status": "failed_closed",
        "rollback_stop_reason": "context_mismatch",
        "session_final_state": "failed_closed",
        "failure_reason": failure,
        "target_scene": baseline.get("target_scene"),
        "backup_source_path": baseline.get("backup_path"),
        "validation_report_path": baseline.get("validation_report_path"),
        "pre_mutation_state_path": baseline.get("pre_mutation_state_path"),
        "current_state_sha1_before_rollback": baseline.get("current_scene_sha1"),
        "backup_sha1": baseline.get("backup_sha1"),
        "marker_expected_removed": EXPECTED_MARKER,
        "marker_present_before_rollback": baseline.get("current_marker_present"),
        "marker_count_before_rollback": baseline.get("current_marker_count"),
        "known_constraint": KNOWN_CONSTRAINT,
    }


def _sha1_path(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _build_diff_text(current_text: str, backup_text: str, target_scene: Path, backup_path: Path) -> str:
    import difflib

    diff = difflib.unified_diff(
        current_text.splitlines(),
        backup_text.splitlines(),
        fromfile=str(target_scene),
        tofile=str(backup_path),
        n=8,
        lineterm="",
    )
    return "\n".join(diff) + "\n"


def _resolve_reference_capability(config: OrchestratorConfig) -> RuntimeCapability:
    capability = CapabilityRegistry(config).match("make grass for level_0001")
    if capability is not None:
        return capability
    return RuntimeCapability(
        capability_id=EXPECTED_CAPABILITY_ID,
        title="LEVEL_0001 add grass",
        intent="mutate",
        target_level="LEVEL_0001",
        target_scene="Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
        requested_execution_lane="approval_required_mutation",
        handler_name="level_0001_grass_handler",
        agent_type="level_0001_grass_mutation_agent",
        approval_required=True,
        eligible_for_auto=False,
        evidence_state="experimental",
        safety_class="approval_gated_automation",
        match_terms=["level_0001", "grass"],
        match_verbs=["make", "add", "create", "generate", "place", "build"],
    )


__all__ = [
    "EXPECTED_CAPABILITY_ID",
    "EXPECTED_MARKER",
    "EXPECTED_PRE_SHA1",
    "EXPECTED_TARGET_REPO",
    "EXPECTED_TARGET_SCENE",
    "KNOWN_CONSTRAINT",
    "PROOF_SESSION_ID",
    "PROOF_TASK_ID",
    "RealTargetRollbackResult",
    "rollback_first_real_target_grass_proof",
]