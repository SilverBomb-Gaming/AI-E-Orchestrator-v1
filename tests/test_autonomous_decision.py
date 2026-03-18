import pytest

from ai_e_runtime.autonomous_decision import DecisionRuntimeContext, evaluate_autonomous_decision


pytestmark = pytest.mark.fast


def test_autonomous_decision_requires_approval_for_supported_compatible_capability():
    decision = evaluate_autonomous_decision(
        requested_intent="mutate",
        resolved_intent="mutate",
        mutation_capable=True,
        capability_supported=True,
        eligible_for_auto=False,
        approval_required_by_capability=True,
        intelligence_execution_decision="approval_required",
        intelligence_summary="Capability is proven but still approval-gated.",
        auto_execution_reason=None,
        missing_evidence=[],
        content_policy_decision="allowed",
        content_policy_summary="Requested content fits the ESRB M project target.",
        rating_locked=True,
        runtime_context=DecisionRuntimeContext(session_phase="approval_auto_decision"),
    )

    assert decision.decision == "require_approval"
    assert decision.approval_required is True
    assert decision.blocked is False


def test_autonomous_decision_auto_executes_when_capability_is_auto_eligible():
    decision = evaluate_autonomous_decision(
        requested_intent="mutate",
        resolved_intent="mutate",
        mutation_capable=True,
        capability_supported=True,
        eligible_for_auto=True,
        approval_required_by_capability=False,
        intelligence_execution_decision="auto_execute",
        intelligence_summary="Capability has sufficient recorded evidence for controlled automatic execution.",
        auto_execution_reason="Autonomy Promotion v1 thresholds satisfied.",
        missing_evidence=[],
        content_policy_decision="allowed",
        content_policy_summary="Requested content fits the ESRB M project target.",
        rating_locked=True,
    )

    assert decision.decision == "auto_execute"
    assert decision.auto_execute is True
    assert decision.promotion_basis == "Autonomy Promotion v1 thresholds satisfied."


def test_autonomous_decision_blocks_locked_rating_mismatch():
    decision = evaluate_autonomous_decision(
        requested_intent="mutate",
        resolved_intent="mutate",
        mutation_capable=True,
        capability_supported=True,
        eligible_for_auto=False,
        approval_required_by_capability=False,
        intelligence_execution_decision="approval_required",
        intelligence_summary="Capability is supported.",
        auto_execution_reason=None,
        missing_evidence=[],
        content_policy_decision="blocked",
        content_policy_summary="Requested content exceeds the locked ESRB T target and requires upgrade to M.",
        rating_locked=True,
    )

    assert decision.decision == "block"
    assert decision.content_policy_block is True
    assert decision.fail_closed_reason == "Locked rating profile blocks this task."


def test_autonomous_decision_requires_review_for_unlocked_rating_mismatch():
    decision = evaluate_autonomous_decision(
        requested_intent="mutate",
        resolved_intent="mutate",
        mutation_capable=True,
        capability_supported=True,
        eligible_for_auto=False,
        approval_required_by_capability=False,
        intelligence_execution_decision="approval_required",
        intelligence_summary="Capability is supported.",
        auto_execution_reason=None,
        missing_evidence=[],
        content_policy_decision="requires_review",
        content_policy_summary="Requested content exceeds the current ESRB T target and would require upgrade to M.",
        rating_locked=False,
    )

    assert decision.decision == "require_review"
    assert decision.review_required is True
    assert decision.approval_required is True


def test_autonomous_decision_blocks_unsupported_mutation_capability():
    decision = evaluate_autonomous_decision(
        requested_intent="mutate",
        resolved_intent="mutate",
        mutation_capable=False,
        capability_supported=False,
        eligible_for_auto=False,
        approval_required_by_capability=False,
        intelligence_execution_decision="blocked",
        intelligence_summary="No write-capable capability matched the request.",
        auto_execution_reason=None,
        missing_evidence=["capability contract", "sandbox validation proof", "rollback proof"],
        content_policy_decision="allowed",
        content_policy_summary="Requested content fits the ESRB M project target.",
        rating_locked=True,
    )

    assert decision.decision == "block"
    assert decision.capability_supported is False
    assert decision.fail_closed_reason == "No supported write-capable capability matched the request."


def test_autonomous_decision_requires_sandbox_first_when_evidence_is_insufficient():
    decision = evaluate_autonomous_decision(
        requested_intent="mutate",
        resolved_intent="mutate",
        mutation_capable=True,
        capability_supported=True,
        eligible_for_auto=False,
        approval_required_by_capability=True,
        intelligence_execution_decision="sandbox_first",
        intelligence_summary="Capability lacks enough recorded evidence for real-target execution and should prove itself in sandbox first.",
        auto_execution_reason=None,
        missing_evidence=["sandbox validation proof", "rollback proof"],
        content_policy_decision="allowed",
        content_policy_summary="Requested content fits the ESRB M project target.",
        rating_locked=True,
    )

    assert decision.decision == "sandbox_first"
    assert decision.sandbox_first is True
    assert decision.approval_required is True