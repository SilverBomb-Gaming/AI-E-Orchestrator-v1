from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from .progress import format_progress_line
from .runtime_state import RuntimeState


@dataclass(frozen=True)
class ConversationResponse:
    title: str
    answer: str
    recommendation: str
    query_type: str
    payload: Dict[str, Any]

    def to_text(self) -> str:
        lines = [
            self.title,
            "",
            self.answer,
            "",
            f"Recommendation: {self.recommendation}",
        ]
        return "\n".join(lines)


class ConversationRouter:
    """Routes conversational status questions to runtime state answers."""

    CONTROL_COMMANDS = (
        "clear",
        "cls",
        "help",
        "show last acceptance",
        "last acceptance",
        "show last artifact",
        "last artifact",
        "pause polling",
        "resume polling",
        "get rating profile",
        "exit",
        "quit",
    )
    CONTROL_COMMAND_PREFIXES = (
        "set_rating_profile",
        "get_rating_profile",
        "set_rating_lock",
    )

    _STATUS_TOKENS = (
        "what plan did you generate",
        "show plan",
        "plan summary",
        "what step is running",
        "what step is next",
        "how many steps are left",
        "steps are left",
        "what task started",
        "last started task",
        "task started",
        "what started",
        "last completed task",
        "what completed",
        "what task completed",
        "show queue",
        "queue",
        "tasks left",
        "how many tasks are left",
        "what are you doing",
        "what task is running",
        "current task",
        "right now",
        "why are you idle",
        "what failed",
        "failed recently",
        "why did the last task fail",
        "what should i do next",
        "next",
        "recommend",
    )

    def __init__(self, runtime_state: RuntimeState) -> None:
        self.runtime_state = runtime_state

    def route(self, prompt: str) -> ConversationResponse:
        normalized = self._normalize(prompt)
        snapshot = self.runtime_state.get_snapshot()
        heartbeat_age = self.runtime_state.heartbeat_age_seconds(now=datetime.now(timezone.utc))

        if any(token in normalized for token in ("what plan did you generate", "show plan", "plan summary")):
            return self._plan_summary_response(snapshot, heartbeat_age)
        if "what step is running" in normalized:
            return self._plan_running_step_response(snapshot, heartbeat_age)
        if "what step is next" in normalized:
            return self._plan_next_step_response(snapshot, heartbeat_age)
        if any(token in normalized for token in ("how many steps are left", "steps are left")):
            return self._plan_steps_remaining_response(snapshot, heartbeat_age)
        if any(token in normalized for token in ("what task started", "last started task", "task started", "what started")):
            return self._last_started_response(snapshot, heartbeat_age)
        if any(token in normalized for token in ("last completed task", "what completed", "what task completed")):
            return self._last_completed_response(snapshot, heartbeat_age)
        if any(token in normalized for token in ("show queue", "queue", "tasks left", "how many tasks are left")):
            return self._queue_response(snapshot, heartbeat_age)
        if any(token in normalized for token in ("what are you doing", "what task is running", "current task", "right now")):
            return self._current_task_response(snapshot, heartbeat_age)
        if "why are you idle" in normalized:
            return self._idle_response(snapshot, heartbeat_age)
        if any(token in normalized for token in ("what failed", "failed recently", "why did the last task fail")):
            return self._failure_response(snapshot, heartbeat_age)
        if any(token in normalized for token in ("what should i do next", "next", "recommend")):
            return self._recommendation_response(snapshot, heartbeat_age)
        return self._general_status_response(snapshot, heartbeat_age)

    def is_status_query(self, prompt: str) -> bool:
        normalized = self._normalize(prompt)
        if not normalized:
            return False
        return any(token in normalized for token in self._STATUS_TOKENS) or normalized.endswith("?")

    def is_control_command(self, prompt: str) -> bool:
        normalized = self._normalize(prompt)
        return normalized in self.CONTROL_COMMANDS or any(normalized.startswith(prefix) for prefix in self.CONTROL_COMMAND_PREFIXES)

    def classify_prompt(self, prompt: str, *, task_request_classifier: Any | None = None) -> str:
        if self.is_control_command(prompt):
            return "CONTROL_COMMAND"
        if self.is_status_query(prompt):
            return "STATUS_QUERY"
        if task_request_classifier is not None and task_request_classifier(prompt) == "task_request":
            return "TASK_REQUEST"
        return "UNKNOWN"

    def _general_status_response(self, snapshot, heartbeat_age):
        answer = self._status_report(snapshot, heartbeat_age)
        recommendation = self._recommendation_text(snapshot)
        return ConversationResponse(
            title="AI-E STATUS REPORT",
            answer=answer,
            recommendation=recommendation,
            query_type="general_status",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _current_task_response(self, snapshot, heartbeat_age):
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Current Task: {snapshot.current_task_id or 'idle'}",
            f"Queue Remaining: {snapshot.queue_remaining}",
            f"Last Started Task: {snapshot.last_started_task or 'none'}",
            f"Last Completed Task: {snapshot.last_completed_task or 'none'}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E STATUS REPORT",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="current_task",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _queue_response(self, snapshot, heartbeat_age):
        queue_line = f"Queue Remaining: {snapshot.queue_remaining}"
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Current Task: {snapshot.current_task_id or 'idle'}",
            queue_line,
            f"Queue Contents: {self._queue_contents_text(snapshot.queue_tasks)}",
            f"Last Started Task: {snapshot.last_started_task or 'none'}",
            f"Last Completed Task: {snapshot.last_completed_task or 'none'}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E STATUS REPORT",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="queue",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _last_started_response(self, snapshot, heartbeat_age):
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Current Task: {snapshot.current_task_id or 'idle'}",
            f"Last Started Task: {snapshot.last_started_task or 'none'}",
            f"Queue Remaining: {snapshot.queue_remaining}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E STATUS REPORT",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="last_started_task",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _last_completed_response(self, snapshot, heartbeat_age):
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Current Task: {snapshot.current_task_id or 'idle'}",
            f"Last Completed Task: {snapshot.last_completed_task or 'none'}",
            f"Queue Remaining: {snapshot.queue_remaining}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E STATUS REPORT",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="last_completed_task",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _idle_response(self, snapshot, heartbeat_age):
        if snapshot.current_task_id:
            reason = f"AI-E is not idle; it is currently running {snapshot.current_task_id}."
        elif snapshot.work_state == "queue_empty" and snapshot.budget_mode == "terminating":
            reason = (
                "Session alive, queue empty, no active work. "
                f"Entering termination path after idle grace window "
                f"({snapshot.idle_poll_count}/{snapshot.idle_timeout_poll_limit} idle polls, "
                f"{snapshot.idle_duration_seconds}/{snapshot.idle_timeout_seconds} seconds)."
            )
        elif snapshot.queue_remaining == 0:
            reason = "Currently idle because there are no pending queue tasks. The supervisor is healthy and still polling for new work."
        else:
            reason = "Currently idle between polls; pending work exists and will be picked up on the next scheduler cycle."
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Idle Analysis: {reason}",
            f"Session State: {snapshot.session_state}",
            f"Work State: {snapshot.work_state}",
            f"Budget Mode: {snapshot.budget_mode}",
            f"Queue Remaining: {snapshot.queue_remaining}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E STATUS REPORT",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="idle_reason",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _failure_response(self, snapshot, heartbeat_age):
        failed = snapshot.last_failed_task
        if failed is None:
            detail = "No failed tasks are recorded in the current session."
        else:
            detail = (
                f"Last Failed Task: {failed.get('task_id', 'unknown')}\n"
                f"Failure Note: {failed.get('note', 'No detail recorded.')}\n"
                f"Failure Timestamp: {failed.get('timestamp', 'unknown')}"
            )
        lines = [
            f"Session ID: {snapshot.session_id}",
            detail,
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E STATUS REPORT",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="failure",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _recommendation_response(self, snapshot, heartbeat_age):
        answer = self._status_report(snapshot, heartbeat_age)
        return ConversationResponse(
            title="AI-E STATUS REPORT",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="recommendation",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _plan_summary_response(self, snapshot, heartbeat_age):
        summary = snapshot.last_generated_plan_summary or "No plan has been generated in this session yet."
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Current Plan ID: {snapshot.current_plan_id or 'none'}",
            f"Plan Summary:\n{summary}",
            f"Steps Remaining: {snapshot.steps_remaining}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E PLAN STATUS",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="plan_summary",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _plan_running_step_response(self, snapshot, heartbeat_age):
        running_step = snapshot.current_plan_step or "none"
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Current Plan ID: {snapshot.current_plan_id or 'none'}",
            f"Current Plan Step: {running_step}",
            f"Steps Remaining: {snapshot.steps_remaining}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E PLAN STATUS",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="plan_running_step",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _plan_next_step_response(self, snapshot, heartbeat_age):
        next_step = snapshot.next_plan_step or "none"
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Current Plan ID: {snapshot.current_plan_id or 'none'}",
            f"Next Plan Step: {next_step}",
            f"Steps Remaining: {snapshot.steps_remaining}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E PLAN STATUS",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="plan_next_step",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _plan_steps_remaining_response(self, snapshot, heartbeat_age):
        lines = [
            f"Session ID: {snapshot.session_id}",
            f"Current Plan ID: {snapshot.current_plan_id or 'none'}",
            f"Steps Remaining: {snapshot.steps_remaining}",
            f"Current Plan Step: {snapshot.current_plan_step or 'none'}",
            f"Next Plan Step: {snapshot.next_plan_step or 'none'}",
        ]
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        answer = "\n".join(lines)
        return ConversationResponse(
            title="AI-E PLAN STATUS",
            answer=answer,
            recommendation=self._recommendation_text(snapshot),
            query_type="plan_steps_remaining",
            payload={"snapshot": snapshot.to_payload(), "heartbeat_age_seconds": heartbeat_age},
        )

    def _status_report(self, snapshot, heartbeat_age):
        lines: List[str] = [
            f"Session ID: {snapshot.session_id}",
            f"Session State: {snapshot.session_state}",
            f"Work State: {snapshot.work_state}",
            f"Budget Mode: {snapshot.budget_mode}",
            f"Current Task: {snapshot.current_task_id or 'idle'}",
            f"Current Plan ID: {snapshot.current_plan_id or 'none'}",
            f"Current Plan Step: {snapshot.current_plan_step or 'none'}",
            f"Steps Remaining: {snapshot.steps_remaining}",
            f"Queue Remaining: {snapshot.queue_remaining}",
            f"Queue Contents: {self._queue_contents_text(snapshot.queue_tasks)}",
            f"Last Started Task: {snapshot.last_started_task or 'none'}",
            f"Last Completed Task: {snapshot.last_completed_task or 'none'}",
        ]
        if snapshot.last_failed_task is not None:
            lines.append(f"Last Failed Task: {snapshot.last_failed_task.get('task_id', 'unknown')}")
        lines.extend(self._shared_status_lines(snapshot, heartbeat_age))
        return "\n".join(lines)

    def _shared_status_lines(self, snapshot, heartbeat_age) -> List[str]:
        lines = [
            f"Rating System: {snapshot.rating_system or 'none'}",
            f"Rating Target: {snapshot.rating_target or 'none'}",
            f"Rating Locked: {'yes' if snapshot.rating_locked else 'no'}",
            format_progress_line(snapshot.to_payload()),
        ]
        if snapshot.waiting_reason:
            lines.append(f"Waiting Reason: {snapshot.waiting_reason}")
        if snapshot.blocked_reason:
            lines.append(f"Blocked Reason: {snapshot.blocked_reason}")
        lines.append(f"Heartbeat Age: {self._heartbeat_text(heartbeat_age)}")
        return lines

    def _recommendation_text(self, snapshot) -> str:
        if snapshot.current_task_id:
            return "Queue contains active work. No operator action required."
        if any(task.get("status") == "needs_approval" for task in snapshot.queue_tasks):
            return "A queued mutation task is awaiting operator approval before execution can begin."
        if snapshot.work_state == "queue_empty" and snapshot.budget_mode == "terminating":
            return "Queue is empty and the idle grace window is active. Inject a new task immediately if the session should stay alive."
        if snapshot.current_plan_id and snapshot.steps_remaining > 0:
            return "A plan is active. Wait for the next scheduler cycle unless activation is blocked."
        if snapshot.queue_remaining > 0:
            return "Pending tasks exist. Wait for the next scheduler cycle unless activation is blocked."
        if snapshot.last_failed_task is not None:
            return "Review the most recent failure details and decide whether to inject follow-up work or operator guidance."
        return "Queue is empty. Inject a new task through intake if more work should begin."

    def _heartbeat_text(self, heartbeat_age: float | None) -> str:
        if heartbeat_age is None:
            return "unknown"
        if heartbeat_age.is_integer():
            return f"{int(heartbeat_age)} seconds"
        return f"{heartbeat_age} seconds"

    def _normalize(self, prompt: str) -> str:
        return " ".join(str(prompt or "").strip().lower().split())

    def _queue_contents_text(self, queue_tasks: List[Dict[str, Any]]) -> str:
        if not queue_tasks:
            return "none"
        return "; ".join(
            f"{task['task_id']} ({task['status']}, priority {task['priority']})"
            for task in queue_tasks
        )


__all__ = ["ConversationResponse", "ConversationRouter"]