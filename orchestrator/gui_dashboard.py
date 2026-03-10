"""Minimal local GUI that visualizes live orchestrator events."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
EVENT_FILE = ROOT / "reports" / "live_events.jsonl"
POLL_INTERVAL_MS = 500


class Dashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AI-E Dashboard")
        self.current_cycle_id: str = ""
        self.current_task_id: str = ""
        self.progress_active = False
        self.details_visible = False
        self.event_position = EVENT_FILE.stat().st_size if EVENT_FILE.exists() else 0
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.cycle_process: Optional[subprocess.Popen[str]] = None

        self.cycle_var = tk.StringVar(value="Cycle: idle")
        self.task_var = tk.StringVar(value="Task: --")
        self.stage_var = tk.StringVar(value="Stage: waiting")
        self.task_filter_var = tk.StringVar(value="")

        self._build_layout()
        self.root.after(POLL_INTERVAL_MS, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.cycle_var, font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(header, textvariable=self.task_var).pack(anchor="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.stage_var).pack(anchor="w")

        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=12, pady=(0, 12))

        controls = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        controls.pack(fill="x")
        ttk.Label(controls, text="Task Filter:").pack(side="left")
        ttk.Entry(controls, textvariable=self.task_filter_var, width=25).pack(side="left", padx=(4, 12))
        ttk.Button(controls, text="Start Night Cycle", command=self._start_cycle).pack(side="left")
        self.toggle_button = ttk.Button(controls, text="Show Advanced Details", command=self._toggle_details)
        self.toggle_button.pack(side="right")

        self.details_frame = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        self.details_text = tk.Text(self.details_frame, height=12, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(self.details_frame, command=self.details_text.yview)
        self.details_text.configure(yscrollcommand=scrollbar.set)
        self.details_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _start_progress(self) -> None:
        if not self.progress_active:
            self.progress.start(10)
            self.progress_active = True

    def _stop_progress(self) -> None:
        if self.progress_active:
            self.progress.stop()
            self.progress_active = False

    def _toggle_details(self) -> None:
        if self.details_visible:
            self.details_frame.pack_forget()
            self.details_visible = False
            self.toggle_button.configure(text="Show Advanced Details")
        else:
            self.details_frame.pack(fill="both", expand=True)
            self.details_visible = True
            self.toggle_button.configure(text="Hide Advanced Details")

    def _start_cycle(self) -> None:
        if self.cycle_process and self.cycle_process.poll() is None:
            self._append_detail("system", "Night cycle already running.")
            return
        args = [sys.executable, "-u", "-m", "orchestrator.night_cycle"]
        task_filter = self.task_filter_var.get().strip()
        if task_filter:
            args.extend(["--task-filter", task_filter])
        self._append_detail("command", "Launching night cycle...")
        self.cycle_process = subprocess.Popen(
            args,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        for stream, label in ((self.cycle_process.stdout, "stdout"), (self.cycle_process.stderr, "stderr")):
            if stream is None:
                continue
            threading.Thread(target=self._read_stream, args=(stream, label), daemon=True).start()
        threading.Thread(target=self._watch_process, daemon=True).start()
        self._start_progress()

    def _read_stream(self, stream: Any, label: str) -> None:
        for line in iter(stream.readline, ""):
            self.output_queue.put((label, line.rstrip()))
        stream.close()

    def _watch_process(self) -> None:
        if not self.cycle_process:
            return
        self.cycle_process.wait()
        self.output_queue.put(("system", f"night_cycle exited with code {self.cycle_process.returncode}"))
        self.cycle_process = None

    def _poll(self) -> None:
        self._tail_events()
        self._drain_process_output()
        self.root.after(POLL_INTERVAL_MS, self._poll)

    def _tail_events(self) -> None:
        if not EVENT_FILE.exists():
            return
        try:
            with EVENT_FILE.open("r", encoding="utf-8") as handle:
                handle.seek(self.event_position)
                lines = handle.readlines()
                self.event_position = handle.tell()
        except OSError:
            return
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._handle_event(event)

    def _handle_event(self, event: Dict[str, Any]) -> None:
        stage = event.get("stage", "unknown")
        message = event.get("message", "")
        cycle_id = str(event.get("cycle_id", ""))
        task_id = str(event.get("task_id", ""))
        if cycle_id:
            self.current_cycle_id = cycle_id
            self.cycle_var.set(f"Cycle: {cycle_id}")
        if stage == "cycle_start":
            self._start_progress()
            self.task_var.set("Task: waiting")
            self.stage_var.set(f"Stage: {message or 'cycle started'}")
        elif stage == "cycle_end":
            self._stop_progress()
            self.stage_var.set(f"Stage: {message or 'cycle finished'}")
        elif stage == "task_start":
            self.current_task_id = task_id
            label = task_id or "--"
            self.task_var.set(f"Task: {label}")
            self.stage_var.set(f"Stage: {message or 'task running'}")
            self._start_progress()
        elif stage == "task_end":
            self.stage_var.set(f"Stage: {message or 'task complete'}")
        elif stage == "command_start":
            self.stage_var.set(f"Stage: {message or 'command running'}")
            self._start_progress()
        elif stage == "command_end":
            self.stage_var.set(f"Stage: {message or 'command finished'}")
        elif stage == "artifact_copied":
            self.stage_var.set(f"Stage: artifact update ({message})")
        elif stage == "gate_decision":
            self.stage_var.set(f"Stage: {message}")
        if stage not in {"command_start"}:
            self._append_detail(stage, f"{message} (task {task_id or '--'})")
        else:
            self._append_detail(stage, message)

    def _drain_process_output(self) -> None:
        while not self.output_queue.empty():
            label, line = self.output_queue.get()
            self._append_detail(label, line)

    def _append_detail(self, label: str, text: str) -> None:
        line = f"[{label}] {text}"
        self.details_text.configure(state="normal")
        self.details_text.insert("end", line + "\n")
        self.details_text.see("end")
        self.details_text.configure(state="disabled")

    def _on_close(self) -> None:
        if self.cycle_process and self.cycle_process.poll() is None:
            try:
                self.cycle_process.terminate()
            except OSError:
                pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
