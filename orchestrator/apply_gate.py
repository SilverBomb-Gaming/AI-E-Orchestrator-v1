from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .utils import ensure_dir


ALLOWED_PREFIXES = ("docs/", "tests/")
ALLOWED_FILES = {"README.md"}


@dataclass
class ApplyPrecheckResult:
    blocked: bool
    reason: str


@dataclass
class ApplyDecision:
    applied: bool
    blocked: bool
    notes: str
    diff_summary: str = ""
    blocked_path: Optional[str] = None
    patch_path: Optional[Path] = None


class ApplyGate:
    """Restricts automatic applies to a safe subset of files."""

    def __init__(self, repo_root: Path, mode: str, cycle_id: str) -> None:
        self.repo_root = repo_root
        self.mode = mode
        self.cycle_id = cycle_id
        self.env = os.environ.copy()
        self.env.setdefault("GIT_AUTHOR_NAME", "Night Cycle Automation")
        self.env.setdefault("GIT_AUTHOR_EMAIL", "night-cycle@example.com")

    def ensure_clean_worktree(self) -> ApplyPrecheckResult:
        if self.mode == "off":
            return ApplyPrecheckResult(blocked=False, reason="apply-mode disabled")
        try:
            status = self._run_git(["status", "--porcelain"], capture_output=True).stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return ApplyPrecheckResult(blocked=True, reason=f"git status failed: {exc}")
        if status:
            return ApplyPrecheckResult(
                blocked=True,
                reason="Working tree is dirty before cycle start; clean or commit changes before apply-mode runs.",
            )
        return ApplyPrecheckResult(blocked=False, reason="clean")

    def process_success(self, task_id: str, run_dir: Path) -> ApplyDecision:
        if self.mode == "off":
            return ApplyDecision(applied=False, blocked=False, notes="apply-mode disabled")
        try:
            status_output = self._run_git(["status", "--porcelain"], capture_output=True).stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return ApplyDecision(applied=False, blocked=True, notes=f"git status failed: {exc}")
        if not status_output:
            return ApplyDecision(applied=False, blocked=False, notes="No changes detected after task execution.")
        if not self._stage_all():
            return ApplyDecision(
                applied=False,
                blocked=True,
                notes="Unable to stage pending changes for apply-mode commit.",
            )
        try:
            names = self._run_git(["diff", "--cached", "--name-only"], capture_output=True).stdout.splitlines()
            patch_text = self._run_git(["diff", "--cached"], capture_output=True).stdout
            diff_summary = self._run_git(["diff", "--cached", "--stat"], capture_output=True).stdout.strip()
        except subprocess.CalledProcessError as exc:
            self._reset_index()
            return ApplyDecision(applied=False, blocked=True, notes=f"git diff failed: {exc}")
        patch_path = self._write_patch(run_dir, patch_text) if patch_text else None
        blocked_path = self._first_blocked_path(names)
        if blocked_path:
            self._reset_index()
            return ApplyDecision(
                applied=False,
                blocked=True,
                blocked_path=blocked_path,
                diff_summary=diff_summary,
                notes=f"Apply-mode blocked by {blocked_path}.",
                patch_path=patch_path,
            )
        commit_msg = f"auto: docs/tests update (cycle {self.cycle_id})"
        commit_proc = self._run_git(["commit", "-m", commit_msg], capture_output=True, check=False)
        if commit_proc.returncode != 0:
            self._reset_index()
            stderr = (commit_proc.stderr or "").strip() or "git commit failed"
            return ApplyDecision(
                applied=False,
                blocked=True,
                diff_summary=diff_summary,
                notes=f"Apply-mode commit failed: {stderr}",
                patch_path=patch_path,
            )
        return ApplyDecision(
            applied=True,
            blocked=False,
            diff_summary=diff_summary,
            notes=diff_summary or f"Docs/tests changes applied for task {task_id}.",
            patch_path=patch_path,
        )

    def _run_git(self, args: List[str], *, capture_output: bool, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            env=self.env,
            capture_output=capture_output,
            text=True,
            check=check,
        )

    def _stage_all(self) -> bool:
        try:
            self._run_git(["add", "-A"], capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def _reset_index(self) -> None:
        try:
            self._run_git(["reset"], capture_output=True, check=False)
        except subprocess.CalledProcessError:
            return

    def _first_blocked_path(self, paths: List[str]) -> Optional[str]:
        for path in paths:
            normalized = path.strip()
            if not normalized:
                continue
            if normalized in ALLOWED_FILES:
                continue
            if any(normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES):
                continue
            return normalized
        return None

    def _write_patch(self, run_dir: Path, patch_text: str) -> Path:
        artifacts_dir = ensure_dir(run_dir / "artifacts")
        patch_path = artifacts_dir / "patch.diff"
        patch_path.write_text(patch_text, encoding="utf-8")
        return patch_path