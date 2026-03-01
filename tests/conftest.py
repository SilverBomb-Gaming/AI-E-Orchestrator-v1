import pytest

from orchestrator.config import OrchestratorConfig


@pytest.fixture()
def cycle_config(tmp_path):
    config = OrchestratorConfig(
        root_dir=tmp_path,
        runs_dir=tmp_path / "runs",
        workspaces_dir=tmp_path / "workspaces",
        queue_path=tmp_path / "backlog" / "queue.json",
        queue_contracts_dir=tmp_path / "contracts" / "queue",
        agent_registry_path=tmp_path / "agents" / "registry.json",
        contracts_dir=tmp_path / "contracts",
        templates_dir=tmp_path / "contracts" / "templates",
        approvals_path=tmp_path / "backlog" / "approvals.json",
        command_allowlist_path=tmp_path / "backlog" / "command_allowlist.json",
        default_timeout_seconds=900,
    )
    config.ensure_directories()
    return config
