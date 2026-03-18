import pytest

from ai_e_runtime.planner import RuleBasedPlanner
from ai_e_runtime.planner_task_graph import build_plan_task_graph


pytestmark = pytest.mark.fast


def test_plan_task_graph_preserves_order_and_dependencies() -> None:
    planner = RuleBasedPlanner()
    plan = planner.plan(
        "Fix LEVEL_0001 zombie animation, weapon bootstrap, and KBM controls",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
        request_id="REQ_GRAPH123456",
    )

    graph = build_plan_task_graph(plan, request_id="REQ_GRAPH123456", task_id_prefix="INTAKE_GRAPH123456")

    assert [node.task_id for node in graph.nodes] == [
        "INTAKE_GRAPH123456__STEP_01",
        "INTAKE_GRAPH123456__STEP_02",
        "INTAKE_GRAPH123456__STEP_03",
        "INTAKE_GRAPH123456__STEP_04",
        "INTAKE_GRAPH123456__STEP_05",
    ]
    assert graph.nodes[0].dependencies == []
    assert graph.nodes[1].dependencies == ["INTAKE_GRAPH123456__STEP_01"]
    assert graph.nodes[4].dependencies == ["INTAKE_GRAPH123456__STEP_04"]
    assert graph.nodes[3].title == "Validate integrated result"