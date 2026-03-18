import json
import os
import threading
from io import StringIO

import pytest

from ai_e_runtime.conversation_router import ConversationRouter
from ai_e_runtime.runtime_state import RuntimeState
from ai_e_runtime.supervisor import Supervisor, SupervisorConfig
from orchestrator.config import OrchestratorConfig
from session_runner import run_interactive_session


pytestmark = pytest.mark.fast


def test_conversation_router_answers_status_queries(tmp_path):
    config = _make_config(tmp_path / "conversation_router")
    _write_queue(
        config.queue_path,
        {
            "tasks": [
                {
                    "task_id": "LEVEL_0001_STAB",
                    "title": "Inspect zombie animation pipeline",
                    "priority": 10,
                    "status": "running",
                    "plan_id": "PLAN_ABC123",
                    "plan_step_index": 1,
                    "plan_step_title": "Inspect zombie animation pipeline",
                },
                {
                    "task_id": "FOLLOWUP_001",
                    "title": "Inspect weapon bootstrap",
                    "priority": 20,
                    "status": "pending",
                    "plan_id": "PLAN_ABC123",
                    "plan_step_index": 2,
                    "plan_step_title": "Inspect weapon bootstrap",
                },
            ]
        },
    )

    state_dir = config.runs_dir / "conversation-session"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "session_state.json").write_text(
        json.dumps(
            {
                "session_id": "conversation-session",
                "status": "running",
                "started_at": "2026-03-16T23:00:00Z",
                "elapsed_time_seconds": 12.5,
                "current_task": "LEVEL_0001_STAB",
                "last_started_task": "LEVEL_0001_STAB",
                "last_completed_task": "INTAKE_3F2BC964001F",
                "queue_remaining": 2,
                "tasks_completed": ["INTAKE_3F2BC964001F"],
                "tasks_failed": [
                    {
                        "task_id": "TASK_FAIL_001",
                        "note": "Validation error.",
                        "timestamp": "2026-03-16T23:01:00Z",
                    }
                ],
                "last_heartbeat_timestamp": "2026-03-16T23:00:08Z",
                "artifacts_generated": [],
                "blockers_detected": [],
                "stop_reason": None,
                "current_plan_id": "PLAN_ABC123",
                "current_plan_step": "Inspect zombie animation pipeline",
                "last_generated_plan_summary": "PLAN\n1. Inspect zombie animation pipeline\n2. Inspect weapon bootstrap\n3. Inspect KBM controls\n4. Validate integrated result\n5. Generate summary artifact",
                "last_generated_plan_steps": [
                    "Inspect zombie animation pipeline",
                    "Inspect weapon bootstrap",
                    "Inspect KBM controls",
                    "Validate integrated result",
                    "Generate summary artifact",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    router = ConversationRouter(RuntimeState(config, "conversation-session"))

    status_response = router.route("what are you doing right now")
    queue_response = router.route("show queue")
    started_response = router.route("what task started")
    completed_response = router.route("what task completed")
    failure_response = router.route("what failed recently")
    next_response = router.route("what should I do next")
    plan_response = router.route("what plan did you generate")
    running_step_response = router.route("what step is running")
    next_step_response = router.route("what step is next")
    steps_left_response = router.route("how many steps are left")

    assert "Current Task: LEVEL_0001_STAB" in status_response.answer
    assert "Last Started Task: LEVEL_0001_STAB" in status_response.answer
    assert "Queue Contents: LEVEL_0001_STAB (running, priority 10); FOLLOWUP_001 (pending, priority 20)" in queue_response.answer
    assert "Last Started Task: LEVEL_0001_STAB" in started_response.answer
    assert "Last Completed Task: INTAKE_3F2BC964001F" in completed_response.answer
    assert "TASK_FAIL_001" in failure_response.answer
    assert "Queue contains active work" in next_response.recommendation
    assert "PLAN" in plan_response.answer
    assert "Current Plan Step: Inspect zombie animation pipeline" in running_step_response.answer
    assert "Next Plan Step: Inspect weapon bootstrap" in next_step_response.answer
    assert "Steps Remaining: 2" in steps_left_response.answer
    assert router.classify_prompt("help") == "CONTROL_COMMAND"
    assert router.classify_prompt("what are you doing right now") == "STATUS_QUERY"
    assert router.classify_prompt("what plan did you generate") == "STATUS_QUERY"
    assert router.classify_prompt(
        "stabilize LEVEL_0001 zombie animation",
        task_request_classifier=lambda prompt: "task_request",
    ) == "TASK_REQUEST"


def test_interactive_mode_answers_prompts_without_breaking_runtime_loop(tmp_path):
    config = _make_config(tmp_path / "interactive")
    _write_queue(
        config.queue_path,
        {
            "tasks": [
                _task(config, "CHAT_001", priority=1, execution_seconds=1),
            ]
        },
    )
    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=3,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            session_id="interactive-session",
            stop_when_queue_empty=True,
        ),
    )

    input_stream = StringIO("what are you doing right now\nshow queue\n")
    output_stream = StringIO()
    result = run_interactive_session(supervisor, input_stream=input_stream, output_stream=output_stream)
    output = output_stream.getvalue()

    assert "AI-E Command Center interactive mode enabled" in output
    assert "AI-E STATUS REPORT" in output
    assert "Queue Remaining" in output
    assert result.tasks_completed == 1
    assert json.loads((config.runs_dir / "interactive-session" / "runtime_status.json").read_text(encoding="utf-8"))["tasks_completed"] == ["CHAT_001"]


def test_interactive_mode_accepts_task_request_directly_without_manual_intake(tmp_path, monkeypatch):
    config = _make_config(tmp_path / "interactive_task_request")
    _write_queue(config.queue_path, {"tasks": []})
    monkeypatch.chdir(config.root_dir)
    monkeypatch.setenv("AI_E_TASK_INTAKE_SIMULATED_DELAY_SECONDS", "1.5")

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=4,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            session_id="interactive-task-request-session",
            stop_when_queue_empty=False,
        ),
    )

    input_stream = StringIO(
        "stabilize LEVEL_0001 zombie animation\n"
        "what are you doing\n"
        "show queue\n"
        "what started\n"
        "what completed last\n"
        "exit\n"
    )
    output_stream = StringIO()
    result = run_interactive_session(supervisor, input_stream=input_stream, output_stream=output_stream)
    output = output_stream.getvalue()

    runtime_status_path = config.runs_dir / "interactive-task-request-session" / "runtime_status.json"
    runtime_status = json.loads(runtime_status_path.read_text(encoding="utf-8"))
    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]

    assert "AI-E TASK ACCEPTED" in output
    assert "Classification: TASK_REQUEST" in output
    assert "Execution Lane: read_only_inspection" in output
    assert "Downgrade: yes" in output
    assert "Supervisor will pick up the task automatically." in output
    assert "AI-E STATUS REPORT" in output
    assert len(queue) == 1
    assert queue[0]["task_id"].startswith("INTAKE_")
    assert queue[0]["request_payload_path"].startswith("contracts/intake/requests/")
    assert queue[0]["task_graph_path"].startswith("contracts/intake/task_graphs/")
    assert queue[0]["contract_path"].startswith("contracts/intake/runtime_tasks/")
    assert runtime_status["last_started_task"] == queue[0]["task_id"]
    assert runtime_status["last_completed_task"] == queue[0]["task_id"]
    assert result.tasks_completed == 1


def test_interactive_mode_supports_control_commands_without_queue_pollution(tmp_path, monkeypatch):
    config = _make_config(tmp_path / "interactive_controls")
    _write_queue(config.queue_path, {"tasks": []})
    monkeypatch.chdir(config.root_dir)
    monkeypatch.setenv("AI_E_TASK_INTAKE_SIMULATED_DELAY_SECONDS", "1")

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=5,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            session_id="interactive-control-session",
            stop_when_queue_empty=False,
        ),
    )

    input_stream = StringIO(
        "help\n"
        "clear\n"
        "stabilize LEVEL_0001 zombie animation\n"
        "pause polling\n"
        "show last acceptance\n"
        "resume polling\n"
        "show last artifact\n"
        "exit\n"
    )
    output_stream = StringIO()
    result = run_interactive_session(supervisor, input_stream=input_stream, output_stream=output_stream)
    output = output_stream.getvalue()

    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]
    state = json.loads((config.runs_dir / "interactive-control-session" / "runtime_status.json").read_text(encoding="utf-8"))

    assert "AI-E COMMAND CENTER HELP" in output
    assert "AI-E POLLING PAUSED" in output
    assert "AI-E POLLING RESUMED" in output
    assert "AI-E LAST ACCEPTANCE" in output
    assert "Execution Lane: read_only_inspection" in output
    assert "AI-E LAST ARTIFACT" in output
    assert "Runtime Task Payload:" in output
    assert len(queue) == 1
    assert queue[0]["task_type"] == "stabilization_request"
    assert state["polling_enabled"] is True
    assert result.stop_reason == "operator_exit"


def test_interactive_mode_accepts_composite_plan_and_answers_plan_queries(tmp_path, monkeypatch):
    config = _make_config(tmp_path / "interactive_plan_request")
    _write_queue(config.queue_path, {"tasks": []})
    monkeypatch.chdir(config.root_dir)
    monkeypatch.setenv("AI_E_TASK_INTAKE_SIMULATED_DELAY_SECONDS", "1")

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=8,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            session_id="interactive-plan-session",
            stop_when_queue_empty=False,
        ),
    )

    input_stream = StringIO(
        "Fix LEVEL_0001 zombie animation, weapon bootstrap, and KBM controls\n"
        "what plan did you generate\n"
        "what step is running\n"
        "what step is next\n"
        "how many steps are left\n"
        "exit\n"
    )
    output_stream = StringIO()
    result = run_interactive_session(supervisor, input_stream=input_stream, output_stream=output_stream)
    output = output_stream.getvalue()
    runtime_status = json.loads((config.runs_dir / "interactive-plan-session" / "runtime_status.json").read_text(encoding="utf-8"))
    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]

    assert "AI-E PLAN ACCEPTED" in output
    assert "Plan Steps:" in output
    assert "AI-E PLAN STATUS" in output
    assert len(queue) == 5
    assert runtime_status["current_plan_id"] is not None
    assert runtime_status["last_generated_plan_summary"].startswith("PLAN")
    assert result.tasks_completed >= 1


def test_interactive_mode_reports_approval_required_lane_for_freeform_grass_request(tmp_path, monkeypatch):
    config = _make_config(tmp_path / "interactive_freeform_mutation_request")
    _write_queue(config.queue_path, {"tasks": []})
    monkeypatch.chdir(config.root_dir)
    monkeypatch.setenv("AI_E_TASK_INTAKE_SIMULATED_DELAY_SECONDS", "1")

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=6,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            session_id="interactive-freeform-mutation-session",
            stop_when_queue_empty=False,
        ),
    )

    input_stream = StringIO(
        "make grass for level_0001\n"
        "show last acceptance\n"
        "exit\n"
    )
    output_stream = StringIO()
    run_interactive_session(supervisor, input_stream=input_stream, output_stream=output_stream)
    output = output_stream.getvalue()

    assert "Requested Intent: mutate" in output
    assert "Requested Lane: approval_required_mutation" in output
    assert "Execution Lane: approval_required_mutation" in output
    assert "Downgrade: no" in output
    assert "Approval Required: yes" in output
    assert "Mutation Capable: yes" in output
    assert "Capability Matched: level_0001_add_grass" in output
    assert "Maturity: experimental" in output
    assert "Execution Decision: sandbox_first" in output
    assert "Trust Score: 0" in output
    assert "Policy State: test_only" in output
    assert "Recommended Action: sandbox_first" in output
    assert "Rating System: ESRB" in output
    assert "Rating Target: M" in output
    assert "Content Policy Match: fits_rating" in output
    assert "Content Policy Decision: allowed" in output


def test_interactive_mode_reports_approval_required_mutation_lane_for_supported_grass_request(tmp_path, monkeypatch):
    config = _make_config(tmp_path / "interactive_supported_grass_request")
    _write_queue(config.queue_path, {"tasks": []})
    monkeypatch.chdir(config.root_dir)
    monkeypatch.setenv("AI_E_TASK_INTAKE_SIMULATED_DELAY_SECONDS", "1")

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=6,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            session_id="interactive-supported-grass-session",
            stop_when_queue_empty=False,
        ),
    )

    input_stream = StringIO(
        "make grass for level_0001\n"
        "show last acceptance\n"
        "exit\n"
    )
    output_stream = StringIO()
    run_interactive_session(supervisor, input_stream=input_stream, output_stream=output_stream)
    output = output_stream.getvalue()

    assert "Requested Intent: mutate" in output
    assert "Requested Lane: approval_required_mutation" in output
    assert "Execution Lane: approval_required_mutation" in output
    assert "Downgrade: no" in output
    assert "Approval Required: yes" in output
    assert "Mutation Capable: yes" in output
    assert "Capability Matched: level_0001_add_grass" in output
    assert "Maturity: experimental" in output
    assert "Execution Decision: sandbox_first" in output
    assert "Trust Score: 0" in output
    assert "Policy State: test_only" in output
    assert "Recommended Action: sandbox_first" in output
    assert "Rating System: ESRB" in output
    assert "Rating Target: M" in output
    assert "Content Policy Match: fits_rating" in output
    assert "Content Policy Decision: allowed" in output
    assert "Status: needs_approval" in output


def test_interactive_mode_exits_when_supervisor_stops_after_idle_timeout(tmp_path):
    config = _make_config(tmp_path / "interactive_idle_timeout")
    _write_queue(config.queue_path, {"tasks": []})

    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=20,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            idle_timeout_seconds=2,
            idle_timeout_poll_limit=99,
            session_id="interactive-idle-timeout-session",
            stop_when_queue_empty=False,
        ),
    )

    class BlockingInput(StringIO):
        def readline(self, *args, **kwargs):
            threading.Event().wait(10)
            return ""

    input_stream = BlockingInput()
    output_stream = StringIO()
    result = run_interactive_session(supervisor, input_stream=input_stream, output_stream=output_stream)
    output = output_stream.getvalue()

    assert "AI-E Command Center interactive mode enabled" in output
    assert result.stop_reason == "queue_empty_idle_timeout"

    runtime_status = json.loads((config.runs_dir / "interactive-idle-timeout-session" / "runtime_status.json").read_text(encoding="utf-8"))
    assert runtime_status["stop_reason"] == "queue_empty_idle_timeout"
    assert runtime_status["queue_remaining"] == 0


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