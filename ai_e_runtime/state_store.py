from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .progress import phase_payload
from .time_utils import get_current_timestamp
from orchestrator.utils import ensure_dir, read_json, write_json


class StateStore:
    """Persists long-running supervisor session state under runs/<session_id>."""

    def __init__(self, runs_dir: Path, session_id: str) -> None:
        self.runs_dir = Path(runs_dir)
        self.session_id = session_id
        self.session_dir = ensure_dir(self.runs_dir / session_id)
        self.state_path = self.session_dir / "session_state.json"

    def start_session(
        self,
        *,
        session_limit_seconds: int,
        heartbeat_interval_seconds: int,
        resume: bool,
    ) -> Dict[str, Any]:
        if resume and self.state_path.exists():
            state = self.load()
            state["status"] = "running"
            state["resumed"] = True
            state["updated_at"] = self._iso_now()
            self.save(state)
            return state

        state = {
            "session_id": self.session_id,
            "status": "running",
            "resumed": False,
            "session_limit_seconds": int(session_limit_seconds),
            "heartbeat_interval_seconds": int(heartbeat_interval_seconds),
            "started_at": self._iso_now(),
            "updated_at": self._iso_now(),
            "finished_at": None,
            "elapsed_time_seconds": 0.0,
            "current_task": None,
            "last_started_task": None,
            "last_completed_task": None,
            "loop_iterations": 0,
            "heartbeats_emitted": 0,
            "queue_remaining": 0,
            "tasks_attempted": [],
            "tasks_completed": [],
            "tasks_failed": [],
            "artifacts_generated": [],
            "blockers_detected": [],
            "last_heartbeat_timestamp": None,
            "stop_reason": None,
            "polling_enabled": True,
            "idle_poll_count": 0,
            "idle_duration_seconds": 0.0,
            "idle_timeout_seconds": 0,
            "idle_timeout_poll_limit": 0,
            "current_plan_id": None,
            "current_plan_step": None,
            "last_generated_plan_summary": None,
            "last_generated_plan_steps": [],
        }
        state.update(phase_payload("intake", waiting_reason="Waiting for new task intake."))
        self.save(state)
        return state

    def load(self) -> Dict[str, Any]:
        state = read_json(self.state_path, default={})
        state.setdefault("session_id", self.session_id)
        state.setdefault("tasks_attempted", [])
        state.setdefault("tasks_completed", [])
        state.setdefault("tasks_failed", [])
        state.setdefault("artifacts_generated", [])
        state.setdefault("blockers_detected", [])
        state.setdefault("elapsed_time_seconds", 0.0)
        state.setdefault("heartbeats_emitted", 0)
        state.setdefault("loop_iterations", 0)
        state.setdefault("queue_remaining", 0)
        state.setdefault("last_heartbeat_timestamp", None)
        state.setdefault("current_task", None)
        state.setdefault("last_started_task", None)
        state.setdefault("last_completed_task", None)
        state.setdefault("polling_enabled", True)
        state.setdefault("idle_poll_count", 0)
        state.setdefault("idle_duration_seconds", 0.0)
        state.setdefault("idle_timeout_seconds", 0)
        state.setdefault("idle_timeout_poll_limit", 0)
        state.setdefault("current_plan_id", None)
        state.setdefault("current_plan_step", None)
        state.setdefault("last_generated_plan_summary", None)
        state.setdefault("last_generated_plan_steps", [])
        state.setdefault("session_phase", "intake")
        state.setdefault("phase_index", 1)
        state.setdefault("phase_total", 7)
        state.setdefault("phase_label", "Intake")
        state.setdefault("progress_mode", "phase_based")
        state.setdefault("progress_percent", None)
        state.setdefault("waiting_reason", "Waiting for new task intake.")
        state.setdefault("blocked_reason", None)
        state.setdefault("timestamp", state.get("updated_at") or state.get("started_at"))
        return state

    def save(self, state: Dict[str, Any]) -> None:
        if self.state_path.exists():
            persisted = read_json(self.state_path, default={})
            if persisted.get("current_plan_id") and not state.get("current_plan_id"):
                state["current_plan_id"] = persisted.get("current_plan_id")
            if persisted.get("last_generated_plan_summary") and not state.get("last_generated_plan_summary"):
                state["last_generated_plan_summary"] = persisted.get("last_generated_plan_summary")
            if persisted.get("last_generated_plan_steps") and not state.get("last_generated_plan_steps"):
                state["last_generated_plan_steps"] = list(persisted.get("last_generated_plan_steps", []))
        state["updated_at"] = self._iso_now()
        state["timestamp"] = state["updated_at"]
        write_json(self.state_path, state)

    def update_runtime(
        self,
        state: Dict[str, Any],
        *,
        elapsed_time_seconds: float,
        current_task: str | None,
        queue_remaining: int,
    ) -> Dict[str, Any]:
        state["elapsed_time_seconds"] = round(float(elapsed_time_seconds), 3)
        state["current_task"] = current_task
        state["queue_remaining"] = int(queue_remaining)
        state["loop_iterations"] = int(state.get("loop_iterations", 0)) + 1
        self.save(state)
        return state

    def record_task_started(
        self,
        state: Dict[str, Any],
        *,
        task_id: str,
        elapsed_time_seconds: float,
        queue_remaining: int,
        plan_id: str | None = None,
        plan_step_title: str | None = None,
    ) -> Dict[str, Any]:
        state["elapsed_time_seconds"] = round(float(elapsed_time_seconds), 3)
        state["current_task"] = task_id
        state["last_started_task"] = task_id
        state["queue_remaining"] = int(queue_remaining)
        if plan_id is not None:
            state["current_plan_id"] = plan_id
        state["current_plan_step"] = plan_step_title
        state["loop_iterations"] = int(state.get("loop_iterations", 0)) + 1
        self.save(state)
        return state

    def record_task_result(
        self,
        state: Dict[str, Any],
        *,
        task_id: str,
        final_status: str,
        artifact_paths: List[str],
        note: str,
    ) -> Dict[str, Any]:
        attempted = list(state.get("tasks_attempted", []))
        attempted.append(
            {
                "task_id": task_id,
                "final_status": final_status,
                "note": note,
                "timestamp": self._iso_now(),
            }
        )
        state["tasks_attempted"] = attempted
        state["current_task"] = None
        state["current_plan_step"] = None

        if final_status == "completed":
            completed = list(state.get("tasks_completed", []))
            if task_id not in completed:
                completed.append(task_id)
            state["tasks_completed"] = completed
            state["last_completed_task"] = task_id
        elif final_status == "blocked":
            blockers = list(state.get("blockers_detected", []))
            failure_record = {"task_id": task_id, "note": note, "timestamp": self._iso_now()}
            blockers.append(failure_record)
            state["blockers_detected"] = blockers
            failed = list(state.get("tasks_failed", []))
            failed.append(failure_record)
            state["tasks_failed"] = failed

        artifacts = list(state.get("artifacts_generated", []))
        artifacts.extend(artifact_paths)
        state["artifacts_generated"] = artifacts
        self.save(state)
        return state

    def record_heartbeat(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["heartbeats_emitted"] = int(state.get("heartbeats_emitted", 0)) + 1
        state["last_heartbeat_timestamp"] = self._iso_now()
        self.save(state)
        return state

    def set_polling_enabled(self, state: Dict[str, Any], enabled: bool) -> Dict[str, Any]:
        state["polling_enabled"] = bool(enabled)
        self.save(state)
        return state

    def register_generated_plan(
        self,
        state: Dict[str, Any],
        *,
        plan_id: str,
        plan_summary: str,
        plan_steps: List[str],
    ) -> Dict[str, Any]:
        state["current_plan_id"] = plan_id
        state["current_plan_step"] = None
        state["last_generated_plan_summary"] = plan_summary
        state["last_generated_plan_steps"] = list(plan_steps)
        self.save(state)
        return state

    def finalize(
        self,
        state: Dict[str, Any],
        *,
        stop_reason: str,
        elapsed_time_seconds: float,
        queue_remaining: int,
    ) -> Dict[str, Any]:
        state["status"] = "completed"
        state["stop_reason"] = stop_reason
        state["finished_at"] = self._iso_now()
        state["elapsed_time_seconds"] = round(float(elapsed_time_seconds), 3)
        state["queue_remaining"] = int(queue_remaining)
        state["current_task"] = None
        state["current_plan_step"] = None
        state.update(phase_payload("complete"))
        self.save(state)
        return state

    def update_progress(
        self,
        state: Dict[str, Any],
        *,
        session_phase: str,
        waiting_reason: str | None = None,
        blocked_reason: str | None = None,
        progress_percent: int | None = None,
    ) -> Dict[str, Any]:
        state.update(
            phase_payload(
                session_phase,
                waiting_reason=waiting_reason,
                blocked_reason=blocked_reason,
                progress_percent=progress_percent,
            )
        )
        self.save(state)
        return state

    def _iso_now(self) -> str:
        return get_current_timestamp()