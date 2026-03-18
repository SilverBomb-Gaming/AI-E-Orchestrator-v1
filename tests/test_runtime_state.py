import json

import pytest

from ai_e_runtime.runtime_state import RuntimeState
from ai_e_runtime.supervisor import Supervisor, SupervisorConfig
from orchestrator.config import OrchestratorConfig


pytestmark = pytest.mark.fast


def test_runtime_state_returns_expected_fields_and_writes_snapshot(tmp_path):
    config = _make_config(tmp_path / "runtime_state")
    _write_queue(
        config.queue_path,
        {
            "tasks": [
                _task(config, "STATE_001", priority=1, execution_seconds=1),
            ]
        },
    )
    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=5,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            session_id="runtime-state-session",
            stop_when_queue_empty=True,
        ),
    )

    result = supervisor.run()
    runtime_state = RuntimeState(config, "runtime-state-session")
    snapshot = runtime_state.get_snapshot()

    assert snapshot.session_id == "runtime-state-session"
    assert snapshot.timestamp
    assert snapshot.session_start_time
    assert snapshot.session_elapsed_seconds >= 0.0
    assert snapshot.session_state == "complete"
    assert snapshot.work_state == "halted"
    assert snapshot.budget_mode == "terminating"
    assert snapshot.queue_remaining == 0
    assert snapshot.current_task_id is None
    assert snapshot.last_started_task == "STATE_001"
    assert snapshot.last_completed_task == "STATE_001"
    assert snapshot.queue_tasks == []
    assert snapshot.tasks_completed == ["STATE_001"]
    assert snapshot.tasks_failed == []
    assert snapshot.heartbeat_timestamp is not None
    assert snapshot.artifact_output_path.endswith("runs\\runtime-state-session\\artifacts")
    assert snapshot.rating_system == "ESRB"
    assert snapshot.rating_target == "M"
    assert snapshot.rating_locked is True
    assert snapshot.session_phase == "complete"
    assert snapshot.phase_index == 7
    assert snapshot.phase_total == 7
    assert snapshot.phase_label == "Complete"
    assert snapshot.progress_mode == "phase_based"
    assert snapshot.waiting_reason is None
    assert snapshot.blocked_reason is None

    runtime_status_path = config.runs_dir / "runtime-state-session" / "runtime_status.json"
    assert runtime_status_path.exists()
    payload = json.loads(runtime_status_path.read_text(encoding="utf-8"))
    assert payload["session_id"] == "runtime-state-session"
    assert payload["timestamp"]
    assert payload["session_state"] == "complete"
    assert payload["work_state"] == "halted"
    assert payload["budget_mode"] == "terminating"
    assert payload["current_task_id"] is None
    assert payload["current_task"] is None
    assert payload["last_started_task"] == "STATE_001"
    assert payload["last_completed_task"] == "STATE_001"
    assert payload["queue_tasks"] == []
    assert payload["tasks_completed"] == ["STATE_001"]
    assert payload["queue_remaining"] == 0
    assert payload["rating_system"] == "ESRB"
    assert payload["rating_target"] == "M"
    assert payload["rating_locked"] is True
    assert payload["session_phase"] == "complete"
    assert payload["phase_index"] == 7
    assert payload["phase_total"] == 7
    assert payload["phase_label"] == "Complete"
    assert result.tasks_completed == 1


def test_runtime_state_queue_tasks_include_capability_maturity_fields(tmp_path):
    config = _make_config(tmp_path / "runtime_state_queue_maturity")
    _write_queue(
        config.queue_path,
        {
            "tasks": [
                {
                    "task_id": "STATE_MATURITY_001",
                    "title": "make grass for level_0001",
                    "priority": 5,
                    "status": "needs_approval",
                    "execution_lane": "approval_required_mutation",
                    "capability_id": "level_0001_add_grass",
                    "maturity_stage": "rollback_verified",
                    "trust_score": 90,
                    "trust_band": "high",
                    "policy_state": "proven",
                    "execution_decision": "auto_execute",
                    "recommended_action": "auto_execute",
                    "sandbox_first_required": False,
                    "auto_execution_enabled": True,
                    "auto_execution_reason": "Reference capability met auto thresholds.",
                    "missing_evidence": [],
                    "approval_required": False,
                    "eligible_for_auto": True,
                    "sandbox_verified": True,
                    "real_target_verified": True,
                    "rollback_verified": True,
                    "last_validation_result": "passed",
                    "last_rollback_result": "passed",
                    "rating_system": "ESRB",
                    "rating_target": "M",
                    "rating_locked": True,
                    "content_policy_match": "fits_rating",
                    "content_policy_decision": "allowed",
                    "required_rating_upgrade": None,
                    "requested_content_dimensions": {},
                    "content_policy_summary": "Requested content fits the ESRB M project target.",
                }
            ]
        },
    )

    runtime_state = RuntimeState(config, "runtime-state-session")
    queue_tasks = runtime_state.queue_tasks()

    assert queue_tasks[0]["capability_id"] == "level_0001_add_grass"
    assert queue_tasks[0]["maturity_stage"] == "rollback_verified"
    assert queue_tasks[0]["trust_score"] == 90
    assert queue_tasks[0]["trust_band"] == "high"
    assert queue_tasks[0]["policy_state"] == "proven"
    assert queue_tasks[0]["execution_decision"] == "auto_execute"
    assert queue_tasks[0]["recommended_action"] == "auto_execute"
    assert queue_tasks[0]["sandbox_first_required"] is False
    assert queue_tasks[0]["auto_execution_enabled"] is True
    assert queue_tasks[0]["approval_required"] is False
    assert queue_tasks[0]["eligible_for_auto"] is True
    assert queue_tasks[0]["sandbox_verified"] is True
    assert queue_tasks[0]["real_target_verified"] is True
    assert queue_tasks[0]["rollback_verified"] is True
    assert queue_tasks[0]["last_validation_result"] == "passed"
    assert queue_tasks[0]["last_rollback_result"] == "passed"
    assert queue_tasks[0]["rating_system"] == "ESRB"
    assert queue_tasks[0]["rating_target"] == "M"
    assert queue_tasks[0]["rating_locked"] is True
    assert queue_tasks[0]["content_policy_match"] == "fits_rating"
    assert queue_tasks[0]["content_policy_decision"] == "allowed"


def _make_config(tmp_path) -> OrchestratorConfig:
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

    for path in [runs_dir, workspaces_dir, queue_contracts_dir, templates_dir, approvals_path.parent, agent_registry_path.parent, root_dir / "logs"]:
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


def _task(config: OrchestratorConfig, task_id: str, *, priority: int, execution_seconds: int):
    payload_dir = config.contracts_dir / "test_runtime"
    payload_dir.mkdir(parents=True, exist_ok=True)
    path = payload_dir / f"{task_id}.json"
    path.write_text(
        json.dumps(
            {
                "runtime_task": {
                    "task_id": task_id,
                    "agent_type": "copilot_coder_agent",
                    "execution_seconds": execution_seconds,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "task_id": task_id,
        "priority": priority,
        "status": "pending",
        "contract_path": str(path.relative_to(config.root_dir)).replace("\\", "/"),
    }


def _write_queue(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")