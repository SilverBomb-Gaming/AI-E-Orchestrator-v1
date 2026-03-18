import pytest

from ai_e_runtime.followup_task_evolver import FollowupTaskEvolver, InteractionFinding


pytestmark = pytest.mark.fast


def test_followup_task_evolver_generates_expected_tasks_from_findings() -> None:
    evolver = FollowupTaskEvolver()

    tasks = evolver.evolve(
        [
            InteractionFinding(finding_type="navigation", summary="Pathways are confusing near the arena exit."),
            InteractionFinding(finding_type="enemy", summary="Zombie never reaches player during engagement."),
            InteractionFinding(finding_type="weapon", summary="Weapon does not fire after bootstrap."),
            InteractionFinding(finding_type="collision", summary="Player gets stuck on geometry by the side wall."),
        ]
    )

    assert [task.title for task in tasks] == [
        "Generate navigation cleanup task",
        "Generate enemy approach tuning task",
        "Generate weapon bootstrap repair task",
        "Generate collider cleanup task",
    ]