from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List

from orchestrator.config import OrchestratorConfig
from orchestrator.utils import ensure_dir, read_json, write_json


_DEFAULT_CAPABILITY = {
    "capability_id": "level_0001_add_grass",
    "title": "LEVEL_0001 add grass",
    "intent": "mutate",
    "target_level": "LEVEL_0001",
    "target_scene": "Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
    "requested_execution_lane": "approval_required_mutation",
    "handler_name": "level_0001_grass_handler",
    "agent_type": "level_0001_grass_mutation_agent",
    "approval_required": True,
    "eligible_for_auto": False,
    "evidence_state": "experimental",
    "safety_class": "approval_gated_automation",
    "match_terms": ["level_0001", "grass"],
    "match_verbs": ["make", "add", "create", "generate", "place", "build"],
}

_MATURITY_STAGES = (
    "experimental",
    "sandbox_verified",
    "real_target_verified",
    "rollback_verified",
    "approval_verified",
    "auto_eligible",
)
_REFERENCE_CAPABILITY_ID = "level_0001_add_grass"
_REFERENCE_REAL_TARGET_SESSION_ID = "live_real_grass_validation_20260317"
_REFERENCE_REAL_TARGET_VALIDATION_REPORT = Path(_REFERENCE_REAL_TARGET_SESSION_ID) / "post_mutation" / "real_target_validation_report.json"
_REFERENCE_ROLLBACK_REPORT = Path(_REFERENCE_REAL_TARGET_SESSION_ID) / "rollback" / "rollback_validation_report.json"


@dataclass(frozen=True)
class RuntimeCapability:
    capability_id: str
    title: str
    intent: str
    target_level: str
    target_scene: str
    requested_execution_lane: str
    handler_name: str
    agent_type: str
    approval_required: bool
    eligible_for_auto: bool
    evidence_state: str
    safety_class: str
    match_terms: List[str]
    match_verbs: List[str]
    times_attempted: int = 0
    times_passed: int = 0
    last_validation_result: str = "none"
    last_rollback_result: str = "none"
    sandbox_verified: bool = False
    real_target_verified: bool = False
    rollback_verified: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "title": self.title,
            "intent": self.intent,
            "target_level": self.target_level,
            "target_scene": self.target_scene,
            "requested_execution_lane": self.requested_execution_lane,
            "handler_name": self.handler_name,
            "agent_type": self.agent_type,
            "approval_required": self.approval_required,
            "eligible_for_auto": self.eligible_for_auto,
            "evidence_state": self.evidence_state,
            "safety_class": self.safety_class,
            "match_terms": list(self.match_terms),
            "match_verbs": list(self.match_verbs),
            "times_attempted": self.times_attempted,
            "times_passed": self.times_passed,
            "last_validation_result": self.last_validation_result,
            "last_rollback_result": self.last_rollback_result,
            "sandbox_verified": self.sandbox_verified,
            "real_target_verified": self.real_target_verified,
            "rollback_verified": self.rollback_verified,
        }

    @staticmethod
    def from_payload(payload: Dict[str, Any]) -> "RuntimeCapability":
        return RuntimeCapability(
            capability_id=str(payload.get("capability_id") or ""),
            title=str(payload.get("title") or ""),
            intent=str(payload.get("intent") or "mutate"),
            target_level=str(payload.get("target_level") or "LEVEL_0001"),
            target_scene=str(payload.get("target_scene") or "Assets/AI_E_TestScenes/MinimalPlayableArena.unity"),
            requested_execution_lane=str(payload.get("requested_execution_lane") or "approval_required_mutation"),
            handler_name=str(payload.get("handler_name") or "level_0001_grass_handler"),
            agent_type=str(payload.get("agent_type") or "level_0001_grass_mutation_agent"),
            approval_required=bool(payload.get("approval_required", True)),
            eligible_for_auto=bool(payload.get("eligible_for_auto", False)),
            evidence_state=str(payload.get("evidence_state") or "experimental"),
            safety_class=str(payload.get("safety_class") or "approval_gated_automation"),
            match_terms=[str(item) for item in payload.get("match_terms", [])],
            match_verbs=[str(item) for item in payload.get("match_verbs", [])],
            times_attempted=int(payload.get("times_attempted", 0) or 0),
            times_passed=int(payload.get("times_passed", 0) or 0),
            last_validation_result=str(payload.get("last_validation_result") or "none"),
            last_rollback_result=str(payload.get("last_rollback_result") or "none"),
            sandbox_verified=bool(payload.get("sandbox_verified", False)),
            real_target_verified=bool(payload.get("real_target_verified", False)),
            rollback_verified=bool(payload.get("rollback_verified", False)),
        )

    def with_evidence(self, evidence: Dict[str, Any]) -> "RuntimeCapability":
        return replace(
            self,
            approval_required=bool(evidence.get("requires_approval", self.approval_required)),
            eligible_for_auto=bool(evidence.get("eligible_for_auto", self.eligible_for_auto)),
            evidence_state=str(evidence.get("evidence_state") or self.evidence_state),
            times_attempted=int(evidence.get("times_attempted", self.times_attempted) or 0),
            times_passed=int(evidence.get("times_passed", self.times_passed) or 0),
            last_validation_result=str(evidence.get("last_validation_result") or self.last_validation_result),
            last_rollback_result=str(evidence.get("last_rollback_result") or self.last_rollback_result),
            sandbox_verified=bool(evidence.get("sandbox_verified", self.sandbox_verified)),
            real_target_verified=bool(evidence.get("real_target_verified", self.real_target_verified)),
            rollback_verified=bool(evidence.get("rollback_verified", self.rollback_verified)),
        )


class CapabilityRegistry:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config
        self.registry_dir = ensure_dir(self.config.contracts_dir / "capabilities")
        self.evidence_path = self.registry_dir / "evidence.json"

    def all_capabilities(self) -> List[RuntimeCapability]:
        files = sorted(self.registry_dir.glob("*.json"))
        capabilities: List[RuntimeCapability] = []
        evidence_store = self.evidence_store()
        for path in files:
            if path.name.lower() == "evidence.json":
                continue
            payload = read_json(path, default={})
            if payload.get("capability_id"):
                capability = RuntimeCapability.from_payload(payload)
                capabilities.append(capability.with_evidence(evidence_store.ensure_entry(capability)))
        if not capabilities:
            capability = RuntimeCapability.from_payload(_DEFAULT_CAPABILITY)
            capabilities.append(capability.with_evidence(evidence_store.ensure_entry(capability)))
        return capabilities

    def match(self, prompt: str) -> RuntimeCapability | None:
        normalized = " ".join(str(prompt or "").strip().lower().split())
        for capability in self.all_capabilities():
            if self._matches_capability(normalized, capability):
                return capability
        return None

    def evidence_store(self) -> "CapabilityEvidenceStore":
        return CapabilityEvidenceStore(self.evidence_path, runs_dir=self.config.runs_dir)

    def _matches_capability(self, normalized_prompt: str, capability: RuntimeCapability) -> bool:
        if not all(term.lower() in normalized_prompt for term in capability.match_terms):
            return False
        return any(self._contains_verb(normalized_prompt, verb.lower()) for verb in capability.match_verbs)

    def _contains_verb(self, normalized_prompt: str, verb: str) -> bool:
        if " " in verb:
            return verb in normalized_prompt
        parts = normalized_prompt.split()
        return verb in parts


class CapabilityEvidenceStore:
    def __init__(self, path: Path, *, runs_dir: Path | None = None) -> None:
        self.path = Path(path)
        self.runs_dir = Path(runs_dir) if runs_dir is not None else None
        ensure_dir(self.path.parent)
        if not self.path.exists():
            write_json(self.path, {"capabilities": {}})

    def ensure_entry(self, capability: RuntimeCapability) -> Dict[str, Any]:
        payload = self._load()
        capabilities = payload.setdefault("capabilities", {})
        entry = capabilities.get(capability.capability_id)
        if not isinstance(entry, dict):
            entry = {
                "capability_id": capability.capability_id,
                "handler_name": capability.handler_name,
                "safety_class": capability.safety_class,
                "times_attempted": 0,
                "times_passed": 0,
                "last_validation_result": "none",
                "last_rollback_result": "none",
                "artifact_requirements_met": False,
                "eligible_for_auto": capability.eligible_for_auto,
                "requires_approval": capability.approval_required,
                "evidence_state": capability.evidence_state,
                "sandbox_verified": False,
                "real_target_verified": False,
                "rollback_verified": False,
                "evidence_progression": ["experimental"],
                "validation_history_summary": "No validation evidence recorded.",
                "rollback_history_summary": "No rollback evidence recorded.",
                "notes": "Initial evidence state created for bounded grass mutation capability.",
            }
        updated = self._finalize_entry(capability, entry)
        if capabilities.get(capability.capability_id) != updated:
            capabilities[capability.capability_id] = updated
            self._save(payload)
        return dict(updated)

    def record_result(
        self,
        capability: RuntimeCapability,
        *,
        passed: bool,
        validation_state: str,
        artifact_requirements_met: bool,
        notes: str,
    ) -> Dict[str, Any]:
        payload = self._load()
        capabilities = payload.setdefault("capabilities", {})
        current = self.ensure_entry(capability)
        current["times_attempted"] = int(current.get("times_attempted", 0)) + 1
        if passed:
            current["times_passed"] = int(current.get("times_passed", 0)) + 1
        current["last_validation_result"] = validation_state
        current["artifact_requirements_met"] = bool(artifact_requirements_met)
        current["eligible_for_auto"] = bool(capability.eligible_for_auto)
        current["requires_approval"] = bool(capability.approval_required)
        current["notes"] = notes
        updated = self._finalize_entry(capability, current)
        capabilities[capability.capability_id] = updated
        self._save(payload)
        return dict(updated)

    def record_rollback_result(
        self,
        capability: RuntimeCapability,
        *,
        passed: bool,
        rollback_state: str,
        notes: str,
    ) -> Dict[str, Any]:
        payload = self._load()
        capabilities = payload.setdefault("capabilities", {})
        current = self.ensure_entry(capability)
        current["last_rollback_result"] = rollback_state
        current["notes"] = notes
        if passed:
            current["rollback_verified"] = True
        updated = self._finalize_entry(capability, current)
        capabilities[capability.capability_id] = updated
        self._save(payload)
        return dict(updated)

    def get(self, capability_id: str) -> Dict[str, Any] | None:
        payload = self._load()
        capabilities = payload.get("capabilities", {})
        entry = capabilities.get(capability_id)
        if isinstance(entry, dict):
            return dict(entry)
        return None

    def _load(self) -> Dict[str, Any]:
        return read_json(self.path, default={"capabilities": {}})

    def _save(self, payload: Dict[str, Any]) -> None:
        write_json(self.path, payload)

    def _finalize_entry(self, capability: RuntimeCapability, entry: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(entry)
        current["capability_id"] = capability.capability_id
        current["handler_name"] = capability.handler_name
        current["safety_class"] = capability.safety_class
        current["times_attempted"] = max(0, int(current.get("times_attempted", 0) or 0))
        current["times_passed"] = max(0, int(current.get("times_passed", 0) or 0))
        current["last_validation_result"] = str(current.get("last_validation_result") or "none")
        current["last_rollback_result"] = str(current.get("last_rollback_result") or "none")
        current["eligible_for_auto"] = bool(capability.eligible_for_auto)
        current["requires_approval"] = bool(capability.approval_required)

        artifact_summary = self._artifact_summary(capability.capability_id)
        if artifact_summary["last_validation_result"] != "none":
            current["last_validation_result"] = artifact_summary["last_validation_result"]
        if artifact_summary["last_rollback_result"] != "none":
            current["last_rollback_result"] = artifact_summary["last_rollback_result"]

        current["real_target_verified"] = bool(current.get("real_target_verified", False) or artifact_summary["real_target_verified"])
        current["rollback_verified"] = bool(current.get("rollback_verified", False) or artifact_summary["rollback_verified"])
        current["sandbox_verified"] = bool(
            current.get("sandbox_verified", False)
            or current["real_target_verified"]
            or current["rollback_verified"]
            or (
                current["times_passed"] > 0
                and bool(current.get("artifact_requirements_met", False))
                and current["last_validation_result"] == "passed"
            )
        )
        current["artifact_requirements_met"] = bool(
            current.get("artifact_requirements_met", False)
            or current["sandbox_verified"]
            or current["real_target_verified"]
            or current["rollback_verified"]
        )

        current["evidence_progression"] = self._evidence_progression(current)
        current["evidence_state"] = self._derive_maturity_state(current)
        current["validation_history_summary"] = (
            f"attempts={current['times_attempted']}; passed={current['times_passed']}; "
            f"last_validation_result={current['last_validation_result']}; "
            f"sandbox_verified={'yes' if current['sandbox_verified'] else 'no'}; "
            f"real_target_verified={'yes' if current['real_target_verified'] else 'no'}"
        )
        current["rollback_history_summary"] = (
            f"last_rollback_result={current['last_rollback_result']}; "
            f"rollback_verified={'yes' if current['rollback_verified'] else 'no'}"
        )
        return current

    def _artifact_summary(self, capability_id: str) -> Dict[str, Any]:
        summary = {
            "real_target_verified": False,
            "rollback_verified": False,
            "last_validation_result": "none",
            "last_rollback_result": "none",
        }
        if self.runs_dir is None or capability_id != _REFERENCE_CAPABILITY_ID:
            return summary

        validation_report = read_json(self.runs_dir / _REFERENCE_REAL_TARGET_VALIDATION_REPORT, default={})
        if (
            str(validation_report.get("session_id") or "") == _REFERENCE_REAL_TARGET_SESSION_ID
            and str(validation_report.get("capability_id") or "") == capability_id
            and str(validation_report.get("validation_result") or "") == "passed"
        ):
            summary["real_target_verified"] = True
            summary["last_validation_result"] = "passed"

        rollback_report = read_json(self.runs_dir / _REFERENCE_ROLLBACK_REPORT, default={})
        if (
            str(rollback_report.get("session_id") or "") == _REFERENCE_REAL_TARGET_SESSION_ID
            and str(rollback_report.get("capability_id") or "") == capability_id
            and str(rollback_report.get("rollback_validation_result") or "") == "passed"
        ):
            summary["rollback_verified"] = True
            summary["last_rollback_result"] = "passed"
        return summary

    def _derive_maturity_state(self, entry: Dict[str, Any]) -> str:
        if bool(entry.get("eligible_for_auto", False)):
            return "auto_eligible"
        if bool(entry.get("rollback_verified", False)):
            return "rollback_verified"
        if bool(entry.get("real_target_verified", False)):
            return "real_target_verified"
        if bool(entry.get("sandbox_verified", False)):
            return "sandbox_verified"
        return "experimental"

    def _evidence_progression(self, entry: Dict[str, Any]) -> List[str]:
        progression = ["experimental"]
        if bool(entry.get("sandbox_verified", False)):
            progression.append("sandbox_verified")
        if bool(entry.get("real_target_verified", False)):
            progression.append("real_target_verified")
        if bool(entry.get("rollback_verified", False)):
            progression.append("rollback_verified")
        if bool(entry.get("eligible_for_auto", False)):
            progression.append("auto_eligible")
        return progression


__all__ = [
    "CapabilityEvidenceStore",
    "CapabilityRegistry",
    "RuntimeCapability",
    "_MATURITY_STAGES",
]