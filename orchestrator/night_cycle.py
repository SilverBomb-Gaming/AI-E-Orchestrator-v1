#!/usr/bin/env python3
"""Night Cycle v1 — bounded overnight task execution."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .apply_gate import ApplyDecision, ApplyGate
from .config import OrchestratorConfig
from .gates import Gatekeeper
from .registry import AgentRegistry
from .runner import QueueManager, TaskResult, TaskRunner
from .utils import ensure_dir, safe_write_text, utc_timestamp
from .validation_pack import prepare_pack_context
from .workspace import WorkspaceManager


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "y"}:
        return True
    if normalized in {"0", "false", "no", "off", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Cannot parse boolean value from '{value}'.")


@dataclass
class CycleOptions:
    max_runs: int = 10
    max_minutes: int = 360
    stop_on_ask: bool = True
    stop_on_deny: bool = True
    retry_per_task: int = 1
    cooldown_seconds: int = 10
    task_filter: Optional[str] = None
    dry_run: bool = False
    purge_stale_runs: bool = False
    apply_mode: str = "off"


class NightCycle:
    """Controlled execution loop that respects Stability Core guardrails."""

    def __init__(
        self,
        config: OrchestratorConfig,
        task_supplier: Callable[[], Iterable[Dict[str, object]]],
        executor: Callable[[Dict[str, object]], Optional[TaskResult]],
        options: CycleOptions,
        *,
        now_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        cycle_id: Optional[str] = None,
        pack_id: Optional[str] = None,
        pack_mode: Optional[str] = None,
        pack_tasks: Optional[List[Dict[str, object]]] = None,
    ) -> None:
        self.config = config
        self.task_supplier = task_supplier
        self.executor = executor
        self.options = options
        self.now_fn = now_fn or time.time
        self.sleep_fn = sleep_fn or time.sleep
        self.cycle_id = cycle_id or utc_timestamp()
        self.pack_id = pack_id
        self.pack_mode = pack_mode or ("snapshot" if pack_id else "queue")
        self.pack_tasks_info = pack_tasks or []
        self.records: List[Dict[str, object]] = []
        self.planned_ids: set[str] = set()
        self.skip_cache: set[Tuple[str, str]] = set()
        self.apply_mode = options.apply_mode
        self.apply_gate: Optional[ApplyGate] = None
        if self.apply_mode != "off":
            self.apply_gate = ApplyGate(
                repo_root=self.config.root_dir,
                mode=self.apply_mode,
                cycle_id=self.cycle_id,
            )
        self.apply_reports: List[Dict[str, object]] = []
        self.task_attempts: Dict[str, int] = {}
        self.exhausted_tasks: set[str] = set()
        self.first_blocker: str = ""
        self.blocker_task: Optional[str] = None
        self.task_pattern = (
            re.compile(options.task_filter, re.IGNORECASE) if options.task_filter else None
        )
        self.report_path = (
            self.config.root_dir / "reports" / f"night_cycle_{self.cycle_id}.md"
        )
        ensure_dir(self.report_path.parent)
        self.runs_index_path = self.config.root_dir / "runs_index.jsonl"
        self.header_printed = False

    def run(self) -> int:
        start = self.now_fn()
        if not self.header_printed:
            print(
                "[NIGHT] cycle_id={cycle} max_runs={runs} max_minutes={minutes} "
                "stop_on_ask={ask} stop_on_deny={deny} retry_per_task={retries} "
                "dry_run={dry} pack_id={pack} pack_mode={mode}".format(
                    cycle=self.cycle_id,
                    runs=self.options.max_runs,
                    minutes=self.options.max_minutes,
                    ask=self.options.stop_on_ask,
                    deny=self.options.stop_on_deny,
                    retries=self.options.retry_per_task,
                    dry=self.options.dry_run,
                    pack=self.pack_id or "none",
                    mode=self.pack_mode,
                )
            )
            self.header_printed = True
        executed_attempts = 0
        planned_attempts = 0
        stop_reason = "completed"
        exit_code = 0
        if self.apply_gate:
            precheck = self.apply_gate.ensure_clean_worktree()
            if precheck.blocked:
                self._log_event(
                    task_id="",
                    outcome="APPLY_BLOCKED",
                    notes=precheck.reason,
                    ran=False,
                    cacheable=False,
                    extra={"applied": False, "blocked_path": None, "diff_summary": precheck.reason},
                )
                stop_reason = "apply_mode_blocked"
                exit_code = 1
                return exit_code
        try:
            while True:
                if self._exceeded_minutes(start):
                    stop_reason = "max_minutes"
                    exit_code = 1 if executed_attempts else 0
                    break
                limit_reached = (
                    executed_attempts >= self.options.max_runs
                    if not self.options.dry_run
                    else planned_attempts >= self.options.max_runs
                )
                if limit_reached:
                    stop_reason = "max_runs"
                    break
                task, blocker = self._next_task()
                if blocker == "blocked_needs_approval":
                    stop_reason = blocker
                    exit_code = 1
                    break
                if blocker == "no_matching_tasks":
                    stop_reason = blocker
                    break
                if blocker == "no_pending":
                    stop_reason = blocker
                    break
                if task is None:
                    stop_reason = "no_pending"
                    break
                if self.options.dry_run:
                    self._record_planned(task)
                    planned_attempts += 1
                    continue
                attempt_records, action = self._execute_with_retries(task)
                executed_attempts += sum(1 for record in attempt_records if record["ran"])
                if action == "continue":
                    if self.options.cooldown_seconds > 0:
                        self.sleep_fn(self.options.cooldown_seconds)
                    continue
                if action == "stop_ask":
                    stop_reason = "blocked_needs_approval"
                    exit_code = 1
                    break
                if action == "apply_blocked":
                    stop_reason = "apply_mode_blocked"
                    exit_code = 1
                    break
                if action == "stop_deny":
                    stop_reason = "stop_on_deny"
                    exit_code = 1
                    break
        except Exception as exc:  # pragma: no cover - defensive guard
            stop_reason = "exception"
            exit_code = 2
            self._log_event(
                task_id="",
                outcome="EXCEPTION",
                notes=str(exc),
                ran=False,
                cacheable=False,
            )
        finally:
            self._write_summary(stop_reason, executed_attempts, planned_attempts)
        return exit_code

    def _exceeded_minutes(self, start: float) -> bool:
        elapsed = self.now_fn() - start
        return elapsed >= max(self.options.max_minutes, 1) * 60

    def _next_task(self) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
        tasks = list(self.task_supplier() or [])
        seen_candidate = False
        filter_match = False if self.task_pattern else True
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("id", "UNKNOWN"))
            if task_id in self.exhausted_tasks:
                continue
            title = str(task.get("title", ""))
            if self.task_pattern and not self.task_pattern.search(f"{task_id}::{title}"):
                continue
            filter_match = True
            if self.options.dry_run and task_id in self.planned_ids:
                continue
            hold_state = task.get("hold_state")
            if hold_state:
                self._log_event(
                    task_id=task_id,
                    outcome="SKIPPED_HOLD",
                    notes=f"Hold '{hold_state}'",
                    ran=False,
                    cacheable=True,
                )
                continue
            status = str(task.get("status", "pending")).lower()
            if status == "needs_approval":
                message = f"Task {task_id} awaiting operator approval."
                self._log_event(
                    task_id=task_id,
                    outcome="BLOCKED_NEEDS_APPROVAL",
                    notes=message,
                    ran=False,
                    cacheable=not self.options.stop_on_ask,
                )
                if not self.first_blocker:
                    self.first_blocker = message
                    self.blocker_task = task_id
                if self.options.stop_on_ask:
                    return None, "blocked_needs_approval"
                continue
            if status != "pending":
                continue
            seen_candidate = True
            return task, None
        if not filter_match:
            return None, "no_matching_tasks"
        if not seen_candidate:
            return None, "no_pending"
        return None, None

    def _record_planned(self, task: Dict[str, object]) -> None:
        task_id = str(task.get("id", "UNKNOWN"))
        if task_id in self.planned_ids:
            return
        self.planned_ids.add(task_id)
        self._log_event(
            task_id=task_id,
            outcome="PLANNED",
            notes="Dry run planning only.",
            ran=False,
            cacheable=True,
        )

    def _execute_with_retries(
        self, task: Dict[str, object]
    ) -> Tuple[List[Dict[str, object]], str]:
        attempt_records: List[Dict[str, object]] = []
        max_attempts = max(self.options.retry_per_task, 0) + 1
        task_id = str(task.get("id", "UNKNOWN"))
        if task_id in self.exhausted_tasks:
            return attempt_records, "stop_deny" if self.options.stop_on_deny else "continue"
        attempts_used = self.task_attempts.get(task_id, 0)
        while attempts_used < max_attempts:
            attempt_number = attempts_used + 1
            record, task_result = self._run_single_attempt(task, attempt_number)
            attempt_records.append(record)
            attempts_used += 1
            self.task_attempts[task_id] = attempts_used
            outcome = record["outcome"]
            if (
                self.apply_gate
                and task_result is not None
                and outcome == "SUCCESS_ALLOW"
            ):
                decision = self.apply_gate.process_success(task_id, task_result.run_dir)
                self._record_apply_decision(task_id, decision)
                if decision.blocked:
                    return attempt_records, "apply_blocked"
            if outcome == "SUCCESS_ALLOW":
                self.task_attempts.pop(task_id, None)
                self.exhausted_tasks.discard(task_id)
                return attempt_records, "continue"
            if outcome == "BLOCKED_NEEDS_APPROVAL":
                return attempt_records, "stop_ask"
            if outcome in {"EXCEPTION", "FAILED_POLICY"}:
                self.exhausted_tasks.add(task_id)
                return attempt_records, "stop_deny"
            if outcome not in {"FAILED", "TIMEOUT"}:
                return attempt_records, "continue"
            if attempts_used < max_attempts:
                continue
            break
        self.exhausted_tasks.add(task_id)
        exhaustion_record = self._log_event(
            task_id=task_id,
            outcome="FAILED_MAX_RETRIES",
            notes=f"Exceeded {max_attempts} attempts within this cycle.",
            ran=False,
            cacheable=True,
        )
        attempt_records.append(exhaustion_record)
        if self.options.stop_on_deny:
            return attempt_records, "stop_deny"
        return attempt_records, "continue"

    def _run_single_attempt(
        self, task: Dict[str, object], attempt: int
    ) -> Tuple[Dict[str, object], Optional[TaskResult]]:
        task_id = str(task.get("id", "UNKNOWN"))
        started = self.now_fn()
        timestamp = utc_timestamp(compact=False)
        run_id = ""
        gate = "UNKNOWN"
        outcome = "FAILED"
        notes = ""
        exit_code = 1
        try:
            result = self.executor(task)
        except Exception as exc:  # pragma: no cover - executor safety
            notes = f"Executor crashed: {exc}"
            return self._log_event(
                task_id=task_id,
                outcome="EXCEPTION",
                notes=notes,
                ran=True,
                run_id=run_id,
                gate=gate,
                duration=self.now_fn() - started,
                timestamp=timestamp,
                exit_code=exit_code,
                attempt=attempt,
            ), None
        duration = self.now_fn() - started
        if result is None:
            notes = "Runner returned no result."
            return self._log_event(
                task_id=task_id,
                outcome=outcome,
                notes=notes,
                ran=True,
                run_id=run_id,
                gate=gate,
                duration=duration,
                timestamp=timestamp,
                exit_code=exit_code,
                attempt=attempt,
            ), None
        run_id = result.run_id or ""
        gate = (result.gate_report or {}).get("overall_status", result.status or "UNKNOWN")
        status = (result.status or "").upper()
        if status == "ALLOW":
            outcome = "SUCCESS_ALLOW"
            notes = "Task completed with ALLOW."
            exit_code = 0
        elif status == "ASK":
            outcome = "BLOCKED_NEEDS_APPROVAL"
            notes = "Gate returned ASK; operator approval required."
        else:
            if self._is_allowlist_rejection(result):
                outcome = "FAILED_POLICY"
                notes = "Command rejected by orchestrator allowlist."
            elif status == "FAILED" and self._is_timeout_result(result):
                outcome = "TIMEOUT"
                notes = "Task failed due to timeout."
            else:
                outcome = "FAILED"
                notes = f"Gate returned {status or 'UNKNOWN'}."
        return self._log_event(
            task_id=task_id,
            outcome=outcome,
            notes=notes,
            ran=True,
            run_id=run_id,
            gate=gate,
            duration=duration,
            timestamp=timestamp,
            exit_code=exit_code,
            attempt=attempt,
        ), result

    def _is_timeout_result(self, result: Optional[TaskResult]) -> bool:
        if not result or not result.gate_report:
            return False
        gates = result.gate_report.get("gates", [])
        for gate in gates:
            for reason in gate.get("reasons", []) or []:
                if "timeout" in str(reason).lower():
                    return True
        return False

    def _is_allowlist_rejection(self, result: Optional[TaskResult]) -> bool:
        if not result or not result.gate_report:
            return False
        gate_report = result.gate_report or {}
        phrases: List[str] = []
        for gate in gate_report.get("gates", []) or []:
            phrases.extend(str(reason) for reason in gate.get("reasons", []) or [])
        policy = gate_report.get("policy") or {}
        for violation in policy.get("violations", []) or []:
            detail = violation.get("detail")
            if detail:
                phrases.append(str(detail))
        blob = " ".join(phrases).lower()
        return "not on the allowlist" in blob

    def _record_apply_decision(self, task_id: str, decision: ApplyDecision) -> None:
        outcome = "APPLY_NO_CHANGES"
        if decision.blocked:
            outcome = "APPLY_BLOCKED"
        elif decision.applied:
            outcome = "APPLY_APPLIED"
        entry = {
            "task_id": task_id,
            "notes": decision.notes,
            "diff_summary": decision.diff_summary,
            "applied": decision.applied,
            "blocked_path": decision.blocked_path,
        }
        self.apply_reports.append(entry)
        self._log_event(
            task_id=task_id,
            outcome=outcome,
            notes=decision.notes,
            ran=False,
            cacheable=False,
            extra={
                "applied": decision.applied,
                "blocked_path": decision.blocked_path,
                "diff_summary": decision.diff_summary,
            },
        )

    def _log_event(
        self,
        *,
        task_id: str,
        outcome: str,
        notes: str,
        ran: bool,
        run_id: str = "",
        gate: str = "UNKNOWN",
        duration: float = 0.0,
        timestamp: Optional[str] = None,
        exit_code: int = 1,
        attempt: Optional[int] = None,
        cacheable: bool = False,
        extra: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        record = {
            "timestamp": timestamp or utc_timestamp(compact=False),
            "cycle_id": self.cycle_id,
            "task_id": task_id,
            "run_id": run_id,
            "outcome": outcome,
            "gate": gate,
            "exit_code": exit_code,
            "duration_sec": round(duration, 2),
            "notes": notes,
            "ran": ran,
            "attempt": attempt,
            "pack_id": self.pack_id,
            "pack_mode": self.pack_mode,
            "applied_mode": self.apply_mode,
            "applied": False,
            "blocked_path": None,
            "diff_summary": "",
        }
        if extra:
            record.update(extra)
        should_record = True
        if cacheable and not ran:
            key = (task_id, outcome)
            if key in self.skip_cache:
                should_record = False
            else:
                self.skip_cache.add(key)
        if should_record:
            self.records.append(record)
            if not self.options.dry_run:
                self._append_run_index(record)
        return record

    def _append_run_index(self, record: Dict[str, object]) -> None:
        ensure_dir(self.runs_index_path.parent)
        with self.runs_index_path.open("a", encoding="utf-8") as handle:
            json.dump(record, handle)
            handle.write("\n")

    def _write_summary(
        self,
        stop_reason: str,
        executed_attempts: int,
        planned_attempts: int,
    ) -> None:
        lines = [
            f"# Night Cycle Report ({self.cycle_id})",
            "",
        ]
        if self.options.dry_run:
            lines.extend(["DRY RUN: no tasks executed.", ""])
        if self.pack_id:
            pack_tasks = ", ".join(task.get("id", "?") for task in self.pack_tasks_info) or "none"
            lines.extend(
                [
                    "## Validation Pack",
                    f"- pack_id: {self.pack_id}",
                    f"- pack_mode: {self.pack_mode}",
                    f"- tasks: {pack_tasks}",
                    "",
                ]
            )
        lines.extend(
            [
                "## Configuration",
            f"- max_runs: {self.options.max_runs}",
            f"- max_minutes: {self.options.max_minutes}",
            f"- stop_on_ask: {self.options.stop_on_ask}",
            f"- stop_on_deny: {self.options.stop_on_deny}",
            f"- retry_per_task: {self.options.retry_per_task}",
            f"- cooldown_seconds: {self.options.cooldown_seconds}",
            f"- task_filter: {self.options.task_filter or 'none'}",
            f"- dry_run: {self.options.dry_run}",
            f"- purge_stale_runs: {self.options.purge_stale_runs}",
            f"- apply_mode: {self.apply_mode}",
            "",
                "## Outcomes",
                f"- Attempts executed: {executed_attempts}",
                f"- Planned (dry-run): {planned_attempts if self.options.dry_run else 0}",
                f"- Stop reason: {stop_reason}",
                f"- First blocker: {self.first_blocker or 'none'}",
                "",
                "## Records",
            ]
        )
        if not self.records:
            lines.append("- No records captured.")
        else:
            for record in self.records:
                if not record:
                    continue
                task_label = record.get("task_id") or "n/a"
                lines.append(
                    f"- {task_label}: {record.get('outcome')} (notes: {record.get('notes')})"
                )
        if self.apply_mode != "off":
            lines.extend([
                "",
                "## Apply Mode",
            ])
            if not self.apply_reports:
                lines.append("- No apply-mode actions recorded.")
            else:
                for entry in self.apply_reports:
                    summary = entry.get("diff_summary") or entry.get("notes")
                    label = entry.get("task_id") or "n/a"
                    lines.append(f"- {label}: {summary}")
        suggestion = self._suggest_action(stop_reason)
        lines.extend(
            [
                "",
                "## Suggested Action",
                f"- {suggestion}",
                "",
                f"Run index: {self.runs_index_path}",
                f"Report path: {self.report_path}",
            ]
        )
        safe_write_text(self.report_path, "\n".join(lines))

    def _suggest_action(self, stop_reason: str) -> str:
        if stop_reason == "blocked_needs_approval" and self.blocker_task:
            return (
                "Queue blocked on approval; run `python Tools/queue_ops.py list` followed by "
                f"`python Tools/queue_ops.py resume --task {self.blocker_task} --dry-run` before applying."
            )
        if stop_reason == "max_runs":
            return "Increase --max-runs or resume tomorrow after operator review."
        if stop_reason == "max_minutes":
            return "Shorten task list or raise --max-minutes within approved bounds."
        if stop_reason == "no_pending":
            return (
                "Queue is clear; either enqueue new contracts or rerun the validation pack "
                "with `python -m orchestrator.night_cycle --pack contracts/validation_pack`."
            )
        if stop_reason == "no_matching_tasks":
            return (
                "No tasks matched the filter; verify the regex or queue contents via "
                "`python Tools/queue_ops.py list`."
            )
        if stop_reason == "stop_on_deny":
            return (
                "Inspect the failing task logs, then run `python Tools/queue_ops.py reset --task <id> --dry-run` "
                "before applying any recovery command."
            )
        if stop_reason == "exception":
            return "Review night cycle logs; file incident before rerunning."
        if stop_reason == "apply_mode_blocked":
            return "Apply-mode blocked changes; clean the repo or limit edits to docs/tests before rerunning."
        return "Monitor queue status in the morning."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Night Cycle v1 controller")
    parser.add_argument("--max-runs", type=int, default=10, help="Maximum task attempts per cycle.")
    parser.add_argument(
        "--max-minutes",
        type=int,
        default=360,
        help="Maximum wall-clock minutes before ending the cycle.",
    )
    parser.add_argument(
        "--stop-on-ask",
        type=_parse_bool,
        default=True,
        help="Stop the cycle when an ASK verdict is encountered (default: true).",
    )
    parser.add_argument(
        "--stop-on-deny",
        type=_parse_bool,
        default=True,
        help="Stop the cycle on BLOCK/FAIL verdicts (default: true).",
    )
    parser.add_argument(
        "--retry-per-task",
        type=int,
        default=1,
        help="Additional retries per task when recoverable failures occur.",
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=int,
        default=10,
        help="Pause between task attempts to reduce churn (default: 10).",
    )
    parser.add_argument(
        "--task-filter",
        help="Regex applied to task id/title to constrain which entries run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the cycle without executing any tasks or touching the queue.",
    )
    parser.add_argument(
        "--pack",
        help="Path to a validation pack directory (contracts/validation_pack) for synthetic runs.",
    )
    parser.add_argument(
        "--pack-mode",
        choices=["snapshot", "enqueue"],
        default="snapshot",
        help="How to load validation packs (snapshot keeps the main queue untouched).",
    )
    parser.add_argument(
        "--pack-id",
        help="Override the pack identifier recorded in reports and run index entries.",
    )
    parser.add_argument(
        "--purge-stale-runs",
        action="store_true",
        help="Enable retention purge of prior run bundles during the cycle (default: disabled).",
    )
    parser.add_argument(
        "--apply-mode",
        choices=["off", "docs_tests"],
        default="off",
        help="Automatically apply safe diffs (docs/tests only) when set to docs_tests.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    options = CycleOptions(
        max_runs=max(1, args.max_runs),
        max_minutes=max(1, args.max_minutes),
        stop_on_ask=bool(args.stop_on_ask),
        stop_on_deny=bool(args.stop_on_deny),
        retry_per_task=max(0, args.retry_per_task),
        cooldown_seconds=max(0, args.cooldown_seconds),
        task_filter=args.task_filter,
        dry_run=args.dry_run,
        purge_stale_runs=args.purge_stale_runs,
        apply_mode=args.apply_mode,
    )
    config = OrchestratorConfig.load()
    config.ensure_directories()
    agent_registry = AgentRegistry(config.agent_registry_path)
    workspace_manager = WorkspaceManager(config.workspaces_dir)
    gatekeeper = Gatekeeper()
    task_runner = TaskRunner(
        config,
        agent_registry,
        workspace_manager,
        gatekeeper,
        retention_enabled=bool(args.purge_stale_runs),
    )
    queue_manager = QueueManager(config.queue_path, config.queue_contracts_dir, config.root_dir)

    def executor(task: Dict[str, object]) -> Optional[TaskResult]:
        return task_runner._execute_task(task, queue_manager)  # type: ignore[attr-defined]

    task_supplier: Callable[[], Iterable[Dict[str, object]]] = queue_manager.all_tasks
    pack_id: Optional[str] = None
    pack_tasks: Optional[List[Dict[str, object]]] = None
    pack_mode = "queue"
    cleanup: Callable[[], None] = lambda: None
    cycle_id = utc_timestamp()

    if args.pack:
        pack_path = Path(args.pack).resolve()
        pack_mode = args.pack_mode or "snapshot"
        pack_context = prepare_pack_context(
            config=config,
            pack_path=pack_path,
            pack_mode=pack_mode,
            cycle_id=cycle_id,
            pack_id_override=args.pack_id,
        )
        task_supplier = pack_context.task_supplier
        executor = pack_context.executor
        pack_id = pack_context.pack.pack_id
        pack_tasks = pack_context.tasks
        cleanup = pack_context.cleanup

    cycle = NightCycle(
        config=config,
        task_supplier=task_supplier,
        executor=executor,
        options=options,
        cycle_id=cycle_id,
        pack_id=pack_id,
        pack_mode=pack_mode,
        pack_tasks=pack_tasks,
    )
    try:
        return cycle.run()
    finally:
        cleanup()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())