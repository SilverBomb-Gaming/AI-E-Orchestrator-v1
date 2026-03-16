from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol

from .read_only_live_adapter_interface import ReadOnlyResponseState


ValidationState = Literal[
    "validation_completed",
    "validation_partial",
    "validation_blocked",
    "validation_failed",
]
ValidationClass = Literal[
    "passed",
    "passed_with_warnings",
    "partial_success",
    "retryable_failure",
    "blocked",
    "unsupported",
    "terminal_failure",
]


@dataclass(frozen=True)
class ValidationInputContract:
    """Contract for bounded read-only validation inputs."""

    validation_id: str
    session_id: str
    request_id: str
    execution_id: str
    task_id: str
    adapter_id: str
    response_state: ReadOnlyResponseState
    inspected_paths: List[str] = field(default_factory=list)
    artifacts_generated: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    validated_at: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "adapter_id": self.adapter_id,
            "response_state": self.response_state,
            "inspected_paths": list(self.inspected_paths),
            "artifacts_generated": list(self.artifacts_generated),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "validated_at": self.validated_at,
        }


@dataclass(frozen=True)
class ValidationRecordContract:
    """Contract for deterministic validation records."""

    validation_id: str
    validation_state: ValidationState
    validation_class: ValidationClass
    passed: bool
    partial: bool
    retryable: bool
    blocked: bool
    terminal: bool
    summary: str
    notes: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "validation_state": self.validation_state,
            "validation_class": self.validation_class,
            "passed": self.passed,
            "partial": self.partial,
            "retryable": self.retryable,
            "blocked": self.blocked,
            "terminal": self.terminal,
            "summary": self.summary,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ValidationVerdictContract:
    """Contract for deterministic validation verdicts."""

    validation_id: str
    validation_state: ValidationState
    retry_recommended: bool
    retry_reason: str
    operator_attention_required: bool
    escalation_required: bool
    finalized: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "validation_state": self.validation_state,
            "retry_recommended": self.retry_recommended,
            "retry_reason": self.retry_reason,
            "operator_attention_required": self.operator_attention_required,
            "escalation_required": self.escalation_required,
            "finalized": self.finalized,
        }


def validation_classes() -> list[str]:
    return [
        "passed",
        "passed_with_warnings",
        "partial_success",
        "retryable_failure",
        "blocked",
        "unsupported",
        "terminal_failure",
    ]


def evaluate_validation_result(
    validation_input: ValidationInputContract,
) -> tuple[ValidationRecordContract, ValidationVerdictContract]:
    response_state = validation_input.response_state
    warnings = validation_input.warnings
    errors = validation_input.errors

    if response_state == "read_completed" and not warnings and not errors:
        record = ValidationRecordContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_completed",
            validation_class="passed",
            passed=True,
            partial=False,
            retryable=False,
            blocked=False,
            terminal=False,
            summary="Read-only inspection completed successfully within the bounded scope.",
            notes="Validation passed without warnings or errors.",
        )
        verdict = ValidationVerdictContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_completed",
            retry_recommended=False,
            retry_reason="",
            operator_attention_required=False,
            escalation_required=False,
            finalized=True,
        )
        return record, verdict

    if response_state == "read_completed" and warnings:
        record = ValidationRecordContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_completed",
            validation_class="passed_with_warnings",
            passed=True,
            partial=False,
            retryable=False,
            blocked=False,
            terminal=False,
            summary="Read-only inspection completed with warnings.",
            notes="Warnings should be reviewed even though the bounded read completed.",
        )
        verdict = ValidationVerdictContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_completed",
            retry_recommended=False,
            retry_reason="",
            operator_attention_required=True,
            escalation_required=False,
            finalized=True,
        )
        return record, verdict

    if response_state == "read_partial":
        record = ValidationRecordContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_partial",
            validation_class="partial_success",
            passed=False,
            partial=True,
            retryable=True,
            blocked=False,
            terminal=False,
            summary="Read-only inspection partially completed with bounded errors.",
            notes="Some requested paths were inspected while others failed policy or scope checks.",
        )
        verdict = ValidationVerdictContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_partial",
            retry_recommended=True,
            retry_reason="Partial inspection completed and may be retried within the same bounded scope.",
            operator_attention_required=True,
            escalation_required=False,
            finalized=True,
        )
        return record, verdict

    if response_state == "read_blocked":
        record = ValidationRecordContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_blocked",
            validation_class="blocked",
            passed=False,
            partial=False,
            retryable=False,
            blocked=True,
            terminal=False,
            summary="Read-only inspection was blocked by bounded scope enforcement.",
            notes="Blocked inspection should be reviewed before any retry is considered.",
        )
        verdict = ValidationVerdictContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_blocked",
            retry_recommended=False,
            retry_reason="",
            operator_attention_required=True,
            escalation_required=False,
            finalized=True,
        )
        return record, verdict

    if response_state == "read_denied":
        record = ValidationRecordContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_blocked",
            validation_class="blocked",
            passed=False,
            partial=False,
            retryable=False,
            blocked=True,
            terminal=False,
            summary="Read-only inspection was denied by policy.",
            notes="Denied inspection falls outside the approved bounded read scope.",
        )
        verdict = ValidationVerdictContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_blocked",
            retry_recommended=False,
            retry_reason="",
            operator_attention_required=True,
            escalation_required=False,
            finalized=True,
        )
        return record, verdict

    if response_state == "read_failed":
        validation_class, retry_recommended, notes, retry_reason = _classify_failed_read(warnings, errors)
        record = ValidationRecordContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_failed",
            validation_class=validation_class,
            passed=False,
            partial=False,
            retryable=retry_recommended,
            blocked=False,
            terminal=not retry_recommended,
            summary="Read-only inspection failed during bounded validation.",
            notes=notes,
        )
        verdict = ValidationVerdictContract(
            validation_id=validation_input.validation_id,
            validation_state="validation_failed",
            retry_recommended=retry_recommended,
            retry_reason=retry_reason,
            operator_attention_required=True,
            escalation_required=not retry_recommended,
            finalized=True,
        )
        return record, verdict

    validation_class: ValidationClass = "retryable_failure" if errors else "terminal_failure"
    retry_recommended = bool(errors)
    retry_reason = "Read-only inspection failed and may be retried within the bounded scope." if errors else ""
    record = ValidationRecordContract(
        validation_id=validation_input.validation_id,
        validation_state="validation_failed",
        validation_class=validation_class,
        passed=False,
        partial=False,
        retryable=retry_recommended,
        blocked=False,
        terminal=not retry_recommended,
        summary="Read-only inspection failed during bounded validation.",
        notes="Failure classification remains deterministic and local-only.",
    )
    verdict = ValidationVerdictContract(
        validation_id=validation_input.validation_id,
        validation_state="validation_failed",
        retry_recommended=retry_recommended,
        retry_reason=retry_reason,
        operator_attention_required=True,
        escalation_required=not retry_recommended,
        finalized=True,
    )
    return record, verdict


def _classify_failed_read(
    warnings: List[str],
    errors: List[str],
) -> tuple[ValidationClass, bool, str, str]:
    failure_messages = list(errors) + list(warnings)
    for message in failure_messages:
        if message.startswith("RETRYABLE:"):
            reason = message.removeprefix("RETRYABLE:").strip()
            return (
                "retryable_failure",
                True,
                f"Retryable bounded read failure: {reason}",
                reason,
            )
        if message.startswith("TERMINAL:"):
            reason = message.removeprefix("TERMINAL:").strip()
            return (
                "terminal_failure",
                False,
                f"Terminal bounded read failure: {reason}",
                "",
            )

    fallback_reason = errors[0] if errors else "Read-only inspection failed without a classified reason."
    return "terminal_failure", False, f"Terminal bounded read failure: {fallback_reason}", ""


class ValidatorEngineInterface(Protocol):
    """Architecture-only boundary for deterministic read-only outcome classification."""

    def build_validation_input(self, execution_id: str) -> ValidationInputContract:
        ...

    def validate(self, validation_input: ValidationInputContract) -> tuple[ValidationRecordContract, ValidationVerdictContract]:
        ...


__all__ = [
    "ValidationClass",
    "ValidationInputContract",
    "ValidationRecordContract",
    "ValidationState",
    "ValidationVerdictContract",
    "ValidatorEngineInterface",
    "evaluate_validation_result",
    "validation_classes",
]