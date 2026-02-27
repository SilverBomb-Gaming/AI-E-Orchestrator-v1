from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .contracts import write_contract_copy
from .utils import ensure_dir, safe_write_text


@dataclass(frozen=True)
class WorkspaceContext:
    task_id: str
    timestamp: str
    base_path: Path
    repo_path: Path
    contract_path: Path
    logs_dir: Path
    artifacts_dir: Path
    patches_dir: Path
    reports_dir: Path


class WorkspaceManager:
    def __init__(self, workspaces_root: Path, *, ignore_dirs: tuple[str, ...] | None = None) -> None:
        self.workspaces_root = workspaces_root
        self.ignore_dirs = ignore_dirs or (
            "Library",
            "Logs",
            "Temp",
            "Builds",
            "obj",
            "UserSettings",
        )

    def prepare(self, task_id: str, contract_file: Path, target_repo: Path, timestamp: str) -> WorkspaceContext:
        base_path = ensure_dir(self.workspaces_root / task_id / timestamp)
        repo_path = base_path / "repo"
        logs_dir = ensure_dir(base_path / "logs")
        artifacts_dir = ensure_dir(base_path / "artifacts")
        patches_dir = ensure_dir(base_path / "patches")
        reports_dir = ensure_dir(base_path / "reports")
        self._hydrate_repo_copy(target_repo, repo_path)
        contract_copy_path = base_path / "contract.md"
        write_contract_copy(contract_file, contract_copy_path)
        return WorkspaceContext(
            task_id=task_id,
            timestamp=timestamp,
            base_path=base_path,
            repo_path=repo_path,
            contract_path=contract_copy_path,
            logs_dir=logs_dir,
            artifacts_dir=artifacts_dir,
            patches_dir=patches_dir,
            reports_dir=reports_dir,
        )

    def _hydrate_repo_copy(self, source_repo: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        if source_repo.exists():
            ignore = shutil.ignore_patterns(*self.ignore_dirs) if self.ignore_dirs else None
            shutil.copytree(source_repo, destination, ignore=ignore)
        else:
            ensure_dir(destination)
            safe_write_text(destination / "README.md", "# Placeholder repo copy\nSource repository missing during workspace prep.\n")
