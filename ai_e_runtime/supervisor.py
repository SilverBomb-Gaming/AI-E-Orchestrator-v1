from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from time import monotonic, sleep
from typing import Any, Callable, Dict

from orchestrator.config import OrchestratorConfig
from orchestrator.utils import ensure_dir

from .agent_router import AgentRouter
from .artifact_writer import ArtifactWriter
from .heartbeat import HeartbeatEmitter
from .runtime_state import RuntimeState, RuntimeStateSnapshot
from .scheduler import Scheduler
from .state_store import StateStore


@dataclass(frozen=True)
class SupervisorConfig:
    session_limit_seconds: int
    heartbeat_interval_seconds: int = 300
    max_retries: int = 3
    poll_interval_seconds: int = 5
    idle_timeout_seconds: int = 30
    idle_timeout_poll_limit: int = 3
    session_id: str | None = None
    resume: bool = False
    stop_when_queue_empty: bool = False


@dataclass(frozen=True)
class SupervisorRunResult:
    session_id: str
    session_dir: Path
    state_path: Path
    heartbeat_log_path: Path
    stop_reason: str
    elapsed_time_seconds: float
    tasks_attempted: int
    tasks_completed: int
    queue_remaining: int
    heartbeats_emitted: int


class Supervisor:
    """Persistent runtime loop for continuous AI-E background sessions."""

    def __init__(
        self,
        orchestrator_config: OrchestratorConfig,
        supervisor_config: SupervisorConfig,
        *,
        agent_router: AgentRouter | None = None,
        scheduler: Scheduler | None = None,
        time_source: Callable[[], datetime] | None = None,
        monotonic_source: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.orchestrator_config = orchestrator_config
        self.supervisor_config = supervisor_config
        self.time_source = time_source or (lambda: datetime.now(timezone.utc))
        self.monotonic_source = monotonic_source or monotonic
        self.sleep_fn = sleep_fn or sleep
        self.session_id = supervisor_config.session_id or f"session_{self._timestamp_slug()}"
        self.scheduler = scheduler or Scheduler(
            orchestrator_config.queue_path,
            max_retries=supervisor_config.max_retries,
        )
        self.state_store = StateStore(orchestrator_config.runs_dir, self.session_id)
        self.heartbeat = HeartbeatEmitter(
            orchestrator_config.root_dir / "logs" / "session_heartbeat.log",
            interval_seconds=supervisor_config.heartbeat_interval_seconds,
            time_source=self.time_source,
        )
        self.runtime_state = RuntimeState(orchestrator_config, self.session_id, scheduler=self.scheduler)
        self.agent_router = agent_router or AgentRouter()
        self.artifact_writer = ArtifactWriter(orchestrator_config.runs_dir, self.session_id)
        self._queue_idle_announced = False
        self._idle_started_monotonic: float | None = None
        self._idle_poll_count = 0
        self._polling_enabled = True
        self._polling_pause_announced = False
        self._control_lock = Lock()
        self._stop_requested = False
        self._stop_reason_override: str | None = None

    def run(self) -> SupervisorRunResult:
        ensure_dir(self.orchestrator_config.runs_dir)
        self._status(
            f"SESSION STARTED session_id={self.session_id} session_limit_seconds={self.supervisor_config.session_limit_seconds}"
        )
        state = self.state_store.start_session(
            session_limit_seconds=self.supervisor_config.session_limit_seconds,
            heartbeat_interval_seconds=self.supervisor_config.heartbeat_interval_seconds,
            resume=self.supervisor_config.resume,
        )
        self.runtime_state.write_snapshot()
        if self.supervisor_config.resume:
            self.scheduler.recover_running_tasks(self.session_id)

        self._reset_idle_tracking(state)

        base_elapsed_seconds = float(state.get("elapsed_time_seconds", 0.0))
        session_started_monotonic = self.monotonic_source()
        self._emit_heartbeat(state, force=True)
        stop_reason = "time_limit_reached"

        while True:
            elapsed_seconds = base_elapsed_seconds + (self.monotonic_source() - session_started_monotonic)
            if self.is_stop_requested():
                stop_reason = self.get_requested_stop_reason() or "operator_exit"
                break
            if elapsed_seconds >= self.supervisor_config.session_limit_seconds:
                stop_reason = "time_limit_reached"
                break

            if not self.is_polling_enabled():
                self._reset_idle_tracking(state)
                queue_remaining = self.scheduler.remaining_count()
                state = self._sync_control_state(state)
                state = self.state_store.update_runtime(
                    state,
                    elapsed_time_seconds=elapsed_seconds,
                    current_task=None,
                    queue_remaining=queue_remaining,
                )
                if not self._polling_pause_announced:
                    self._status(
                        f"QUEUE POLLING PAUSED session_id={self.session_id} queue_remaining={queue_remaining}"
                    )
                    self._polling_pause_announced = True
                self._emit_heartbeat(state)
                self.sleep_fn(self.supervisor_config.poll_interval_seconds)
                continue

            self._polling_pause_announced = False

            next_task = self.scheduler.get_next_task()
            queue_remaining = self.scheduler.remaining_count()
            if next_task is None:
                awaiting_approval = any(
                    str(task.get("status", "pending")).lower() == "needs_approval"
                    for task in self.scheduler.all_tasks()
                )
                state = self._record_idle_runtime(
                    state,
                    elapsed_time_seconds=elapsed_seconds,
                    queue_remaining=queue_remaining,
                )
                if not self._queue_idle_announced:
                    status_text = "QUEUE WAITING FOR APPROVAL" if awaiting_approval else "QUEUE EMPTY / WAITING FOR TASKS"
                    self._status(f"{status_text} session_id={self.session_id} queue_remaining={queue_remaining}")
                    self._queue_idle_announced = True
                self._emit_heartbeat(state)
                if self.supervisor_config.stop_when_queue_empty and queue_remaining == 0:
                    stop_reason = "queue_empty"
                    break
                if self._should_terminate_for_idle(queue_remaining=queue_remaining):
                    stop_reason = "queue_empty_idle_timeout"
                    self._status(
                        "QUEUE EMPTY IDLE TIMEOUT "
                        f"session_id={self.session_id} queue_remaining={queue_remaining} "
                        f"idle_seconds={round(float(state.get('idle_duration_seconds', 0.0)), 3)} "
                        f"idle_polls={int(state.get('idle_poll_count', 0))}"
                    )
                    break
                self.sleep_fn(self.supervisor_config.poll_interval_seconds)
                continue

            task_id = str(next_task.get("task_id") or next_task.get("id"))
            if self._queue_idle_announced:
                self._queue_idle_announced = False
            self._reset_idle_tracking(state)
            self._status(f"TASK ACCEPTED task_id={task_id} status={next_task.get('status', 'pending')}")
            payload_path = self._resolve_task_payload_path(next_task)
            if payload_path is None or not payload_path.exists():
                reason = "Task missing contract or payload file; activation denied."
                self.scheduler.mark_blocked(task_id, session_id=self.session_id, reason=reason, result={"status": "blocked"})
                state = self.state_store.update_runtime(
                    state,
                    elapsed_time_seconds=elapsed_seconds,
                    current_task=task_id,
                    queue_remaining=self.scheduler.remaining_count(),
                )
                state = self.state_store.record_task_result(
                    state,
                    task_id=task_id,
                    final_status="blocked",
                    artifact_paths=[],
                    note=reason,
                )
                self.runtime_state.write_snapshot()
                self._status(f"TASK BLOCKED task_id={task_id} reason={reason}")
                self._emit_heartbeat(state)
                continue

            next_task = self._merge_task_payload(next_task, payload_path)
            running_task = self.scheduler.mark_running(task_id, session_id=self.session_id)
            running_task = self._merge_task_payload(running_task, payload_path)
            state = self._sync_control_state(state)
            state = self.state_store.record_task_started(
                state,
                elapsed_time_seconds=elapsed_seconds,
                queue_remaining=queue_remaining,
                task_id=task_id,
                plan_id=running_task.get("plan_id"),
                plan_step_title=running_task.get("plan_step_title") or running_task.get("title"),
            )
            self.runtime_state.write_snapshot()

            self._status(f"TASK STARTED task_id={task_id} agent_type={running_task.get('agent_type', 'copilot_coder_agent')}")

            result = self.agent_router.run(running_task)
            validation = self.agent_router.validate(result, task=running_task)
            artifact_paths = self.artifact_writer.store(task=running_task, result=result, validation=validation)

            queue_action = validation.get("queue_action", "complete")
            note = str(validation.get("note") or result.get("summary") or "Supervisor processed task.")
            if queue_action == "complete":
                self.scheduler.mark_completed(task_id, session_id=self.session_id, result=result)
                final_status = "completed"
            elif queue_action == "retry":
                _, should_retry = self.scheduler.requeue_failed(
                    task_id,
                    session_id=self.session_id,
                    reason=note,
                    result=result,
                )
                final_status = "retry_scheduled" if should_retry else "blocked"
            else:
                self.scheduler.mark_blocked(task_id, session_id=self.session_id, reason=note, result=result)
                final_status = "blocked"

            state = self._sync_control_state(state)
            state = self.state_store.update_runtime(
                state,
                elapsed_time_seconds=base_elapsed_seconds + (self.monotonic_source() - session_started_monotonic),
                current_task=None,
                queue_remaining=self.scheduler.remaining_count(),
            )

            state = self.state_store.record_task_result(
                state,
                task_id=task_id,
                final_status=final_status,
                artifact_paths=artifact_paths,
                note=note,
            )
            self.runtime_state.write_snapshot()
            terminal_status = "TASK RETRY" if final_status == "retry_scheduled" else f"TASK {final_status.upper()}"
            self._status(f"{terminal_status} task_id={task_id} note={note}")
            self._emit_heartbeat(state)

        final_elapsed_seconds = base_elapsed_seconds + (self.monotonic_source() - session_started_monotonic)
        final_queue_remaining = self.scheduler.remaining_count()
        state = self._sync_control_state(state)
        state = self.state_store.finalize(
            state,
            stop_reason=stop_reason,
            elapsed_time_seconds=final_elapsed_seconds,
            queue_remaining=final_queue_remaining,
        )
        self.runtime_state.write_snapshot()
        self._emit_heartbeat(state, force=True)
        self.artifact_writer.write_session_summary(
            {
                "session_id": self.session_id,
                "stop_reason": stop_reason,
                "elapsed_time_seconds": round(final_elapsed_seconds, 3),
                "tasks_attempted": len(state.get("tasks_attempted", [])),
                "tasks_completed": len(state.get("tasks_completed", [])),
                "queue_remaining": final_queue_remaining,
                "heartbeats_emitted": state.get("heartbeats_emitted", 0),
            }
        )
        self._status(
            f"SESSION STOPPED session_id={self.session_id} stop_reason={stop_reason} queue_remaining={final_queue_remaining}"
        )

        return SupervisorRunResult(
            session_id=self.session_id,
            session_dir=self.state_store.session_dir,
            state_path=self.state_store.state_path,
            heartbeat_log_path=self.heartbeat.log_path,
            stop_reason=stop_reason,
            elapsed_time_seconds=round(final_elapsed_seconds, 3),
            tasks_attempted=len(state.get("tasks_attempted", [])),
            tasks_completed=len(state.get("tasks_completed", [])),
            queue_remaining=final_queue_remaining,
            heartbeats_emitted=int(state.get("heartbeats_emitted", 0)),
        )

    def get_runtime_state(self) -> RuntimeStateSnapshot:
        return self.runtime_state.get_snapshot()

    def pause_polling(self) -> bool:
        with self._control_lock:
            changed = self._polling_enabled
            self._polling_enabled = False
            state = self.state_store.load()
            self.state_store.set_polling_enabled(state, False)
            self.runtime_state.write_snapshot()
            return changed

    def resume_polling(self) -> bool:
        with self._control_lock:
            changed = not self._polling_enabled
            self._polling_enabled = True
            state = self.state_store.load()
            self.state_store.set_polling_enabled(state, True)
            self.runtime_state.write_snapshot()
            return changed

    def is_polling_enabled(self) -> bool:
        with self._control_lock:
            return self._polling_enabled

    def request_stop(self, reason: str = "operator_exit") -> None:
        with self._control_lock:
            self._stop_requested = True
            self._stop_reason_override = reason

    def is_stop_requested(self) -> bool:
        with self._control_lock:
            return self._stop_requested

    def get_requested_stop_reason(self) -> str | None:
        with self._control_lock:
            return self._stop_reason_override

    def _emit_heartbeat(self, state: Dict[str, Any], *, force: bool = False) -> None:
        state = self._sync_control_state(state)
        snapshot = self.runtime_state.get_snapshot()
        payload = self.heartbeat.emit(
            session_elapsed_time=float(state.get("elapsed_time_seconds", 0.0)),
            current_task=snapshot.current_task_id,
            queue_remaining=int(snapshot.queue_remaining),
            session_id=self.session_id,
            force=force,
        )
        if payload is not None:
            self.runtime_state.write_snapshot()
            self._status(
                f"SESSION HEARTBEAT session_id={self.session_id} elapsed={round(float(state.get('elapsed_time_seconds', 0.0)), 3)} current_task={snapshot.current_task_id or 'idle'} queue_remaining={int(snapshot.queue_remaining)}"
            )
            self.state_store.record_heartbeat(state)
            self.runtime_state.write_snapshot()

    def _sync_control_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["polling_enabled"] = self.is_polling_enabled()
        state.setdefault("idle_timeout_seconds", int(self.supervisor_config.idle_timeout_seconds))
        state.setdefault("idle_timeout_poll_limit", int(self.supervisor_config.idle_timeout_poll_limit))
        return state

    def _record_idle_runtime(
        self,
        state: Dict[str, Any],
        *,
        elapsed_time_seconds: float,
        queue_remaining: int,
    ) -> Dict[str, Any]:
        if self._idle_started_monotonic is None:
            self._idle_started_monotonic = self.monotonic_source()
        self._idle_poll_count += 1
        state = self._sync_control_state(state)
        state["idle_poll_count"] = self._idle_poll_count
        state["idle_duration_seconds"] = round(self.monotonic_source() - self._idle_started_monotonic, 3)
        state["idle_timeout_seconds"] = int(self.supervisor_config.idle_timeout_seconds)
        state["idle_timeout_poll_limit"] = int(self.supervisor_config.idle_timeout_poll_limit)
        return self.state_store.update_runtime(
            state,
            elapsed_time_seconds=elapsed_time_seconds,
            current_task=None,
            queue_remaining=queue_remaining,
        )

    def _reset_idle_tracking(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self._idle_started_monotonic = None
        self._idle_poll_count = 0
        state["idle_poll_count"] = 0
        state["idle_duration_seconds"] = 0.0
        state["idle_timeout_seconds"] = int(self.supervisor_config.idle_timeout_seconds)
        state["idle_timeout_poll_limit"] = int(self.supervisor_config.idle_timeout_poll_limit)
        return state

    def _should_terminate_for_idle(self, *, queue_remaining: int) -> bool:
        if queue_remaining != 0:
            return False
        timeout_seconds = int(self.supervisor_config.idle_timeout_seconds)
        poll_limit = int(self.supervisor_config.idle_timeout_poll_limit)
        idle_duration = 0.0
        if self._idle_started_monotonic is not None:
            idle_duration = self.monotonic_source() - self._idle_started_monotonic
        timeout_reached = timeout_seconds > 0 and idle_duration >= float(timeout_seconds)
        poll_limit_reached = poll_limit > 0 and self._idle_poll_count >= poll_limit
        return timeout_reached or poll_limit_reached

    def _timestamp_slug(self) -> str:
        return self.time_source().strftime("%Y%m%d_%H%M%S")

    def _resolve_task_payload_path(self, task: Dict[str, Any]) -> Path | None:
        for key in ("contract_path", "payload_path", "request_payload_path"):
            value = task.get(key)
            if not value:
                continue
            candidate = Path(str(value))
            if not candidate.is_absolute():
                candidate = (self.orchestrator_config.root_dir / candidate).resolve()
            return candidate
        return None

    def _merge_task_payload(self, task: Dict[str, Any], payload_path: Path) -> Dict[str, Any]:
        merged = dict(task)
        if payload_path.suffix.lower() != ".json":
            return merged
        try:
            raw = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return merged
        payload = raw.get("runtime_task") if isinstance(raw, dict) else None
        if not isinstance(payload, dict):
            return merged
        for key, value in payload.items():
            merged.setdefault(key, value)
        return merged

    def _status(self, message: str) -> None:
        print(message)