import json

import pytest

from aie_prompt_test import EXPECTED_TASK_TYPES, PROMPT_TEXT, run_first_prompt_test


pytestmark = pytest.mark.fast


def test_first_prompt_loop_writes_deterministic_artifacts(tmp_path):
    artifacts = run_first_prompt_test(tmp_path / "aie_first_prompt_test")

    prompt_text = artifacts.prompt_path.read_text(encoding="utf-8")
    task_graph = json.loads(artifacts.task_graph_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert prompt_text == PROMPT_TEXT
    assert [task["task_type"] for task in task_graph["tasks"]] == EXPECTED_TASK_TYPES
    assert task_graph["dependency_map"]["REQ_AIE_FIRST_PROMPT_TEST_REPORT"] == ["REQ_AIE_FIRST_PROMPT_TEST_GRAPH"]
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report