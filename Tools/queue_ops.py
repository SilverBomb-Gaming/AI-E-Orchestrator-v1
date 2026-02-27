#!/usr/bin/env python3
"""Utility helpers for inspecting and recovering AI-E Orchestrator queue state."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "backlog" / "queue.json"
APPROVALS_PATH = ROOT / "backlog" / "approvals.json"
RUNS_DIR = ROOT / "runs"


def _timestamp() -> str:
    return _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return json.loads(json.dumps(default))
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any, *, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[dry-run] Would update {path}.")
        return

    backup = path.with_name(f"{path.name}.bak.{_timestamp()}")
    if path.exists():
        shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _load_queue() -> Dict[str, Any]:
    return _load_json(QUEUE_PATH, {"tasks": []})


def _write_queue(data: Dict[str, Any], *, dry_run: bool = False) -> None:
    _write_json(QUEUE_PATH, data, dry_run=dry_run)


def _load_approvals() -> Dict[str, Any]:
    return _load_json(APPROVALS_PATH, {"approvals": []})


def _write_approvals(data: Dict[str, Any], *, dry_run: bool = False) -> None:
    _write_json(APPROVALS_PATH, data, dry_run=dry_run)


def _find_task(queue: Dict[str, Any], task_id: str) -> Optional[Dict[str, Any]]:
    for task in queue.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


def _purge_runs(task_id: str, *, dry_run: bool = False) -> List[Path]:
    targets: List[Path] = []
    if not RUNS_DIR.exists():
        return targets
    suffix = f"_{task_id}"
    for child in RUNS_DIR.iterdir():
        if not child.is_dir():
            continue
        if child.name.endswith(suffix):
            targets.append(child)

    if dry_run:
        for entry in targets:
            print(f"[dry-run] Would delete run bundle {entry}.")
        return targets

    removed: List[Path] = []
    for entry in targets:
        shutil.rmtree(entry)
        removed.append(entry)
    return removed


def _remove_hold_fields(task: Dict[str, Any]) -> None:
    task.pop("hold_state", None)
    task.pop("resolution_note", None)


def cmd_list(_: argparse.Namespace) -> int:
    queue = _load_queue()
    tasks = queue.get("tasks", [])
    if not tasks:
        print("Queue is empty.")
        return 0

    headers = ("ID", "Status", "Run", "Last Error")
    rows: List[tuple[str, str, str, str]] = []
    blocked_label = None
    for task in tasks:
        status = task.get("status", "pending")
        hold_state = task.get("hold_state")
        if blocked_label is None:
            if status != "completed" or hold_state:
                blocked_label = task.get("id")
        rows.append(
            (
                task.get("id", ""),
                f"{status}{' (hold)' if hold_state else ''}",
                task.get("current_run_id") or "",
                task.get("last_error") or "",
            )
        )

    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]

    line = " | ".join(header.ljust(width) for header, width in zip(headers, widths))
    print(line)
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))

    if blocked_label:
        print(f"\nFirst blocking task: {blocked_label}")
    else:
        print("\nQueue is clear; next pending task may run.")
    return 0


def _ensure_task(task: Optional[Dict[str, Any]], task_id: str) -> Dict[str, Any]:
    if task is None:
        raise SystemExit(f"Task {task_id} not found in queue.json")
    return task


def cmd_reset(args: argparse.Namespace) -> int:
    if args.purge_runs and not args.force:
        raise SystemExit("--force is required when using --purge-runs.")

    queue = _load_queue()
    task = _ensure_task(_find_task(queue, args.task), args.task)
    before_status = task.get("status")
    task["status"] = "pending"
    task["current_run_id"] = None
    _remove_hold_fields(task)
    if args.clear_error:
        task["last_error"] = ""
    _write_queue(queue, dry_run=args.dry_run)

    removed_runs: List[Path] = []
    if args.purge_runs:
        removed_runs = _purge_runs(args.task, dry_run=args.dry_run)

    print(f"Reset task {args.task} ({before_status} → pending)")
    if removed_runs:
        verb = "Would purge" if args.dry_run else "Purged"
        print(f"{verb} {len(removed_runs)} run bundle(s).")
    if args.dry_run:
        print("[dry-run] No queue files were modified.")
    return 0


def _has_approval(task_id: str, run_id: Optional[str]) -> bool:
    approvals = _load_approvals()
    for entry in approvals.get("approvals", []):
        entry_task = (entry.get("task_id") or "").strip()
        entry_run = (entry.get("run_id") or "").strip()
        if not entry_task and not entry_run:
            continue
        if entry_run and run_id and entry_run == run_id:
            return True
        if not entry_run and entry_task == task_id:
            return True
    return False


def _consume_approval(task_id: str, run_id: Optional[str], *, dry_run: bool = False) -> bool:
    approvals = _load_approvals()
    pending = approvals.get("approvals", [])
    for idx, entry in enumerate(pending):
        entry_task = (entry.get("task_id") or "").strip()
        entry_run = (entry.get("run_id") or "").strip()
        if entry_run and run_id and entry_run == run_id:
            if dry_run:
                print(
                    f"[dry-run] Would consume approval for run {entry_run} (task {task_id})."
                )
            else:
                pending.pop(idx)
                _write_approvals({"approvals": pending})
            return True
        if not entry_run and entry_task == task_id:
            if dry_run:
                print(f"[dry-run] Would consume approval for task {task_id}.")
            else:
                pending.pop(idx)
                _write_approvals({"approvals": pending})
            return True
    return False


def cmd_resume(args: argparse.Namespace) -> int:
    queue = _load_queue()
    task = _ensure_task(_find_task(queue, args.task), args.task)
    status = task.get("status")
    hold_state = task.get("hold_state")

    if status == "pending" and not hold_state:
        print(f"Task {args.task} is already pending.")
        return 0

    if status == "needs_approval" and not args.force:
        run_id = task.get("current_run_id") or task.get("last_run_id")
        if not _has_approval(args.task, run_id):
            raise SystemExit(
                "Task requires approval; rerun with --force or record an approval first."
            )
        _consume_approval(args.task, run_id, dry_run=args.dry_run)

    before_status = task.get("status")
    task["status"] = "pending"
    task["current_run_id"] = None
    _remove_hold_fields(task)
    _write_queue(queue, dry_run=args.dry_run)
    print(f"Resumed task {args.task} ({before_status} → pending)")
    if args.dry_run:
        print("[dry-run] No queue files were modified.")
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    queue = _load_queue()
    task = _ensure_task(_find_task(queue, args.task), args.task)
    task["status"] = "aborted"
    task["current_run_id"] = None
    task["last_error"] = args.reason or "Aborted via queue_ops"
    task["last_run_status"] = "ABORTED"
    _write_queue(queue, dry_run=args.dry_run)
    print(f"Marked task {args.task} as aborted.")
    if args.dry_run:
        print("[dry-run] No queue files were modified.")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    if not args.force:
        raise SystemExit("--force is required to delete queue entries.")

    queue = _load_queue()
    tasks = queue.get("tasks", [])
    before_len = len(tasks)
    tasks = [task for task in tasks if task.get("id") != args.task]
    if len(tasks) == before_len:
        raise SystemExit(f"Task {args.task} not found.")
    queue["tasks"] = tasks
    _write_queue(queue, dry_run=args.dry_run)

    if args.purge_runs:
        removed = _purge_runs(args.task, dry_run=args.dry_run)
        if removed:
            verb = "Would purge" if args.dry_run else "Purged"
            print(f"{verb} {len(removed)} run bundle(s).")

    approvals = _load_approvals()
    filtered = [
        entry for entry in approvals.get("approvals", []) if entry.get("task_id") != args.task
    ]
    if len(filtered) != len(approvals.get("approvals", [])):
        _write_approvals({"approvals": filtered}, dry_run=args.dry_run)

    print(f"Deleted task {args.task} from queue.")
    if args.dry_run:
        print("[dry-run] No queue files were modified.")
    return 0


def _apply_unblock_action(kind: str, task_id: str, args: argparse.Namespace) -> int:
    if kind == "resume":
        resume_args = argparse.Namespace(task=task_id, force=True, dry_run=args.dry_run)
        return cmd_resume(resume_args)
    if kind == "reset":
        reset_args = argparse.Namespace(
            task=task_id,
            purge_runs=False,
            clear_error=False,
            force=True,
            dry_run=args.dry_run,
        )
        return cmd_reset(reset_args)
    raise SystemExit(f"Unsupported unblock action: {kind}")


def cmd_unblock(args: argparse.Namespace) -> int:
    if args.apply and not args.force:
        raise SystemExit("--force is required when using --apply.")

    queue = _load_queue()
    tasks = queue.get("tasks", [])
    for task in tasks:
        status = task.get("status", "pending")
        hold_state = task.get("hold_state")
        if status == "completed" and not hold_state:
            continue
        task_id = task.get("id")
        if status == "pending":
            print(f"Queue ready. Next pending task: {task_id}")
            return 0
        if status == "needs_approval":
            message = (
                f"Queue blocked: task {task_id} awaits approval. "
                f"Suggested: queue_ops.py resume --task {task_id}"
            )
            print(message)
            if args.apply:
                return _apply_unblock_action("resume", task_id, args)
            return 0
        if status == "running":
            print(f"Queue blocked: task {task_id} is running (run {task.get('current_run_id')}).")
            return 0
        if hold_state:
            message = (
                f"Queue blocked: task {task_id} has hold state '{hold_state}'. "
                f"Suggested: queue_ops.py resume --task {task_id}"
            )
            print(message)
            if args.apply:
                return _apply_unblock_action("resume", task_id, args)
            return 0
        message = (
            f"Queue blocked: task {task_id} status={status}. "
            f"Suggested: queue_ops.py reset --task {task_id}"
        )
        print(message)
        if args.apply:
            return _apply_unblock_action("reset", task_id, args)
        return 0
    print("Queue is empty.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Queue recovery helpers for AI-E Orchestrator.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List queue entries.").set_defaults(func=cmd_list)

    p_reset = sub.add_parser("reset", help="Reset a task back to pending.")
    p_reset.add_argument("--task", required=True, help="Task ID to reset.")
    p_reset.add_argument("--purge-runs", action="store_true", help="Delete run bundles for the task.")
    p_reset.add_argument("--clear-error", action="store_true", help="Clear last_error field.")
    p_reset.add_argument("--force", action="store_true", help="Acknowledge destructive options like --purge-runs.")
    p_reset.add_argument("--dry-run", action="store_true", help="Simulate without writing files or deleting runs.")
    p_reset.set_defaults(func=cmd_reset)

    p_resume = sub.add_parser("resume", help="Resume a held or approval-gated task.")
    p_resume.add_argument("--task", required=True, help="Task ID to resume.")
    p_resume.add_argument("--force", action="store_true", help="Bypass approval requirement.")
    p_resume.add_argument("--dry-run", action="store_true", help="Simulate without writing files.")
    p_resume.set_defaults(func=cmd_resume)

    p_abort = sub.add_parser("abort", help="Mark a task as failed/aborted.")
    p_abort.add_argument("--task", required=True, help="Task ID to abort.")
    p_abort.add_argument("--reason", default="", help="Optional explanation for audit trail.")
    p_abort.add_argument("--dry-run", action="store_true", help="Simulate without writing files.")
    p_abort.set_defaults(func=cmd_abort)

    p_delete = sub.add_parser("delete", help="Remove a task from the queue entirely.")
    p_delete.add_argument("--task", required=True, help="Task ID to delete.")
    p_delete.add_argument("--force", action="store_true", help="Acknowledge destructive delete.")
    p_delete.add_argument("--purge-runs", action="store_true", help="Delete run bundles for the task.")
    p_delete.add_argument("--dry-run", action="store_true", help="Simulate without writing files or deleting runs.")
    p_delete.set_defaults(func=cmd_delete)

    p_unblock = sub.add_parser("unblock", help="Report the next blocker and suggested fix.")
    p_unblock.add_argument(
        "--apply",
        action="store_true",
        help="Apply the suggested fix automatically (requires --force).",
    )
    p_unblock.add_argument(
        "--force",
        action="store_true",
        help="Acknowledge that applying suggestions may modify queue.json.",
    )
    p_unblock.add_argument("--dry-run", action="store_true", help="Simulate apply mode without changes.")
    p_unblock.set_defaults(func=cmd_unblock)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
