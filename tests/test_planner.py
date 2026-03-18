import pytest

from ai_e_runtime.planner import RuleBasedPlanner


pytestmark = pytest.mark.fast


def test_planner_decomposes_composite_stabilization_request() -> None:
    planner = RuleBasedPlanner()

    plan = planner.plan(
        "Fix LEVEL_0001 zombie animation, weapon bootstrap, and KBM controls",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
        request_id="REQ_ABC123DEF456",
    )

    assert plan.plan_id == "PLAN_ABC123DEF456"
    assert plan.request_type == "COMPOSITE_REQUEST"
    assert plan.plan_step_titles() == [
        "Inspect zombie animation pipeline",
        "Inspect weapon bootstrap",
        "Inspect KBM controls",
        "Validate integrated result",
        "Generate summary artifact",
    ]


def test_planner_handles_single_diagnostic_request() -> None:
    planner = RuleBasedPlanner()

    plan = planner.plan(
        "Inspect Unity logs",
        target_repo="E:/AI projects 2025/AI-E Orchestrator v1",
        request_id="REQ_DEF456ABC123",
    )

    assert plan.request_type == "DIAGNOSTIC_REQUEST"
    assert len(plan.steps) == 1
    assert plan.steps[0].title == "Inspect Unity logs"


def test_planner_decomposes_autonomous_gameplay_iteration_prompt() -> None:
    planner = RuleBasedPlanner()

    plan = planner.plan(
        "Expand LEVEL_0001 by adding pathways instead of only enlarging the map, test it by controlling the player, document world interactions, evolve follow-up tasks from the findings, and keep iterating until the session budget is used.",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
        request_id="REQ_AUTONOMOUS123",
    )

    assert plan.request_type == "AUTONOMOUS_GAMEPLAY_ITERATION_REQUEST"
    assert plan.plan_step_titles() == [
        "Plan world layout and pathway improvement",
        "Implement world layout/pathway improvement",
        "Run runtime gameplay validation",
        "Execute player-controlled world interaction test",
        "Document world interaction findings",
        "Evolve follow-up tasks from findings",
        "Repeat iteration while session time remains",
    ]