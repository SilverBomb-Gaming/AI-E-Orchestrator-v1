from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

from orchestrator.config import OrchestratorConfig
from orchestrator.utils import write_json

from .content_policy import load_profile
from .scheduler import Scheduler
from .state_store import StateStore


@dataclass(frozen=True)
class RuntimeStateSnapshot:
    session_id: str
    session_start_time: str
    session_elapsed_seconds: float
    session_state: str
    work_state: str
    budget_mode: str
    current_task_id: str | None
    last_started_task: str | None
    queue_remaining: int
    queue_tasks: List[Dict[str, Any]]
    tasks_completed: List[str]
    tasks_failed: List[Dict[str, Any]]
    heartbeat_timestamp: str | None
    artifact_output_path: str
    last_artifact_path: str | None
    last_completed_task: str | None
    last_failed_task: Dict[str, Any] | None
    status: str
    stop_reason: str | None
    polling_enabled: bool
    idle_poll_count: int
    idle_duration_seconds: float
    idle_timeout_seconds: int
    idle_timeout_poll_limit: int
    current_plan_id: str | None
    current_plan_step: str | None
    next_plan_step: str | None
    steps_remaining: int
    last_generated_plan_summary: str | None
    last_generated_plan_steps: List[str]
    rating_system: str | None
    rating_target: str | None
    rating_locked: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_start_time": self.session_start_time,
            "session_elapsed_seconds": self.session_elapsed_seconds,
            "session_state": self.session_state,
            "work_state": self.work_state,
            "budget_mode": self.budget_mode,
            "current_task_id": self.current_task_id,
            "current_task": self.current_task_id,
            "last_started_task": self.last_started_task,
            "queue_remaining": self.queue_remaining,
            "queue_tasks": [dict(task) for task in self.queue_tasks],
            "tasks_completed": list(self.tasks_completed),
            "tasks_failed": list(self.tasks_failed),
            "heartbeat_timestamp": self.heartbeat_timestamp,
            "artifact_output_path": self.artifact_output_path,
            "last_artifact_path": self.last_artifact_path,
            "last_completed_task": self.last_completed_task,
            "last_failed_task": dict(self.last_failed_task) if self.last_failed_task else None,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "polling_enabled": self.polling_enabled,
            "idle_poll_count": self.idle_poll_count,
            "idle_duration_seconds": self.idle_duration_seconds,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "idle_timeout_poll_limit": self.idle_timeout_poll_limit,
            "current_plan_id": self.current_plan_id,
            "current_plan_step": self.current_plan_step,
            "next_plan_step": self.next_plan_step,
            "steps_remaining": self.steps_remaining,
            "last_generated_plan_summary": self.last_generated_plan_summary,
            "last_generated_plan_steps": list(self.last_generated_plan_steps),
            "rating_system": self.rating_system,
            "rating_target": self.rating_target,
            "rating_locked": self.rating_locked,
        }


class RuntimeState:
    """Structured runtime state API for terminal and future Command Center clients."""

    def __init__(self, config: OrchestratorConfig, session_id: str, *, scheduler: Scheduler | None = None) -> None:
        self.config = config
        self.session_id = session_id
        self.scheduler = scheduler or Scheduler(self.config.queue_path)
        self.state_store = StateStore(self.config.runs_dir, session_id)
        self.snapshot_path = self.state_store.session_dir / "runtime_status.json"

    def get_snapshot(self) -> RuntimeStateSnapshot:
        state = self.state_store.load()
        tasks_completed = list(state.get("tasks_completed", []))
        tasks_failed = [
            dict(entry)
            for entry in state.get("tasks_failed", [])
            if isinstance(entry, Mapping)
        ]
        queue_tasks = self.queue_tasks()
        queue_remaining = self.scheduler.remaining_count()
        heartbeat_timestamp = state.get("last_heartbeat_timestamp")
        current_plan_id = state.get("current_plan_id")
        status = str(state.get("status") or "unknown")
        polling_enabled = bool(state.get("polling_enabled", True))
        idle_poll_count = int(state.get("idle_poll_count", 0) or 0)
        idle_duration_seconds = round(float(state.get("idle_duration_seconds", 0.0) or 0.0), 3)
        idle_timeout_seconds = int(state.get("idle_timeout_seconds", 0) or 0)
        idle_timeout_poll_limit = int(state.get("idle_timeout_poll_limit", 0) or 0)
        next_plan_step = None
        steps_remaining = 0
        profile = load_profile(self.config)
        if current_plan_id:
            plan_tasks = [task for task in self.scheduler.all_tasks() if str(task.get("plan_id") or "") == str(current_plan_id)]
            done = {"completed", "blocked"}
            steps_remaining = sum(1 for task in plan_tasks if str(task.get("status", "pending")).lower() not in done)
            pending_plan_tasks = [
                task for task in queue_tasks if str(task.get("plan_id") or "") == str(current_plan_id) and task["status"] == "pending"
            ]
            if pending_plan_tasks:
                next_plan_step = str(pending_plan_tasks[0].get("plan_step_title") or pending_plan_tasks[0].get("title") or "")
        current_plan_step = state.get("current_plan_step")
        if current_plan_step is None:
            running_plan_task = next(
                (task for task in queue_tasks if task["status"] == "running" and (not current_plan_id or str(task.get("plan_id") or "") == str(current_plan_id))),
                None,
            )
            if running_plan_task is not None:
                current_plan_step = running_plan_task.get("plan_step_title") or running_plan_task.get("title")
        artifact_output_path = str((self.state_store.session_dir / "artifacts").resolve())
        artifacts_generated = []
        for path in state.get("artifacts_generated", []):
            candidate = Path(str(path))
            if not candidate.is_absolute():
                candidate = (self.state_store.session_dir / candidate).resolve()
            artifacts_generated.append(str(candidate))
        session_state, work_state, budget_mode = self._classify_states(
            status=status,
            current_task_id=state.get("current_task"),
            queue_remaining=queue_remaining,
            polling_enabled=polling_enabled,
            idle_timeout_enabled=(idle_timeout_seconds > 0 or idle_timeout_poll_limit > 0),
            stop_reason=state.get("stop_reason"),
            tasks_failed=tasks_failed,
        )
        return RuntimeStateSnapshot(
            session_id=str(state.get("session_id") or self.session_id),
            session_start_time=str(state.get("started_at") or ""),
            session_elapsed_seconds=round(float(state.get("elapsed_time_seconds", 0.0)), 3),
            session_state=session_state,
            work_state=work_state,
            budget_mode=budget_mode,
            current_task_id=state.get("current_task"),
            last_started_task=state.get("last_started_task"),
            queue_remaining=queue_remaining,
            queue_tasks=queue_tasks,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            heartbeat_timestamp=heartbeat_timestamp,
            artifact_output_path=artifact_output_path,
            last_artifact_path=artifacts_generated[-1] if artifacts_generated else None,
            last_completed_task=state.get("last_completed_task") or (tasks_completed[-1] if tasks_completed else None),
            last_failed_task=tasks_failed[-1] if tasks_failed else None,
            status=status,
            stop_reason=state.get("stop_reason"),
            polling_enabled=polling_enabled,
            idle_poll_count=idle_poll_count,
            idle_duration_seconds=idle_duration_seconds,
            idle_timeout_seconds=idle_timeout_seconds,
            idle_timeout_poll_limit=idle_timeout_poll_limit,
            current_plan_id=current_plan_id,
            current_plan_step=current_plan_step,
            next_plan_step=next_plan_step,
            steps_remaining=steps_remaining,
            last_generated_plan_summary=state.get("last_generated_plan_summary"),
            last_generated_plan_steps=[str(item) for item in state.get("last_generated_plan_steps", [])],
            rating_system=profile.rating_system,
            rating_target=profile.rating_target,
            rating_locked=profile.rating_locked,
        )

    def _classify_states(
        self,
        *,
        status: str,
        current_task_id: str | None,
        queue_remaining: int,
        polling_enabled: bool,
        idle_timeout_enabled: bool,
        stop_reason: str | None,
        tasks_failed: List[Dict[str, Any]],
    ) -> tuple[str, str, str]:
        if status != "running":
            return ("complete", "halted", "terminating")
        if current_task_id:
            return ("active", "executing", "consuming")
        if not polling_enabled:
            return ("waiting", "halted", "paused")
        if queue_remaining == 0:
            budget_mode = "terminating" if idle_timeout_enabled and stop_reason is None else "paused"
            work_state = "blocked" if tasks_failed else "queue_empty"
            return ("idle", work_state, budget_mode)
        return ("waiting", "blocked" if tasks_failed else "executing", "consuming")

    def write_snapshot(self) -> RuntimeStateSnapshot:
        snapshot = self.get_snapshot()
        write_json(self.snapshot_path, snapshot.to_payload())
        return snapshot

    def heartbeat_age_seconds(self, *, now: datetime | None = None) -> float | None:
        snapshot = self.get_snapshot()
        if not snapshot.heartbeat_timestamp:
            return None
        current = now or datetime.now(timezone.utc)
        try:
            heartbeat = datetime.fromisoformat(snapshot.heartbeat_timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(0.0, round((current - heartbeat).total_seconds(), 3))

    def queue_tasks(self) -> List[Dict[str, Any]]:
        visible_statuses = {"pending", "running", "needs_approval"}
        tasks: List[Dict[str, Any]] = []
        for task in self.scheduler.all_tasks():
            status = str(task.get("status", "pending")).lower()
            if status not in visible_statuses:
                continue
            tasks.append(
                {
                    "task_id": str(task.get("task_id") or task.get("id") or "unknown_task"),
                    "title": str(task.get("title") or task.get("task_id") or task.get("id") or "untitled"),
                    "status": status,
                    "priority": int(task.get("priority", 1000)),
                    "execution_lane": task.get("execution_lane"),
                    "capability_id": task.get("capability_id"),
                    "maturity_stage": task.get("maturity_stage") or task.get("evidence_state"),
                    "trust_score": int(task.get("trust_score", 0) or 0),
                    "trust_band": task.get("trust_band"),
                    "policy_state": task.get("policy_state"),
                    "execution_decision": task.get("execution_decision"),
                    "recommended_action": task.get("recommended_action"),
                    "sandbox_first_required": bool(task.get("sandbox_first_required", False)),
                    "auto_execution_enabled": bool(task.get("auto_execution_enabled", False)),
                    "auto_execution_reason": task.get("auto_execution_reason"),
                    "missing_evidence": [str(item) for item in task.get("missing_evidence", [])] if isinstance(task.get("missing_evidence"), list) else [],
                    "approval_required": bool(task.get("approval_required", False)),
                    "eligible_for_auto": bool(task.get("eligible_for_auto", False)),
                    "sandbox_verified": bool(task.get("sandbox_verified", False)),
                    "real_target_verified": bool(task.get("real_target_verified", False)),
                    "rollback_verified": bool(task.get("rollback_verified", False)),
                    "last_validation_result": task.get("last_validation_result"),
                    "last_rollback_result": task.get("last_rollback_result"),
                    "rating_system": task.get("rating_system"),
                    "rating_target": task.get("rating_target"),
                    "rating_locked": bool(task.get("rating_locked", False)),
                    "content_policy_match": task.get("content_policy_match"),
                    "content_policy_decision": task.get("content_policy_decision"),
                    "required_rating_upgrade": task.get("required_rating_upgrade"),
                    "requested_content_dimensions": dict(task.get("requested_content_dimensions") or {}) if isinstance(task.get("requested_content_dimensions"), dict) else {},
                    "content_policy_summary": task.get("content_policy_summary"),
                    "approval_state": task.get("approval_state"),
                    "plan_id": task.get("plan_id"),
                    "plan_step_index": int(task.get("plan_step_index", 0) or 0),
                    "plan_step_title": task.get("plan_step_title") or task.get("title"),
                    "dependencies": [str(item) for item in task.get("dependencies", [])] if isinstance(task.get("dependencies"), list) else [],
                }
            )
        tasks.sort(
            key=lambda item: (
                0 if item["status"] == "running" else 1,
                1 if item["status"] == "pending" else 2,
                int(item["priority"]),
                int(item.get("plan_step_index", 0)),
                item["task_id"],
            )
        )
        return tasks


__all__ = ["RuntimeState", "RuntimeStateSnapshot"]