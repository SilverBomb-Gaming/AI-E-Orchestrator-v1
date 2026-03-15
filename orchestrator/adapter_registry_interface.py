from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol


AdapterAvailability = Literal["available", "unavailable", "planned"]
AdapterRegistryStatus = Literal["registered", "blocked", "unsupported"]


@dataclass(frozen=True)
class AdapterRegistrationContract:
    """Deterministic registration record for a future execution adapter."""

    adapter_id: str
    adapter_type: str
    supported_task_types: List[str] = field(default_factory=list)
    supported_targets: List[str] = field(default_factory=list)
    allowed_actions: List[str] = field(default_factory=list)
    requires_approval: List[str] = field(default_factory=list)
    dry_run_supported: bool = True
    live_run_supported: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_type": self.adapter_type,
            "supported_task_types": list(self.supported_task_types),
            "supported_targets": list(self.supported_targets),
            "allowed_actions": list(self.allowed_actions),
            "requires_approval": list(self.requires_approval),
            "dry_run_supported": self.dry_run_supported,
            "live_run_supported": self.live_run_supported,
        }


@dataclass(frozen=True)
class AdapterDiscoveryOutput:
    """Deterministic discovery view for future adapter selection."""

    adapter_id: str
    adapter_status: AdapterRegistryStatus
    capabilities: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    availability: AdapterAvailability = "planned"

    def to_payload(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_status": self.adapter_status,
            "capabilities": {key: self.capabilities[key] for key in sorted(self.capabilities)},
            "priority": self.priority,
            "availability": self.availability,
        }


class AdapterRegistryInterface(Protocol):
    """Architecture-only boundary for future adapter registration and discovery.

    This layer records and exposes adapter metadata without performing runtime
    discovery or invoking any adapters.
    """

    def register_adapter(self, registration: AdapterRegistrationContract) -> Dict[str, Any]:
        ...

    def discover_adapters(self, task_type: str) -> List[AdapterDiscoveryOutput]:
        ...


__all__ = [
    "AdapterAvailability",
    "AdapterDiscoveryOutput",
    "AdapterRegistrationContract",
    "AdapterRegistryInterface",
    "AdapterRegistryStatus",
]