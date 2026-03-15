from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Literal, Sequence

from .contracts import Contract
from .registry import AgentProfile

PolicyVerdict = Literal["ALLOW", "ASK", "BLOCK"]
PolicySeverity = Literal["hard", "soft"]

_NETWORK_KEYWORDS = (
    "curl ",
    "wget ",
    "invoke-webrequest",
    "invoke-restmethod",
    "start-bitstransfer",
    "http://",
    "https://",
)
_DESKTOP_CAPTURE_KEYWORDS = (
    "run_unity_screenshot",
    "capturewindow",
    "snippingtool",
    "desktopcapture",
)
_FORBIDDEN_COMMAND_KEYWORDS = (
    "install ",
    "reg add",
    "net start",
    "sc ",
    "format ",
)


def _normalize_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    return None


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _attempts_desktop_capture(shell: str) -> bool:
    normalized = (shell or "").lower()
    if not normalized:
        return False
    for keyword in _DESKTOP_CAPTURE_KEYWORDS:
        if keyword == "run_unity_screenshot":
            if re.search(r"(^|[^a-z0-9_])run_unity_screenshot(?:\.ps1)?([^a-z0-9_]|$)", normalized):
                return True
            continue
        if keyword in normalized:
            return True
    return False


@dataclass
class PolicyViolation:
    rule: str
    detail: str
    evidence: str
    severity: PolicySeverity = "hard"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "detail": self.detail,
            "evidence": self.evidence,
            "severity": self.severity,
        }


@dataclass
class PolicyDecision:
    allowed: bool
    violations: List[PolicyViolation]
    risk_score: float
    verdict: PolicyVerdict

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "risk_score": round(min(max(self.risk_score, 0.0), 1.0), 2),
            "violations": [violation.as_dict() for violation in self.violations],
            "verdict": self.verdict,
        }

    @staticmethod
    def blocked(reason: str, *, evidence: str = "scheduler") -> "PolicyDecision":
        violation = PolicyViolation(
            rule="runtime_failure",
            detail=reason,
            evidence=evidence,
            severity="hard",
        )
        return PolicyDecision(allowed=False, violations=[violation], risk_score=1.0, verdict="BLOCK")


@dataclass(frozen=True)
class PolicyConfig:
    allow_network: bool = False
    allow_desktop_capture: bool = False
    allowed_extensions: Sequence[str] = (".cs", ".json", ".yaml", ".yml", ".md", ".txt")
    forbidden_paths: Sequence[str] = (
        "Library/",
        "Temp/",
        "UserSettings/",
        "Packages/manifest.json",
        "ProjectSettings/",
        "contracts/active",
        "contracts/completed",
        "contracts/failed",
        "backlog/",
        "runs/",
        "workspaces/",
        "system32",
    )
    max_patch_lines: int = 500
    max_files_touched: int = 8
    forbid_modifying_orchestrator_repo: bool = True
    require_writer_for_patches: bool = True

    def merge(self, overrides: Dict[str, Any] | None) -> "PolicyConfig":
        if not overrides:
            return self
        data = dict(self.__dict__)
        for key, value in overrides.items():
            if key not in data:
                continue
            if isinstance(data[key], bool):
                normalized = _normalize_bool(value)
                if normalized is not None:
                    data[key] = normalized
            elif isinstance(data[key], int):
                try:
                    data[key] = int(value)
                except (TypeError, ValueError):
                    continue
            elif isinstance(data[key], Sequence):
                normalized_list = _normalize_list(value)
                if normalized_list:
                    data[key] = tuple(item.strip() for item in normalized_list if item.strip())
        return PolicyConfig(**data)


class PolicyEngine:
    def __init__(self, *, orchestrator_root: Path, base_config: PolicyConfig | None = None) -> None:
        self.orchestrator_root = orchestrator_root
        self.base_config = base_config or PolicyConfig()

    def evaluate(
        self,
        *,
        contract: Contract,
        agent_profiles: Iterable[AgentProfile],
        patch_stats: Dict[str, Any],
        command_results: List[Dict[str, Any]],
    ) -> PolicyDecision:
        overrides = self._extract_overrides(contract)
        config = self.base_config.merge(overrides)
        violations: List[PolicyViolation] = []
        hard_hit = False
        risk_score = 0.0
        writers = [profile for profile in agent_profiles if "write_patch" in profile.allowed_actions]
        files_changed = int(patch_stats.get("files_changed", 0) or 0)
        loc_delta = int(patch_stats.get("loc_delta", 0) or 0)
        touched_files = [str(path).strip() for path in (patch_stats.get("touched_files") or [])]

        def add_violation(rule: str, detail: str, evidence: str, severity: PolicySeverity = "hard", weight: float = 0.4) -> None:
            nonlocal hard_hit, risk_score
            violations.append(PolicyViolation(rule=rule, detail=detail, evidence=evidence, severity=severity))
            if severity == "hard":
                hard_hit = True
            risk_score = min(1.0, risk_score + weight)

        if config.require_writer_for_patches and files_changed > 0 and not writers:
            add_violation(
                "patch_authorization",
                "Patch output detected without a writer profile assigned.",
                evidence=";".join(profile.id for profile in agent_profiles) or "agents",
            )

        if files_changed > config.max_files_touched:
            add_violation(
                "max_files_touched",
                f"Files changed ({files_changed}) exceeds policy cap ({config.max_files_touched}).",
                evidence=", ".join(touched_files[:5]) or "patch",
                severity="hard",
            )

        if loc_delta > config.max_patch_lines:
            add_violation(
                "max_patch_lines",
                f"Patch LOC delta ({loc_delta}) exceeds policy cap ({config.max_patch_lines}).",
                evidence="patch",
            )

        lowered_forbidden = [entry.lower() for entry in config.forbidden_paths]
        for path in touched_files:
            normalized = path.replace("\\", "/")
            lowered = normalized.lower()
            for forbidden in lowered_forbidden:
                if lowered.startswith(forbidden.lower()):
                    add_violation(
                        "forbidden_path",
                        f"Path {normalized} is on the forbidden list ({forbidden}).",
                        evidence=normalized,
                    )
                    break
            suffix = Path(normalized).suffix.lower()
            if suffix and suffix not in [ext.lower() for ext in config.allowed_extensions]:
                add_violation(
                    "extension_restriction",
                    f"Extension {suffix} is outside allowed set {config.allowed_extensions}.",
                    evidence=normalized,
                    severity="soft",
                    weight=0.2,
                )

        target_repo_value = contract.metadata.get("Target Repo Path") or contract.metadata.get("Target Repo")
        if config.forbid_modifying_orchestrator_repo and target_repo_value:
            candidate = Path(str(target_repo_value)).expanduser()
            try:
                resolved_candidate = candidate.resolve()
            except OSError:
                resolved_candidate = candidate
            orchestrator_root = self.orchestrator_root
            try:
                resolved_root = orchestrator_root.resolve()
            except OSError:
                resolved_root = orchestrator_root
            if resolved_candidate == resolved_root or resolved_root in resolved_candidate.parents:
                add_violation(
                    "target_repo_guard",
                    "Target repo points to the orchestrator itself, which is forbidden by policy.",
                    evidence=str(candidate),
                )

        for result in command_results or []:
            shell = (result.get("shell") or "").lower()
            if not shell:
                continue
            evidence = result.get("stdout_log") or result.get("stderr_log") or result.get("name", "command")
            if any(keyword in shell for keyword in _FORBIDDEN_COMMAND_KEYWORDS):
                add_violation(
                    "forbidden_command",
                    f"Command '{result.get('name', 'command')}' uses forbidden keyword.",
                    evidence=evidence,
                )
            if not config.allow_network and any(keyword in shell for keyword in _NETWORK_KEYWORDS):
                add_violation(
                    "network_call",
                    f"Command '{result.get('name', 'command')}' includes a network keyword.",
                    evidence=evidence,
                )
            if not config.allow_desktop_capture and _attempts_desktop_capture(shell):
                add_violation(
                    "desktop_capture",
                    f"Command '{result.get('name', 'command')}' attempts desktop capture.",
                    evidence=evidence,
                )

        allowed = not hard_hit
        verdict = self._determine_verdict(allowed, risk_score)
        return PolicyDecision(allowed=allowed, violations=violations, risk_score=risk_score, verdict=verdict)

    def failure_decision(self, detail: str, *, evidence: str = "scheduler") -> PolicyDecision:
        return PolicyDecision.blocked(detail, evidence=evidence)

    def _extract_overrides(self, contract: Contract) -> Dict[str, Any]:
        for key in ("Policy Overrides", "policy_overrides"):
            overrides = contract.metadata.get(key)
            if isinstance(overrides, dict):
                return overrides
        return {}

    def _determine_verdict(self, allowed: bool, risk_score: float) -> PolicyVerdict:
        if not allowed:
            return "BLOCK"
        if risk_score > 0.3:
            return "ASK"
        return "ALLOW"