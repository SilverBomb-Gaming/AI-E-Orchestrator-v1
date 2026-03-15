import pytest

from orchestrator.agent_execution_interface import AgentExecutionRequest, AgentExecutionResult
from orchestrator.architecture_blueprint import ConversationalRequest, TaskContract
from orchestrator.artifact_store_interface import ArtifactDescriptor, ArtifactStoreSummary
from orchestrator.chat_gateway_interface import ChatPromptEnvelope, NormalizedRequestEnvelope
from orchestrator.planner_agent_interface import PlanningStrategyContract


pytestmark = pytest.mark.fast


def test_chat_gateway_contracts_are_explicit():
    envelope = ChatPromptEnvelope(
        prompt_text="Build a report-only plan.",
        session_id="SESSION_001",
        channel="cli_chat",
        received_at="2026-03-15T00:00:00Z",
        metadata={"operator": "local"},
    )
    normalized = NormalizedRequestEnvelope(request_payload={"request_id": "REQ_001"})

    assert envelope.channel == "cli_chat"
    assert normalized.schema_version == "v1"
    assert normalized.source == "chat_gateway"


def test_planner_strategy_contract_tracks_phase_and_artifacts():
    strategy = PlanningStrategyContract(
        request_id="REQ_001",
        request_type="report_request",
        goals=["stay architecture_only"],
        constraints=["Do not modify runner.py"],
        requested_artifacts=["summary.md"],
    )

    assert strategy.planning_phase_id == "PHASE_2"
    assert strategy.requested_artifacts == ["summary.md"]


def test_agent_execution_contracts_remain_non_runtime():
    task = TaskContract(
        task_id="REQ_001_GRAPH",
        request_id="REQ_001",
        task_type="task_graph_emission",
        objective="Emit a task graph.",
    )
    request = AgentExecutionRequest(agent_name="TestingAgent", task=task, allowed_tools=["pytest"])
    result = AgentExecutionResult(agent_name="TestingAgent", task_id=task.task_id, status="planned")

    assert request.allowed_tools == ["pytest"]
    assert result.status == "planned"
    assert result.validation_results == []


def test_artifact_store_contracts_cover_expected_categories():
    descriptor = ArtifactDescriptor(
        artifact_id="ART_001",
        request_id="REQ_001",
        task_id="REQ_001_REPORT",
        category="structured_reports",
        relative_path="runs/REQ_001/report_outline.md",
        created_at="2026-03-15T00:00:00Z",
    )
    summary = ArtifactStoreSummary(
        request_id="REQ_001",
        artifact_counts={"structured_reports": 1},
        categories=["structured_reports"],
    )

    assert descriptor.category == "structured_reports"
    assert summary.artifact_counts["structured_reports"] == 1


def test_interface_contracts_accept_existing_request_types():
    request = ConversationalRequest(
        request_id="REQ_001",
        session_id="SESSION_001",
        channel="cli_chat",
        operator_prompt="Generate an architecture report.",
        created_at="2026-03-15T00:00:00Z",
    )

    assert request.request_id == "REQ_001"
    assert request.channel == "cli_chat"