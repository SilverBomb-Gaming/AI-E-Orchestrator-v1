from __future__ import annotations

import argparse
import json
import signal
from queue import Empty, Queue
import sys
import threading
import time
from dataclasses import dataclass
from io import TextIOBase
from pathlib import Path

from ai_e_runtime.control_commands import ControlCommandHandler
from ai_e_runtime.conversation_router import ConversationRouter
from ai_e_runtime.supervisor import Supervisor, SupervisorConfig
from ai_e_runtime.task_intake import ConversationalTaskIntake, IntakeResult
from orchestrator.config import OrchestratorConfig


DEFAULT_SESSION_LIMIT_SECONDS = 2 * 60 * 60
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5 * 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_IDLE_TIMEOUT_SECONDS = 30
DEFAULT_IDLE_TIMEOUT_POLL_LIMIT = 3


@dataclass
class InteractiveSessionContext:
    last_acceptance: dict[str, object] | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AI-E persistent supervisor loop.")
    parser.add_argument("--session-id", default=None, help="Optional explicit session id.")
    parser.add_argument(
        "--session-limit-seconds",
        type=int,
        default=DEFAULT_SESSION_LIMIT_SECONDS,
        help="Wall-clock runtime budget in seconds.",
    )
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=int,
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        help="Heartbeat cadence in seconds.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=5,
        help="Idle wait between queue polls when no task is ready.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum retries before the scheduler blocks a task.",
    )
    parser.add_argument(
        "--idle-timeout-seconds",
        type=int,
        default=DEFAULT_IDLE_TIMEOUT_SECONDS,
        help="Terminate after this many idle seconds with an empty queue. Use 0 to disable the time-based idle timeout.",
    )
    parser.add_argument(
        "--idle-timeout-poll-limit",
        type=int,
        default=DEFAULT_IDLE_TIMEOUT_POLL_LIMIT,
        help="Terminate after this many consecutive idle polls with an empty queue. Use 0 to disable the poll-count idle timeout.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an existing session state and reclaim this session's running tasks.",
    )
    parser.add_argument(
        "--stop-when-queue-empty",
        action="store_true",
        help="Stop early when the queue is empty instead of waiting for the full time budget.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable terminal conversational status queries while the supervisor runs.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    orchestrator_config = OrchestratorConfig.load()
    supervisor = Supervisor(
        orchestrator_config,
        SupervisorConfig(
            session_limit_seconds=args.session_limit_seconds,
            heartbeat_interval_seconds=args.heartbeat_interval_seconds,
            max_retries=args.max_retries,
            poll_interval_seconds=args.poll_interval_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
            idle_timeout_poll_limit=args.idle_timeout_poll_limit,
            session_id=args.session_id,
            resume=args.resume,
            stop_when_queue_empty=args.stop_when_queue_empty,
        ),
    )
    interrupt_state = _install_interrupt_handlers(supervisor)
    try:
        if args.interactive:
            result = run_interactive_session(supervisor)
        else:
            result = supervisor.run()
    finally:
        _restore_interrupt_handlers(interrupt_state)
    print_runtime_result(result)
    if interrupt_state["triggered"].is_set():
        return 130
    return 0


def run_interactive_session(
    supervisor: Supervisor,
    *,
    input_stream: TextIOBase | None = None,
    output_stream: TextIOBase | None = None,
) -> object:
    input_handle = input_stream or sys.stdin
    output_handle = output_stream or sys.stdout
    router = ConversationRouter(supervisor.runtime_state)
    intake = ConversationalTaskIntake(supervisor.orchestrator_config)
    command_handler = ControlCommandHandler(supervisor, supervisor.runtime_state)
    context = InteractiveSessionContext()
    result_holder: dict[str, object] = {}
    input_queue: Queue[str | object] = Queue()
    input_closed = object()

    def _run_supervisor() -> None:
        result_holder["result"] = supervisor.run()

    def _read_input() -> None:
        while True:
            line = input_handle.readline()
            if line == "":
                input_queue.put(input_closed)
                return
            input_queue.put(line)

    worker = threading.Thread(target=_run_supervisor, name="ai-e-supervisor", daemon=False)
    reader = threading.Thread(target=_read_input, name="ai-e-interactive-input", daemon=True)
    worker.start()
    reader.start()
    deadline = time.time() + 2.0
    while not supervisor.state_store.state_path.exists() and time.time() < deadline:
        time.sleep(0.01)
    output_handle.write("AI-E Command Center interactive mode enabled. Type a status question or 'exit'.\n")
    output_handle.flush()

    while True:
        if not worker.is_alive() and input_queue.empty() and "result" in result_holder:
            break
        try:
            line = input_queue.get(timeout=0.1)
        except Empty:
            continue
        if line is input_closed:
            if not worker.is_alive() and "result" in result_holder:
                break
            continue
        prompt = line.strip()
        if not prompt:
            continue
        classification = router.classify_prompt(prompt, task_request_classifier=intake.classify_message)
        if classification == "CONTROL_COMMAND":
            command_result = command_handler.execute(prompt, last_acceptance=context.last_acceptance)
            output_handle.write(command_result.to_text() + "\n")
            output_handle.flush()
            if command_result.should_exit:
                break
        elif classification == "STATUS_QUERY":
            response = router.route(prompt)
            output_handle.write(response.to_text() + "\n")
            output_handle.flush()
        elif classification == "TASK_REQUEST":
            acceptance = _accept_interactive_task_request(intake, prompt=prompt, session_id=supervisor.session_id)
            _wait_for_interactive_task_progress(supervisor, acceptance["details"])
            output_handle.write(acceptance["text"] + "\n")
            context.last_acceptance = acceptance["details"]
            output_handle.flush()
        else:
            output_handle.write(
                "AI-E INPUT NOT RECOGNIZED\n\n"
                "Message was not classified as a status query or TASK_REQUEST.\n\n"
                "Recommendation: Ask a status question or enter a direct task request such as 'stabilize LEVEL_0001 ...'.\n"
            )
            output_handle.flush()
        if not worker.is_alive() and "result" in result_holder:
            break

    worker.join()
    return result_holder["result"]


def _accept_interactive_task_request(
    intake: ConversationalTaskIntake,
    *,
    prompt: str,
    session_id: str,
) -> dict[str, object]:
    result = intake.accept_message(
        prompt,
        session_id=session_id,
        channel="interactive_command_center",
    )
    return {
        "text": _format_task_acceptance_response(result),
        "details": {
            "task_id": result.task_id,
            "task_ids": list(result.task_ids),
            "request_id": result.request_id,
            "plan_id": result.plan_id,
            "status": result.queue_entry.get("status", "pending"),
            "runtime_task_payload_path": str(result.artifacts.runtime_task_payload_path),
            "runtime_task_payload_paths": [str(path) for path in result.artifacts.runtime_task_payload_paths],
            "request_payload_path": str(result.artifacts.request_payload_path),
            "task_graph_path": str(result.artifacts.task_graph_path),
            "plan_step_titles": list(result.plan_step_titles),
            "plan_summary": result.plan_summary,
            "requested_intent": result.routing.requested_intent,
            "resolved_intent": result.routing.resolved_intent,
            "requested_execution_lane": result.routing.requested_execution_lane,
            "execution_lane": result.routing.execution_lane,
            "downgraded": result.routing.downgraded,
            "downgrade_reason": result.routing.downgrade_reason,
            "approval_required": result.routing.approval_required,
            "mutation_capable": result.routing.mutation_capable,
            "capability_id": result.routing.capability_id,
            "capability_title": result.routing.capability_title,
            "handler_name": result.routing.handler_name,
            "trust_score": result.routing.trust_score,
            "trust_band": result.routing.trust_band,
            "policy_state": result.routing.policy_state,
            "execution_decision": result.routing.execution_decision,
            "recommended_action": result.routing.recommended_action,
            "sandbox_first_required": result.routing.sandbox_first_required,
            "auto_execution_enabled": result.routing.auto_execution_enabled,
            "auto_execution_reason": result.routing.auto_execution_reason,
            "missing_evidence": list(result.routing.missing_evidence or []),
            "intelligence_summary": result.routing.intelligence_summary,
            "maturity_stage": result.routing.maturity_stage or result.routing.evidence_state,
            "evidence_state": result.routing.evidence_state,
            "eligible_for_auto": result.routing.eligible_for_auto,
            "times_attempted": result.routing.times_attempted,
            "times_passed": result.routing.times_passed,
            "last_validation_result": result.routing.last_validation_result,
            "last_rollback_result": result.routing.last_rollback_result,
            "sandbox_verified": result.routing.sandbox_verified,
            "real_target_verified": result.routing.real_target_verified,
            "rollback_verified": result.routing.rollback_verified,
            "rating_system": result.routing.rating_system,
            "rating_target": result.routing.rating_target,
            "rating_locked": result.routing.rating_locked,
            "content_policy_match": result.routing.content_policy_match,
            "content_policy_decision": result.routing.content_policy_decision,
            "required_rating_upgrade": result.routing.required_rating_upgrade,
            "requested_content_dimensions": dict(result.routing.requested_content_dimensions or {}),
            "content_policy_summary": result.routing.content_policy_summary,
            "queue_write_status": "confirmed" if result.created else "existing_task_reused",
        },
    }


def _format_task_acceptance_response(result: IntakeResult) -> str:
    if result.is_multi_step:
        lines = [
            "AI-E PLAN ACCEPTED",
            "",
            f"Request ID: {result.request_id}",
            f"Plan ID: {result.plan_id}",
            f"Requested Intent: {result.routing.requested_intent}",
            f"Resolved Intent: {result.routing.resolved_intent}",
            f"Requested Lane: {result.routing.requested_execution_lane}",
            f"Current Lane: {result.routing.execution_lane}",
            f"Downgrade: {_yes_no(result.routing.downgraded)}",
            f"Approval Required: {_yes_no(result.routing.approval_required)}",
            f"Mutation Capable: {_yes_no(result.routing.mutation_capable)}",
            f"Capability Matched: {result.routing.capability_id or 'none'}",
            f"Maturity: {result.routing.maturity_stage or result.routing.evidence_state or 'none'}",
            f"Trust Score: {result.routing.trust_score}",
            f"Trust Band: {result.routing.trust_band or 'none'}",
            f"Policy State: {result.routing.policy_state or 'none'}",
            f"Execution Decision: {result.routing.execution_decision or 'none'}",
            f"Recommended Action: {result.routing.recommended_action or 'none'}",
            f"Sandbox First: {_yes_no(result.routing.sandbox_first_required)}",
            f"Auto Execution: {_yes_no(result.routing.auto_execution_enabled)}",
            f"Eligible for Auto: {_yes_no(result.routing.eligible_for_auto)}",
            f"Sandbox Verified: {_yes_no(result.routing.sandbox_verified)}",
            f"Real Target Verified: {_yes_no(result.routing.real_target_verified)}",
            f"Rollback Verified: {_yes_no(result.routing.rollback_verified)}",
            f"Last Validation: {result.routing.last_validation_result or 'none'}",
            f"Last Rollback: {result.routing.last_rollback_result or 'none'}",
            f"Rating System: {result.routing.rating_system or 'none'}",
            f"Rating Target: {result.routing.rating_target or 'none'}",
            f"Rating Locked: {_yes_no(result.routing.rating_locked)}",
            f"Content Policy Match: {result.routing.content_policy_match or 'none'}",
            f"Content Policy Decision: {result.routing.content_policy_decision or 'none'}",
            f"Required Rating Upgrade: {result.routing.required_rating_upgrade or 'none'}",
            f"Requested Content Dimensions: {_format_content_dimensions(result.routing.requested_content_dimensions)}",
            f"Missing Evidence: {', '.join(result.routing.missing_evidence or []) or 'none'}",
            f"Auto Reason: {result.routing.auto_execution_reason or 'none'}",
            f"Content Policy Summary: {result.routing.content_policy_summary or 'none'}",
            f"Queue Write: {'confirmed' if result.created else 'existing task reused'}",
            f"Status: {result.queue_entry.get('status', 'pending')}",
            "Plan Steps:",
        ]
        if result.routing.downgraded and result.routing.downgrade_reason:
            lines.append(f"Downgrade Reason: {result.routing.downgrade_reason}")
        for index, title in enumerate(result.plan_step_titles, start=1):
            lines.append(f"{index}. {title}")
        lines.extend(
            [
                "",
                f"Task Graph Payload: {result.artifacts.task_graph_path}",
                f"Runtime Task Payloads: {', '.join(str(path) for path in result.artifacts.runtime_task_payload_paths)}",
                "Supervisor will process the plan automatically.",
                "",
                "Recommendation: Monitor plan progress with 'what plan did you generate', 'what step is running', or 'how many steps are left'.",
            ]
        )
        return "\n".join(lines)
    lines = [
        "AI-E TASK ACCEPTED",
        "",
        "Classification: TASK_REQUEST",
        f"Task ID: {result.task_id}",
        f"Request ID: {result.request_id}",
        f"Status: {result.queue_entry.get('status', 'pending')}",
        f"Task Type: {result.task_type}",
        f"Requested Intent: {result.routing.requested_intent}",
        f"Resolved Intent: {result.routing.resolved_intent}",
        f"Requested Lane: {result.routing.requested_execution_lane}",
        f"Execution Lane: {result.routing.execution_lane}",
        f"Downgrade: {_yes_no(result.routing.downgraded)}",
        f"Approval Required: {_yes_no(result.routing.approval_required)}",
        f"Mutation Capable: {_yes_no(result.routing.mutation_capable)}",
        f"Capability Matched: {result.routing.capability_id or 'none'}",
        f"Maturity: {result.routing.maturity_stage or result.routing.evidence_state or 'none'}",
        f"Trust Score: {result.routing.trust_score}",
        f"Trust Band: {result.routing.trust_band or 'none'}",
        f"Policy State: {result.routing.policy_state or 'none'}",
        f"Execution Decision: {result.routing.execution_decision or 'none'}",
        f"Recommended Action: {result.routing.recommended_action or 'none'}",
        f"Sandbox First: {_yes_no(result.routing.sandbox_first_required)}",
        f"Auto Execution: {_yes_no(result.routing.auto_execution_enabled)}",
        f"Eligible for Auto: {_yes_no(result.routing.eligible_for_auto)}",
        f"Sandbox Verified: {_yes_no(result.routing.sandbox_verified)}",
        f"Real Target Verified: {_yes_no(result.routing.real_target_verified)}",
        f"Rollback Verified: {_yes_no(result.routing.rollback_verified)}",
        f"Last Validation: {result.routing.last_validation_result or 'none'}",
        f"Last Rollback: {result.routing.last_rollback_result or 'none'}",
        f"Rating System: {result.routing.rating_system or 'none'}",
        f"Rating Target: {result.routing.rating_target or 'none'}",
        f"Rating Locked: {_yes_no(result.routing.rating_locked)}",
        f"Content Policy Match: {result.routing.content_policy_match or 'none'}",
        f"Content Policy Decision: {result.routing.content_policy_decision or 'none'}",
        f"Required Rating Upgrade: {result.routing.required_rating_upgrade or 'none'}",
        f"Requested Content Dimensions: {_format_content_dimensions(result.routing.requested_content_dimensions)}",
        f"Missing Evidence: {', '.join(result.routing.missing_evidence or []) or 'none'}",
        f"Auto Reason: {result.routing.auto_execution_reason or 'none'}",
        f"Content Policy Summary: {result.routing.content_policy_summary or 'none'}",
        f"Queue Write: {'confirmed' if result.created else 'existing task reused'}",
        f"Target Repo: {result.target_repo}",
        f"Runtime Task Payload: {result.artifacts.runtime_task_payload_path}",
        f"Request Payload: {result.artifacts.request_payload_path}",
        f"Task Graph Payload: {result.artifacts.task_graph_path}",
        "Supervisor will pick up the task automatically.",
        "",
        f"Recommendation: {'Monitor the queue for task start and completion.' if result.created else 'Task already existed in the queue; monitor current task state.'}",
    ]
    if result.routing.downgraded and result.routing.downgrade_reason:
        lines.insert(-4, f"Downgrade Reason: {result.routing.downgrade_reason}")
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_content_dimensions(payload: dict[str, object] | None) -> str:
    if not payload:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in payload.items())


def _wait_for_interactive_task_progress(supervisor: Supervisor, acceptance_details: dict[str, object]) -> None:
    task_ids = [str(item) for item in acceptance_details.get("task_ids", []) if str(item)]
    if not task_ids:
        task_id = str(acceptance_details.get("task_id") or "")
        if task_id:
            task_ids = [task_id]
    if not task_ids:
        return

    runtime_payload_paths = acceptance_details.get("runtime_task_payload_paths", [])
    max_delay_seconds = 0.0
    if isinstance(runtime_payload_paths, list) and runtime_payload_paths:
        first_payload = Path(str(runtime_payload_paths[0]))
        if first_payload.exists():
            try:
                payload = json.loads(first_payload.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            runtime_task = payload.get("runtime_task", {}) if isinstance(payload, dict) else {}
            if isinstance(runtime_task, dict):
                raw_delay = runtime_task.get("simulated_delay_seconds", 0.0)
                try:
                    max_delay_seconds = max(0.0, float(raw_delay or 0.0))
                except (TypeError, ValueError):
                    max_delay_seconds = 0.0

    timeout_seconds = max(0.25, float(supervisor.supervisor_config.poll_interval_seconds) + max_delay_seconds + 0.75)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        snapshot = supervisor.runtime_state.get_snapshot()
        if snapshot.current_task_id in task_ids:
            return
        if snapshot.last_started_task in task_ids:
            return
        if any(task_id in snapshot.tasks_completed for task_id in task_ids):
            return
        time.sleep(0.05)


def print_runtime_result(result: object) -> None:
    print(
        json.dumps(
            {
                "session_id": result.session_id,
                "stop_reason": result.stop_reason,
                "elapsed_time_seconds": result.elapsed_time_seconds,
                "tasks_attempted": result.tasks_attempted,
                "tasks_completed": result.tasks_completed,
                "queue_remaining": result.queue_remaining,
                "heartbeats_emitted": result.heartbeats_emitted,
                "state_path": str(result.state_path),
                "heartbeat_log_path": str(result.heartbeat_log_path),
            },
            indent=2,
        )
    )
    return None


def _install_interrupt_handlers(supervisor: Supervisor) -> dict[str, object]:
    triggered = threading.Event()
    previous_handlers: dict[int, object] = {}

    def _handle_interrupt(signum, _frame) -> None:
        if not triggered.is_set():
            print(f"SESSION INTERRUPTED BY OPERATOR signal={signum}")
        triggered.set()
        supervisor.request_stop(reason="operator_interrupt")

    for signal_name in ("SIGINT", "SIGBREAK"):
        sig = getattr(signal, signal_name, None)
        if sig is None:
            continue
        previous_handlers[int(sig)] = signal.getsignal(sig)
        signal.signal(sig, _handle_interrupt)

    return {"triggered": triggered, "previous_handlers": previous_handlers}


def _restore_interrupt_handlers(interrupt_state: dict[str, object]) -> None:
    previous_handlers = interrupt_state.get("previous_handlers", {})
    if not isinstance(previous_handlers, dict):
        return
    for signum, handler in previous_handlers.items():
        signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())