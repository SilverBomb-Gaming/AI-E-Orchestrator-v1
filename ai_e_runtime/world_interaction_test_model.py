from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class WorldInteractionTestCase:
    test_id: str
    title: str
    objective: str
    actions: List[str]
    expected_observations: List[str]
    log_fields: List[str]

    def to_payload(self) -> dict[str, object]:
        return {
            "test_id": self.test_id,
            "title": self.title,
            "objective": self.objective,
            "actions": list(self.actions),
            "expected_observations": list(self.expected_observations),
            "log_fields": list(self.log_fields),
        }


@dataclass(frozen=True)
class WorldInteractionTestModel:
    model_id: str
    target_scene: str
    target_level: str
    control_mode: str
    tests: List[WorldInteractionTestCase]
    interaction_log_schema: List[str]

    def to_payload(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "target_scene": self.target_scene,
            "target_level": self.target_level,
            "control_mode": self.control_mode,
            "tests": [test.to_payload() for test in self.tests],
            "interaction_log_schema": list(self.interaction_log_schema),
        }


def build_level0001_world_interaction_test_model(
    *,
    target_scene: str = "Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
    target_level: str = "LEVEL_0001",
) -> WorldInteractionTestModel:
    tests = [
        WorldInteractionTestCase(
            test_id="movement_test",
            title="Movement test",
            objective="Confirm the player can move through the arena with expected input response.",
            actions=[
                "Spawn into the target scene.",
                "Move forward, backward, left, and right.",
                "Observe acceleration, stoppage, and collision response.",
            ],
            expected_observations=[
                "Player responds to movement input.",
                "No immediate movement lock or spawn collision.",
            ],
            log_fields=["position_trace", "movement_response", "collision_events"],
        ),
        WorldInteractionTestCase(
            test_id="route_traversal_test",
            title="Route/pathway traversal test",
            objective="Verify the player can traverse intended pathways and transitions.",
            actions=[
                "Attempt traversal across each primary route or pathway.",
                "Record dead ends, confusing turns, or blocked movement.",
            ],
            expected_observations=[
                "Primary routes are reachable.",
                "Pathways communicate progression clearly enough for navigation.",
            ],
            log_fields=["route_id", "traversal_result", "navigation_confusion_points"],
        ),
        WorldInteractionTestCase(
            test_id="enemy_engagement_test",
            title="Enemy engagement test",
            objective="Observe whether enemies detect, approach, and engage the player.",
            actions=[
                "Enter enemy detection range.",
                "Allow time for approach and engagement.",
                "Record approach, pathing, and attack behavior.",
            ],
            expected_observations=[
                "Enemy attempts to approach the player.",
                "Enemy interaction is observable and not permanently idle.",
            ],
            log_fields=["enemy_id", "approach_started", "engagement_result", "pathing_failures"],
        ),
        WorldInteractionTestCase(
            test_id="weapon_firing_test",
            title="Weapon firing test",
            objective="Confirm weapon bootstrap and firing interactions are observable in runtime.",
            actions=[
                "Trigger weapon equip/bootstrap path.",
                "Attempt firing input.",
                "Record projectile, muzzle, or firing feedback.",
            ],
            expected_observations=[
                "Weapon bootstrap completes.",
                "A firing action or failure is explicitly observable.",
            ],
            log_fields=["weapon_state", "firing_input_result", "projectile_observed"],
        ),
        WorldInteractionTestCase(
            test_id="health_damage_test",
            title="Health/damage observation",
            objective="Observe whether combat interactions affect player health and damage state.",
            actions=[
                "Allow enemy interaction or hazard contact.",
                "Observe health, damage, or hit feedback.",
            ],
            expected_observations=[
                "Damage events are visible when expected.",
                "Health or hit-state changes are logged clearly enough for review.",
            ],
            log_fields=["damage_event", "health_before", "health_after", "hit_feedback"],
        ),
        WorldInteractionTestCase(
            test_id="interaction_logging_test",
            title="Interaction logging",
            objective="Produce a structured log of all observed world interactions for later task evolution.",
            actions=[
                "Capture noteworthy movement, combat, and traversal outcomes.",
                "Record failures, confusion points, and stuck states.",
            ],
            expected_observations=[
                "A structured interaction log is produced.",
                "Observed issues are specific enough to derive follow-up tasks.",
            ],
            log_fields=["timestamp", "interaction_type", "result", "evidence", "followup_signal"],
        ),
    ]
    interaction_log_schema = [
        "timestamp",
        "test_id",
        "interaction_type",
        "actor",
        "result",
        "evidence",
        "severity",
        "followup_signal",
    ]
    return WorldInteractionTestModel(
        model_id="LEVEL_0001_WORLD_INTERACTION_MODEL",
        target_scene=target_scene,
        target_level=target_level,
        control_mode="planned_player_control",
        tests=tests,
        interaction_log_schema=interaction_log_schema,
    )


__all__ = [
    "WorldInteractionTestCase",
    "WorldInteractionTestModel",
    "build_level0001_world_interaction_test_model",
]