from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from orchestrator.approvals import ApprovalRecord, OperatorApprovalStore
from orchestrator.config import OrchestratorConfig
from orchestrator.utils import read_json, write_json


@dataclass(frozen=True)
class MutationApprovalResult:
    task_id: str
    queue_status: str
    approval_record: ApprovalRecord


def approve_mutation_task(
    config: OrchestratorConfig,
    *,
    task_id: str,
    approved_by: str,
    notes: str = "",
) -> MutationApprovalResult:
    tasks, shape = _load_tasks(config.queue_path)
    task = _find_task(tasks, task_id)
    if str(task.get("execution_lane") or "") != "approval_required_mutation":
        raise ValueError(f"Task {task_id} is not an approval-required mutation task.")
    if str(task.get("status") or "").lower() != "needs_approval":
        raise ValueError(f"Task {task_id} is not awaiting approval.")

    store = OperatorApprovalStore(config.approvals_path)
    record = store.add(task_id=task_id, run_id="", approved_by=approved_by, notes=notes)

    task["status"] = "pending"
    task["approval_state"] = "approved"
    task["approved_by"] = record.approved_by
    task["approved_at"] = record.approved_at
    task["approval_notes"] = record.notes
    task["last_error"] = ""
    _write_tasks(config.queue_path, tasks, shape)
    _update_runtime_payload(config, task)
    return MutationApprovalResult(task_id=task_id, queue_status=str(task.get("status") or "pending"), approval_record=record)


def _update_runtime_payload(config: OrchestratorConfig, task: Dict[str, Any]) -> None:
    contract_path = task.get("contract_path")
    if not contract_path:
        return
    runtime_payload_path = Path(str(contract_path))
    if not runtime_payload_path.is_absolute():
        runtime_payload_path = (config.root_dir / runtime_payload_path).resolve()
    payload = read_json(runtime_payload_path, default={})
    runtime_task = payload.get("runtime_task") if isinstance(payload, dict) else None
    if not isinstance(runtime_task, dict):
        return
    runtime_task["approval_state"] = task.get("approval_state")
    runtime_task["approved_by"] = task.get("approved_by")
    runtime_task["approved_at"] = task.get("approved_at")
    runtime_task["approval_notes"] = task.get("approval_notes", "")
    write_json(runtime_payload_path, payload)


def _load_tasks(queue_path: Path) -> Tuple[list[Dict[str, Any]], str]:
    raw = read_json(queue_path, default={"tasks": []})
    if isinstance(raw, list):
        return [dict(task) for task in raw if isinstance(task, dict)], "list"
    tasks = raw.get("tasks", []) if isinstance(raw, dict) else []
    return [dict(task) for task in tasks if isinstance(task, dict)], "dict"


def _write_tasks(queue_path: Path, tasks: list[Dict[str, Any]], shape: str) -> None:
    payload: Any = tasks if shape == "list" else {"tasks": tasks}
    write_json(queue_path, payload)


def _find_task(tasks: list[Dict[str, Any]], task_id: str) -> Dict[str, Any]:
    for task in tasks:
        candidate = str(task.get("task_id") or task.get("id") or "")
        if candidate == task_id:
            return task
    raise KeyError(f"Task {task_id} not found.")


__all__ = ["MutationApprovalResult", "approve_mutation_task"]