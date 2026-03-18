from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .capability_registry import RuntimeCapability


_AUTO_EXECUTION_REFERENCE_CAPABILITIES = {"level_0001_add_grass"}
_MIN_AUTO_PROMOTION_PASSES = 3


@dataclass(frozen=True)
class CapabilityIntelligenceAssessment:
    capability_id: str | None
    trust_score: int
    trust_band: str
    policy_state: str
    execution_decision: str
    recommended_action: str
    sandbox_first_required: bool
    auto_execution_enabled: bool
    auto_execution_reason: str | None
    missing_evidence: List[str]
    summary: str

    def to_payload(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "trust_score": self.trust_score,
            "trust_band": self.trust_band,
            "policy_state": self.policy_state,
            "execution_decision": self.execution_decision,
            "recommended_action": self.recommended_action,
            "sandbox_first_required": self.sandbox_first_required,
            "auto_execution_enabled": self.auto_execution_enabled,
            "auto_execution_reason": self.auto_execution_reason,
            "missing_evidence": list(self.missing_evidence),
            "summary": self.summary,
        }


def assess_capability_intelligence(capability: RuntimeCapability) -> CapabilityIntelligenceAssessment:
    missing_evidence: List[str] = []
    if capability.times_passed <= 0:
        missing_evidence.append("successful validation pass")
    if not capability.sandbox_verified:
        missing_evidence.append("sandbox validation proof")
    if not capability.real_target_verified:
        missing_evidence.append("explicit real-target proof")
    if not capability.rollback_verified:
        missing_evidence.append("rollback proof")

    trust_score = 0
    if capability.times_attempted > 0:
        trust_score += 10
    trust_score += min(20, max(0, capability.times_passed) * 5)
    if capability.last_validation_result == "passed":
        trust_score += 10
    elif capability.last_validation_result not in {"none", "passed"}:
        trust_score = max(0, trust_score - 10)
    if capability.sandbox_verified:
        trust_score += 15
    if capability.real_target_verified:
        trust_score += 20
    if capability.rollback_verified:
        trust_score += 25
    if capability.eligible_for_auto and not capability.approval_required:
        trust_score += 10
    trust_score = max(0, min(100, trust_score))

    if trust_score >= 85:
        trust_band = "high"
    elif trust_score >= 60:
        trust_band = "guarded"
    elif trust_score >= 30:
        trust_band = "developing"
    else:
        trust_band = "low"

    no_recent_failures = (
        capability.times_attempted == capability.times_passed
        and capability.last_validation_result == "passed"
        and capability.last_rollback_result in {"none", "passed"}
    )
    auto_promotion_eligible = (
        capability.capability_id in _AUTO_EXECUTION_REFERENCE_CAPABILITIES
        and capability.real_target_verified
        and capability.rollback_verified
        and capability.times_passed >= _MIN_AUTO_PROMOTION_PASSES
        and no_recent_failures
    )

    if auto_promotion_eligible:
        policy_state = "proven"
        execution_decision = "auto_execute"
        recommended_action = "auto_execute"
        sandbox_first_required = False
        auto_execution_enabled = True
        auto_execution_reason = (
            "Capability satisfied Autonomy Promotion v1 thresholds: explicit allowlist, real-target proof, rollback proof, "
            f"at least {_MIN_AUTO_PROMOTION_PASSES} successful passes, and no recorded recent failures."
        )
        summary = "Capability has sufficient recorded evidence for controlled automatic execution."
    elif capability.times_passed <= 0 or not capability.sandbox_verified:
        policy_state = "test_only"
        execution_decision = "sandbox_first"
        recommended_action = "sandbox_first"
        sandbox_first_required = True
        auto_execution_enabled = False
        auto_execution_reason = None
        summary = "Capability lacks enough recorded evidence for real-target execution and should prove itself in sandbox first."
    elif capability.approval_required or not capability.eligible_for_auto or not auto_promotion_eligible:
        policy_state = "proven" if capability.rollback_verified else "approval_gated"
        execution_decision = "approval_required"
        recommended_action = "approval_required"
        sandbox_first_required = False
        auto_execution_enabled = False
        auto_execution_reason = None
        if capability.rollback_verified:
            if not no_recent_failures:
                summary = "Capability is proven by recorded evidence but reverted to approval-required because recent failures or regressions were detected."
            else:
                summary = "Capability is proven by recorded evidence but remains approval-gated until explicit automation promotion is granted."
        else:
            summary = "Capability has usable evidence but still requires operator approval because automation promotion has not been earned."
    else:
        policy_state = "blocked"
        execution_decision = "blocked"
        recommended_action = "blocked"
        sandbox_first_required = False
        auto_execution_enabled = False
        auto_execution_reason = None
        summary = "Capability should remain blocked until missing evidence is resolved."

    return CapabilityIntelligenceAssessment(
        capability_id=capability.capability_id,
        trust_score=trust_score,
        trust_band=trust_band,
        policy_state=policy_state,
        execution_decision=execution_decision,
        recommended_action=recommended_action,
        sandbox_first_required=sandbox_first_required,
        auto_execution_enabled=auto_execution_enabled,
        auto_execution_reason=auto_execution_reason,
        missing_evidence=missing_evidence,
        summary=summary,
    )


def assess_mutation_without_capability() -> CapabilityIntelligenceAssessment:
    return CapabilityIntelligenceAssessment(
        capability_id=None,
        trust_score=0,
        trust_band="low",
        policy_state="blocked",
        execution_decision="blocked",
        recommended_action="blocked",
        sandbox_first_required=True,
        auto_execution_enabled=False,
        auto_execution_reason=None,
        missing_evidence=["capability contract", "sandbox validation proof", "rollback proof"],
        summary="No write-capable capability matched the request, so the mutation should remain blocked from autonomous execution.",
    )


__all__ = [
    "CapabilityIntelligenceAssessment",
    "assess_capability_intelligence",
    "assess_mutation_without_capability",
]