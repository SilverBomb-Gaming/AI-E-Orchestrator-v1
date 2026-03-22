import json
import subprocess
from pathlib import Path

import pytest

from ai_e_runtime.unity_action_executor import execute_unity_action


pytestmark = pytest.mark.fast


def test_execute_unity_action_blocks_multiple_tasks(tmp_path):
    project_path = tmp_path / "BABYLON VER 2"
    launcher_path = project_path / "Tools" / "run_unity_create_debug_cube.ps1"
    launcher_path.parent.mkdir(parents=True)
    launcher_path.write_text("placeholder", encoding="utf-8")

    request = {
        "source": "sandbox_execution",
        "status": "ready_for_execution",
        "tasks": [
            {"task_id": "task_001", "action_type": "create_debug_cube"},
            {"task_id": "task_002", "action_type": "create_debug_cube"},
        ],
        "project_path": str(project_path),
    }

    result = execute_unity_action(request)

    assert result["status"] == "blocked"
    assert "exactly one task" in result["notes"][0]
    assert Path(result["output_path"]).exists()


def test_execute_unity_action_runs_explicit_request(monkeypatch, tmp_path):
    project_path = tmp_path / "BABYLON VER 2"
    launcher_path = project_path / "Tools" / "run_unity_create_debug_cube.ps1"
    output_dir = tmp_path / "orchestrator_runs"
    launcher_path.parent.mkdir(parents=True)
    launcher_path.write_text("placeholder", encoding="utf-8")
    project_path.mkdir(exist_ok=True)

    def fake_run(command, cwd, capture_output, text, check):
        artifact_path = Path(command[command.index("-ArtifactPath") + 1])
        log_path = Path(command[command.index("-LogPath") + 1])
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(
                {
                    "status": "success",
                    "scene": "MainMenu",
                    "scene_name": "MainMenu",
                    "action_type": "create_debug_cube",
                    "created_object_name": "AIE_DebugCube_001",
                    "notes": [
                        "Created the debug cube in the active scene.",
                        "The change is reversible by deleting AIE_DebugCube_001 from the scene.",
                    ],
                    "timestamp": "2026-03-21T00:00:00Z",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log_path.write_text("unity log", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="UNITY_EXIT_CODE=0\nUNITY_EXIT_REASON=success\n",
            stderr="",
        )

    monkeypatch.setattr("ai_e_runtime.unity_action_executor.subprocess.run", fake_run)

    result = execute_unity_action(
        {
            "task_id": "cube_task_001",
            "action_type": "create_debug_cube",
            "scene_name": "MainMenu",
            "project_path": str(project_path),
            "launcher_path": str(launcher_path),
            "output_dir": str(output_dir),
        }
    )

    assert result["status"] == "completed"
    assert result["scene_name"] == "MainMenu"
    assert result["created_object_name"] == "AIE_DebugCube_001"
    assert result["unity_exit_code"] == "0"

    report = json.loads(Path(result["output_path"]).read_text(encoding="utf-8"))
    assert report["status"] == "completed"


def test_execute_unity_action_fails_with_invalid_artifact(monkeypatch, tmp_path):
    project_path = tmp_path / "BABYLON VER 2"
    launcher_path = project_path / "Tools" / "run_unity_create_debug_cube.ps1"
    launcher_path.parent.mkdir(parents=True)
    launcher_path.write_text("placeholder", encoding="utf-8")
    project_path.mkdir(exist_ok=True)

    def fake_run(command, cwd, capture_output, text, check):
        artifact_path = Path(command[command.index("-ArtifactPath") + 1])
        log_path = Path(command[command.index("-LogPath") + 1])
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps({"status": "success"}), encoding="utf-8")
        log_path.write_text("unity log", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="UNITY_EXIT_CODE=0\nUNITY_EXIT_REASON=success\n",
            stderr="",
        )

    monkeypatch.setattr("ai_e_runtime.unity_action_executor.subprocess.run", fake_run)

    result = execute_unity_action(
        {
            "task_id": "cube_task_invalid",
            "action_type": "create_debug_cube",
            "scene_name": "MainMenu",
            "project_path": str(project_path),
            "launcher_path": str(launcher_path),
            "output_dir": str(tmp_path / "orchestrator_runs"),
        }
    )

    assert result["status"] == "failed"
    assert "missing required field" in result["notes"][0]


def test_execute_unity_action_accepts_expected_object_override(monkeypatch, tmp_path):
    project_path = tmp_path / "BABYLON VER 2"
    launcher_path = project_path / "Tools" / "run_unity_create_debug_cube_002.ps1"
    launcher_path.parent.mkdir(parents=True)
    launcher_path.write_text("placeholder", encoding="utf-8")
    project_path.mkdir(exist_ok=True)

    def fake_run(command, cwd, capture_output, text, check):
        artifact_path = Path(command[command.index("-ArtifactPath") + 1])
        log_path = Path(command[command.index("-LogPath") + 1])
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(
                {
                    "status": "success",
                    "scene": "MainMenu",
                    "scene_name": "MainMenu",
                    "action_type": "create_debug_cube",
                    "created_object_name": "AIE_DebugCube_002",
                    "notes": [
                        "Created the second debug cube in the active scene.",
                        "Placed the cube at the deterministic position [2.0, 0.0, 3.0].",
                    ],
                    "timestamp": "2026-03-22T00:00:00Z",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log_path.write_text("unity log", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="UNITY_EXIT_CODE=0\nUNITY_EXIT_REASON=success\n",
            stderr="",
        )

    monkeypatch.setattr("ai_e_runtime.unity_action_executor.subprocess.run", fake_run)

    result = execute_unity_action(
        {
            "task_id": "cube_task_002",
            "action_type": "create_debug_cube",
            "scene_name": "MainMenu",
            "project_path": str(project_path),
            "launcher_path": str(launcher_path),
            "expected_created_object_name": "AIE_DebugCube_002",
            "output_dir": str(tmp_path / "orchestrator_runs"),
        }
    )

    assert result["status"] == "completed"
    assert result["created_object_name"] == "AIE_DebugCube_002"


def test_execute_unity_action_accepts_existing_object_mutation_artifact(monkeypatch, tmp_path):
    project_path = tmp_path / "BABYLON VER 2"
    launcher_path = project_path / "Tools" / "run_unity_mutate_debug_cube_001_scale.ps1"
    launcher_path.parent.mkdir(parents=True)
    launcher_path.write_text("placeholder", encoding="utf-8")
    project_path.mkdir(exist_ok=True)

    def fake_run(command, cwd, capture_output, text, check):
        artifact_path = Path(command[command.index("-ArtifactPath") + 1])
        log_path = Path(command[command.index("-LogPath") + 1])
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(
                {
                    "status": "success",
                    "scene": "MainMenu",
                    "scene_name": "MainMenu",
                    "action_type": "mutate_existing_object",
                    "target_object_name": "AIE_DebugCube_001",
                    "property_changed": "localScale",
                    "before_value": [1.0, 1.0, 1.0],
                    "after_value": [1.25, 1.0, 1.0],
                    "notes": [
                        "Reused the existing object AIE_DebugCube_001 in the active scene.",
                        "Set localScale to the deterministic value [1.25, 1.0, 1.0].",
                    ],
                    "timestamp": "2026-03-22T00:00:00Z",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log_path.write_text("unity log", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="UNITY_EXIT_CODE=0\nUNITY_EXIT_REASON=success\n",
            stderr="",
        )

    monkeypatch.setattr("ai_e_runtime.unity_action_executor.subprocess.run", fake_run)

    result = execute_unity_action(
        {
            "task_id": "mutate_cube_001",
            "action_type": "mutate_existing_object",
            "scene_name": "MainMenu",
            "project_path": str(project_path),
            "launcher_path": str(launcher_path),
            "expected_target_object_name": "AIE_DebugCube_001",
            "expected_property_changed": "localScale",
            "output_dir": str(tmp_path / "orchestrator_runs"),
        }
    )

    assert result["status"] == "completed"
    assert result["target_object_name"] == "AIE_DebugCube_001"
    assert result["property_changed"] == "localScale"
    assert result["before_value"] == [1.0, 1.0, 1.0]
    assert result["after_value"] == [1.25, 1.0, 1.0]


def test_execute_unity_action_writes_running_result_before_mutation_subprocess_returns(monkeypatch, tmp_path):
    project_path = tmp_path / "BABYLON VER 2"
    launcher_path = project_path / "Tools" / "run_unity_mutate_debug_cube_001_scale.ps1"
    output_dir = tmp_path / "orchestrator_runs"
    launcher_path.parent.mkdir(parents=True)
    launcher_path.write_text("placeholder", encoding="utf-8")
    project_path.mkdir(exist_ok=True)

    def fake_run(command, cwd, capture_output, text, check):
        result_path = output_dir / "mutate-cube-queue-001_execution_result.json"
        assert result_path.exists()

        running_report = json.loads(result_path.read_text(encoding="utf-8"))
        assert running_report["status"] == "running"
        assert running_report["target_object_name"] == "AIE_DebugCube_001"
        assert running_report["property_changed"] == "localScale"

        artifact_path = Path(command[command.index("-ArtifactPath") + 1])
        log_path = Path(command[command.index("-LogPath") + 1])
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(
                {
                    "status": "success",
                    "scene": "MainMenu",
                    "scene_name": "MainMenu",
                    "action_type": "mutate_existing_object",
                    "target_object_name": "AIE_DebugCube_001",
                    "property_changed": "localScale",
                    "before_value": [1.25, 1.0, 1.0],
                    "after_value": [1.25, 1.0, 1.0],
                    "notes": [
                        "Identity-only diagnostic executed with no scene mutation.",
                        "YAML mapping was anchored to exact local file identifiers for the target GameObject and Transform.",
                    ],
                    "timestamp": "2026-03-22T16:17:12Z",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log_path.write_text("unity log", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="UNITY_EXIT_CODE=0\nUNITY_EXIT_REASON=success\n",
            stderr="",
        )

    monkeypatch.setattr("ai_e_runtime.unity_action_executor.subprocess.run", fake_run)

    result = execute_unity_action(
        {
            "task_id": "mutate_cube_queue_001",
            "action_type": "mutate_existing_object",
            "scene_name": "MainMenu",
            "project_path": str(project_path),
            "launcher_path": str(launcher_path),
            "expected_target_object_name": "AIE_DebugCube_001",
            "expected_property_changed": "localScale",
            "output_dir": str(output_dir),
        }
    )

    assert result["status"] == "completed"
    final_report = json.loads(Path(result["output_path"]).read_text(encoding="utf-8"))
    assert final_report["status"] == "completed"
    assert final_report["target_object_name"] == "AIE_DebugCube_001"