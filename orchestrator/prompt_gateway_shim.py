from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from .chat_gateway_interface import ChatPromptEnvelope, ChatGatewayInterface, NormalizedRequestEnvelope


@dataclass(frozen=True)
class PromptGatewayShimConfig:
    """Deterministic configuration for architecture-only prompt normalization."""

    request_id: str
    session_id: str
    channel: str
    received_at: str
    intent: str
    context: Dict[str, Any]
    constraints: list[str]
    requested_artifacts: list[str]
    metadata: Dict[str, Any]


class PromptGatewayShim(ChatGatewayInterface):
    """Architecture-only prompt gateway shim.

    Responsibilities:
    - accept prompt text
    - normalize prompt payload
    - forward payload to request_schema_loader

    This module is reusable for architecture tests and remains outside runtime
    orchestration.
    """

    def __init__(self, config: PromptGatewayShimConfig) -> None:
        self._config = config

    def receive_prompt(self, raw_prompt: str, session_metadata: Mapping[str, Any]) -> ChatPromptEnvelope:
        return ChatPromptEnvelope(
            prompt_text=raw_prompt.strip(),
            session_id=str(session_metadata["session_id"]),
            channel=str(session_metadata["channel"]),
            received_at=str(session_metadata["received_at"]),
            metadata=dict(session_metadata.get("metadata") or {}),
        )

    def normalize_request(self, envelope: ChatPromptEnvelope) -> NormalizedRequestEnvelope:
        return NormalizedRequestEnvelope(
            request_payload={
                "request_id": self._config.request_id,
                "session_id": envelope.session_id,
                "channel": envelope.channel,
                "operator_prompt": envelope.prompt_text,
                "created_at": envelope.received_at,
                "intent": self._config.intent,
                "clarification_needed": False,
                "context": dict(self._config.context),
                "constraints": list(self._config.constraints),
                "requested_artifacts": list(self._config.requested_artifacts),
            }
        )

    def forward_to_schema_loader(self, normalized_request: NormalizedRequestEnvelope) -> Mapping[str, Any]:
        return dict(normalized_request.request_payload)

    @property
    def session_metadata(self) -> Dict[str, Any]:
        return {
            "session_id": self._config.session_id,
            "channel": self._config.channel,
            "received_at": self._config.received_at,
            "metadata": dict(self._config.metadata),
        }


__all__ = ["PromptGatewayShim", "PromptGatewayShimConfig"]