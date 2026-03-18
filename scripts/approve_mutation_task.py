from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_e_runtime.mutation_approval import approve_mutation_task
from orchestrator.config import OrchestratorConfig


def _default_operator() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Approve and activate an approval-gated mutation task.")
    parser.add_argument("--task-id", required=True, help="Queue task id awaiting mutation approval.")
    parser.add_argument("--notes", default="", help="Optional approval notes.")
    parser.add_argument("--operator", default=_default_operator(), help="Operator name; defaults to the current user.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = OrchestratorConfig.load()
    result = approve_mutation_task(
        config,
        task_id=args.task_id,
        approved_by=args.operator,
        notes=args.notes,
    )
    print(
        "MUTATION TASK APPROVED "
        f"task_id={result.task_id} "
        f"queue_status={result.queue_status} "
        f"approved_by={result.approval_record.approved_by}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())