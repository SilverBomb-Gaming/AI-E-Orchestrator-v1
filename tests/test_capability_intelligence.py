import pytest

from ai_e_runtime.capability_intelligence import assess_capability_intelligence, assess_mutation_without_capability
from ai_e_runtime.capability_registry import RuntimeCapability


pytestmark = pytest.mark.fast


def test_capability_intelligence_marks_reference_grass_capability_as_proven_but_approval_gated():
    capability = RuntimeCapability(
        capability_id="level_0001_add_grass",
        title="LEVEL_0001 add grass",
        intent="mutate",
        target_level="LEVEL_0001",
        target_scene="Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
        requested_execution_lane="approval_required_mutation",
        handler_name="level_0001_grass_handler",
        agent_type="level_0001_grass_mutation_agent",
        approval_required=True,
        eligible_for_auto=False,
        evidence_state="rollback_verified",
        safety_class="approval_gated_automation",
        match_terms=["level_0001", "grass"],
        match_verbs=["make", "add"],
        times_attempted=2,
        times_passed=2,
        last_validation_result="passed",
        last_rollback_result="passed",
        sandbox_verified=True,
        real_target_verified=True,
        rollback_verified=True,
    )

    assessment = assess_capability_intelligence(capability)

    assert assessment.trust_score >= 80
    assert assessment.policy_state == "proven"
    assert assessment.execution_decision == "approval_required"
    assert assessment.recommended_action == "approval_required"
    assert assessment.sandbox_first_required is False
    assert assessment.missing_evidence == []


def test_capability_intelligence_promotes_reference_grass_capability_to_auto_execute_when_thresholds_are_met():
    capability = RuntimeCapability(
        capability_id="level_0001_add_grass",
        title="LEVEL_0001 add grass",
        intent="mutate",
        target_level="LEVEL_0001",
        target_scene="Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
        requested_execution_lane="approval_required_mutation",
        handler_name="level_0001_grass_handler",
        agent_type="level_0001_grass_mutation_agent",
        approval_required=True,
        eligible_for_auto=False,
        evidence_state="rollback_verified",
        safety_class="approval_gated_automation",
        match_terms=["level_0001", "grass"],
        match_verbs=["make", "add"],
        times_attempted=4,
        times_passed=4,
        last_validation_result="passed",
        last_rollback_result="passed",
        sandbox_verified=True,
        real_target_verified=True,
        rollback_verified=True,
    )

    assessment = assess_capability_intelligence(capability)

    assert assessment.policy_state == "proven"
    assert assessment.execution_decision == "auto_execute"
    assert assessment.recommended_action == "auto_execute"
    assert assessment.auto_execution_enabled is True
    assert assessment.auto_execution_reason is not None


def test_capability_intelligence_requires_sandbox_first_for_unproven_capability():
    capability = RuntimeCapability(
        capability_id="level_0001_remove_grass",
        title="LEVEL_0001 remove grass",
        intent="mutate",
        target_level="LEVEL_0001",
        target_scene="Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
        requested_execution_lane="approval_required_mutation",
        handler_name="level_0001_remove_grass_handler",
        agent_type="level_0001_grass_mutation_agent",
        approval_required=True,
        eligible_for_auto=False,
        evidence_state="experimental",
        safety_class="approval_gated_automation",
        match_terms=["level_0001", "grass"],
        match_verbs=["remove", "delete"],
        times_attempted=0,
        times_passed=0,
        last_validation_result="none",
        last_rollback_result="none",
        sandbox_verified=False,
        real_target_verified=False,
        rollback_verified=False,
    )

    assessment = assess_capability_intelligence(capability)

    assert assessment.policy_state == "test_only"
    assert assessment.execution_decision == "sandbox_first"
    assert assessment.recommended_action == "sandbox_first"
    assert assessment.sandbox_first_required is True
    assert "sandbox validation proof" in assessment.missing_evidence
    assert "rollback proof" in assessment.missing_evidence


def test_capability_intelligence_blocks_unmatched_mutation():
    assessment = assess_mutation_without_capability()

    assert assessment.policy_state == "blocked"
    assert assessment.execution_decision == "blocked"
    assert assessment.recommended_action == "blocked"
    assert assessment.sandbox_first_required is True