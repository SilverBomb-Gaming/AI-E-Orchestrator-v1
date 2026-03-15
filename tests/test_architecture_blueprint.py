import json
from pathlib import Path

import pytest

from orchestrator.architecture_blueprint import (
    ConversationalRequest,
    RetryPolicy,
    TaskContract,
    TaskGraph,
    ValidationRule,
    default_remote_work_constraints,
    default_remote_work_phases,
    required_response_sections,
    required_run_log_fields,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_conversational_request_payload_is_deterministic():
    request = ConversationalRequest(
        request_id="REQ_001",
        session_id="SESSION_001",
        channel="cli_chat",
        operator_prompt="show failures",
        created_at="2026-03-15T00:00:00Z",
        intent="show_failures",
        context={"zeta": 2, "alpha": 1},
        constraints=["Do not start LEVEL_0002."],
        requested_artifacts=["summary.md"],
    )

    assert request.to_payload() == {
        "request_id": "REQ_001",
        "session_id": "SESSION_001",
        "channel": "cli_chat",
        "operator_prompt": "show failures",
        "created_at": "2026-03-15T00:00:00Z",
        "intent": "show_failures",
        "clarification_needed": False,
        "context": {"alpha": 1, "zeta": 2},
        "constraints": ["Do not start LEVEL_0002."],
        "requested_artifacts": ["summary.md"],
    }


def test_task_graph_dependency_map_is_stable():
    request = ConversationalRequest(
        request_id="REQ_001",
        session_id="SESSION_001",
        channel="cli_chat",
        operator_prompt="run combat test",
        created_at="2026-03-15T00:00:00Z",
    )
    task_a = TaskContract(
        task_id="TASK_A",
        request_id="REQ_001",
        task_type="planning",
        objective="Build the plan.",
        validation_rules=[ValidationRule(rule_id="VR_001", description="Must stay deterministic.")],
    )
    task_b = TaskContract(
        task_id="TASK_B",
        request_id="REQ_001",
        task_type="reporting",
        objective="Summarize the results.",
        dependencies=["TASK_A"],
        retry_policy=RetryPolicy(max_attempts=2, retry_on=["TIMEOUT"]),
    )

    graph = TaskGraph(request=request, tasks=[task_a, task_b])

    assert graph.dependency_map() == {"TASK_A": [], "TASK_B": ["TASK_A"]}
    assert graph.task_ids() == ["TASK_A", "TASK_B"]


def test_remote_work_defaults_match_handoff_rules():
    constraints = default_remote_work_constraints()
    phases = default_remote_work_phases()
    log_fields = required_run_log_fields()
    response_sections = required_response_sections()

    assert "Do not modify gameplay systems." in constraints
    assert "Do not bypass policy or validation layers." in constraints
    assert [phase.phase_id for phase in phases] == [
        "PHASE_1",
        "PHASE_2",
        "PHASE_3",
        "PHASE_4",
        "PHASE_5",
        "PHASE_6",
        "PHASE_7",
        "PHASE_8",
    ]
    assert log_fields == [
        "run_id",
        "timestamp",
        "task_list",
        "policy_decisions",
        "artifacts",
        "validation_results",
        "recommendations",
    ]
    assert response_sections == [
        "SUMMARY",
        "FACTS",
        "ASSUMPTIONS",
        "RECOMMENDATIONS",
        "TIMESTAMP",
    ]


def test_architecture_templates_are_valid_json():
    request_template = ROOT / "contracts" / "templates" / "conversational_request_template.json"
    graph_template = ROOT / "contracts" / "templates" / "task_graph_template.json"

    request_payload = json.loads(request_template.read_text(encoding="utf-8"))
    graph_payload = json.loads(graph_template.read_text(encoding="utf-8"))

    assert request_payload["request_id"].startswith("REQ_")
    assert request_payload["channel"] == "cli_chat"
    assert graph_payload["tasks"][0]["assigned_agent"] == "PlannerAgent"
    assert graph_payload["tasks"][1]["dependencies"] == ["TASK_001"]