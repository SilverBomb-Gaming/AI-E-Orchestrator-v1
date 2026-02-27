#!/usr/bin/env python3
"""Sanity checks for Stability Core v1 file layout and guard-rails."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class CheckDefinition:
    label: str
    candidates: List[str]
    kind: str = "file"
    optional: bool = False


REQUIRED_ITEMS: List[CheckDefinition] = [
    CheckDefinition(label="orchestrator/runner.py", candidates=["orchestrator/runner.py"]),
    CheckDefinition(label="scripts/run_once.ps1", candidates=["scripts/run_once.ps1"]),
    CheckDefinition(label="queue_ops.py", candidates=["Tools/queue_ops.py", "queue_ops.py"]),
    CheckDefinition(
        label="docs/MODULE_BOUNDARIES.md",
        candidates=["docs/MODULE_BOUNDARIES.md", "MODULE_BOUNDARIES.md"],
    ),
    CheckDefinition(label="README.md", candidates=["README.md"]),
    CheckDefinition(label="tests/test_queue_ops.py", candidates=["tests/test_queue_ops.py", "test_queue_ops.py"]),
    CheckDefinition(label="tests/fixtures", candidates=["tests/fixtures"], kind="dir"),
    CheckDefinition(label="tests/fixtures/queue_minimal.json", candidates=["tests/fixtures/queue_minimal.json"]),
    CheckDefinition(
        label="tests/fixtures/queue_blocked_needs_approval.json",
        candidates=["tests/fixtures/queue_blocked_needs_approval.json"],
    ),
    CheckDefinition(
        label="tests/fixtures/approvals_minimal.json",
        candidates=["tests/fixtures/approvals_minimal.json"],
        optional=False,
    ),
]

CONTENT_CHECKS = [
    {
        "label": "runner.py parser supports frames and ticks",
        "candidates": ["orchestrator/runner.py"],
        "patterns": ["frames|ticks"],
    },
    {
        "label": "queue_ops.py exposes --dry-run/--force/--apply",
        "candidates": ["Tools/queue_ops.py", "queue_ops.py"],
        "patterns": ["--dry-run", "--force", "--apply"],
    },
]


@dataclass
class CheckResult:
    label: str
    status: str
    path: Optional[str]
    optional: bool
    details: str = ""


def _resolve_path(root: Path, candidates: Iterable[str], kind: str) -> Optional[Path]:
    for candidate in candidates:
        target = (root / candidate).resolve()
        if kind == "dir" and target.is_dir():
            return target
        if kind != "dir" and target.is_file():
            return target
    return None


def _status_text(passed: bool, optional: bool) -> str:
    if passed:
        return "PASS"
    if optional:
        return "PASS"
    return "FAIL"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Stability Core v1 file layout.")
    parser.add_argument("--root", help="Override repo root path.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output only.")
    parser.add_argument("--verbose", action="store_true", help="Print additional details per check.")
    args = parser.parse_args(argv)

    default_root = Path(__file__).resolve().parent.parent
    root = Path(args.root).resolve() if args.root else default_root
    results: List[CheckResult] = []
    required_total = len([item for item in REQUIRED_ITEMS if not item.optional])
    required_failures = 0

    for item in REQUIRED_ITEMS:
        resolved = _resolve_path(root, item.candidates, item.kind)
        passed = resolved is not None
        if not passed and not item.optional:
            required_failures += 1
        details = ""
        if resolved is None and item.optional:
            details = "optional; not found"
        elif resolved is not None and args.verbose:
            details = str(resolved)
        status = _status_text(passed, item.optional)
        results.append(
            CheckResult(
                label=item.label,
                status=status,
                path=str(resolved) if resolved else None,
                optional=item.optional,
                details=details,
            )
        )

    content_results: List[CheckResult] = []
    content_failures = 0
    for check in CONTENT_CHECKS:
        target = _resolve_path(root, check["candidates"], kind="file")
        if target is None:
            content_failures += 1
            content_results.append(
                CheckResult(
                    label=check["label"],
                    status="FAIL",
                    path=None,
                    optional=False,
                    details="file missing",
                )
            )
            continue
        text = target.read_text(encoding="utf-8", errors="ignore")
        passed = all(pattern in text for pattern in check["patterns"])
        if not passed:
            content_failures += 1
        details = str(target) if args.verbose else ""
        content_results.append(
            CheckResult(
                label=check["label"],
                status="PASS" if passed else "FAIL",
                path=str(target),
                optional=False,
                details=details,
            )
        )

    overall_ok = required_failures == 0 and content_failures == 0

    if args.json:
        payload = {
            "root": str(root),
            "checks": [result.__dict__ for result in results],
            "content_checks": [result.__dict__ for result in content_results],
            "summary": {
                "required_total": required_total,
                "required_failures": required_failures,
                "content_failures": content_failures,
                "status": "PASS" if overall_ok else "FAIL",
            },
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"[VERIFY] root={root}")
        for result in results:
            path_info = result.path or "missing"
            detail = f" ({result.details})" if result.details else ""
            print(f"{result.status} {result.label} -> {path_info}{detail}")
        for result in content_results:
            path_info = result.path or "missing"
            detail = f" ({result.details})" if result.details else ""
            print(f"{result.status} {result.label} -> {path_info}{detail}")
        status_text = "PASS" if overall_ok else "FAIL"
        print(
            f"[VERIFY] RESULT: {status_text} "
            f"(required failures={required_failures}, content failures={content_failures})"
        )

    return 0 if overall_ok else 2


if __name__ == "__main__":
    sys.exit(main())
