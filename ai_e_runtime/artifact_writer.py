from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .time_utils import get_current_timestamp
from orchestrator.utils import ensure_dir, safe_write_text, write_json


class ArtifactWriter:
    """Stores per-task runtime artifacts under runs/<session_id>."""

    def __init__(self, runs_dir: Path, session_id: str) -> None:
        self.session_dir = ensure_dir(Path(runs_dir) / session_id)
        self.artifacts_dir = ensure_dir(self.session_dir / "artifacts")

    def store(
        self,
        *,
        task: Dict[str, Any],
        result: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> List[str]:
        task_id = self._task_id(task)
        attempt = int(task.get("retry_count", 0)) + 1
        stem = f"{task_id}_attempt_{attempt:02d}"
        artifact_path = self.artifacts_dir / f"{stem}.json"
        summary_path = self.artifacts_dir / f"{stem}.md"

        payload = {
            "task": dict(task),
            "result": dict(result),
            "validation": dict(validation),
            "timestamp": get_current_timestamp(),
        }
        write_json(artifact_path, payload)
        safe_write_text(summary_path, self._summary_markdown(task, result, validation))

        return [self._relative(artifact_path), self._relative(summary_path)]

    def write_session_summary(self, payload: Dict[str, Any]) -> str:
        path = self.session_dir / "session_summary.json"
        summary_payload = dict(payload)
        summary_payload.setdefault("timestamp", get_current_timestamp())
        write_json(path, summary_payload)
        return self._relative(path)

    def _summary_markdown(
        self,
        task: Dict[str, Any],
        result: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> str:
        task_id = self._task_id(task)
        lines = [
            "SUMMARY",
            f"Task {task_id} executed in the persistent supervisor loop.",
            "",
            "FACTS",
            f"- result_status: {result.get('status', 'unknown')}",
            f"- validation_state: {validation.get('validation_state', validation.get('status', 'unknown'))}",
            f"- agent_type: {result.get('agent_type', task.get('agent_type', 'copilot_coder_agent'))}",
            "",
            "ASSUMPTIONS",
            "- This artifact captures one task attempt only.",
            "",
            "RECOMMENDATIONS",
            f"- queue_action: {validation.get('queue_action', 'complete')}",
            "",
            "TIMESTAMP",
            task.get("last_attempt_timestamp") or task.get("completed_timestamp") or get_current_timestamp(),
            "",
        ]
        return "\n".join(lines)

    def _task_id(self, task: Dict[str, Any]) -> str:
        return str(task.get("task_id") or task.get("id") or "unknown_task")

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self.session_dir)).replace("\\", "/")