import json

import pytest

from aie_prompt_test import EXPECTED_TASK_TYPES, PROMPT_TEXT, run_first_prompt_test
from orchestrator.prompt_gateway_shim import PromptGatewayShim, PromptGatewayShimConfig


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


def test_prompt_gateway_shim_normalizes_request_payload():
    gateway = PromptGatewayShim(
        PromptGatewayShimConfig(
            request_id="REQ_TEST_001",
            session_id="SESSION_TEST_001",
            channel="cli_chat",
            received_at="2026-03-15T00:00:00Z",
            intent="create_sandbox",
            context={"project": "BABYLON VER 2"},
            constraints=["Do not execute tools."],
            requested_artifacts=["task_graph.json"],
            metadata={"source": "test"},
        )
    )

    envelope = gateway.receive_prompt("Build a sandbox.", gateway.session_metadata)
    normalized = gateway.normalize_request(envelope)
    payload = gateway.forward_to_schema_loader(normalized)

    assert payload["request_id"] == "REQ_TEST_001"
    assert payload["session_id"] == "SESSION_TEST_001"
    assert payload["context"]["project"] == "BABYLON VER 2"