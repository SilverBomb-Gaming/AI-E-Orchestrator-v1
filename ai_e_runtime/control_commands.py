from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from .content_policy import load_profile, update_rating_lock, update_rating_target
from .runtime_state import RuntimeState
from .supervisor import Supervisor
from .time_utils import get_current_timestamp


@dataclass(frozen=True)
class ControlCommandResult:
    title: str
    body: str
    should_exit: bool = False
    timestamp: str = field(default_factory=get_current_timestamp)

    def to_text(self) -> str:
        if not self.title and not self.body.strip():
            return self.body
        if not self.title:
            return f"{self.body}\n\nTIMESTAMP: {self.timestamp}"
        if not self.body:
            return f"{self.title}\n\nTIMESTAMP: {self.timestamp}"
        return f"{self.title}\n\n{self.body}\n\nTIMESTAMP: {self.timestamp}"


class ControlCommandHandler:
    """Executes safe interactive runtime control commands without queue mutation."""

    COMMAND_ALIASES = {
        "clear": "clear",
        "cls": "clear",
        "help": "help",
        "show last acceptance": "show_last_acceptance",
        "last acceptance": "show_last_acceptance",
        "show last artifact": "show_last_artifact",
        "last artifact": "show_last_artifact",
        "pause polling": "pause_polling",
        "resume polling": "resume_polling",
        "get rating profile": "get_rating_profile",
        "exit": "exit",
        "quit": "exit",
    }
    COMMAND_PREFIXES = (
        "set_rating_profile",
        "get_rating_profile",
        "set_rating_lock",
    )

    def __init__(self, supervisor: Supervisor, runtime_state: RuntimeState) -> None:
        self.supervisor = supervisor
        self.runtime_state = runtime_state

    def is_control_command(self, prompt: str) -> bool:
        return self.normalize_command(prompt) is not None

    def normalize_command(self, prompt: str) -> str | None:
        normalized = " ".join(str(prompt or "").strip().lower().split())
        if not normalized:
            return None
        for prefix in self.COMMAND_PREFIXES:
            if normalized.startswith(prefix):
                return prefix
        return self.COMMAND_ALIASES.get(normalized)

    def execute(self, prompt: str, *, last_acceptance: Dict[str, Any] | None = None) -> ControlCommandResult:
        command = self.normalize_command(prompt)
        if command == "clear":
            return ControlCommandResult(title="", body=self._clear_output())
        if command == "help":
            return ControlCommandResult(title="AI-E COMMAND CENTER HELP", body=self._help_text())
        if command == "show_last_acceptance":
            return ControlCommandResult(title="AI-E LAST ACCEPTANCE", body=self._last_acceptance_text(last_acceptance))
        if command == "show_last_artifact":
            return ControlCommandResult(title="AI-E LAST ARTIFACT", body=self._last_artifact_text())
        if command == "pause_polling":
            changed = self.supervisor.pause_polling()
            body = "Queue polling paused. Heartbeats continue and no new queue items will start until polling resumes."
            if not changed:
                body = "Queue polling was already paused. Heartbeats continue and queued work remains idle."
            return ControlCommandResult(title="AI-E POLLING PAUSED", body=body)
        if command == "resume_polling":
            changed = self.supervisor.resume_polling()
            body = "Queue polling resumed. Pending work can start on the next scheduler cycle without restarting the session."
            if not changed:
                body = "Queue polling was already active. Pending work can continue on the next scheduler cycle."
            return ControlCommandResult(title="AI-E POLLING RESUMED", body=body)
        if command == "get_rating_profile":
            profile = load_profile(self.supervisor.orchestrator_config)
            return ControlCommandResult(title="AI-E RATING PROFILE", body=self._rating_profile_text(profile, confirmation=None))
        if command == "set_rating_profile":
            return self._set_rating_profile(prompt)
        if command == "set_rating_lock":
            return self._set_rating_lock(prompt)
        if command == "exit":
            self.supervisor.request_stop()
            return ControlCommandResult(
                title="AI-E INTERACTIVE SESSION EXIT",
                body="Interactive prompt closed. Supervisor shutdown requested.",
                should_exit=True,
            )
        return ControlCommandResult(
            title="AI-E CONTROL COMMAND ERROR",
            body="Command was not recognized. Use 'help' to list supported commands.",
        )

    def _clear_output(self) -> str:
        return "\n" * 50

    def _help_text(self) -> str:
        return "\n".join(
            [
                "Supported commands:",
                "help",
                "clear",
                "show last acceptance",
                "show last artifact",
                "pause polling",
                "resume polling",
                "get_rating_profile",
                "set_rating_profile <rating>",
                "set_rating_lock <true|false>",
                "exit",
                "",
                "Examples:",
                "help",
                "pause polling",
                "resume polling",
                "show last acceptance",
                "show last artifact",
                "get_rating_profile",
                "set_rating_profile T",
                "set_rating_lock false",
            ]
        )

    def _last_acceptance_text(self, last_acceptance: Dict[str, Any] | None) -> str:
        if not last_acceptance:
            return "No task has been accepted in this interactive session yet."
        lines = [
            f"Task ID: {last_acceptance.get('task_id', 'unknown')}",
            f"Request ID: {last_acceptance.get('request_id', 'unknown')}",
            f"Plan ID: {last_acceptance.get('plan_id', 'unknown')}",
            f"Status: {last_acceptance.get('status', 'unknown')}",
            f"Requested Intent: {last_acceptance.get('requested_intent', 'unknown')}",
            f"Resolved Intent: {last_acceptance.get('resolved_intent', 'unknown')}",
            f"Requested Lane: {last_acceptance.get('requested_execution_lane', 'unknown')}",
            f"Execution Lane: {last_acceptance.get('execution_lane', 'unknown')}",
            f"Downgrade: {'yes' if bool(last_acceptance.get('downgraded', False)) else 'no'}",
            f"Approval Required: {'yes' if bool(last_acceptance.get('approval_required', False)) else 'no'}",
            f"Mutation Capable: {'yes' if bool(last_acceptance.get('mutation_capable', False)) else 'no'}",
            f"Capability Matched: {last_acceptance.get('capability_id', 'none')}",
            f"Maturity: {last_acceptance.get('maturity_stage') or last_acceptance.get('evidence_state', 'none')}",
            f"Trust Score: {last_acceptance.get('trust_score', 0)}",
            f"Trust Band: {last_acceptance.get('trust_band', 'none')}",
            f"Policy State: {last_acceptance.get('policy_state', 'none')}",
            f"Execution Decision: {last_acceptance.get('execution_decision', 'none')}",
            f"Recommended Action: {last_acceptance.get('recommended_action', 'none')}",
            f"Sandbox First: {'yes' if bool(last_acceptance.get('sandbox_first_required', False)) else 'no'}",
            f"Auto Execution: {'yes' if bool(last_acceptance.get('auto_execution_enabled', False)) else 'no'}",
            f"Eligible for Auto: {'yes' if bool(last_acceptance.get('eligible_for_auto', False)) else 'no'}",
            f"Sandbox Verified: {'yes' if bool(last_acceptance.get('sandbox_verified', False)) else 'no'}",
            f"Real Target Verified: {'yes' if bool(last_acceptance.get('real_target_verified', False)) else 'no'}",
            f"Rollback Verified: {'yes' if bool(last_acceptance.get('rollback_verified', False)) else 'no'}",
            f"Last Validation: {last_acceptance.get('last_validation_result', 'none')}",
            f"Last Rollback: {last_acceptance.get('last_rollback_result', 'none')}",
            f"Rating System: {last_acceptance.get('rating_system', 'none')}",
            f"Rating Target: {last_acceptance.get('rating_target', 'none')}",
            f"Rating Locked: {'yes' if bool(last_acceptance.get('rating_locked', False)) else 'no'}",
            f"Content Policy Match: {last_acceptance.get('content_policy_match', 'none')}",
            f"Content Policy Decision: {last_acceptance.get('content_policy_decision', 'none')}",
            f"Required Rating Upgrade: {last_acceptance.get('required_rating_upgrade', 'none')}",
            f"Decision: {last_acceptance.get('decision', 'none')}",
            f"Decision Reason: {last_acceptance.get('decision_reason', 'none')}",
            f"Decision Summary: {last_acceptance.get('decision_summary', 'none')}",
            f"Requested Content Dimensions: {self._format_content_dimensions(last_acceptance.get('requested_content_dimensions'))}",
            f"Missing Evidence: {', '.join(last_acceptance.get('missing_evidence', []) or []) or 'none'}",
            f"Auto Reason: {last_acceptance.get('auto_execution_reason', 'none')}",
            f"Promotion Basis: {last_acceptance.get('promotion_basis', 'none')}",
            f"Fail Closed Reason: {last_acceptance.get('fail_closed_reason', 'none')}",
            f"Content Policy Summary: {last_acceptance.get('content_policy_summary', 'none')}",
            f"Queue Write: {last_acceptance.get('queue_write_status', 'unknown')}",
            f"Runtime Task Payload: {last_acceptance.get('runtime_task_payload_path', 'unknown')}",
            f"Request Payload: {last_acceptance.get('request_payload_path', 'unknown')}",
            f"Task Graph Payload: {last_acceptance.get('task_graph_path', 'unknown')}",
        ]
        if last_acceptance.get('downgrade_reason'):
            lines.append(f"Downgrade Reason: {last_acceptance.get('downgrade_reason')}")
        step_titles = last_acceptance.get('plan_step_titles') or []
        if isinstance(step_titles, list) and step_titles:
            lines.append("Plan Steps:")
            lines.extend(f"{index}. {title}" for index, title in enumerate(step_titles, start=1))
        return "\n".join(lines)

    def _format_content_dimensions(self, payload: Any) -> str:
        if not isinstance(payload, dict) or not payload:
            return "none"
        return ", ".join(f"{key}={value}" for key, value in payload.items())

    def _last_artifact_text(self) -> str:
        snapshot = self.runtime_state.get_snapshot()
        latest_artifact = snapshot.last_artifact_path or snapshot.artifact_output_path
        return "\n".join(
            [
                f"Latest Artifact Path: {latest_artifact}",
                f"Artifact Output Directory: {snapshot.artifact_output_path}",
            ]
        )

    def _set_rating_profile(self, prompt: str) -> ControlCommandResult:
        parts = str(prompt or "").strip().split()
        if len(parts) != 2:
            return ControlCommandResult(
                title="AI-E RATING PROFILE ERROR",
                body="Usage: set_rating_profile <rating>",
            )
        rating_target = parts[1]
        try:
            profile = update_rating_target(self.supervisor.orchestrator_config, rating_target)
        except ValueError as exc:
            return ControlCommandResult(title="AI-E RATING PROFILE ERROR", body=str(exc))
        confirmation = f"Rating profile updated: {profile.rating_system} -> {profile.rating_target} (locked: {'true' if profile.rating_locked else 'false'})"
        return ControlCommandResult(title="AI-E RATING PROFILE UPDATED", body=self._rating_profile_text(profile, confirmation=confirmation))

    def _set_rating_lock(self, prompt: str) -> ControlCommandResult:
        parts = str(prompt or "").strip().split()
        if len(parts) != 2:
            return ControlCommandResult(
                title="AI-E RATING LOCK ERROR",
                body="Usage: set_rating_lock <true|false>",
            )
        raw = parts[1].strip().lower()
        if raw not in {"true", "false"}:
            return ControlCommandResult(
                title="AI-E RATING LOCK ERROR",
                body="Lock value must be true or false.",
            )
        profile = update_rating_lock(self.supervisor.orchestrator_config, raw == "true")
        confirmation = f"Rating lock updated: {profile.rating_system} {profile.rating_target} (locked: {'true' if profile.rating_locked else 'false'})"
        return ControlCommandResult(title="AI-E RATING LOCK UPDATED", body=self._rating_profile_text(profile, confirmation=confirmation))

    def _rating_profile_text(self, profile: Any, *, confirmation: str | None) -> str:
        lines = []
        if confirmation:
            lines.append(confirmation)
            lines.append("")
        lines.extend(
            [
                f"Rating System: {profile.rating_system}",
                f"Rating Target: {profile.rating_target}",
                f"Rating Locked: {'yes' if profile.rating_locked else 'no'}",
                "New tasks will use the updated rating profile immediately.",
            ]
        )
        return "\n".join(lines)


__all__ = ["ControlCommandHandler", "ControlCommandResult"]