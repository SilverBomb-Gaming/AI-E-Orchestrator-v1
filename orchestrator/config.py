from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class OrchestratorConfig:
    """Resolved filesystem locations and global options."""

    root_dir: Path
    runs_dir: Path
    workspaces_dir: Path
    queue_path: Path
    queue_contracts_dir: Path
    agent_registry_path: Path
    contracts_dir: Path
    templates_dir: Path
    approvals_path: Path
    command_allowlist_path: Path
    default_timeout_seconds: int = 900

    @staticmethod
    def load(overrides: Dict[str, Any] | None = None) -> "OrchestratorConfig":
        base = Path(__file__).resolve().parent.parent
        overrides = overrides or {}
        runs_dir = Path(overrides.get("runs_dir", base / "runs"))
        workspaces_dir = Path(overrides.get("workspaces_dir", base / "workspaces"))
        queue_path = Path(overrides.get("queue_path", base / "backlog" / "queue.json"))
        queue_contracts_dir = Path(overrides.get("queue_contracts_dir", base / "contracts" / "queue"))
        agent_registry_path = Path(overrides.get("agent_registry_path", base / "agents" / "registry.json"))
        contracts_dir = Path(overrides.get("contracts_dir", base / "contracts"))
        templates_dir = Path(overrides.get("templates_dir", contracts_dir / "templates"))
        timeout = int(overrides.get("default_timeout_seconds", 900))
        approvals_path = Path(overrides.get("approvals_path", base / "backlog" / "approvals.json"))
        command_allowlist_path = Path(
            overrides.get("command_allowlist_path", base / "backlog" / "command_allowlist.json")
        )
        return OrchestratorConfig(
            root_dir=base,
            runs_dir=runs_dir,
            workspaces_dir=workspaces_dir,
            queue_path=queue_path,
            queue_contracts_dir=queue_contracts_dir,
            agent_registry_path=agent_registry_path,
            contracts_dir=contracts_dir,
            templates_dir=templates_dir,
            approvals_path=approvals_path,
            command_allowlist_path=command_allowlist_path,
            default_timeout_seconds=timeout,
        )

    def ensure_directories(self) -> None:
        for target in (self.runs_dir, self.workspaces_dir, self.contracts_dir, self.queue_contracts_dir):
            target.mkdir(parents=True, exist_ok=True)
