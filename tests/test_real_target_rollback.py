from __future__ import annotations

import hashlib
import json
from pathlib import Path

import ai_e_runtime.real_target_rollback as real_target_rollback
from orchestrator.config import OrchestratorConfig


def test_rollback_helper_restores_scene_from_fixed_session_backup(tmp_path, monkeypatch):
    config = _make_config(tmp_path / "rollback_success")
    scene_path = _prepare_fixed_session_constants(config, monkeypatch)
    backup_sha1 = _seed_fixed_session_artifacts(config, scene_path=scene_path)

    result = real_target_rollback.rollback_first_real_target_grass_proof(config, expected_pre_sha1=backup_sha1)

    assert result.restored is True
    assert result.status == "completed"

    scene_text = scene_path.read_text(encoding="utf-8")
    assert "AIE_LEVEL_0001_GrassPatch_001" not in scene_text

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["rollback_validation_result"] == "passed"
    assert report["marker_present_after_rollback"] is False
    assert report["restored_scene_matches_expected_sha1"] is True


def test_rollback_helper_fails_closed_when_marker_state_is_ambiguous(tmp_path, monkeypatch):
    config = _make_config(tmp_path / "rollback_failure")
    scene_path = _prepare_fixed_session_constants(config, monkeypatch)
    backup_sha1 = _seed_fixed_session_artifacts(config, include_marker=False, scene_path=scene_path)

    result = real_target_rollback.rollback_first_real_target_grass_proof(config, expected_pre_sha1=backup_sha1)

    assert result.restored is False
    assert result.status == "failed_closed"

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["rollback_status"] == "failed_closed"
    assert "does not confirm the marker was present" in report["failure_reason"]


def test_rollback_helper_accepts_exact_already_restored_state(tmp_path, monkeypatch):
    config = _make_config(tmp_path / "rollback_already_restored")
    scene_path = _prepare_fixed_session_constants(config, monkeypatch)
    backup_sha1 = _seed_fixed_session_artifacts(config, scene_path=scene_path)

    backup_path = config.runs_dir / "live_real_grass_validation_20260317" / "pre_mutation" / "MinimalPlayableArena.pre_mutation.unity"
    scene_path.write_bytes(backup_path.read_bytes())

    result = real_target_rollback.rollback_first_real_target_grass_proof(config, expected_pre_sha1=backup_sha1)

    assert result.restored is True
    assert result.status == "completed"
    assert result.message == "rollback already satisfied"

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["rollback_stop_reason"] == "already_restored"
    assert report["rollback_validation_result"] == "passed"
    assert report["restored_scene_matches_expected_sha1"] is True


def _prepare_fixed_session_constants(config: OrchestratorConfig, monkeypatch) -> Path:
    target_repo = config.root_dir / "BABYLON_TEST"
    scene_path = target_repo / "Assets" / "AI_E_TestScenes" / "MinimalPlayableArena.unity"
    monkeypatch.setattr(real_target_rollback, "EXPECTED_TARGET_REPO", target_repo)
    monkeypatch.setattr(real_target_rollback, "EXPECTED_TARGET_SCENE", scene_path)
    return scene_path


def _make_config(tmp_path: Path) -> OrchestratorConfig:
    root_dir = tmp_path / "repo_root"
    runs_dir = root_dir / "runs"
    workspaces_dir = root_dir / "workspaces"
    queue_path = root_dir / "backlog" / "queue.json"
    queue_contracts_dir = root_dir / "contracts" / "queue"
    agent_registry_path = root_dir / "agents" / "registry.json"
    contracts_dir = root_dir / "contracts"
    templates_dir = contracts_dir / "templates"
    approvals_path = root_dir / "backlog" / "approvals.json"
    command_allowlist_path = root_dir / "backlog" / "command_allowlist.json"

    for path in [runs_dir, workspaces_dir, queue_contracts_dir, templates_dir, approvals_path.parent, agent_registry_path.parent]:
        path.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps({"tasks": []}, indent=2), encoding="utf-8")
    approvals_path.write_text(json.dumps({"approvals": []}, indent=2), encoding="utf-8")
    command_allowlist_path.write_text(json.dumps({"exact": [], "prefix": []}, indent=2), encoding="utf-8")
    agent_registry_path.write_text(json.dumps({"agents": []}, indent=2), encoding="utf-8")

    return OrchestratorConfig(
        root_dir=root_dir,
        runs_dir=runs_dir,
        workspaces_dir=workspaces_dir,
        queue_path=queue_path,
        queue_contracts_dir=queue_contracts_dir,
        agent_registry_path=agent_registry_path,
        contracts_dir=contracts_dir,
        templates_dir=templates_dir,
        approvals_path=approvals_path,
        command_allowlist_path=command_allowlist_path,
    )


def _seed_fixed_session_artifacts(config: OrchestratorConfig, *, scene_path: Path, include_marker: bool = True) -> str:
    session_id = "live_real_grass_validation_20260317"
    run_dir = config.runs_dir / session_id
    pre_dir = run_dir / "pre_mutation"
    post_dir = run_dir / "post_mutation"
    rollback_dir = run_dir / "rollback"
    pre_dir.mkdir(parents=True, exist_ok=True)
    post_dir.mkdir(parents=True, exist_ok=True)
    rollback_dir.mkdir(parents=True, exist_ok=True)

    backup_text = "--- !u!1660057539 &9223372036854775807\nSceneRoots:\n  m_ObjectHideFlags: 0\n  m_Roots:\n  - {fileID: 1001}\n"
    mutated_text = (
        "--- !u!1 &2001\n"
        "GameObject:\n"
        "  m_Name: AIE_LEVEL_0001_GrassPatch_001\n"
        "--- !u!4 &2002\n"
        "Transform:\n"
        "  m_GameObject: {fileID: 2001}\n"
        "--- !u!1660057539 &9223372036854775807\n"
        "SceneRoots:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_Roots:\n"
        "  - {fileID: 1001}\n"
        "  - {fileID: 2002}\n"
    )

    backup_path = pre_dir / "MinimalPlayableArena.pre_mutation.unity"
    backup_path.write_text(backup_text, encoding="utf-8")

    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text(mutated_text if include_marker else backup_text, encoding="utf-8")
    backup_sha1 = hashlib.sha1(backup_path.read_bytes()).hexdigest()
    include_marker_sha1 = hashlib.sha1(scene_path.read_bytes()).hexdigest()

    pre_state = {
        "session_id": session_id,
        "target_scene": str(scene_path),
        "expected_marker": "AIE_LEVEL_0001_GrassPatch_001",
        "scene_sha1_before": backup_sha1,
    }
    (pre_dir / "pre_mutation_state.json").write_text(json.dumps(pre_state, indent=2), encoding="utf-8")

    report = {
        "session_id": session_id,
        "task_id": "INTAKE_EE04F913D280",
        "capability_id": "level_0001_add_grass",
        "target_scene": str(scene_path),
        "backup_path": str(backup_path),
        "expected_marker": "AIE_LEVEL_0001_GrassPatch_001",
        "scene_sha1_before": backup_sha1,
        "scene_sha1_after": include_marker_sha1,
        "expected_marker_present": include_marker,
    }
    (post_dir / "real_target_validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return backup_sha1