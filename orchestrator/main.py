from __future__ import annotations

import argparse

from .config import OrchestratorConfig
from .gates import Gatekeeper
from .registry import AgentRegistry
from .runner import QueueManager, TaskRunner
from .workspace import WorkspaceManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-E Orchestrator entry point")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="Process a single pending task")
    group.add_argument("--nightly", action="store_true", help="Process all pending tasks")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = OrchestratorConfig.load()
    config.ensure_directories()
    agent_registry = AgentRegistry(config.agent_registry_path)
    workspace_manager = WorkspaceManager(config.workspaces_dir)
    gatekeeper = Gatekeeper()
    runner = TaskRunner(config, agent_registry, workspace_manager, gatekeeper)
    queue_manager = QueueManager(config.queue_path, config.queue_contracts_dir, config.root_dir)
    recovered = queue_manager.recover_stale_tasks()
    if recovered:
        recovered_list = ", ".join(recovered)
        print(f"[orchestrator] Recovered stale running tasks: {recovered_list}")
        print("[orchestrator] Halting queue until operator reviews recovered tasks.")
        return
    if args.nightly:
        runner.run_all(queue_manager)
    else:
        runner.run_once(queue_manager)


if __name__ == "__main__":
    main()
