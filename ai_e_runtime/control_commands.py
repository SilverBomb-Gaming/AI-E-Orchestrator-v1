from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .runtime_state import RuntimeState
from .supervisor import Supervisor


@dataclass(frozen=True)
class ControlCommandResult:
    title: str
    body: str
    should_exit: bool = False

    def to_text(self) -> str:
        if not self.title:
            return self.body
        if not self.body:
            return self.title
        return f"{self.title}\n\n{self.body}"


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
        "exit": "exit",
        "quit": "exit",
    }

    def __init__(self, supervisor: Supervisor, runtime_state: RuntimeState) -> None:
        self.supervisor = supervisor
        self.runtime_state = runtime_state

    def is_control_command(self, prompt: str) -> bool:
        return self.normalize_command(prompt) is not None

    def normalize_command(self, prompt: str) -> str | None:
        normalized = " ".join(str(prompt or "").strip().lower().split())
        if not normalized:
            return None
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
                "exit",
                "",
                "Examples:",
                "help",
                "pause polling",
                "resume polling",
                "show last acceptance",
                "show last artifact",
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
            f"Missing Evidence: {', '.join(last_acceptance.get('missing_evidence', []) or []) or 'none'}",
            f"Auto Reason: {last_acceptance.get('auto_execution_reason', 'none')}",
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

    def _last_artifact_text(self) -> str:
        snapshot = self.runtime_state.get_snapshot()
        latest_artifact = snapshot.last_artifact_path or snapshot.artifact_output_path
        return "\n".join(
            [
                f"Latest Artifact Path: {latest_artifact}",
                f"Artifact Output Directory: {snapshot.artifact_output_path}",
            ]
        )


__all__ = ["ControlCommandHandler", "ControlCommandResult"]