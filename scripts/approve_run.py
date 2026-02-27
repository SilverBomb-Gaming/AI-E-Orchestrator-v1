#!/usr/bin/env python
"""Operator approval helper for AI-E Orchestrator."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.approvals import OperatorApprovalStore
from orchestrator.config import OrchestratorConfig


def _default_operator() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser()


def list_pending(store: OperatorApprovalStore) -> None:
    rows = store.list_pending()
    if not rows:
        print("No pending approvals recorded.")
        return
    headers = ("Task", "Run ID", "Approved By", "Approved At", "Notes")
    widths = [len(header) for header in headers]
    table: List[tuple[str, str, str, str, str]] = []
    for row in rows:
        record = (
            (row.get("task_id") or ""),
            (row.get("run_id") or ""),
            (row.get("approved_by") or ""),
            (row.get("approved_at") or ""),
            (row.get("notes") or ""),
        )
        widths = [max(width, len(value)) for width, value in zip(widths, record)]
        table.append(record)
    line = " | ".join(header.ljust(width) for header, width in zip(headers, widths))
    print(line)
    print("-+-".join("-" * width for width in widths))
    for record in table:
        print(" | ".join(value.ljust(width) for value, width in zip(record, widths)))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record or review operator approvals.")
    parser.add_argument("--task-id", help="Task identifier the approval applies to.")
    parser.add_argument("--run-id", help="Specific run identifier to approve.")
    parser.add_argument("--notes", default="", help="Optional audit notes to embed with the approval.")
    parser.add_argument(
        "--operator",
        default=_default_operator(),
        help="Operator name; defaults to the current user.",
    )
    parser.add_argument("--list", action="store_true", help="List pending approvals and exit.")
    args = parser.parse_args(argv)

    config = OrchestratorConfig.load()
    store = OperatorApprovalStore(config.approvals_path)

    if args.list:
        list_pending(store)
        return 0

    if not args.task_id and not args.run_id:
        parser.error("Specify --task-id or --run-id when recording an approval.")

    record = store.add(
        task_id=args.task_id or "",
        run_id=args.run_id or "",
        approved_by=args.operator,
        notes=args.notes,
    )
    print(
        "Recorded approval for task {task} (run {run}) by {owner}.".format(
            task=record.task_id or "*", run=record.run_id or "*", owner=record.approved_by
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
