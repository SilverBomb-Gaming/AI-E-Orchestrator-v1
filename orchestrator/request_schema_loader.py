from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from .architecture_blueprint import ConversationalRequest
from .time_utils import normalize_timestamp, parse_timestamp


_REQUIRED_FIELDS = {
    "request_id": str,
    "session_id": str,
    "channel": str,
    "operator_prompt": str,
    "created_at": str,
}

_OPTIONAL_FIELDS = {
    "intent",
    "clarification_needed",
    "context",
    "constraints",
    "requested_artifacts",
}


@dataclass(frozen=True)
class RequestSchemaError:
    field: str
    message: str


class RequestSchemaValidationError(ValueError):
    def __init__(self, errors: Iterable[RequestSchemaError]) -> None:
        self.errors = list(errors)
        detail = "; ".join(f"{error.field}: {error.message}" for error in self.errors) or "invalid request payload"
        super().__init__(detail)


def load_request_payload(raw_text: str) -> Dict[str, Any]:
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise RequestSchemaValidationError([RequestSchemaError(field="payload", message="must deserialize to a JSON object")])
    return payload


def load_request_file(path: Path) -> ConversationalRequest:
    payload = load_request_payload(path.read_text(encoding="utf-8"))
    return validate_request_payload(payload)


def validate_request_payload(payload: Mapping[str, Any]) -> ConversationalRequest:
    errors: list[RequestSchemaError] = []
    normalized = dict(payload)
    _validate_unknown_fields(normalized, errors)
    for field_name, expected_type in _REQUIRED_FIELDS.items():
        value = normalized.get(field_name)
        if value is None:
            errors.append(RequestSchemaError(field=field_name, message="is required"))
            continue
        if not isinstance(value, expected_type):
            errors.append(RequestSchemaError(field=field_name, message=f"must be {expected_type.__name__}"))
            continue
        if not str(value).strip():
            errors.append(RequestSchemaError(field=field_name, message="must not be empty"))

    _validate_iso8601_utc(normalized.get("created_at"), errors)
    _validate_mapping_field(normalized, "context", errors)
    _validate_list_of_strings(normalized, "constraints", errors)
    _validate_list_of_strings(normalized, "requested_artifacts", errors)
    _validate_optional_string(normalized, "intent", errors)
    _validate_optional_bool(normalized, "clarification_needed", errors)

    if errors:
        raise RequestSchemaValidationError(errors)

    normalized["created_at"] = normalize_timestamp(str(normalized["created_at"]).strip())

    return ConversationalRequest(
        request_id=str(normalized["request_id"]).strip(),
        session_id=str(normalized["session_id"]).strip(),
        channel=str(normalized["channel"]).strip(),
        operator_prompt=str(normalized["operator_prompt"]).strip(),
        created_at=str(normalized["created_at"]).strip(),
        intent=str(normalized.get("intent") or "unspecified").strip() or "unspecified",
        clarification_needed=normalized.get("clarification_needed", False),
        context=dict(normalized.get("context") or {}),
        constraints=[str(item).strip() for item in normalized.get("constraints") or []],
        requested_artifacts=[str(item).strip() for item in normalized.get("requested_artifacts") or []],
    )


def _validate_unknown_fields(payload: Mapping[str, Any], errors: list[RequestSchemaError]) -> None:
    allowed_fields = set(_REQUIRED_FIELDS) | _OPTIONAL_FIELDS
    for field_name in sorted(payload):
        if field_name not in allowed_fields:
            errors.append(
                RequestSchemaError(
                    field=field_name,
                    message="is not supported by the current request schema; place extra metadata under context",
                )
            )


def _validate_iso8601_utc(value: Any, errors: list[RequestSchemaError]) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    try:
        parse_timestamp(value.strip())
    except ValueError:
        errors.append(
            RequestSchemaError(
                field="created_at",
                message="must be a valid timestamp convertible to the standardized AI-E format",
            )
        )


def _validate_mapping_field(payload: Mapping[str, Any], field_name: str, errors: list[RequestSchemaError]) -> None:
    value = payload.get(field_name)
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(RequestSchemaError(field=field_name, message="must be an object when provided"))


def _validate_list_of_strings(payload: Mapping[str, Any], field_name: str, errors: list[RequestSchemaError]) -> None:
    value = payload.get(field_name)
    if value is None:
        return
    if not isinstance(value, list):
        errors.append(RequestSchemaError(field=field_name, message="must be a list of strings when provided"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(RequestSchemaError(field=f"{field_name}[{index}]", message="must be a non-empty string"))


def _validate_optional_string(payload: Mapping[str, Any], field_name: str, errors: list[RequestSchemaError]) -> None:
    value = payload.get(field_name)
    if value is None:
        return
    if not isinstance(value, str):
        errors.append(RequestSchemaError(field=field_name, message="must be a string when provided"))


def _validate_optional_bool(payload: Mapping[str, Any], field_name: str, errors: list[RequestSchemaError]) -> None:
    value = payload.get(field_name)
    if value is None:
        return
    if not isinstance(value, bool):
        errors.append(RequestSchemaError(field=field_name, message="must be a boolean when provided"))


__all__ = [
    "RequestSchemaError",
    "RequestSchemaValidationError",
    "load_request_file",
    "load_request_payload",
    "validate_request_payload",
]