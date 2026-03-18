import json
from datetime import datetime, timedelta, timezone

import pytest

from ai_e_runtime.agent_router import AgentRouter
from ai_e_runtime.capability_registry import CapabilityEvidenceStore, CapabilityRegistry
from ai_e_runtime.mutation_approval import approve_mutation_task
from ai_e_runtime.scheduler import Scheduler
from ai_e_runtime.supervisor import Supervisor, SupervisorConfig
from ai_e_runtime.task_intake import ConversationalTaskIntake
from orchestrator.config import OrchestratorConfig


pytestmark = pytest.mark.fast


class FakeClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 3, 16, 12, 0, 0, tzinfo=timezone.utc)
        self._monotonic = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        self._monotonic += float(seconds)
        self._now += timedelta(seconds=float(seconds))


def test_supervisor_runs_multiple_tasks_emits_heartbeat_and_stops_on_time_limit(tmp_path):
    config = _make_config(tmp_path / "time_limit")
    _write_queue(
        config.queue_path,
        {
            "tasks": [
                _task(config, "TASK_001", priority=1, execution_seconds=2),
                _task(config, "TASK_002", priority=2, execution_seconds=2),
                _task(config, "TASK_003", priority=3, execution_seconds=2),
                _task(config, "TASK_004", priority=4, execution_seconds=2),
                _task(config, "TASK_005", priority=5, execution_seconds=2),
            ]
        },
    )
    clock = FakeClock()
    router = _make_router(clock)

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=7,
            heartbeat_interval_seconds=3,
            poll_interval_seconds=1,
            session_id="persistent-test-session",
            stop_when_queue_empty=False,
        ),
        agent_router=router,
        time_source=clock.now,
        monotonic_source=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    result = supervisor.run()

    assert result.stop_reason == "time_limit_reached"
    assert result.tasks_attempted >= 3
    assert result.tasks_completed >= 3
    assert result.queue_remaining == 1
    assert result.heartbeats_emitted >= 2

    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]
    assert [task["status"] for task in queue[:4]] == ["completed", "completed", "completed", "completed"]
    assert queue[4]["status"] == "pending"

    heartbeat_log = result.heartbeat_log_path.read_text(encoding="utf-8")
    assert heartbeat_log.count("SESSION_HEARTBEAT") >= 2
    assert "queue_remaining=1" in heartbeat_log

    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["session_id"] == "persistent-test-session"
    assert len(state["tasks_attempted"]) == 4
    assert len(state["tasks_completed"]) == 4


def test_supervisor_resumes_interrupted_session_and_reclaims_running_task(tmp_path):
    config = _make_config(tmp_path / "resume")
    _write_queue(
        config.queue_path,
        {
            "tasks": [
                {
                    "task_id": "RESUME_001",
                    "priority": 1,
                    "status": "running",
                    "current_session_id": "resume-session",
                    "execution_seconds": 1,
                    "contract_path": _create_runtime_payload(config, "RESUME_001", execution_seconds=1),
                },
                _task(config, "RESUME_002", priority=2, execution_seconds=1),
            ]
        },
    )
    session_dir = config.runs_dir / "resume-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session_state.json").write_text(
        json.dumps(
            {
                "session_id": "resume-session",
                "status": "running",
                "elapsed_time_seconds": 2.0,
                "tasks_attempted": [],
                "tasks_completed": [],
                "artifacts_generated": [],
                "blockers_detected": [],
                "heartbeats_emitted": 0,
                "loop_iterations": 0,
                "queue_remaining": 2,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    clock = FakeClock()
    router = _make_router(clock)

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=10,
            heartbeat_interval_seconds=2,
            poll_interval_seconds=1,
            session_id="resume-session",
            resume=True,
            stop_when_queue_empty=True,
        ),
        agent_router=router,
        time_source=clock.now,
        monotonic_source=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    result = supervisor.run()

    assert result.stop_reason == "queue_empty"
    assert result.tasks_completed == 2
    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]
    assert [task["status"] for task in queue] == ["completed", "completed"]
    assert queue[0]["current_session_id"] is None

    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["resumed"] is True
    assert state["tasks_completed"] == ["RESUME_001", "RESUME_002"]


def test_scheduler_supports_list_queue_shape_and_retry_limit(tmp_path):
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps([
            {"task_id": "LIST_001", "priority": 1, "status": "pending"}
        ], indent=2),
        encoding="utf-8",
    )
    scheduler = Scheduler(queue_path, max_retries=3)

    next_task = scheduler.get_next_task()
    assert next_task is not None
    assert next_task["task_id"] == "LIST_001"

    scheduler.mark_running("LIST_001", session_id="session-a")
    updated, should_retry = scheduler.requeue_failed(
        "LIST_001",
        session_id="session-a",
        reason="retry once",
    )
    assert should_retry is True
    assert updated["status"] == "pending"

    scheduler.mark_running("LIST_001", session_id="session-a")
    scheduler.requeue_failed("LIST_001", session_id="session-a", reason="retry twice")
    scheduler.mark_running("LIST_001", session_id="session-a")
    updated, should_retry = scheduler.requeue_failed(
        "LIST_001",
        session_id="session-a",
        reason="retry exhausted",
    )

    assert should_retry is False
    assert updated["status"] == "blocked"
    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert raw[0]["status"] == "blocked"
    assert raw[0]["retry_count"] == 3


def test_supervisor_detects_new_intake_task_while_idling_and_prints_status(tmp_path, capsys):
    config = _make_config(tmp_path / "idle_activation")
    _write_queue(config.queue_path, {"tasks": []})
    clock = FakeClock()
    router = _make_router(clock)
    intake = ConversationalTaskIntake(config)
    intake_done = {"value": False}

    def sleep_and_inject(seconds: float) -> None:
        if not intake_done["value"]:
            intake.accept_message(
                    "Stabilize LEVEL_0001 zombie animation.",
                session_id="live-intake-session",
            )
            intake_done["value"] = True
        clock.advance(seconds)

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=6,
            heartbeat_interval_seconds=2,
            poll_interval_seconds=1,
            session_id="idle-activation-session",
            stop_when_queue_empty=False,
        ),
        agent_router=router,
        time_source=clock.now,
        monotonic_source=clock.monotonic,
        sleep_fn=sleep_and_inject,
    )

    result = supervisor.run()
    output = capsys.readouterr().out

    assert result.stop_reason == "queue_empty_idle_timeout"
    assert "SESSION STARTED" in output
    assert "QUEUE EMPTY / WAITING FOR TASKS" in output
    assert "SESSION HEARTBEAT" in output

    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]
    assert len(queue) == 1
    assert queue[0]["status"] == "blocked"
    assert queue[0]["task_type"] == "stabilization_request"
    assert queue[0]["decision"] == "block"
    assert queue[0]["execution_lane"] == "approval_required_mutation"

    runtime_status = json.loads((config.runs_dir / "idle-activation-session" / "runtime_status.json").read_text(encoding="utf-8"))
    assert runtime_status["current_task"] is None
    assert runtime_status["last_started_task"] is None
    assert runtime_status["last_completed_task"] is None
    assert runtime_status["queue_tasks"] == []
    assert runtime_status["rating_system"] == "ESRB"
    assert runtime_status["rating_target"] == "M"
    assert runtime_status["rating_locked"] is True
    assert runtime_status["session_phase"] == "complete"
    assert runtime_status["phase_index"] == 7
    assert runtime_status["phase_total"] == 7
    assert runtime_status["phase_label"] == "Complete"


def test_scheduler_respects_plan_dependencies_for_multi_step_queue(tmp_path):
    config = _make_config(tmp_path / "plan_dependencies")
    _write_queue(
        config.queue_path,
        {
            "tasks": [
                {
                    "task_id": "PLAN_A__STEP_01",
                    "title": "Inspect zombie animation pipeline",
                    "status": "pending",
                    "priority": 25,
                    "plan_id": "PLAN_A",
                    "plan_step_index": 1,
                    "dependencies": [],
                },
                {
                    "task_id": "PLAN_A__STEP_02",
                    "title": "Inspect weapon bootstrap",
                    "status": "pending",
                    "priority": 25,
                    "plan_id": "PLAN_A",
                    "plan_step_index": 2,
                    "dependencies": ["PLAN_A__STEP_01"],
                },
            ]
        },
    )

    scheduler = Scheduler(config.queue_path)

    assert scheduler.get_next_task()["task_id"] == "PLAN_A__STEP_01"
    scheduler.mark_running("PLAN_A__STEP_01", session_id="plan-session")
    scheduler.mark_completed("PLAN_A__STEP_01", session_id="plan-session", result={"status": "completed"})
    assert scheduler.get_next_task()["task_id"] == "PLAN_A__STEP_02"


def test_supervisor_terminates_after_idle_grace_when_queue_stays_empty(tmp_path):
    config = _make_config(tmp_path / "idle_timeout")
    _write_queue(config.queue_path, {"tasks": []})
    clock = FakeClock()
    router = _make_router(clock)

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=20,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            idle_timeout_seconds=3,
            idle_timeout_poll_limit=99,
            session_id="idle-timeout-session",
            stop_when_queue_empty=False,
        ),
        agent_router=router,
        time_source=clock.now,
        monotonic_source=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    result = supervisor.run()

    assert result.stop_reason == "queue_empty_idle_timeout"
    assert result.tasks_completed == 0
    assert result.queue_remaining == 0

    runtime_status = json.loads((config.runs_dir / "idle-timeout-session" / "runtime_status.json").read_text(encoding="utf-8"))
    assert runtime_status["stop_reason"] == "queue_empty_idle_timeout"
    assert runtime_status["session_state"] == "complete"
    assert runtime_status["work_state"] == "halted"
    assert runtime_status["budget_mode"] == "terminating"

    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["idle_duration_seconds"] >= 3.0
    assert state["queue_remaining"] == 0


def test_supervisor_records_operator_interrupt_stop_reason(tmp_path):
    config = _make_config(tmp_path / "operator_interrupt")
    _write_queue(config.queue_path, {"tasks": []})
    clock = FakeClock()
    router = _make_router(clock)
    interrupt_requested = {"value": False}

    def sleep_and_interrupt(seconds: float) -> None:
        if not interrupt_requested["value"]:
            supervisor.request_stop(reason="operator_interrupt")
            interrupt_requested["value"] = True
        clock.advance(seconds)

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=20,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            idle_timeout_seconds=0,
            idle_timeout_poll_limit=0,
            session_id="operator-interrupt-session",
            stop_when_queue_empty=False,
        ),
        agent_router=router,
        time_source=clock.now,
        monotonic_source=clock.monotonic,
        sleep_fn=sleep_and_interrupt,
    )

    result = supervisor.run()

    assert result.stop_reason == "operator_interrupt"
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["stop_reason"] == "operator_interrupt"
    assert state["status"] == "completed"


def test_supervisor_executes_approved_level0001_grass_mutation_and_records_evidence(tmp_path):
    config = _make_config(tmp_path / "grass_mutation")
    _write_grass_capability_contracts(config)
    _create_minimal_scene_repo(config, target_repo_name="BABYLON_TEST")
    intake = ConversationalTaskIntake(config)
    result = intake.accept_message(
        "make grass for level_0001",
        session_id="grass-mutation-session",
        target_repo=str((config.root_dir / "BABYLON_TEST").resolve()),
    )

    assert result.queue_entry["status"] == "needs_approval"

    approval = approve_mutation_task(
        config,
        task_id=result.task_id,
        approved_by="operator-test",
        notes="Approve first bounded grass mutation.",
    )
    assert approval.queue_status == "pending"

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=10,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            idle_timeout_seconds=2,
            idle_timeout_poll_limit=99,
            session_id="grass-mutation-session",
            stop_when_queue_empty=False,
        ),
    )

    run_result = supervisor.run()

    assert run_result.tasks_completed == 1
    assert run_result.stop_reason == "queue_empty_idle_timeout"

    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]
    assert queue[0]["status"] == "completed"
    assert queue[0]["approved_by"] == "operator-test"

    scene_path = config.root_dir / "BABYLON_TEST" / "Assets" / "AI_E_TestScenes" / "MinimalPlayableArena.unity"
    scene_text = scene_path.read_text(encoding="utf-8")
    assert "AIE_LEVEL_0001_GrassPatch_001" in scene_text

    evidence_store = CapabilityEvidenceStore(config.contracts_dir / "capabilities" / "evidence.json")
    evidence = evidence_store.get("level_0001_add_grass")
    assert evidence is not None
    assert evidence["times_attempted"] == 1
    assert evidence["times_passed"] == 1
    assert evidence["last_validation_result"] == "passed"

    artifact_path = config.runs_dir / "grass-mutation-session" / "artifacts" / f"{result.task_id}_attempt_01.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["result"]["details"]["added_object_name"] == "AIE_LEVEL_0001_GrassPatch_001"
    assert artifact["result"]["details"]["validation"]["status"] == "passed"
    assert artifact["result"]["details"]["approval_state"] == "approved"


def test_supervisor_executes_auto_promoted_level0001_grass_mutation_without_manual_approval(tmp_path):
    config = _make_config(tmp_path / "grass_mutation_auto")
    _write_grass_capability_contracts(config)
    _seed_auto_promoted_reference_capability_proof(config)
    _create_minimal_scene_repo(config, target_repo_name="BABYLON_TEST")
    intake = ConversationalTaskIntake(config)
    result = intake.accept_message(
        "make grass for level_0001",
        session_id="grass-mutation-auto-session",
        target_repo=str((config.root_dir / "BABYLON_TEST").resolve()),
    )

    assert result.queue_entry["status"] == "pending"
    assert result.queue_entry["approval_state"] == "auto_approved"
    assert result.queue_entry["approved_by"] == "system_intelligence_v1"

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=10,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            idle_timeout_seconds=2,
            idle_timeout_poll_limit=99,
            session_id="grass-mutation-auto-session",
            stop_when_queue_empty=False,
        ),
    )

    run_result = supervisor.run()

    assert run_result.tasks_completed == 1
    assert run_result.stop_reason == "queue_empty_idle_timeout"

    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]
    assert queue[0]["status"] == "completed"
    assert queue[0]["approval_state"] == "auto_approved"
    assert queue[0]["approved_by"] == "system_intelligence_v1"
    assert queue[0]["execution_decision"] == "auto_execute"

    scene_path = config.root_dir / "BABYLON_TEST" / "Assets" / "AI_E_TestScenes" / "MinimalPlayableArena.unity"
    scene_text = scene_path.read_text(encoding="utf-8")
    assert "AIE_LEVEL_0001_GrassPatch_001" in scene_text

    artifact_path = config.runs_dir / "grass-mutation-auto-session" / "artifacts" / f"{result.task_id}_attempt_01.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["task"]["execution_decision"] == "auto_execute"
    assert artifact["task"]["auto_execution_enabled"] is True
    assert artifact["task"]["approval_state"] == "auto_approved"
    assert artifact["result"]["details"]["execution_decision"] == "auto_execute"
    assert artifact["result"]["details"]["auto_execution_enabled"] is True
    assert artifact["result"]["details"]["approval_state"] == "auto_approved"


def test_supervisor_executes_approved_level0001_grass_removal_and_records_evidence(tmp_path):
    config = _make_config(tmp_path / "grass_removal")
    _write_grass_capability_contracts(config)
    _create_minimal_scene_repo(config, target_repo_name="BABYLON_TEST")
    intake = ConversationalTaskIntake(config)
    target_repo = str((config.root_dir / "BABYLON_TEST").resolve())

    add_result = intake.accept_message(
        "make grass for level_0001",
        session_id="grass-removal-seed",
        target_repo=target_repo,
    )
    approve_mutation_task(
        config,
        task_id=add_result.task_id,
        approved_by="operator-test",
        notes="Seed grass patch before removal.",
    )
    Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=10,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            idle_timeout_seconds=2,
            idle_timeout_poll_limit=99,
            session_id="grass-removal-seed",
            stop_when_queue_empty=False,
        ),
    ).run()

    result = intake.accept_message(
        "remove grass for level_0001",
        session_id="grass-removal-session",
        target_repo=target_repo,
    )

    assert result.queue_entry["status"] == "needs_approval"

    approval = approve_mutation_task(
        config,
        task_id=result.task_id,
        approved_by="operator-test",
        notes="Approve bounded grass removal.",
    )
    assert approval.queue_status == "pending"

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=10,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            idle_timeout_seconds=2,
            idle_timeout_poll_limit=99,
            session_id="grass-removal-session",
            stop_when_queue_empty=False,
        ),
    )

    run_result = supervisor.run()

    assert run_result.tasks_completed == 1
    assert run_result.stop_reason == "queue_empty_idle_timeout"

    scene_path = config.root_dir / "BABYLON_TEST" / "Assets" / "AI_E_TestScenes" / "MinimalPlayableArena.unity"
    scene_text = scene_path.read_text(encoding="utf-8")
    assert "AIE_LEVEL_0001_GrassPatch_001" not in scene_text

    evidence_store = CapabilityEvidenceStore(config.contracts_dir / "capabilities" / "evidence.json")
    evidence = evidence_store.get("level_0001_remove_grass")
    assert evidence is not None
    assert evidence["times_attempted"] == 1
    assert evidence["times_passed"] == 1
    assert evidence["last_validation_result"] == "passed"
    assert evidence["sandbox_verified"] is True

    artifact_path = config.runs_dir / "grass-removal-session" / "artifacts" / f"{result.task_id}_attempt_01.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["result"]["details"]["removed_object_name"] == "AIE_LEVEL_0001_GrassPatch_001"
    assert artifact["result"]["details"]["validation"]["status"] == "passed"
    assert artifact["result"]["details"]["approval_state"] == "approved"


def test_supervisor_executes_chained_add_then_remove_grass_in_one_session(tmp_path):
    config = _make_config(tmp_path / "grass_chain")
    _write_grass_capability_contracts(config)
    _create_minimal_scene_repo(config, target_repo_name="BABYLON_TEST")
    intake = ConversationalTaskIntake(config)
    target_repo = str((config.root_dir / "BABYLON_TEST").resolve())

    add_result = intake.accept_message(
        "make grass for level_0001",
        session_id="grass-chain-session",
        target_repo=target_repo,
    )
    remove_result = intake.accept_message(
        "remove grass for level_0001",
        session_id="grass-chain-session",
        target_repo=target_repo,
    )

    queue_payload = json.loads(config.queue_path.read_text(encoding="utf-8"))
    for task in queue_payload["tasks"]:
        if task["task_id"] == remove_result.task_id:
            task["dependencies"] = [add_result.task_id]
    config.queue_path.write_text(json.dumps(queue_payload, indent=2), encoding="utf-8")

    remove_runtime_payload = json.loads(remove_result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))
    remove_runtime_payload["runtime_task"]["dependencies"] = [add_result.task_id]
    remove_result.artifacts.runtime_task_payload_path.write_text(json.dumps(remove_runtime_payload, indent=2), encoding="utf-8")

    approve_mutation_task(
        config,
        task_id=add_result.task_id,
        approved_by="operator-test",
        notes="Approve chained add grass task.",
    )
    approve_mutation_task(
        config,
        task_id=remove_result.task_id,
        approved_by="operator-test",
        notes="Approve chained remove grass task.",
    )

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=10,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            idle_timeout_seconds=2,
            idle_timeout_poll_limit=99,
            session_id="grass-chain-session",
            stop_when_queue_empty=False,
        ),
    )

    run_result = supervisor.run()

    assert run_result.tasks_completed == 2
    assert run_result.stop_reason == "queue_empty_idle_timeout"

    scene_path = config.root_dir / "BABYLON_TEST" / "Assets" / "AI_E_TestScenes" / "MinimalPlayableArena.unity"
    scene_text = scene_path.read_text(encoding="utf-8")
    assert "AIE_LEVEL_0001_GrassPatch_001" not in scene_text

    add_artifact_path = config.runs_dir / "grass-chain-session" / "artifacts" / f"{add_result.task_id}_attempt_01.json"
    remove_artifact_path = config.runs_dir / "grass-chain-session" / "artifacts" / f"{remove_result.task_id}_attempt_01.json"
    add_artifact = json.loads(add_artifact_path.read_text(encoding="utf-8"))
    remove_artifact = json.loads(remove_artifact_path.read_text(encoding="utf-8"))
    assert add_artifact["result"]["details"]["added_object_name"] == "AIE_LEVEL_0001_GrassPatch_001"
    assert remove_artifact["result"]["details"]["removed_object_name"] == "AIE_LEVEL_0001_GrassPatch_001"
    assert add_artifact["result"]["details"]["validation"]["status"] == "passed"
    assert remove_artifact["result"]["details"]["validation"]["status"] == "passed"


def _make_router(clock: FakeClock) -> AgentRouter:
    router = AgentRouter()

    def run_task(task):
        clock.advance(float(task.get("execution_seconds", 0)))
        outcome = str(task.get("simulated_outcome", "completed"))
        if outcome == "blocked":
            return {
                "status": "blocked",
                "summary": f"blocked {task['task_id']}",
                "error": "blocked by test",
            }
        if outcome == "retryable_failure":
            return {
                "status": "retryable_failure",
                "summary": f"retry {task['task_id']}",
                "error": "retry requested by test",
                "retryable": True,
            }
        return {
            "status": "completed",
            "summary": f"completed {task['task_id']}",
            "details": {"task_id": task["task_id"]},
        }

    router.register("copilot_coder_agent", run_task)
    return router


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

    for path in [
        runs_dir,
        workspaces_dir,
        queue_contracts_dir,
        templates_dir,
        approvals_path.parent,
        agent_registry_path.parent,
        root_dir / "logs",
    ]:
        path.mkdir(parents=True, exist_ok=True)
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


def _task(config: OrchestratorConfig, task_id: str, *, priority: int, execution_seconds: int, simulated_outcome: str = "completed"):
    return {
        "task_id": task_id,
        "priority": priority,
        "status": "pending",
        "execution_seconds": execution_seconds,
        "simulated_outcome": simulated_outcome,
        "contract_path": _create_runtime_payload(
            config,
            task_id,
            execution_seconds=execution_seconds,
            simulated_outcome=simulated_outcome,
        ),
    }


def _write_queue(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_runtime_payload(
    config: OrchestratorConfig,
    task_id: str,
    *,
    execution_seconds: int,
    simulated_outcome: str = "completed",
) -> str:
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
                    "simulated_outcome": simulated_outcome,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return str(path.relative_to(config.root_dir)).replace("\\", "/")


def _create_minimal_scene_repo(config: OrchestratorConfig, *, target_repo_name: str) -> None:
    repo_root = config.root_dir / target_repo_name
    scene_dir = repo_root / "Assets" / "AI_E_TestScenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "MinimalPlayableArena.unity").write_text(
        "%YAML 1.1\n"
        "%TAG !u! tag:unity3d.com,2011:\n"
        "--- !u!29 &1\n"
        "OcclusionCullingSettings:\n"
        "  m_ObjectHideFlags: 0\n"
        "  serializedVersion: 2\n"
        "  m_SceneGUID: 00000000000000000000000000000000\n"
        "  m_OcclusionCullingData: {fileID: 0}\n"
        "--- !u!1660057539 &9223372036854775807\n"
        "SceneRoots:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_Roots:\n",
        encoding="utf-8",
    )


def _write_grass_capability_contracts(config: OrchestratorConfig) -> None:
    capabilities_dir = config.contracts_dir / "capabilities"
    capabilities_dir.mkdir(parents=True, exist_ok=True)
    (capabilities_dir / "level_0001_add_grass.json").write_text(
        json.dumps(
            {
                "capability_id": "level_0001_add_grass",
                "title": "LEVEL_0001 add grass",
                "intent": "mutate",
                "target_level": "LEVEL_0001",
                "target_scene": "Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
                "requested_execution_lane": "approval_required_mutation",
                "handler_name": "level_0001_grass_handler",
                "agent_type": "level_0001_grass_mutation_agent",
                "approval_required": True,
                "eligible_for_auto": False,
                "evidence_state": "experimental",
                "safety_class": "approval_gated_automation",
                "match_terms": ["level_0001", "grass"],
                "match_verbs": ["make", "add", "create", "generate", "place", "build"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (capabilities_dir / "level_0001_remove_grass.json").write_text(
        json.dumps(
            {
                "capability_id": "level_0001_remove_grass",
                "title": "LEVEL_0001 remove grass",
                "intent": "mutate",
                "target_level": "LEVEL_0001",
                "target_scene": "Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
                "requested_execution_lane": "approval_required_mutation",
                "handler_name": "level_0001_remove_grass_handler",
                "agent_type": "level_0001_grass_mutation_agent",
                "approval_required": True,
                "eligible_for_auto": False,
                "evidence_state": "experimental",
                "safety_class": "approval_gated_automation",
                "match_terms": ["level_0001", "grass"],
                "match_verbs": ["remove", "delete", "clear"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _seed_auto_promoted_reference_capability_proof(config: OrchestratorConfig) -> None:
    capabilities_dir = config.contracts_dir / "capabilities"
    capabilities_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = capabilities_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "capabilities": {
                    "level_0001_add_grass": {
                        "capability_id": "level_0001_add_grass",
                        "handler_name": "level_0001_grass_handler",
                        "safety_class": "approval_gated_automation",
                        "times_attempted": 4,
                        "times_passed": 4,
                        "last_validation_result": "passed",
                        "last_rollback_result": "none",
                        "artifact_requirements_met": True,
                        "eligible_for_auto": False,
                        "requires_approval": True,
                        "evidence_state": "experimental",
                        "sandbox_verified": False,
                        "real_target_verified": False,
                        "rollback_verified": False,
                        "notes": "Reference capability evidence seeded for auto-promotion derivation.",
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    run_dir = config.runs_dir / "live_real_grass_validation_20260317"
    post_dir = run_dir / "post_mutation"
    rollback_dir = run_dir / "rollback"
    post_dir.mkdir(parents=True, exist_ok=True)
    rollback_dir.mkdir(parents=True, exist_ok=True)

    (post_dir / "real_target_validation_report.json").write_text(
        json.dumps(
            {
                "session_id": "live_real_grass_validation_20260317",
                "capability_id": "level_0001_add_grass",
                "validation_result": "passed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (rollback_dir / "rollback_validation_report.json").write_text(
        json.dumps(
            {
                "session_id": "live_real_grass_validation_20260317",
                "capability_id": "level_0001_add_grass",
                "rollback_validation_result": "passed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )