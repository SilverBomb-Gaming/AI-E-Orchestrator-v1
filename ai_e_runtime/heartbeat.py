from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Any

from orchestrator.utils import ensure_dir

from .time_utils import format_timestamp


class HeartbeatEmitter:
    """Appends SESSION_HEARTBEAT records to logs/session_heartbeat.log."""

    def __init__(
        self,
        log_path: Path,
        *,
        interval_seconds: int = 300,
        time_source: Callable[[], datetime] | None = None,
    ) -> None:
        self.log_path = Path(log_path)
        self.interval_seconds = max(1, int(interval_seconds))
        self.time_source = time_source
        self.last_emitted_at: datetime | None = None
        ensure_dir(self.log_path.parent)

    def should_emit(self, now: datetime | None = None) -> bool:
        current = now or self._now()
        if self.last_emitted_at is None:
            return True
        return (current - self.last_emitted_at).total_seconds() >= self.interval_seconds

    def emit(
        self,
        *,
        session_elapsed_time: float,
        current_task: str | None,
        queue_remaining: int,
        session_id: str,
        force: bool = False,
    ) -> str | None:
        now = self._now()
        if not force and not self.should_emit(now):
            return None
        timestamp = format_timestamp(now)
        block = "\n".join(
            [
                "SESSION_HEARTBEAT",
                f"timestamp={timestamp}",
                f"session_id={session_id}",
                f"session_elapsed_time={round(float(session_elapsed_time), 3)}",
                f"current_task={current_task or 'idle'}",
                f"queue_remaining={int(queue_remaining)}",
                "",
            ]
        )
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(block)
        self.last_emitted_at = now
        return block

    def read_status(self) -> Dict[str, Any]:
        return {
            "log_path": str(self.log_path),
            "interval_seconds": self.interval_seconds,
            "last_emitted_at": format_timestamp(self.last_emitted_at) if self.last_emitted_at else None,
        }

    def _now(self) -> datetime:
        if self.time_source is not None:
            return self.time_source()
        return datetime.utcnow()