from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class PlanStep:
    step_index: int
    title: str
    task_type: str
    component_key: str
    priority: int
    execution_mode: str = "bounded_read_only"

    def to_payload(self) -> dict[str, object]:
        return {
            "step_index": self.step_index,
            "title": self.title,
            "task_type": self.task_type,
            "component_key": self.component_key,
            "priority": self.priority,
            "execution_mode": self.execution_mode,
        }


@dataclass(frozen=True)
class PlanResult:
    plan_id: str
    request_type: str
    target_repo: str
    operator_prompt: str
    steps: List[PlanStep]

    @property
    def is_composite(self) -> bool:
        return self.request_type == "COMPOSITE_REQUEST"

    def plan_step_titles(self) -> List[str]:
        return [step.title for step in self.steps]

    def summary_text(self) -> str:
        lines = ["PLAN"]
        for step in self.steps:
            lines.append(f"{step.step_index}. {step.title}")
        return "\n".join(lines)

    def to_payload(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "request_type": self.request_type,
            "target_repo": self.target_repo,
            "operator_prompt": self.operator_prompt,
            "is_composite": self.is_composite,
            "steps": [step.to_payload() for step in self.steps],
            "summary_text": self.summary_text(),
        }


class RuleBasedPlanner:
    """Deterministic prompt-to-plan decomposition for AI-E Command Center."""

    _STABILIZATION_VERBS = ("fix", "stabilize", "repair", "restore")
    _DIAGNOSTIC_VERBS = ("inspect", "diagnose", "audit", "analyze", "review", "check")
    _VALIDATION_VERBS = ("validate", "verify", "confirm")
    _AUTONOMOUS_ITERATION_MARKERS = (
        "controlling the player",
        "control the player",
        "document world interactions",
        "world interactions",
        "evolve follow-up tasks",
        "follow-up tasks",
        "keep iterating",
        "continue iterating",
        "session budget",
        "2-hour session",
        "until the session ends",
    )

    _COMPONENT_RULES = (
        {
            "key": "zombie_animation",
            "aliases": ("zombie animation", "animation pipeline"),
            "inspect_title": "Inspect zombie animation pipeline",
            "stabilize_title": "Stabilize zombie animation pipeline",
            "validate_title": "Validate zombie animation",
        },
        {
            "key": "weapon_bootstrap",
            "aliases": ("weapon bootstrap", "weapon startup"),
            "inspect_title": "Inspect weapon bootstrap",
            "stabilize_title": "Stabilize weapon bootstrap",
            "validate_title": "Validate weapon bootstrap",
        },
        {
            "key": "kbm_controls",
            "aliases": ("kbm controls", "keyboard and mouse bindings", "keyboard and mouse", "mouse bindings"),
            "inspect_title": "Inspect KBM controls",
            "stabilize_title": "Stabilize KBM controls",
            "validate_title": "Validate KBM controls",
        },
        {
            "key": "unity_logs",
            "aliases": ("unity logs", "editor logs"),
            "inspect_title": "Inspect Unity logs",
            "stabilize_title": "Inspect Unity logs",
            "validate_title": "Validate Unity log findings",
        },
        {
            "key": "zombie_spawning",
            "aliases": ("zombie spawning", "zombie spawn", "spawn logic"),
            "inspect_title": "Inspect zombie spawning",
            "stabilize_title": "Stabilize zombie spawning",
            "validate_title": "Validate zombie spawning",
        },
        {
            "key": "queue_state",
            "aliases": ("queue state", "queue status"),
            "inspect_title": "Inspect queue state",
            "stabilize_title": "Inspect queue state",
            "validate_title": "Validate queue state",
        },
        {
            "key": "minimap",
            "aliases": ("minimap",),
            "inspect_title": "Inspect minimap",
            "stabilize_title": "Stabilize minimap",
            "validate_title": "Validate minimap",
        },
        {
            "key": "combat_loop",
            "aliases": ("combat loop", "level_0001 combat loop"),
            "inspect_title": "Inspect LEVEL_0001 combat loop",
            "stabilize_title": "Stabilize LEVEL_0001 combat loop",
            "validate_title": "Validate LEVEL_0001 combat loop",
        },
    )

    def plan(
        self,
        operator_prompt: str,
        *,
        target_repo: str,
        request_id: str,
    ) -> PlanResult:
        normalized_prompt = self._normalize(operator_prompt)
        if not normalized_prompt:
            raise ValueError("operator prompt must not be empty")
        request_type = self.classify_request(normalized_prompt)
        components = self.extract_components(normalized_prompt)
        steps = self._build_steps(normalized_prompt, request_type, components)
        return PlanResult(
            plan_id=f"PLAN_{request_id.split('_', 1)[1]}",
            request_type=request_type,
            target_repo=target_repo,
            operator_prompt=normalized_prompt,
            steps=steps,
        )

    def classify_request(self, operator_prompt: str) -> str:
        normalized = self._normalize(operator_prompt)
        if self._is_autonomous_iteration_request(normalized):
            return "AUTONOMOUS_GAMEPLAY_ITERATION_REQUEST"
        components = self.extract_components(normalized)
        action_groups = self._action_groups(normalized)
        if len(components) > 1 or len(action_groups) > 1:
            return "COMPOSITE_REQUEST"
        if "stabilization" in action_groups:
            return "STABILIZATION_REQUEST"
        if "validation" in action_groups:
            return "VALIDATION_REQUEST"
        if "diagnostic" in action_groups:
            return "DIAGNOSTIC_REQUEST"
        return "DIAGNOSTIC_REQUEST"

    def extract_components(self, operator_prompt: str) -> List[dict[str, str]]:
        normalized = self._normalize(operator_prompt)
        discovered: List[dict[str, str]] = []
        for component in self._COMPONENT_RULES:
            if any(alias in normalized for alias in component["aliases"]):
                discovered.append(component)
        if discovered:
            return discovered
        return [self._fallback_component(normalized)]

    def _build_steps(
        self,
        operator_prompt: str,
        request_type: str,
        components: Iterable[dict[str, str]],
    ) -> List[PlanStep]:
        component_list = list(components)
        steps: List[PlanStep] = []
        action_groups = self._action_groups(operator_prompt)

        if request_type == "AUTONOMOUS_GAMEPLAY_ITERATION_REQUEST":
            return [
                self._step(1, "Plan world layout and pathway improvement", "planning_step", "world_layout", 20),
                self._step(2, "Implement world layout/pathway improvement", "implementation_step", "world_layout", 15),
                self._step(3, "Run runtime gameplay validation", "runtime_test_step", "runtime_validation", 20),
                self._step(4, "Execute player-controlled world interaction test", "world_interaction_test_step", "player_control_test", 20),
                self._step(5, "Document world interaction findings", "interaction_review_step", "interaction_review", 25),
                self._step(6, "Evolve follow-up tasks from findings", "followup_evolution_step", "followup_evolution", 25),
                self._step(7, "Repeat iteration while session time remains", "iteration_loop_step", "iteration_loop", 30),
            ]

        if request_type == "COMPOSITE_REQUEST" and len(action_groups) > 1:
            primary_component = component_list[0]
            if "diagnostic" in action_groups:
                steps.append(self._step(len(steps) + 1, primary_component["inspect_title"], "diagnostic_step", primary_component["key"], 25))
            if "stabilization" in action_groups:
                steps.append(self._step(len(steps) + 1, primary_component["stabilize_title"], "stabilization_step", primary_component["key"], 25))
            if "validation" in action_groups:
                steps.append(self._step(len(steps) + 1, primary_component["validate_title"], "validation_step", primary_component["key"], 30))
            steps.append(self._step(len(steps) + 1, "Generate summary report", "summary_step", "summary", 40))
            return steps

        if request_type == "STABILIZATION_REQUEST":
            component = component_list[0]
            return [self._step(1, component["stabilize_title"], "stabilization_step", component["key"], 25)]

        if request_type == "COMPOSITE_REQUEST":
            for component in component_list:
                steps.append(self._step(len(steps) + 1, component["inspect_title"], "diagnostic_step", component["key"], 25))
            validation_title = "Validate integrated result" if len(component_list) > 1 else "Run stabilization validation"
            steps.append(self._step(len(steps) + 1, validation_title, "validation_step", "integrated_validation", 30))
            steps.append(self._step(len(steps) + 1, "Generate summary artifact", "summary_step", "summary", 40))
            return steps

        if request_type == "VALIDATION_REQUEST":
            component = component_list[0]
            return [self._step(1, component["validate_title"], "validation_step", component["key"], 30)]

        component = component_list[0]
        return [self._step(1, component["inspect_title"], "diagnostic_step", component["key"], 35)]

    def _action_groups(self, operator_prompt: str) -> set[str]:
        normalized = self._normalize(operator_prompt)
        groups: set[str] = set()
        if any(self._contains_verb(normalized, verb) for verb in self._STABILIZATION_VERBS):
            groups.add("stabilization")
        if any(self._contains_verb(normalized, verb) for verb in self._DIAGNOSTIC_VERBS):
            groups.add("diagnostic")
        if any(self._contains_verb(normalized, verb) for verb in self._VALIDATION_VERBS):
            groups.add("validation")
        return groups

    def _contains_verb(self, text: str, verb: str) -> bool:
        return re.search(rf"\b{re.escape(verb)}\b", text) is not None

    def _is_autonomous_iteration_request(self, text: str) -> bool:
        return any(marker in text for marker in self._AUTONOMOUS_ITERATION_MARKERS)

    def _fallback_component(self, normalized_prompt: str) -> dict[str, str]:
        cleaned = normalized_prompt.rstrip(".?")
        title = cleaned[0].upper() + cleaned[1:] if cleaned else "Operator request"
        return {
            "key": "general_request",
            "inspect_title": f"Inspect request scope: {title}",
            "stabilize_title": f"Stabilize request scope: {title}",
            "validate_title": f"Validate request scope: {title}",
        }

    def _step(self, step_index: int, title: str, task_type: str, component_key: str, priority: int) -> PlanStep:
        return PlanStep(
            step_index=step_index,
            title=title,
            task_type=task_type,
            component_key=component_key,
            priority=priority,
        )

    def _normalize(self, operator_prompt: str) -> str:
        return re.sub(r"\s+", " ", str(operator_prompt or "")).strip().lower()


__all__ = ["PlanResult", "PlanStep", "RuleBasedPlanner"]