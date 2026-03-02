from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .approvals import OperatorApprovalStore
from .command_controls import CommandAllowlist
from .config import OrchestratorConfig
from .contracts import Contract, load_contract
from .diffing import RegressionGate, build_diff_report, find_previous_run
from .error_classifier import UnityErrorClassifier
from .gates import Gatekeeper
from .log_parser import UnityLogParser
from .registry import AgentProfile, AgentRegistry
from .report import ReportEmitter
from .utils import ensure_dir, read_json, safe_write_text, slugify, utc_timestamp, write_json
from .workspace import WorkspaceContext, WorkspaceManager


@dataclass
class TaskResult:
    task_id: str
    run_id: str
    run_dir: Path
    gate_report: Dict[str, Any]
    command_results: List[Dict[str, Any]]
    status: str
    no_change_detected: bool = False
    regression_verdict: Optional[str] = None


@dataclass(frozen=True)
class LoopSettings:
    enabled: bool
    max_attempts: int
    max_minutes: int


class QueueManager:
    DEFAULT_AGENTS = ["builder", "qa", "auditor"]
    QUEUE_FILE_PATTERN = re.compile(r"^(\d{4})_")
    SUPPORTED_SUFFIXES = {".md", ".markdown", ".yaml", ".yml"}

    def __init__(self, queue_path: Path, queue_contracts_dir: Path, root_dir: Path) -> None:
        self.queue_path = queue_path
        self.queue_contracts_dir = queue_contracts_dir
        self.root_dir = root_dir
        ensure_dir(queue_path.parent)
        ensure_dir(queue_contracts_dir)
        if not queue_path.exists():
            write_json(queue_path, {"tasks": []})
        self._payload: Dict[str, Any] = {"tasks": []}
        self._blocked_reason: str = ""
        self.refresh()

    def refresh(self) -> None:
        self._payload = read_json(self.queue_path, default={"tasks": []})
        self._sync_with_directory()

    def pending_tasks(self) -> List[Dict[str, Any]]:
        self.refresh()
        tasks = sorted(self._payload.get("tasks", []), key=self._sort_key)
        allowed = {"pending"}
        for task in tasks:
            status = task.get("status", "pending")
            if status == "completed":
                continue
            if status in allowed:
                self._set_blocked_reason(None)
                return [task]
            if status == "needs_approval":
                reason = f"Task {task.get('id', 'UNKNOWN')} requires operator approval before continuing."
            else:
                reason = f"Task {task.get('id', 'UNKNOWN')} is {status}; awaiting operator action."
            last_error = task.get("last_error")
            if last_error:
                reason = f"{reason} Last error: {last_error}."
            self._set_blocked_reason(reason)
            return []
        self._set_blocked_reason(None)
        return []

    def recover_stale_tasks(self) -> List[str]:
        self.refresh()
        recovered: List[str] = []
        for task in self._payload.get("tasks", []):
            if task.get("status") == "running":
                task_id = task.get("id", "UNKNOWN")
                task["status"] = "failed"
                task["current_run_id"] = None
                task["last_error"] = "Recovered stale running state"
                task["last_run_status"] = "ERROR"
                task["last_run"] = utc_timestamp()
                recovered.append(task_id)
        if recovered:
            self._persist()
        return recovered

    @property
    def blocked_reason(self) -> str:
        return self._blocked_reason

    def all_tasks(self) -> List[Dict[str, Any]]:
        self.refresh()
        return sorted(self._payload.get("tasks", []), key=self._sort_key)

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> None:
        self.refresh()
        for task in self._payload.get("tasks", []):
            if task.get("id") == task_id:
                task.update(updates)
                break
        self._persist()

    def _persist(self) -> None:
        write_json(self.queue_path, self._payload)

    def _set_blocked_reason(self, reason: Optional[str]) -> None:
        self._blocked_reason = reason or ""

    def _sync_with_directory(self) -> None:
        tasks_by_id = {task.get("id"): task for task in self._payload.get("tasks", [])}
        discovered: List[str] = []
        dirty = False
        for entry in sorted(self.queue_contracts_dir.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in self.SUPPORTED_SUFFIXES:
                continue
            match = self.QUEUE_FILE_PATTERN.match(entry.name)
            if not match:
                continue
            defaults = self._discover_defaults(entry)
            task_id = defaults["task_id"]
            discovered.append(task_id)
            relative_path = self._relative_contract_path(entry)
            record = tasks_by_id.get(task_id)
            if record is None:
                record = {
                    "id": task_id,
                    "title": defaults["title"],
                    "contract_path": relative_path,
                    "target_repo": defaults.get("target_repo"),
                    "agents": defaults["agents"],
                    "status": "pending",
                }
                tasks_by_id[task_id] = record
                dirty = True
            else:
                if record.get("contract_path") != relative_path:
                    record["contract_path"] = relative_path
                    dirty = True
                if not record.get("title") and defaults["title"]:
                    record["title"] = defaults["title"]
                    dirty = True
                if not record.get("agents") and defaults["agents"]:
                    record["agents"] = defaults["agents"]
                    dirty = True
                if not record.get("target_repo") and defaults.get("target_repo"):
                    record["target_repo"] = defaults.get("target_repo")
                    dirty = True
        ordered_ids = sorted(set(discovered), key=lambda value: self._safe_int(value))
        ordered_set = set(ordered_ids)
        new_task_list = [tasks_by_id[task_id] for task_id in ordered_ids]

        # Preserve tasks that were curated manually (no backing contract file).
        original_order = [task.get("id") for task in self._payload.get("tasks", [])]
        for task_id in original_order:
            if not task_id or task_id in ordered_set:
                continue
            record = tasks_by_id.get(task_id)
            if record:
                new_task_list.append(record)

        if new_task_list != self._payload.get("tasks", []):
            dirty = True
        if dirty:
            self._payload["tasks"] = new_task_list
            self._persist()
        else:
            self._payload["tasks"] = new_task_list

    def _discover_defaults(self, path: Path) -> Dict[str, Any]:
        defaults = {
            "task_id": self._extract_task_id_from_name(path),
            "title": path.stem.replace("_", " ").title(),
            "agents": self.DEFAULT_AGENTS,
            "target_repo": None,
        }
        try:
            contract = load_contract(path)
        except Exception as exc:  # pragma: no cover - defensive parse guard
            print(f"[orchestrator] Warning: unable to parse contract {path.name}: {exc}")
            return defaults
        metadata = contract.metadata
        defaults["task_id"] = contract.task_id or defaults["task_id"]
        defaults["title"] = metadata.get("Objective", defaults["title"])
        agents_meta = metadata.get("Agents")
        normalized_agents = self._normalize_agents(agents_meta)
        if normalized_agents:
            defaults["agents"] = normalized_agents
        target_repo = metadata.get("Target Repo Path") or metadata.get("Target Repo")
        if target_repo:
            defaults["target_repo"] = target_repo
        return defaults

    def _normalize_agents(self, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            trimmed = value.strip()
            return [trimmed] if trimmed else []
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            return normalized
        return []

    def _relative_contract_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root_dir)).replace("\\", "/")
        except ValueError:
            return str(path)

    def _extract_task_id_from_name(self, path: Path) -> str:
        match = self.QUEUE_FILE_PATTERN.match(path.name)
        if match:
            return match.group(1)
        return path.stem[:4].zfill(4)

    def _sort_key(self, task: Dict[str, Any]) -> int:
        return self._safe_int(task.get("id", "0"))

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


class TaskRunner:
    MAX_RUN_BUNDLES = 25
    MAX_LOOP_ATTEMPTS = 3
    MAX_LOOP_MINUTES = 30
    LOOP_DEFAULT_ATTEMPTS = 2
    LOOP_DEFAULT_MINUTES = 20
    RUN_ID_PATTERN = re.compile(r"^\d{8}_\d{6}_\d{4}$")
    UNITY_LOG_RELATIVE_PATH = Path("scripts") / "logs" / "Editor.log"
    UNITY_SUMMARY_RELATIVE_PATH = Path("Tools") / "CI" / "unity_log_summary.json"
    UNITY_CLASSIFICATION_RELATIVE_PATH = Path("Tools") / "CI" / "unity_error_classification.json"
    PLAYMODE_TICK_PATTERN = re.compile(
        r"\[PLAYMODE\]\s+tick_ok\s+(?:frames|ticks)=(\d+)", re.IGNORECASE
    )

    def __init__(
        self,
        config: OrchestratorConfig,
        agent_registry: AgentRegistry,
        workspace_manager: WorkspaceManager,
        gatekeeper: Gatekeeper,
        *,
        retention_enabled: bool = True,
    ) -> None:
        self.config = config
        self.agent_registry = agent_registry
        self.workspace_manager = workspace_manager
        self.gatekeeper = gatekeeper
        self.retention_enabled = retention_enabled
        self.log_parser = UnityLogParser()
        self.error_classifier = UnityErrorClassifier()
        self.approval_store = OperatorApprovalStore(self.config.approvals_path)
        self.command_allowlist = CommandAllowlist(self.config.command_allowlist_path)

    def run_once(self, queue_manager: QueueManager) -> Optional[TaskResult]:
        pending = queue_manager.pending_tasks()
        if not pending:
            if queue_manager.blocked_reason:
                print(f"[orchestrator] Queue blocked: {queue_manager.blocked_reason}")
            else:
                print("[orchestrator] No pending tasks in queue.")
            return None
        task = pending[0]
        return self._execute_task(task, queue_manager)

    def run_all(self, queue_manager: QueueManager) -> List[TaskResult]:
        results: List[TaskResult] = []
        while True:
            pending = queue_manager.pending_tasks()
            if not pending:
                if queue_manager.blocked_reason:
                    print(f"[orchestrator] Queue blocked: {queue_manager.blocked_reason}")
                elif not results:
                    print("[orchestrator] No pending tasks in queue.")
                break
            result = self._execute_task(pending[0], queue_manager)
            if not result:
                break
            results.append(result)
            if result.status != "ALLOW":
                print(f"[orchestrator] Halting queue after task {result.task_id} returned {result.status}.")
                break
        return results

    def _execute_task(self, task: Dict[str, Any], queue_manager: QueueManager) -> Optional[TaskResult]:
        contract_path = self._resolve_path(task.get("contract_path"))
        loop_settings = self._resolve_loop_settings(contract_path)
        if not loop_settings.enabled:
            return self._execute_task_attempt(task, queue_manager)
        return self._execute_with_loop(task, queue_manager, loop_settings, contract_path)

    def _execute_task_attempt(self, task: Dict[str, Any], queue_manager: QueueManager) -> Optional[TaskResult]:
        task_id = task.get("id", "UNKNOWN")
        timestamp = utc_timestamp()
        contract_path = self._resolve_path(task.get("contract_path"))
        print(f"[orchestrator] Starting task {task_id} using contract {contract_path}.")
        run_id = f"{timestamp}_{task_id}"
        run_dir = ensure_dir(self.config.runs_dir / run_id)
        if not contract_path.exists():
            failure_reason = f"Contract {contract_path} missing"
            print(f"[orchestrator] {failure_reason}; marking task as failed.")
            gate_report = self._build_failure_gate_report(task_id, failure_reason)
            retention_info = self._apply_retention(run_id)
            summary_text = self._build_summary(
                None,
                gate_report,
                [],
                [],
                [],
                retention_info,
                diff_report=None,
                additional_notes=[f"Last error: {failure_reason}"],
            )
            self._emit_gate_report(None, run_dir, gate_report)
            self._emit_command_results(None, run_dir, [])
            self._emit_summary(None, run_dir, summary_text)
            run_meta = {
                "task_id": task_id,
                "run_id": run_id,
                "timestamp": timestamp,
                "contract_path": str(contract_path),
                "workspace_path": "",
                "run_dir": str(run_dir),
                "agents": [],
                "gate_overall": gate_report["overall_status"],
                "retention": retention_info,
                "last_error": failure_reason,
                "policy": gate_report.get("policy", {}),
                "diff_report": {
                    "path": "",
                    "regression_verdict": None,
                    "no_change_detected": False,
                    "regression_config": {"no_change_verdict": "ALLOW"},
                },
            }
            write_json(run_dir / "run_meta.json", run_meta)
            queue_manager.update_task(
                task_id,
                {
                    "status": "failed",
                    "last_run": timestamp,
                    "last_run_status": "ERROR",
                    "last_run_dir": str(run_dir),
                    "last_run_id": run_id,
                    "current_run_id": None,
                    "last_error": failure_reason,
                },
            )
            return TaskResult(
                task_id=task_id,
                run_id=run_id,
                run_dir=run_dir,
                gate_report=gate_report,
                command_results=[],
                status="FAILED",
                no_change_detected=False,
                regression_verdict=None,
            )

        queue_manager.update_task(
            task_id,
            {
                "status": "running",
                "current_run_id": run_id,
                "last_run": timestamp,
                "last_error": "",
            },
        )
        contract: Optional[Contract] = None
        workspace_ctx: Optional[WorkspaceContext] = None
        reporter: Optional[ReportEmitter] = None
        agents: List[AgentProfile] = []
        command_results: List[Dict[str, Any]] = []
        gate_report: Optional[Dict[str, Any]] = None
        artifacts_info: List[Dict[str, Any]] = []
        retention_info: Optional[Dict[str, Any]] = None
        patch_content = ""
        task_result: Optional[TaskResult] = None
        result_status = "FAILED"
        queue_status = "failed"
        last_error = ""
        last_run_status_value = "ERROR"
        failure_reason = ""
        run_meta_emitted = False
        diff_report_payload: Optional[Dict[str, Any]] = None
        regression_config: Dict[str, Any] = {"no_change_verdict": "ALLOW"}
        no_change_detected = False
        playmode_meta: Dict[str, Any] = {}
        summary_notes: List[str] = []
        try:
            contract = load_contract(contract_path)
            target_value = (
                task.get("target_repo")
                or contract.metadata.get("Target Repo Path")
                or contract.metadata.get("Target Repo")
            )
            target_repo = Path(target_value).expanduser() if target_value else self.config.root_dir / "targets" / task_id
            workspace_ctx = self.workspace_manager.prepare(task_id, contract_path, target_repo, timestamp)
            reporter = ReportEmitter(workspace_ctx, run_dir)
            reporter.copy_contract()
            agent_ids = task.get("agents") or self._default_agents()
            agents = self._load_agents(agent_ids)
            plan_content = self._build_plan(contract, agents, target_repo)
            reporter.emit_plan(plan_content)
            regression_config = self._extract_regression_config(contract)
            command_results = self._run_commands(contract.commands, workspace_ctx, contract)
            self._emit_command_results(reporter, run_dir, command_results)
            self._maybe_generate_log_summary(contract, workspace_ctx)
            artifacts_info = self._collect_artifacts(workspace_ctx, contract)
            playmode_context = self._evaluate_playmode_context(contract, workspace_ctx)
            playmode_meta = self._playmode_meta(contract, playmode_context)
            if playmode_context.get("note"):
                summary_notes.append(f"- {playmode_context['note']}")
            if playmode_context.get("halt"):
                gate_report = self._build_playmode_gate_report(task_id, playmode_context["reason"])
                self._emit_gate_report(reporter, run_dir, gate_report)
                retention_info = self._apply_retention(run_id)
                halt_notes = summary_notes + [f"- Play mode gating failed: {playmode_context['reason']}"]
                summary_text = self._build_summary(
                    contract,
                    gate_report,
                    command_results,
                    agents,
                    artifacts_info,
                    retention_info,
                    diff_report=None,
                    additional_notes=halt_notes,
                )
                self._emit_summary(reporter, run_dir, summary_text)
                run_meta = {
                    "task_id": task_id,
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "contract_path": str(contract_path),
                    "workspace_path": str(workspace_ctx.base_path),
                    "run_dir": str(run_dir),
                    "agents": [agent.id for agent in agents],
                    "gate_overall": gate_report["overall_status"],
                    "retention": retention_info,
                    "policy": gate_report.get("policy", {}),
                    "diff_report": {
                        "path": "",
                        "regression_verdict": None,
                        "no_change_detected": False,
                        "regression_config": regression_config,
                    },
                    "playmode": playmode_meta,
                }
                write_json(run_dir / "run_meta.json", run_meta)
                run_meta_emitted = True
                result_status = "ASK"
                queue_status = "needs_approval"
                last_error = playmode_context["reason"]
                last_run_status_value = "ASK"
                task_result = TaskResult(
                    task_id=task_id,
                    run_id=run_id,
                    run_dir=run_dir,
                    gate_report=gate_report,
                    command_results=command_results,
                    status=result_status,
                    no_change_detected=False,
                    regression_verdict=None,
                )
                return task_result
            if self._agents_can_write(agents):
                patch_content = self._generate_patch(workspace_ctx, contract, agents)
                reporter.emit_patch(f"{task_id}_changes.patch", patch_content)
            gate_report = self.gatekeeper.evaluate(
                contract=contract,
                agent_profiles=agents,
                patch_text=patch_content,
                command_results=command_results,
                artifact_info=artifacts_info,
            )
            self._emit_gate_report(reporter, run_dir, gate_report)
            self._record_artifact_manifest(workspace_ctx, contract, gate_report, artifacts_info)
            diff_report_payload: Optional[Dict[str, Any]] = None
            previous_run_dir = find_previous_run(self.config.runs_dir, task_id, run_id)
            if previous_run_dir:
                current_summary_path = workspace_ctx.repo_path / self.UNITY_SUMMARY_RELATIVE_PATH
                current_classification_path = workspace_ctx.repo_path / self.UNITY_CLASSIFICATION_RELATIVE_PATH
                try:
                    diff_report_payload, regression_gate = build_diff_report(
                        current_run_dir=run_dir,
                        previous_run_dir=previous_run_dir,
                        gate_report=gate_report,
                        command_results=command_results,
                        current_summary_path=current_summary_path,
                        current_classification_path=current_classification_path,
                        regression_config=regression_config,
                    )
                    if diff_report_payload:
                        self._emit_diff_report(reporter, run_dir, diff_report_payload)
                        gate_report = self._attach_regression_gate(gate_report, regression_gate)
                        self._emit_gate_report(reporter, run_dir, gate_report)
                        no_change_detected = bool(diff_report_payload.get("no_change_detected", False))
                except Exception as diff_exc:
                    print(f"[orchestrator] Failed to generate diff report for task {task_id}: {diff_exc}")
                    diff_report_payload = None
            retention_info = self._apply_retention(run_id)
            summary_text = self._build_summary(
                contract,
                gate_report,
                command_results,
                agents,
                artifacts_info,
                retention_info,
                diff_report=diff_report_payload,
                additional_notes=summary_notes,
            )
            self._emit_summary(reporter, run_dir, summary_text)
            run_meta = {
                "task_id": task_id,
                "run_id": run_id,
                "timestamp": timestamp,
                "contract_path": str(contract_path),
                "workspace_path": str(workspace_ctx.base_path),
                "run_dir": str(run_dir),
                "agents": [agent.id for agent in agents],
                "gate_overall": gate_report["overall_status"],
                "retention": retention_info,
                "policy": gate_report.get("policy", {}),
                "diff_report": {
                    "path": str(run_dir / "diff_report.json") if diff_report_payload else "",
                    "regression_verdict": (diff_report_payload or {}).get("regression_verdict"),
                    "no_change_detected": no_change_detected,
                    "regression_config": regression_config,
                },
                "playmode": playmode_meta,
            }
            write_json(run_dir / "run_meta.json", run_meta)
            run_meta_emitted = True
            overall = gate_report["overall_status"].upper()
            result_status = gate_report["overall_status"]
            queue_status = self._queue_status_for_overall(overall)
            last_run_status_value = gate_report["overall_status"]
            gate_failure_reason = self._summarize_gate_failure(gate_report)
            last_error = "" if queue_status == "completed" else gate_failure_reason or f"Gate result {overall}"
            task_result = TaskResult(
                task_id=task_id,
                run_id=run_id,
                run_dir=run_dir,
                gate_report=gate_report,
                command_results=command_results,
                status=result_status,
                no_change_detected=no_change_detected,
                regression_verdict=(diff_report_payload or {}).get("regression_verdict"),
            )
        except Exception as exc:
            failure_reason = str(exc) or exc.__class__.__name__
            print(f"[orchestrator] Task {task_id} crashed: {failure_reason}")
            if gate_report is None:
                gate_report = self._build_failure_gate_report(task_id, failure_reason)
            self._emit_gate_report(reporter, run_dir, gate_report)
            self._emit_command_results(reporter, run_dir, command_results)
            if retention_info is None:
                retention_info = self._apply_retention(run_id)
            summary_text = self._build_summary(
                contract,
                gate_report,
                command_results,
                agents,
                artifacts_info,
                retention_info,
                diff_report=diff_report_payload,
                additional_notes=summary_notes + [f"- Last error: {failure_reason}"],
            )
            self._emit_summary(reporter, run_dir, summary_text)
            if not run_meta_emitted:
                run_meta = {
                    "task_id": task_id,
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "contract_path": str(contract_path),
                    "workspace_path": str(workspace_ctx.base_path) if workspace_ctx else "",
                    "run_dir": str(run_dir),
                    "agents": [agent.id for agent in agents] if agents else [],
                    "gate_overall": gate_report["overall_status"],
                    "retention": retention_info or {},
                    "last_error": failure_reason,
                    "policy": gate_report.get("policy", {}),
                    "diff_report": {
                        "path": str(run_dir / "diff_report.json") if diff_report_payload else "",
                        "regression_verdict": (diff_report_payload or {}).get("regression_verdict"),
                        "no_change_detected": no_change_detected,
                        "regression_config": regression_config,
                    },
                    "playmode": playmode_meta,
                }
                write_json(run_dir / "run_meta.json", run_meta)
                run_meta_emitted = True
            result_status = "FAILED"
            queue_status = "failed"
            last_error = failure_reason
            last_run_status_value = "ERROR"
            task_result = TaskResult(
                task_id=task_id,
                run_id=run_id,
                run_dir=run_dir,
                gate_report=gate_report,
                command_results=command_results,
                status=result_status,
                no_change_detected=no_change_detected,
                regression_verdict=(diff_report_payload or {}).get("regression_verdict"),
            )
        finally:
            if retention_info is None:
                retention_info = self._apply_retention(run_id)
            if reporter and workspace_ctx:
                try:
                    reporter.mirror_logs()
                    reporter.mirror_artifacts()
                except Exception as mirror_exc:
                    print(f"[orchestrator] Failed to mirror workspace artifacts for task {task_id}: {mirror_exc}")
            queue_manager.update_task(
                task_id,
                {
                    "status": queue_status,
                    "last_run": timestamp,
                    "last_run_status": last_run_status_value,
                    "last_run_dir": str(run_dir),
                    "last_run_id": run_id,
                    "current_run_id": None,
                    "last_error": last_error,
                },
            )
        if gate_report is None:
            gate_report = self._build_failure_gate_report(task_id, "Unknown failure state")
        if task_result is None:
            task_result = TaskResult(
                task_id=task_id,
                run_id=run_id,
                run_dir=run_dir,
                gate_report=gate_report,
                command_results=command_results,
                status=result_status,
                no_change_detected=no_change_detected,
                regression_verdict=(diff_report_payload or {}).get("regression_verdict"),
            )
        return task_result

    def _execute_with_loop(
        self,
        task: Dict[str, Any],
        queue_manager: QueueManager,
        loop_settings: LoopSettings,
        contract_path: Path,
    ) -> Optional[TaskResult]:
        task_id = task.get("id", "UNKNOWN")
        attempts: List[Dict[str, Any]] = []
        final_result: Optional[TaskResult] = None
        stop_reason = "loop_not_started"
        started = time.time()
        attempt_index = 0
        while attempt_index < loop_settings.max_attempts:
            # enforce total runtime guard before firing new attempt
            if attempt_index > 0:
                elapsed_minutes = (time.time() - started) / 60
                if elapsed_minutes >= loop_settings.max_minutes:
                    stop_reason = "time_limit_exceeded"
                    break
                time.sleep(1)
            attempt_index += 1
            result = self._execute_task_attempt(task, queue_manager)
            final_result = result
            attempt_record = {
                "attempt": attempt_index,
                "run_id": result.run_id if result else "",
                "status": (result.status if result else "NO_RESULT") or "UNKNOWN",
                "timestamp": utc_timestamp(compact=False),
                "operator_approval_applied": False,
                "reason": "",
                "run_dir": str(result.run_dir) if result else "",
            }
            attempts.append(attempt_record)
            if result is None:
                stop_reason = "no_result"
                attempt_record["reason"] = stop_reason
                break
            no_change_flag = bool(getattr(result, "no_change_detected", False))
            attempt_record["no_change_detected"] = no_change_flag
            verdict = (result.status or "").upper()
            if no_change_flag:
                stop_reason = "no_change_detected"
                attempt_record["reason"] = stop_reason
                break
            if verdict == "ALLOW":
                stop_reason = "allow"
                attempt_record["reason"] = stop_reason
                break
            if verdict == "ASK":
                approval_applied = self.approval_store.consume(result.task_id, result.run_id)
                attempt_record["operator_approval_applied"] = approval_applied
                if approval_applied:
                    attempt_record["reason"] = "operator_approval_consumed"
                    continue
                stop_reason = "awaiting_operator"
                attempt_record["reason"] = stop_reason
                break
            if verdict == "BLOCK":
                stop_reason = "gate_block"
                attempt_record["reason"] = stop_reason
                break
            if not self._can_retry(result):
                stop_reason = "non_recoverable_gate"
                attempt_record["reason"] = stop_reason
                break
            elapsed_minutes = (time.time() - started) / 60
            if elapsed_minutes >= loop_settings.max_minutes:
                stop_reason = "time_limit_exceeded"
                attempt_record["reason"] = stop_reason
                break
            if attempt_index >= loop_settings.max_attempts:
                stop_reason = "max_attempts_reached"
                attempt_record["reason"] = stop_reason
                break
            attempt_record["reason"] = "retrying"
        else:
            stop_reason = "max_attempts_reached"
        self._write_fix_loop_report(
            task_id,
            attempts,
            stop_reason,
            loop_settings,
            contract_path,
            retry_performed=len(attempts) > 1,
        )
        return final_result

    def _write_fix_loop_report(
        self,
        task_id: str,
        attempts: List[Dict[str, Any]],
        stop_reason: str,
        loop_settings: LoopSettings,
        contract_path: Path,
        *,
        retry_performed: bool,
    ) -> None:
        if not attempts:
            return
        payload = {
            "task_id": task_id,
            "stop_reason": stop_reason,
            "loop_settings": asdict(loop_settings),
            "contract_path": str(contract_path),
            "retry_performed": retry_performed,
            "attempts": [
                {
                    "attempt": entry.get("attempt"),
                    "run_id": entry.get("run_id"),
                    "status": entry.get("status"),
                    "timestamp": entry.get("timestamp"),
                    "reason": entry.get("reason"),
                    "operator_approval_applied": entry.get("operator_approval_applied", False),
                    "no_change_detected": entry.get("no_change_detected", False),
                }
                for entry in attempts
            ],
            "operator_approvals_consumed": sum(1 for entry in attempts if entry.get("operator_approval_applied")),
            "generated_at": utc_timestamp(compact=False),
        }
        for entry in attempts:
            run_dir = entry.get("run_dir")
            if not run_dir:
                continue
            destination = Path(run_dir) / "fix_loop_report.json"
            try:
                write_json(destination, payload)
            except Exception as exc:  # pragma: no cover - defensive persistence guard
                print(f"[orchestrator] Failed to write fix loop report to {destination}: {exc}")

    def _can_retry(self, result: TaskResult) -> bool:
        gate_report = result.gate_report or {}
        gates = gate_report.get("gates", [])
        recoverable = False
        for gate in gates:
            status = (gate.get("status") or "").upper()
            if status in {"ALLOW", "INFO"}:
                continue
            name = (gate.get("name") or "").lower()
            if name in {"policy", "signal"}:
                return False
            if name == "regression":
                return False
            recoverable = True
        return recoverable or not gates

    def _resolve_loop_settings(self, contract_path: Path) -> LoopSettings:
        defaults = LoopSettings(
            enabled=False,
            max_attempts=self.LOOP_DEFAULT_ATTEMPTS,
            max_minutes=self.LOOP_DEFAULT_MINUTES,
        )
        if not contract_path.exists():
            return defaults
        try:
            contract = load_contract(contract_path)
        except Exception:
            return defaults
        metadata = contract.metadata or {}
        loop_section = metadata.get("Fix Loop Controller") or metadata.get("Loop Controller")
        if not loop_section:
            loop_section = metadata.get("Controls", {}).get("Fix Loop Controller")
        if not loop_section:
            return defaults
        enabled = self._coerce_bool(loop_section.get("Enabled", False))
        attempts_hint = loop_section.get("Max Attempts") or loop_section.get("Attempts") or self.LOOP_DEFAULT_ATTEMPTS
        minutes_hint = loop_section.get("Max Minutes") or loop_section.get("Minutes") or self.LOOP_DEFAULT_MINUTES
        max_attempts = self._clamp_int(
            attempts_hint,
            minimum=1,
            maximum=self.MAX_LOOP_ATTEMPTS,
            default=self.LOOP_DEFAULT_ATTEMPTS,
        )
        max_minutes = self._clamp_int(
            minutes_hint,
            minimum=5,
            maximum=self.MAX_LOOP_MINUTES,
            default=self.LOOP_DEFAULT_MINUTES,
        )
        return LoopSettings(enabled=enabled, max_attempts=max_attempts, max_minutes=max_minutes)

    def _extract_regression_config(self, contract: Contract | None) -> Dict[str, Any]:
        default = {"no_change_verdict": "ALLOW"}
        if not contract:
            return dict(default)
        metadata = contract.metadata or {}
        regression_meta = metadata.get("Regression") or {}
        if not isinstance(regression_meta, dict):
            regression_meta = {}
        raw_value = regression_meta.get("NoChangeVerdict", default["no_change_verdict"])
        normalized = str(raw_value).upper()
        if normalized not in {"ALLOW", "ASK", "BLOCK"}:
            normalized = default["no_change_verdict"]
        return {"no_change_verdict": normalized}

    def _coerce_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "y", "enable", "enabled"}
        return False

    def _clamp_int(self, value: Any, minimum: int, maximum: int, default: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(number, maximum))

    def _load_agents(self, agent_ids: Iterable[str]) -> List[AgentProfile]:
        return self.agent_registry.get_many(agent_ids)

    def _default_agents(self) -> List[str]:
        return QueueManager.DEFAULT_AGENTS.copy()

    def _agents_can_write(self, agents: Iterable[AgentProfile]) -> bool:
        return any("write_patch" in agent.allowed_actions for agent in agents)

    def _build_plan(self, contract: Contract, agents: List[AgentProfile], target_repo: Path) -> str:
        objective = contract.metadata.get("Objective", "Undefined objective")
        dod = contract.metadata.get("Definition of Done", [])
        dod_lines = dod if isinstance(dod, list) else [dod]
        agent_roles = ", ".join(f"{agent.id}({agent.role})" for agent in agents)
        plan_steps = [
            "Confirm contract metadata and risk constraints.",
            "Create isolated workspace and copy target repository.",
            "Collect Unity logs into artifacts bucket.",
            "Parse logs for errors and emit structured JSON.",
            "Compile summary, gate results, and patches for review.",
        ]
        lines = [
            f"# Plan for Task {contract.task_id}",
            "",
            f"**Objective:** {objective}",
            f"**Agents:** {agent_roles}",
            f"**Target Repo:** {target_repo if target_repo else 'Not provided'}",
            "",
            *[f"{idx}. {step}" for idx, step in enumerate(plan_steps, start=1)],
            "",
            "## Definition of Done",
        ]
        lines.extend(f"- {item}" for item in dod_lines if item)
        return "\n".join(lines)

    def _generate_patch(
        self,
        workspace: WorkspaceContext,
        contract: Contract,
        agents: List[AgentProfile],
    ) -> str:
        repo_path = workspace.repo_path
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            return ""
        scope = [scope.strip("/") for scope in (contract.allowed_scope or []) if scope]
        if not scope:
            scope = ["scripts"]
        cmd = ["git", "diff", "--no-color"]
        if scope:
            cmd.append("--")
            cmd.extend(scope)
        try:
            completed = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return ""
        if completed.returncode != 0:
            return completed.stdout or ""
        return completed.stdout

    def _run_commands(
        self,
        commands: List[Dict[str, Any]],
        workspace_ctx: WorkspaceContext,
        contract: Contract | None,
    ) -> List[Dict[str, Any]]:
        if not commands:
            payload = self._write_placeholder_log(workspace_ctx.logs_dir, "no-commands")
            return [payload]
        results: List[Dict[str, Any]] = []
        self.command_allowlist.reload()
        command_env = self._build_command_env(contract)
        for command in commands:
            name = command.get("name", "command")
            shell = command.get("shell", "")
            timeout = command.get("timeout", self.config.default_timeout_seconds)
            cmd_type = command.get("type", "utility")
            slug = slugify(name)
            stdout_path = workspace_ctx.logs_dir / f"{slug}.out.log"
            stderr_path = workspace_ctx.logs_dir / f"{slug}.err.log"
            started = time.time()
            self._enforce_command_allowlist(shell, name)
            try:
                completed = subprocess.run(
                    shell,
                    shell=True,
                    cwd=workspace_ctx.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=command_env,
                )
                stdout_path.write_text(completed.stdout, encoding="utf-8")
                stderr_path.write_text(completed.stderr, encoding="utf-8")
                returncode = completed.returncode
            except subprocess.TimeoutExpired as exc:
                stdout_path.write_text(exc.stdout or "", encoding="utf-8")
                stderr_path.write_text(exc.stderr or "", encoding="utf-8")
                returncode = -1
            duration = round(time.time() - started, 2)
            results.append(
                {
                    "name": name,
                    "shell": shell,
                    "type": cmd_type,
                    "stdout_log": str(stdout_path),
                    "stderr_log": str(stderr_path),
                    "duration_seconds": duration,
                    "returncode": returncode,
                }
            )
        return results

    def _build_command_env(self, contract: Contract | None) -> Dict[str, str]:
        env = os.environ.copy()
        if contract and contract.execution_mode == "playmode_required":
            env["BABYLON_CI_EXECUTION_MODE"] = "playmode_required"
        return env

    def _enforce_command_allowlist(self, shell: str | None, name: str) -> None:
        if self.command_allowlist.is_allowed(shell):
            return
        raise PermissionError(
            f"Command '{name}' is not on the allowlist ({self.command_allowlist.path})."
        )

    def _write_placeholder_log(self, logs_dir: Path, stem: str) -> Dict[str, Any]:
        placeholder = logs_dir / f"{stem}.log"
        safe_write_text(placeholder, "No commands defined in contract; placeholder log created.")
        return {
            "name": "contract-noop",
            "shell": "",
            "type": "utility",
            "stdout_log": str(placeholder),
            "stderr_log": str(placeholder),
            "duration_seconds": 0,
            "returncode": 0,
        }

    def _maybe_generate_log_summary(self, contract: Contract, workspace_ctx: WorkspaceContext) -> Optional[Path]:
        if not contract.requires_unity_log:
            return None
        log_path = workspace_ctx.repo_path / self.UNITY_LOG_RELATIVE_PATH
        summary_path = workspace_ctx.repo_path / self.UNITY_SUMMARY_RELATIVE_PATH
        if not log_path.exists():
            print(
                f"[orchestrator] Unity log missing for task {contract.task_id}; signal gate will record the failure."
            )
            return None
        try:
            summary = self.log_parser.write_summary(log_path, summary_path)
            self._write_error_classification(summary, summary_path)
            return summary_path
        except Exception as exc:
            print(f"[orchestrator] Unity log summarization failed for task {contract.task_id}: {exc}")
        return None

    def _write_error_classification(self, summary: Dict[str, Any], summary_path: Path) -> Optional[Path]:
        if not summary:
            return None
        try:
            classification = self.error_classifier.classify(summary)
        except Exception as exc:
            print(f"[orchestrator] Unity log classification failed: {exc}")
            return None
        destination = summary_path.parent / self.UNITY_CLASSIFICATION_RELATIVE_PATH.name
        write_json(destination, classification)
        return destination

    def _record_artifact_manifest(
        self,
        workspace_ctx: WorkspaceContext,
        contract: Contract,
        gate_report: Dict[str, Any],
        artifacts_info: List[Dict[str, Any]],
    ) -> None:
        payload = {
            "contract": contract.metadata,
            "gate_overall": gate_report["overall_status"],
            "artifacts": artifacts_info,
            "generated_at": utc_timestamp(compact=False),
        }
        destination = workspace_ctx.artifacts_dir / "artifact_manifest.json"
        write_json(destination, payload)

    def _collect_artifacts(self, workspace_ctx: WorkspaceContext, contract: Contract) -> List[Dict[str, Any]]:
        artifacts = contract.artifact_requirements
        if not artifacts:
            return []
        statuses: List[Dict[str, Any]] = []
        for relative in artifacts:
            relative_path = Path(relative)
            source = workspace_ctx.repo_path / relative_path
            destination = workspace_ctx.artifacts_dir / relative_path
            ensure_dir(destination.parent)
            if source.exists():
                shutil.copy2(source, destination)
                status = "copied"
                size_bytes = destination.stat().st_size
                snippet = self._read_snippet(destination)
                contains_error = self._detect_error_marker(snippet)
            else:
                safe_write_text(destination, "Artifact missing in repo copy during collection.")
                status = "missing"
                size_bytes = 0
                contains_error = False
            statuses.append(
                {
                    "artifact": str(relative_path).replace('\\', '/'),
                    "status": status,
                    "size_bytes": size_bytes,
                    "contains_error_marker": contains_error,
                }
            )
        return statuses

    def _evaluate_playmode_context(self, contract: Contract, workspace_ctx: WorkspaceContext) -> Dict[str, Any]:
        mode = contract.execution_mode if contract else "editor"
        log_path = workspace_ctx.repo_path / self.UNITY_LOG_RELATIVE_PATH
        context: Dict[str, Any] = {
            "mode": mode,
            "required": mode == "playmode_required",
            "verified": False,
            "frames": None,
            "halt": False,
            "reason": "",
            "note": "",
            "log_path": str(log_path),
        }
        if mode not in {"playmode_required", "either"}:
            context["note"] = "Play mode probe skipped (playmode not requested)."
            return context
        if not log_path.exists():
            if context["required"]:
                context["halt"] = True
                context["reason"] = f"Play Mode gating requires Editor.log at {log_path}, but no log was captured."
            else:
                context["note"] = "Play mode log unavailable; optional verification skipped."
            return context
        snippet = self._read_snippet(log_path, limit=500000)
        lowered = snippet.lower()
        entered = "[playmode] entered" in lowered
        tick_match = self.PLAYMODE_TICK_PATTERN.search(snippet)
        frames = int(tick_match.group(1)) if tick_match else None
        if entered and frames is not None:
            context["verified"] = True
            context["frames"] = frames
            if context["required"]:
                context["note"] = f"Play mode verified ({frames} harness ticks)."
            else:
                context["note"] = f"Optional play mode markers observed ({frames} harness ticks)."
            return context
        missing: List[str] = []
        if not entered:
            missing.append("[PLAYMODE] entered")
        if frames is None:
            missing.append("[PLAYMODE] tick_ok")
        if context["required"]:
            marker_text = ", ".join(missing) if missing else "required markers"
            context["halt"] = True
            context["reason"] = f"Play Mode gating failed; missing {marker_text}."
        else:
            context["note"] = "Play mode markers not detected (optional)."
        return context

    def _playmode_meta(self, contract: Contract | None, context: Dict[str, Any]) -> Dict[str, Any]:
        meta = {
            "execution_mode": contract.execution_mode if contract else "editor",
            "required": context.get("required", False),
            "verified": context.get("verified", False),
            "frames_observed": context.get("frames"),
            "log_path": context.get("log_path", ""),
            "note": context.get("note", ""),
        }
        reason = context.get("reason")
        if reason:
            meta["reason"] = reason
        return meta

    def _apply_retention(self, current_run_id: str) -> Dict[str, Any]:
        runs_dir = self.config.runs_dir
        retention = {"max": self.MAX_RUN_BUNDLES, "deleted": [], "kept": 0}
        if not runs_dir.exists():
            return retention
        bundles = [
            entry
            for entry in runs_dir.iterdir()
            if entry.is_dir() and self.RUN_ID_PATTERN.match(entry.name)
        ]
        bundles.sort(key=lambda entry: entry.name)
        total = len(bundles)
        retention["kept"] = total
        if not self.retention_enabled or total <= self.MAX_RUN_BUNDLES:
            return retention
        delete_candidates = [entry for entry in bundles if entry.name != current_run_id]
        extra = max(total - self.MAX_RUN_BUNDLES, 0)
        deleted: List[str] = []
        for entry in delete_candidates[:extra]:
            try:
                shutil.rmtree(entry)
                deleted.append(entry.name)
                print(f"[orchestrator] Retention removed run bundle {entry.name}.")
            except OSError as exc:
                print(f"[orchestrator] Retention failed for {entry.name}: {exc}")
        retention["deleted"] = deleted
        remaining = [
            entry
            for entry in runs_dir.iterdir()
            if entry.is_dir() and self.RUN_ID_PATTERN.match(entry.name)
        ]
        retention["kept"] = len(remaining)
        return retention

    def _read_snippet(self, path: Path, limit: int = 20000) -> str:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                return handle.read(limit)
        except OSError:
            return ""

    def _detect_error_marker(self, snippet: str) -> bool:
        lowered = snippet.lower()
        if not lowered:
            return False
        if "error" in lowered or "exception" in lowered:
            return True
        return " cs" in lowered or "cs0" in lowered

    def _build_summary(
        self,
        contract: Contract | None,
        gate_report: Dict[str, Any],
        command_results: List[Dict[str, Any]],
        agents: List[AgentProfile],
        artifacts_info: List[Dict[str, Any]],
        retention_info: Dict[str, Any],
        diff_report: Optional[Dict[str, Any]] = None,
        additional_notes: Optional[List[str]] = None,
    ) -> str:
        gate_lines = [f"- {gate['name'].title()}: {gate['status']} ({'; '.join(gate['reasons'])})" for gate in gate_report["gates"]]
        policy_payload = gate_report.get("policy") or {}
        policy_lines = [
            f"- Verdict: {policy_payload.get('verdict', 'UNKNOWN')} (allowed={policy_payload.get('allowed', False)}, risk={policy_payload.get('risk_score', 0.0)})"
        ]
        policy_violations = policy_payload.get("violations") or []
        if policy_violations:
            policy_lines.extend(
                f"- {item.get('rule', 'rule')}: {item.get('detail', '')} (evidence: {item.get('evidence', 'n/a')})"
                for item in policy_violations
            )
        else:
            policy_lines.append("- No policy violations recorded.")
        command_lines = [
            f"- {result['name']} ({result['type']}): exit {result['returncode']} in {result['duration_seconds']}s"
            for result in command_results
        ]
        agent_list = ", ".join(f"{agent.id}({agent.role})" for agent in agents) if agents else "None assigned"
        artifact_lines = [
            f"- {item['artifact']}: {item['status']} ({item.get('size_bytes', 0)} bytes)"
            for item in artifacts_info
        ] or ["- No artifacts recorded"]
        retention_lines = [
            f"- Max bundles: {retention_info.get('max', self.MAX_RUN_BUNDLES)}",
            f"- Kept bundles: {retention_info.get('kept', 0)}",
        ]
        if retention_info.get("deleted"):
            retention_lines.append(f"- Deleted: {', '.join(retention_info['deleted'])}")
        else:
            retention_lines.append("- Deleted: none")
        diff_lines: List[str]
        if diff_report:
            diff_lines = [
                f"- Previous bundle: {diff_report.get('previous_bundle_id', 'unknown')}",
                f"- Regression verdict: {diff_report.get('regression_verdict', 'UNKNOWN')}",
                f"- Error delta: {diff_report.get('error_count_delta', 0)}",
                f"- Policy risk delta: {diff_report.get('policy_risk_delta', 0)}",
                f"- Patch LOC delta: {diff_report.get('patch_loc_delta', 0)}",
                f"- Files touched delta: {diff_report.get('files_touched_delta', 0)}",
            ]
            new_signatures = diff_report.get("new_error_signatures") or []
            if new_signatures:
                diff_lines.append("- New error signatures: " + ", ".join(new_signatures[:5]))
            diff_lines.extend(f"- {reason}" for reason in diff_report.get("regression_reasons", [])[:3])
            if diff_report.get("no_change_detected"):
                diff_lines.append("- No change detected relative to previous bundle.")
            config = (diff_report.get("regression_config") or {}) if isinstance(diff_report, dict) else {}
            preference = config.get("no_change_verdict")
            if preference:
                diff_lines.append(f"- No-change policy: {preference}")
        else:
            diff_lines = ["- No previous bundle available for comparison."]
        task_label = contract.task_id if contract else "UNKNOWN"
        metadata = contract.metadata if contract else {}
        lines = [
            f"# Run Summary — Task {task_label}",
            "",
            f"**Overall Gate:** {gate_report['overall_status']} (score {gate_report['overall_score']})",
            f"**Agents:** {agent_list}",
            "",
            "## Gate Outcomes",
            *gate_lines,
            "",
            "## Policy Verdict",
            *policy_lines,
            "",
            "## Command Results",
            *(command_lines or ["- No commands executed"]),
            "",
            "## Artifacts",
            *artifact_lines,
            "",
            "## Diff / Regression",
            *diff_lines,
            "",
            "## Retention",
            *retention_lines,
            "",
            "## Notes",
            "- Contract objective: {objective}".format(objective=metadata.get("Objective", "")),
            "- Artifacts mirrored to runs directory.",
        ]
        if additional_notes:
            lines.extend(additional_notes)
        return "\n".join(lines)

    def _emit_command_results(
        self,
        reporter: Optional[ReportEmitter],
        run_dir: Path,
        command_results: List[Dict[str, Any]],
    ) -> None:
        payload = {"commands": command_results}
        if reporter:
            reporter.emit_command_results(payload)
        else:
            write_json(run_dir / "command_results.json", payload)

    def _emit_gate_report(
        self,
        reporter: Optional[ReportEmitter],
        run_dir: Path,
        payload: Dict[str, Any],
    ) -> None:
        if reporter:
            reporter.emit_gate_report(payload)
        else:
            write_json(run_dir / "gate_report.json", payload)

    def _emit_summary(self, reporter: Optional[ReportEmitter], run_dir: Path, content: str) -> None:
        if reporter:
            reporter.emit_summary(content)
        else:
            safe_write_text(run_dir / "summary.md", content)

    def _emit_diff_report(self, reporter: Optional[ReportEmitter], run_dir: Path, payload: Dict[str, Any]) -> None:
        if reporter:
            reporter.emit_diff_report(payload)
        else:
            write_json(run_dir / "diff_report.json", payload)

    def _build_playmode_gate_report(self, task_id: str, reason: str) -> Dict[str, Any]:
        message = f"Play Mode verification failed for task {task_id}: {reason}"
        policy_payload = dict(self._failure_policy_payload(message))
        policy_payload["verdict"] = "ASK"
        return {
            "overall_status": "ASK",
            "overall_score": 0.0,
            "gates": [
                {
                    "name": "playmode_verification",
                    "status": "ASK",
                    "score": 0.0,
                    "reasons": [message],
                }
            ],
            "patch_stats": {
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
                "touched_files": [],
                "loc_delta": 0,
            },
            "artifacts": [],
            "policy": policy_payload,
        }

    def _build_failure_gate_report(
        self, task_id: str, error_message: str, policy_payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        reason = f"Task {task_id} encountered an unexpected error: {error_message}"
        policy_info = policy_payload or self._failure_policy_payload(reason)
        return {
            "overall_status": "BLOCK",
            "overall_score": 0.0,
            "gates": [
                {
                    "name": "scheduler",
                    "status": "BLOCK",
                    "score": 0.0,
                    "reasons": [reason],
                }
            ],
            "patch_stats": {
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
                "touched_files": [],
                "loc_delta": 0,
            },
            "artifacts": [],
            "policy": policy_info,
        }

    def _failure_policy_payload(self, reason: str) -> Dict[str, Any]:
        if hasattr(self.gatekeeper, "policy_engine"):
            return self.gatekeeper.policy_engine.failure_decision(reason).as_dict()
        return {
            "allowed": False,
            "violations": [
                {
                    "rule": "runtime_failure",
                    "detail": reason,
                    "evidence": "scheduler",
                    "severity": "hard",
                }
            ],
            "risk_score": 1.0,
            "verdict": "BLOCK",
        }

    def _summarize_gate_failure(self, gate_report: Dict[str, Any]) -> str:
        if not gate_report:
            return ""
        failing_gates = [gate for gate in gate_report.get("gates", []) if gate.get("status", "").upper() != "ALLOW"]
        if not failing_gates:
            return ""
        gate = failing_gates[0]
        reasons = gate.get("reasons") or []
        reason_text = "; ".join(reasons) if reasons else "See gate report for details."
        gate_name = gate.get("name", "gate")
        gate_status = gate.get("status", "BLOCK")
        return f"{gate_status} in {gate_name} gate: {reason_text}"

    def _attach_regression_gate(self, gate_report: Dict[str, Any], regression_gate: RegressionGate | None) -> Dict[str, Any]:
        if not gate_report or not regression_gate:
            return gate_report
        gate_entry = {
            "name": "regression",
            "status": regression_gate.verdict,
            "score": 1.0 if regression_gate.verdict == "ALLOW" else 0.5 if regression_gate.verdict == "ASK" else 0.0,
            "reasons": regression_gate.reasons,
        }
        gate_report.setdefault("gates", []).append(gate_entry)
        self._recompute_gate_overall(gate_report)
        return gate_report

    def _recompute_gate_overall(self, gate_report: Dict[str, Any]) -> None:
        gates = gate_report.get("gates", [])
        statuses = [str(gate.get("status", "")).upper() for gate in gates]
        if "BLOCK" in statuses:
            overall = "BLOCK"
        elif "ASK" in statuses:
            overall = "ASK"
        else:
            overall = "ALLOW"
        gate_report["overall_status"] = overall
        if gates:
            total_score = 0.0
            for gate in gates:
                try:
                    total_score += float(gate.get("score", 0) or 0)
                except (TypeError, ValueError):
                    continue
            gate_report["overall_score"] = round(total_score / len(gates), 2)

    def _resolve_path(self, path_value: str | None) -> Path:
        if not path_value:
            return self.config.contracts_dir
        candidate = Path(path_value)
        if candidate.is_absolute():
            return candidate
        return (self.config.root_dir / candidate).resolve()

    def _queue_status_for_overall(self, overall: str) -> str:
        verdict = (overall or "").upper()
        if verdict == "ALLOW":
            return "completed"
        if verdict == "ASK":
            return "needs_approval"
        return "failed"
