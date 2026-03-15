from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Protocol


@dataclass(frozen=True)
class ChatPromptEnvelope:
    """Contract for raw conversational ingress before schema validation."""

    prompt_text: str
    session_id: str
    channel: str
    received_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedRequestEnvelope:
    """Contract for chat-normalized request payloads forwarded to the schema loader."""

    request_payload: Dict[str, Any]
    schema_version: str = "v1"
    source: str = "chat_gateway"


class ChatGatewayInterface(Protocol):
    """Placeholder interface for future conversational ingress.

    Responsibilities:
    - receive prompt
    - normalize request payload
    - forward to schema loader

    This module is architecture-only. It defines contracts and responsibilities,
    but it does not execute gateway logic or bypass policy.
    """

    def receive_prompt(self, raw_prompt: str, session_metadata: Mapping[str, Any]) -> ChatPromptEnvelope:
        ...

    def normalize_request(self, envelope: ChatPromptEnvelope) -> NormalizedRequestEnvelope:
        ...

    def forward_to_schema_loader(self, normalized_request: NormalizedRequestEnvelope) -> Mapping[str, Any]:
        ...


__all__ = ["ChatGatewayInterface", "ChatPromptEnvelope", "NormalizedRequestEnvelope"]