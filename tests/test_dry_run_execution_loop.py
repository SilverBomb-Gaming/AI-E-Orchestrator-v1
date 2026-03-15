import json

import pytest

from dry_run_execution_loop import run_dry_run_execution_test


pytestmark = pytest.mark.fast


def test_dry_run_execution_loop_writes_simulated_outputs(tmp_path):
    artifacts = run_dry_run_execution_test(tmp_path / "aie_dry_run_execution_test")

    task_graph = json.loads(artifacts.task_graph_path.read_text(encoding="utf-8"))
    execution_results = json.loads(artifacts.execution_results_path.read_text(encoding="utf-8"))
    artifact_registry = json.loads(artifacts.artifact_registry_path.read_text(encoding="utf-8"))
    validation_results = json.loads(artifacts.validation_results_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert [task["task_type"] for task in task_graph["tasks"]] == [
        "request_analysis",
        "task_graph_emission",
        "report_contract_preparation",
    ]
    assert all(result["status"] == "simulated_success" for result in execution_results["execution_results"])
    assert len(artifact_registry["artifacts"]) == 3
    assert all(entry["validation"]["validation_status"] == "passed" for entry in validation_results["validation_results"])
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report