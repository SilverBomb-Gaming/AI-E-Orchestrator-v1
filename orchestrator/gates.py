from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal

from .contracts import Contract
from .policy import PolicyDecision, PolicyEngine
from .registry import AgentProfile
from .utils import parse_patch_stats, within_scope

GateStatus = Literal["ALLOW", "ASK", "BLOCK"]


@dataclass
class GateResult:
    name: str
    status: GateStatus
    score: float
    reasons: List[str]

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = self.reasons
        return payload


class Gatekeeper:
    ORCHESTRATOR_ROOT = Path(__file__).resolve().parent.parent

    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine(orchestrator_root=self.ORCHESTRATOR_ROOT)

    def evaluate(
        self,
        *,
        contract: Contract,
        agent_profiles: Iterable[AgentProfile],
        patch_text: str,
        command_results: List[Dict[str, Any]],
        artifact_info: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        patch_stats = parse_patch_stats(patch_text)
        profiles = list(agent_profiles)
        artifact_info = artifact_info or []
        policy_decision = self.policy_engine.evaluate(
            contract=contract,
            agent_profiles=profiles,
            patch_stats=patch_stats,
            command_results=command_results,
        )
        gates: List[GateResult] = [
            self._build_gate(command_results),
            self._test_gate(command_results),
            self._diff_gate(patch_stats, contract, profiles),
            self._policy_gate(policy_decision),
            self._signal_gate(contract, artifact_info),
        ]
        overall_status = self._aggregate_status(gates)
        overall_score = round(sum(g.score for g in gates) / len(gates), 2)
        return {
            "overall_status": overall_status,
            "overall_score": overall_score,
            "gates": [g.as_dict() for g in gates],
            "patch_stats": patch_stats,
            "artifacts": artifact_info,
            "policy": policy_decision.as_dict(),
        }

    def _build_gate(self, command_results: List[Dict[str, Any]]) -> GateResult:
        relevant = [c for c in command_results if c.get("type") == "build"]
        if not relevant:
            return GateResult("build", "ALLOW", 1.0, ["No build commands defined; skipping."])
        failures = [c for c in relevant if c.get("returncode", 1) != 0]
        if failures:
            reasons = [f"Command '{c['name']}' failed with code {c['returncode']}" for c in failures]
            return GateResult("build", "BLOCK", 0.0, reasons)
        return GateResult("build", "ALLOW", 1.0, ["All build commands exited with 0."])

    def _test_gate(self, command_results: List[Dict[str, Any]]) -> GateResult:
        relevant = [c for c in command_results if c.get("type") == "test"]
        if not relevant:
            return GateResult("test", "ASK", 0.5, ["No test commands supplied; manual review required."])
        failures = [c for c in relevant if c.get("returncode", 1) != 0]
        if failures:
            reasons = [f"Command '{c['name']}' failed with code {c['returncode']}" for c in failures]
            return GateResult("test", "BLOCK", 0.0, reasons)
        return GateResult("test", "ALLOW", 1.0, ["All tests passed."])

    def _diff_gate(
        self,
        patch_stats: Dict[str, Any],
        contract: Contract,
        profiles: List[AgentProfile],
    ) -> GateResult:
        reasons: List[str] = []
        status: GateStatus = "ALLOW"
        files_changed = patch_stats["files_changed"]
        loc_delta = patch_stats["loc_delta"]
        touched_files = patch_stats["touched_files"]
        budget = self._combined_budget(profiles)
        max_files = budget.get("max_files_changed", 1)
        max_loc = budget.get("max_loc_changed", 50)
        effective_scope, blocklist = self._scope_controls(contract, profiles)
        if files_changed > max_files:
            status = "ASK" if status == "ALLOW" else status
            reasons.append(f"Files changed ({files_changed}) exceeds budget ({max_files}).")
        if loc_delta > max_loc:
            status = "BLOCK"
            reasons.append(f"LOC delta ({loc_delta}) exceeds budget ({max_loc}).")
        if effective_scope and touched_files and not within_scope(touched_files, effective_scope):
            status = "BLOCK"
            reasons.append("Patch touches files outside the allowed scope.")
        if blocklist and any(within_scope([path], blocklist) for path in touched_files):
            status = "BLOCK"
            reasons.append("Patch touches blocklisted paths.")
        if not reasons:
            reasons.append("Patch size within risk budget and scope constraints.")
        score = 1.0 if status == "ALLOW" else 0.5 if status == "ASK" else 0.0
        return GateResult("diff", status, score, reasons)

    def _policy_gate(self, decision: PolicyDecision) -> GateResult:
        if decision.violations:
            reasons = [
                f"{violation.rule}: {violation.detail} (evidence: {violation.evidence})"
                for violation in decision.violations
            ]
        else:
            reasons = ["No policy violations detected."]
        status: GateStatus = decision.verdict
        score = 1.0 if status == "ALLOW" else 0.5 if status == "ASK" else 0.0
        return GateResult("policy", status, score, reasons)


    def _signal_gate(self, contract: Contract, artifact_info: List[Dict[str, Any]]) -> GateResult:
        if not contract.requires_unity_log:
            return GateResult(
                "signal",
                "ALLOW",
                1.0,
                ["Unity log capture not required for this contract."],
            )
        target = None
        for artifact in artifact_info:
            if artifact.get("artifact", "").endswith("scripts/logs/Editor.log"):
                target = artifact
                break
        if target is None:
            return GateResult(
                "signal",
                "BLOCK",
                0.0,
                ["Unity log artifact missing despite contract requirement."],
            )
        if target.get("status") != "copied":
            return GateResult(
                "signal",
                "BLOCK",
                0.0,
                ["Unity log capture failed; review collection commands."],
            )
        size = int(target.get("size_bytes", 0))
        has_signal = bool(target.get("contains_error_marker"))
        reasons: List[str] = []
        status: GateStatus = "ALLOW"
        if size < 2048:
            status = "ASK"
            reasons.append(f"Unity log too small ({size} bytes); expected >= 2048 bytes.")
        if not has_signal and size < 8192:
            status = "ASK"
            reasons.append("Unity log missing error markers; capture may be incomplete.")
        if not reasons:
            reasons.append(f"Unity log captured ({size} bytes) with error markers present.")
        score = 1.0 if status == "ALLOW" else 0.5 if status == "ASK" else 0.0
        return GateResult("signal", status, score, reasons)

    def _combined_budget(self, profiles: List[AgentProfile]) -> Dict[str, int]:
        budget: Dict[str, int] = {}
        for profile in profiles:
            if "write_patch" not in profile.allowed_actions:
                continue
            for key, value in profile.risk_budget.items():
                if value is None:
                    continue
                current = budget.get(key)
                budget[key] = min(current, value) if current is not None else value
        return budget

    def _scope_controls(self, contract: Contract, profiles: List[AgentProfile]) -> tuple[List[str], List[str]]:
        writers = [profile for profile in profiles if "write_patch" in profile.allowed_actions]
        scope_profiles = writers or profiles
        contract_scope = [scope.strip("/") for scope in contract.allowed_scope if scope]
        agent_allowlist = sorted({scope.strip("/") for profile in scope_profiles for scope in profile.scope_allowlist if scope})
        blocklist = sorted({scope.strip("/") for profile in scope_profiles for scope in profile.scope_blocklist if scope})
        if contract_scope:
            effective_scope = contract_scope
        else:
            effective_scope = agent_allowlist
        return effective_scope, blocklist

    def _aggregate_status(self, gates: List[GateResult]) -> GateStatus:
        if any(g.status == "BLOCK" for g in gates):
            return "BLOCK"
        if any(g.status == "ASK" for g in gates):
            return "ASK"
        return "ALLOW"
