from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import ensure_dir, read_json, utc_timestamp, write_json


@dataclass(frozen=True)
class ApprovalRecord:
    task_id: str
    run_id: str
    approved_by: str
    approved_at: str
    notes: str


class OperatorApprovalStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        ensure_dir(self.path.parent)
        if not self.path.exists():
            write_json(self.path, {"approvals": []})

    def consume(self, task_id: str, run_id: str) -> bool:
        payload = self._load()
        approvals = payload.get("approvals", [])
        index = self._find_index(approvals, task_id, run_id)
        if index is None:
            return False
        approvals.pop(index)
        write_json(self.path, {"approvals": approvals})
        return True

    def add(self, *, task_id: str, run_id: str, approved_by: str, notes: str = "") -> ApprovalRecord:
        payload = self._load()
        record = {
            "task_id": task_id,
            "run_id": run_id,
            "approved_by": approved_by,
            "approved_at": utc_timestamp(compact=False),
            "notes": notes,
        }
        approvals = payload.get("approvals", [])
        approvals.append(record)
        write_json(self.path, {"approvals": approvals})
        return ApprovalRecord(**record)

    def list_pending(self) -> List[Dict[str, Any]]:
        payload = self._load()
        return list(payload.get("approvals", []))

    def _load(self) -> Dict[str, Any]:
        return read_json(self.path, default={"approvals": []})

    def _find_index(self, approvals: List[Dict[str, Any]], task_id: str, run_id: str) -> Optional[int]:
        for idx, entry in enumerate(approvals):
            entry_run_id = (entry.get("run_id") or "").strip()
            entry_task_id = (entry.get("task_id") or "").strip()
            if entry_run_id and run_id and entry_run_id == run_id:
                return idx
            if not entry_run_id and entry_task_id == task_id:
                return idx
        return None
