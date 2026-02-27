from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict

from .utils import ensure_dir, safe_write_text, write_json
from .workspace import WorkspaceContext


class ReportEmitter:
    def __init__(self, workspace: WorkspaceContext, run_dir: Path) -> None:
        self.workspace = workspace
        self.run_dir = ensure_dir(run_dir)

    def emit_plan(self, content: str) -> Path:
        workspace_path = self.workspace.reports_dir / "plan.md"
        run_path = self.run_dir / "plan.md"
        self._write_text_dual(workspace_path, run_path, content)
        return workspace_path

    def emit_summary(self, content: str) -> Path:
        workspace_path = self.workspace.reports_dir / "summary.md"
        run_path = self.run_dir / "summary.md"
        self._write_text_dual(workspace_path, run_path, content)
        return run_path

    def emit_gate_report(self, payload: Dict[str, Any]) -> Path:
        workspace_path = self.workspace.reports_dir / "gate_report.json"
        run_path = self.run_dir / "gate_report.json"
        self._write_json_dual(workspace_path, run_path, payload)
        return run_path

    def emit_command_results(self, payload: Dict[str, Any]) -> Path:
        workspace_path = self.workspace.reports_dir / "command_results.json"
        run_path = self.run_dir / "command_results.json"
        self._write_json_dual(workspace_path, run_path, payload)
        return run_path

    def emit_diff_report(self, payload: Dict[str, Any]) -> Path:
        workspace_path = self.workspace.reports_dir / "diff_report.json"
        run_path = self.run_dir / "diff_report.json"
        self._write_json_dual(workspace_path, run_path, payload)
        return run_path

    def emit_run_meta(self, payload: Dict[str, Any]) -> Path:
        path = self.run_dir / "run_meta.json"
        write_json(path, payload)
        return path

    def emit_patch(self, filename: str, content: str) -> Path:
        workspace_path = self.workspace.patches_dir / filename
        run_path = ensure_dir(self.run_dir / "patches") / filename
        self._write_text_dual(workspace_path, run_path, content)
        return run_path

    def copy_contract(self) -> None:
        destination = self.run_dir / "contract.md"
        shutil.copy2(self.workspace.contract_path, destination)

    def mirror_logs(self) -> None:
        destination = self.run_dir / "logs"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(self.workspace.logs_dir, destination)

    def mirror_artifacts(self) -> None:
        destination = self.run_dir / "artifacts"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(self.workspace.artifacts_dir, destination)

    def _write_text_dual(self, workspace_path: Path, run_path: Path, content: str) -> None:
        safe_write_text(workspace_path, content)
        safe_write_text(run_path, content)

    def _write_json_dual(self, workspace_path: Path, run_path: Path, payload: Dict[str, Any]) -> None:
        ensure_dir(workspace_path.parent)
        ensure_dir(run_path.parent)
        workspace_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        run_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
