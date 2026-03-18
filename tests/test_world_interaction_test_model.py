import pytest

from ai_e_runtime.world_interaction_test_model import build_level0001_world_interaction_test_model


pytestmark = pytest.mark.fast


def test_world_interaction_test_model_contains_expected_level0001_tests() -> None:
    model = build_level0001_world_interaction_test_model()

    assert model.target_scene == "Assets/AI_E_TestScenes/MinimalPlayableArena.unity"
    assert model.target_level == "LEVEL_0001"
    assert model.control_mode == "planned_player_control"
    assert [test.test_id for test in model.tests] == [
        "movement_test",
        "route_traversal_test",
        "enemy_engagement_test",
        "weapon_firing_test",
        "health_damage_test",
        "interaction_logging_test",
    ]
    assert "followup_signal" in model.interaction_log_schema