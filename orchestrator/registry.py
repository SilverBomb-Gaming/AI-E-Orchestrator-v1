from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from . import utils


@dataclass(frozen=True)
class AgentProfile:
    id: str
    role: str
    description: str
    allowed_actions: List[str]
    scope_allowlist: List[str]
    scope_blocklist: List[str]
    risk_budget: Dict[str, int]
    outputs_required: List[str]
    stop_conditions: Dict[str, str | int]


class AgentRegistry:
    """Loads and exposes agent profiles defined in JSON."""

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path
        self._profiles: Dict[str, AgentProfile] = {}
        self.reload()

    def reload(self) -> None:
        payload = utils.read_json(self.registry_path, default={"agents": []})
        profiles = {}
        for entry in payload.get("agents", []):
            profile = AgentProfile(
                id=entry["id"],
                role=entry.get("role", ""),
                description=entry.get("description", ""),
                allowed_actions=list(entry.get("allowed_actions", [])),
                scope_allowlist=list(entry.get("scope_allowlist", [])),
                scope_blocklist=list(entry.get("scope_blocklist", [])),
                risk_budget=dict(entry.get("risk_budget", {})),
                outputs_required=list(entry.get("outputs_required", [])),
                stop_conditions=dict(entry.get("stop_conditions", {})),
            )
            profiles[profile.id] = profile
        self._profiles = profiles

    def get(self, profile_id: str) -> AgentProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"Agent profile '{profile_id}' not found in registry {self.registry_path}") from exc

    def get_many(self, profile_ids: Iterable[str]) -> List[AgentProfile]:
        return [self.get(pid) for pid in profile_ids]

    def roles(self) -> Dict[str, AgentProfile]:
        return dict(self._profiles)
