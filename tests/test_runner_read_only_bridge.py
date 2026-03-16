import json

import pytest

from orchestrator.config import OrchestratorConfig
from orchestrator.gates import Gatekeeper
from orchestrator.registry import AgentRegistry
from orchestrator.runner import QueueManager, TaskRunner
from orchestrator.runner_read_only_bridge import execute_read_only_session
from orchestrator.workspace import WorkspaceManager


pytestmark = pytest.mark.fast


def test_execute_read_only_session_writes_live_artifacts(tmp_path):
    artifacts = execute_read_only_session(
        {"scenario": "read_completed", "session_id": "LIVE_READ_ONLY_TEST_001"},
        output_dir=tmp_path / "aie_live_read_only_session",
    )

    execution_request = json.loads(artifacts.execution_request_path.read_text(encoding="utf-8"))["execution_request"]
    execution_response = json.loads(artifacts.execution_response_path.read_text(encoding="utf-8"))["execution_response"]
    validator_summary = json.loads(artifacts.validator_summary_path.read_text(encoding="utf-8"))
    session_summary = json.loads(artifacts.session_execution_summary_path.read_text(encoding="utf-8"))["session_execution_summary"]
    handoff_report = artifacts.operator_handoff_report_path.read_text(encoding="utf-8")

    assert execution_request["scenario"] == "read_completed"
    assert execution_response["read_only_response"]["response_state"] == "read_completed"
    assert validator_summary["validator_record"]["validation_class"] == "passed"
    assert session_summary["gate_overall"] == "ALLOW"
    assert session_summary["no_write_capable_execution"] is True
    for file_name in [
        "execution_request.json",
        "execution_response.json",
        "validator_summary.json",
        "session_execution_summary.json",
        "operator_handoff_report.md",
    ]:
        assert (artifacts.session_bundle_dir / file_name).exists()
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in handoff_report


def test_runner_executes_read_only_completed_session(tmp_path):
    result, config, queue_manager = _run_single_session(tmp_path / "completed", "0001", "read_completed")

    assert result is not None
    assert result.status == "ALLOW"
    task = queue_manager.all_tasks()[0]
    assert task["status"] == "completed"

    execution_response = json.loads(
        (config.runs_dir / "aie_live_read_only_session" / "execution_response.json").read_text(encoding="utf-8")
    )["execution_response"]
    validator_summary = json.loads(
        (config.runs_dir / "aie_live_read_only_session" / "validator_summary.json").read_text(encoding="utf-8")
    )
    run_meta = json.loads((result.run_dir / "run_meta.json").read_text(encoding="utf-8"))

    assert execution_response["read_only_response"]["response_state"] == "read_completed"
    assert validator_summary["validator_record"]["validation_class"] == "passed"
    assert run_meta["live_read_only_session"]["response_state"] == "read_completed"
    assert run_meta["live_read_only_session"]["validation_class"] == "passed"


def test_runner_executes_read_only_partial_and_retryable_failed_sessions(tmp_path):
    partial_result, partial_config, partial_queue = _run_single_session(tmp_path / "partial", "0002", "read_partial")
    failed_result, failed_config, failed_queue = _run_single_session(
        tmp_path / "retryable",
        "0003",
        "read_failed_retryable",
    )

    assert partial_result is not None
    assert partial_result.status == "ASK"
    assert partial_queue.all_tasks()[0]["status"] == "needs_approval"
    partial_validator = json.loads(
        (partial_config.runs_dir / "aie_live_read_only_session" / "validator_summary.json").read_text(encoding="utf-8")
    )
    assert partial_validator["validator_record"]["validation_class"] == "partial_success"

    assert failed_result is not None
    assert failed_result.status == "ASK"
    assert failed_queue.all_tasks()[0]["status"] == "needs_approval"
    failed_validator = json.loads(
        (failed_config.runs_dir / "aie_live_read_only_session" / "validator_summary.json").read_text(encoding="utf-8")
    )
    assert failed_validator["validator_record"]["validation_class"] == "retryable_failure"


def _run_single_session(tmp_path, task_id: str, scenario: str):
    config = _make_config(tmp_path)
    contract_path = config.queue_contracts_dir / f"{task_id}_read_only_capability.json"
    contract_path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "Objective": f"Run bounded read-only live session for {scenario}",
                "type": "read_only_capability",
                "read_only_scenario": scenario,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    queue_manager = QueueManager(config.queue_path, config.queue_contracts_dir, config.root_dir)
    task_runner = TaskRunner(
        config,
        AgentRegistry(config.agent_registry_path),
        WorkspaceManager(config.workspaces_dir),
        Gatekeeper(),
    )
    result = task_runner.run_once(queue_manager)
    return result, config, queue_manager


def _make_config(tmp_path):
    root_dir = tmp_path / "repo_root"
    runs_dir = root_dir / "runs"
    workspaces_dir = root_dir / "workspaces"
    queue_path = root_dir / "backlog" / "queue.json"
    queue_contracts_dir = root_dir / "contracts" / "queue"
    agent_registry_path = root_dir / "agents" / "registry.json"
    contracts_dir = root_dir / "contracts"
    templates_dir = contracts_dir / "templates"
    approvals_path = root_dir / "backlog" / "approvals.json"
    command_allowlist_path = root_dir / "backlog" / "command_allowlist.json"

    for path in [runs_dir, workspaces_dir, queue_contracts_dir, templates_dir, approvals_path.parent, agent_registry_path.parent]:
        path.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps({"tasks": []}, indent=2), encoding="utf-8")
    approvals_path.write_text(json.dumps({"approvals": []}, indent=2), encoding="utf-8")
    command_allowlist_path.write_text(json.dumps({"exact": [], "prefix": []}, indent=2), encoding="utf-8")
    agent_registry_path.write_text(json.dumps({"agents": []}, indent=2), encoding="utf-8")

    return OrchestratorConfig(
        root_dir=root_dir,
        runs_dir=runs_dir,
        workspaces_dir=workspaces_dir,
        queue_path=queue_path,
        queue_contracts_dir=queue_contracts_dir,
        agent_registry_path=agent_registry_path,
        contracts_dir=contracts_dir,
        templates_dir=templates_dir,
        approvals_path=approvals_path,
        command_allowlist_path=command_allowlist_path,
    )