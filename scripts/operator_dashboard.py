#!/usr/bin/env python
"""Minimal Tkinter dashboard for AI-E Orchestrator operators."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.approvals import OperatorApprovalStore
from orchestrator.config import OrchestratorConfig
from orchestrator.runner import QueueManager


def _default_operator() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or os.environ.get("COMPUTERNAME") or "operator"


class OperatorDashboard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AI-E Orchestrator Dashboard")
        self.geometry("1180x700")
        self.config_obj = OrchestratorConfig.load()
        self.queue_manager = QueueManager(
            queue_path=self.config_obj.queue_path,
            queue_contracts_dir=self.config_obj.queue_contracts_dir,
            root_dir=self.config_obj.root_dir,
        )
        self.approval_store = OperatorApprovalStore(self.config_obj.approvals_path)
        self.task_cache: Dict[str, Dict[str, Any]] = {}
        self.selected_task_id: str | None = None
        self.queue_status_var = tk.StringVar(value="Queue state unknown")
        self.detail_vars = {
            "title": tk.StringVar(value=""),
            "status": tk.StringVar(value=""),
            "last_run": tk.StringVar(value=""),
            "last_result": tk.StringVar(value=""),
            "last_error": tk.StringVar(value=""),
            "run_dir": tk.StringVar(value=""),
            "resolution_note": tk.StringVar(value=""),
        }
        self.run_id_var = tk.StringVar(value="")
        self.operator_var = tk.StringVar(value=_default_operator())
        self.notes_var = tk.StringVar(value="")
        self.pending_list: tk.Listbox | None = None
        self.artifact_list: tk.Listbox | None = None
        self._build_ui()
        self.refresh_data()

    def _build_ui(self) -> None:
        top_bar = ttk.Frame(self)
        top_bar.pack(fill=tk.X, padx=10, pady=6)
        ttk.Label(top_bar, textvariable=self.queue_status_var, font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(top_bar, text="Refresh", command=self.refresh_data).pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        tree_frame = ttk.Frame(body)
        tree_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        columns = ("title", "status", "result", "updated")
        self.task_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=18)
        headings = {
            "title": "Title",
            "status": "Status",
            "result": "Last Result",
            "updated": "Last Run",
        }
        for col in columns:
            self.task_tree.heading(col, text=headings[col])
            self.task_tree.column(col, width=160 if col == "title" else 120, anchor=tk.W)
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=tree_scroll.set)
        self.task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_tree.bind("<<TreeviewSelect>>", lambda _event: self._on_task_selected())

        detail_frame = ttk.Frame(body)
        detail_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(12, 0))

        info_frame = ttk.LabelFrame(detail_frame, text="Task Details")
        info_frame.pack(fill=tk.X)
        for idx, (label, var) in enumerate(self.detail_vars.items()):
            ttk.Label(info_frame, text=f"{label.replace('_', ' ').title()}:", width=14).grid(row=idx, column=0, sticky=tk.W, padx=4, pady=2)
            ttk.Label(info_frame, textvariable=var, width=60).grid(row=idx, column=1, sticky=tk.W, padx=4, pady=2)

        artifact_frame = ttk.LabelFrame(detail_frame, text="Artifacts Snapshot")
        artifact_frame.pack(fill=tk.BOTH, expand=True, pady=8)
        self.artifact_list = tk.Listbox(artifact_frame, height=10)
        self.artifact_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        approvals_frame = ttk.LabelFrame(detail_frame, text="Operator Approvals")
        approvals_frame.pack(fill=tk.BOTH, expand=True)
        list_container = ttk.Frame(approvals_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.pending_list = tk.Listbox(list_container, height=6)
        self.pending_list.pack(fill=tk.BOTH, expand=True)

        form = ttk.Frame(approvals_frame)
        form.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(form, text="Run ID:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(form, textvariable=self.run_id_var, width=38).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(form, text="Operator:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(form, textvariable=self.operator_var, width=38).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(form, text="Notes:").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(form, textvariable=self.notes_var, width=38).grid(row=2, column=1, sticky=tk.W)
        ttk.Button(form, text="Approve Selected Run", command=self._approve_selected).grid(row=3, column=0, columnspan=2, pady=(6, 0))

    def refresh_data(self) -> None:
        self.queue_manager.refresh()
        tasks = self.queue_manager.all_tasks()
        self.task_cache = {task.get("id", "UNKNOWN"): task for task in tasks}
        self.queue_status_var.set(self._format_queue_status(tasks))
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
        for task in tasks:
            task_id = task.get("id", "UNKNOWN")
            values = (
                task.get("title", ""),
                task.get("status", ""),
                task.get("last_run_status", ""),
                task.get("last_run", ""),
            )
            self.task_tree.insert("", tk.END, iid=task_id, values=values)
        self._load_pending()
        if self.selected_task_id and self.selected_task_id in self.task_cache:
            self._select_task(self.selected_task_id)
        else:
            self._clear_details()

    def _format_queue_status(self, tasks: List[Dict[str, Any]]) -> str:
        if not tasks:
            return "Queue: empty"
        blocked = self.queue_manager.blocked_reason
        if blocked:
            return f"Queue blocked: {blocked}"
        pending = sum(1 for task in tasks if task.get("status") == "pending")
        running = sum(1 for task in tasks if task.get("status") == "running")
        needs = sum(1 for task in tasks if task.get("status") == "needs_approval")
        parts = [f"Queue: {pending} pending", f"{running} running"]
        if needs:
            parts.append(f"{needs} needs approval")
        return " / ".join(parts)

    def _on_task_selected(self) -> None:
        selection = self.task_tree.selection()
        if not selection:
            self.selected_task_id = None
            self._clear_details()
            return
        self._select_task(selection[0])

    def _select_task(self, task_id: str) -> None:
        self.selected_task_id = task_id
        task = self.task_cache.get(task_id)
        if not task:
            self._clear_details()
            return
        self.detail_vars["title"].set(task.get("title", ""))
        self.detail_vars["status"].set(task.get("status", ""))
        self.detail_vars["last_run"].set(task.get("last_run", ""))
        self.detail_vars["last_result"].set(task.get("last_run_status", ""))
        self.detail_vars["last_error"].set(task.get("last_error", ""))
        last_run_dir = task.get("last_run_dir") or ""
        self.detail_vars["run_dir"].set(last_run_dir)
        self.detail_vars["resolution_note"].set(task.get("resolution_note", ""))
        self.run_id_var.set(task.get("last_run_id") or "")
        self._load_artifacts(last_run_dir)

    def _clear_details(self) -> None:
        for var in self.detail_vars.values():
            var.set("")
        self.run_id_var.set("")
        if self.artifact_list:
            self.artifact_list.delete(0, tk.END)

    def _load_artifacts(self, run_dir_value: str) -> None:
        if not self.artifact_list:
            return
        self.artifact_list.delete(0, tk.END)
        if not run_dir_value:
            return
        run_dir = Path(run_dir_value)
        artifacts_dir = run_dir / "artifacts"
        if not artifacts_dir.exists():
            self.artifact_list.insert(tk.END, "No artifacts folder found.")
            return
        entries = []
        for entry in artifacts_dir.rglob("*"):
            if entry.is_dir():
                continue
            relative = entry.relative_to(run_dir)
            entries.append(str(relative).replace("\\", "/"))
            if len(entries) >= 30:
                break
        if not entries:
            self.artifact_list.insert(tk.END, "No artifact files captured.")
            return
        for item in entries:
            self.artifact_list.insert(tk.END, item)
        if len(entries) >= 30:
            self.artifact_list.insert(tk.END, "...")

    def _load_pending(self) -> None:
        if not self.pending_list:
            return
        self.pending_list.delete(0, tk.END)
        for entry in self.approval_store.list_pending():
            label = f"{entry.get('task_id', '*')} :: {entry.get('run_id', '*')} :: {entry.get('approved_by', '')}"
            self.pending_list.insert(tk.END, label)

    def _approve_selected(self) -> None:
        task_id = self.selected_task_id or ""
        run_id = self.run_id_var.get().strip()
        operator = self.operator_var.get().strip() or _default_operator()
        notes = self.notes_var.get().strip()
        if not task_id and not run_id:
            messagebox.showwarning("Approval", "Select a task or enter a run ID before approving.")
            return
        self.approval_store.add(task_id=task_id, run_id=run_id, approved_by=operator, notes=notes)
        messagebox.showinfo("Approval", "Approval recorded.")
        self.notes_var.set("")
        self._load_pending()


def main() -> int:
    dashboard = OperatorDashboard()
    dashboard.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
