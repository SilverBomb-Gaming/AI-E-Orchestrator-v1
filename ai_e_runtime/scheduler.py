from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from orchestrator.utils import ensure_dir, read_json, write_json


class Scheduler:
    """Persistent queue reader/writer for continuous runtime sessions."""

    def __init__(self, queue_path: Path, *, max_retries: int = 3) -> None:
        self.queue_path = Path(queue_path)
        self.max_retries = max(1, int(max_retries))
        ensure_dir(self.queue_path.parent)
        if not self.queue_path.exists():
            write_json(self.queue_path, {"tasks": []})

    def get_next_task(self) -> Dict[str, Any] | None:
        tasks, _ = self._load_tasks()
        completed_ids = {
            self._task_id(task)
            for task in tasks
            if str(task.get("status", "pending")).lower() == "completed"
        }
        pending = [
            task
            for task in tasks
            if str(task.get("status", "pending")).lower() == "pending"
            and self._dependencies_satisfied(task, completed_ids)
        ]
        if not pending:
            return None
        pending.sort(key=self._sort_key)
        return dict(pending[0])

    def all_tasks(self) -> List[Dict[str, Any]]:
        tasks, _ = self._load_tasks()
        return [dict(task) for task in tasks]

    def remaining_count(self) -> int:
        tasks, _ = self._load_tasks()
        done = {"completed", "blocked"}
        return sum(1 for task in tasks if str(task.get("status", "pending")).lower() not in done)

    def pending_count(self) -> int:
        tasks, _ = self._load_tasks()
        return sum(1 for task in tasks if str(task.get("status", "pending")).lower() == "pending")

    def recover_running_tasks(self, session_id: str) -> List[str]:
        tasks, shape = self._load_tasks()
        recovered: List[str] = []
        for task in tasks:
            if str(task.get("status", "")).lower() != "running":
                continue
            if str(task.get("current_session_id") or "") != session_id:
                continue
            task["status"] = "pending"
            task["current_session_id"] = None
            task["last_error"] = "Recovered interrupted running task for supervisor resume."
            recovered.append(self._task_id(task))
        if recovered:
            self._write_tasks(tasks, shape)
        return recovered

    def mark_running(self, task_id: str, *, session_id: str) -> Dict[str, Any]:
        tasks, shape = self._load_tasks()
        task = self._find_task(tasks, task_id)
        task["status"] = "running"
        task["current_session_id"] = session_id
        task["last_attempt_timestamp"] = self._iso_now()
        self._write_tasks(tasks, shape)
        return dict(task)

    def mark_completed(
        self,
        task_id: str,
        *,
        session_id: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        tasks, shape = self._load_tasks()
        task = self._find_task(tasks, task_id)
        task["status"] = "completed"
        task["current_session_id"] = None
        task["last_session_id"] = session_id
        task["completed_timestamp"] = self._iso_now()
        task["last_error"] = ""
        task["last_result_status"] = result.get("status", "completed")
        self._write_tasks(tasks, shape)
        return dict(task)

    def mark_blocked(
        self,
        task_id: str,
        *,
        session_id: str,
        reason: str,
        result: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        tasks, shape = self._load_tasks()
        task = self._find_task(tasks, task_id)
        task["status"] = "blocked"
        task["current_session_id"] = None
        task["last_session_id"] = session_id
        task["blocked_timestamp"] = self._iso_now()
        task["last_error"] = reason
        if result is not None:
            task["last_result_status"] = result.get("status", "blocked")
        self._write_tasks(tasks, shape)
        return dict(task)

    def requeue_failed(
        self,
        task_id: str,
        *,
        session_id: str,
        reason: str,
        result: Dict[str, Any] | None = None,
    ) -> Tuple[Dict[str, Any], bool]:
        tasks, shape = self._load_tasks()
        task = self._find_task(tasks, task_id)
        retries = int(task.get("retry_count", 0)) + 1
        task["retry_count"] = retries
        task["current_session_id"] = None
        task["last_session_id"] = session_id
        task["last_error"] = reason
        task["last_retry_timestamp"] = self._iso_now()
        if result is not None:
            task["last_result_status"] = result.get("status", "retryable_failure")
        should_retry = retries < self.max_retries
        task["status"] = "pending" if should_retry else "blocked"
        self._write_tasks(tasks, shape)
        return dict(task), should_retry

    def _load_tasks(self) -> Tuple[List[Dict[str, Any]], str]:
        raw = read_json(self.queue_path, default={"tasks": []})
        if isinstance(raw, list):
            tasks = raw
            shape = "list"
        elif isinstance(raw, dict):
            nested = raw.get("tasks", [])
            tasks = nested if isinstance(nested, list) else []
            shape = "dict"
        else:
            tasks = []
            shape = "dict"
        normalized = [self._normalize_task(task) for task in tasks if isinstance(task, dict)]
        return normalized, shape

    def _write_tasks(self, tasks: List[Dict[str, Any]], shape: str) -> None:
        payload: Any = tasks if shape == "list" else {"tasks": tasks}
        write_json(self.queue_path, payload)

    def _normalize_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(task)
        normalized.setdefault("status", "pending")
        normalized.setdefault("priority", 1000)
        normalized.setdefault("retry_count", 0)
        dependencies = normalized.get("dependencies", [])
        normalized["dependencies"] = [str(item) for item in dependencies] if isinstance(dependencies, list) else []
        return normalized

    def _dependencies_satisfied(self, task: Dict[str, Any], completed_ids: set[str]) -> bool:
        dependencies = task.get("dependencies", [])
        if not isinstance(dependencies, list):
            return True
        return all(str(item) in completed_ids for item in dependencies)

    def _find_task(self, tasks: List[Dict[str, Any]], task_id: str) -> Dict[str, Any]:
        for task in tasks:
            if self._task_id(task) == task_id:
                return task
        raise KeyError(f"Task {task_id} not found in queue {self.queue_path}")

    def _sort_key(self, task: Dict[str, Any]) -> Tuple[int, str]:
        priority = task.get("priority", 1000)
        try:
            priority_value = int(priority)
        except (TypeError, ValueError):
            priority_value = 1000
        return priority_value, self._task_id(task)

    def _task_id(self, task: Dict[str, Any]) -> str:
        for key in ("task_id", "id"):
            value = task.get(key)
            if value:
                return str(value)
        raise KeyError("Queue task is missing task_id/id")

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")