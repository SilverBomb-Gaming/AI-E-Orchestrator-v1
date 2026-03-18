from __future__ import annotations

from time import sleep
from typing import Any, Callable, Dict

from .level_0001_grass_mutation import run_level_0001_grass_mutation


AgentCallable = Callable[[Dict[str, Any]], Dict[str, Any]]


class AgentRouter:
    """Unified runtime entrypoint for minimal continuous-session agent execution."""

    def __init__(self) -> None:
        self._agents: Dict[str, AgentCallable] = {
            "copilot_coder_agent": self._run_copilot_coder_agent,
            "read_only_inspector_agent": self._run_read_only_inspector_agent,
            "level_0001_grass_mutation_agent": run_level_0001_grass_mutation,
            "validator_agent": self._run_validator_agent,
            "unity_control_agent": self._run_unity_control_agent,
            "artifact_summarizer_agent": self._run_artifact_summarizer_agent,
        }

    def register(self, agent_type: str, runner: AgentCallable) -> None:
        self._agents[str(agent_type)] = runner

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        agent_type = self.resolve_agent_type(task)
        runner = self._agents.get(agent_type)
        if runner is None:
            raise KeyError(f"Unsupported agent type: {agent_type}")
        result = runner(dict(task))
        result.setdefault("agent_type", agent_type)
        return result

    def validate(self, result: Dict[str, Any], *, task: Dict[str, Any] | None = None) -> Dict[str, Any]:
        validator_task = {
            "agent_type": "validator_agent",
            "result": dict(result),
            "task": dict(task or {}),
        }
        return self.run(validator_task)

    def resolve_agent_type(self, task: Dict[str, Any]) -> str:
        explicit = task.get("agent_type")
        if explicit:
            return str(explicit)
        agents = task.get("agents")
        if isinstance(agents, list):
            for entry in agents:
                candidate = str(entry)
                if candidate in self._agents:
                    return candidate
        if task.get("contract_type") == "read_only_capability":
            return "read_only_inspector_agent"
        return "copilot_coder_agent"

    def _run_copilot_coder_agent(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self._sleep_if_requested(task)
        outcome = str(task.get("simulated_outcome", "completed"))
        title = task.get("title") or task.get("task_id") or task.get("id") or "task"
        payload = dict(task.get("result_payload") or {})
        if outcome == "blocked":
            return {
                "status": "blocked",
                "summary": f"copilot_coder_agent blocked {title}",
                "details": payload,
                "error": str(task.get("error") or "Task was blocked by agent logic."),
            }
        if outcome in {"retryable_failure", "failed", "retryable"}:
            return {
                "status": "retryable_failure",
                "summary": f"copilot_coder_agent needs retry for {title}",
                "details": payload,
                "error": str(task.get("error") or "Retryable failure requested by task payload."),
                "retryable": True,
            }
        return {
            "status": "completed",
            "summary": f"copilot_coder_agent completed {title}",
            "details": payload,
            "artifacts": list(task.get("artifacts") or []),
        }

    def _run_read_only_inspector_agent(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self._sleep_if_requested(task)
        title = task.get("title") or task.get("task_id") or task.get("id") or "task"
        return {
            "status": "completed",
            "summary": f"read_only_inspector_agent inspected {title}",
            "details": dict(task.get("result_payload") or {}),
            "artifacts": list(task.get("artifacts") or []),
        }

    def _run_validator_agent(self, task: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(task.get("result") or {})
        result_status = str(result.get("status", "completed"))
        error = str(result.get("error") or "").strip()
        if result_status == "completed":
            return {
                "status": "completed",
                "validation_state": "passed",
                "queue_action": "complete",
                "note": str(result.get("summary") or "Validation passed."),
            }
        if result_status == "retryable_failure":
            return {
                "status": "retryable_failure",
                "validation_state": "retryable_failure",
                "queue_action": "retry",
                "note": error or "Validation requested a retry.",
            }
        return {
            "status": "blocked",
            "validation_state": "blocked",
            "queue_action": "block",
            "note": error or "Validation blocked the task.",
        }

    def _run_unity_control_agent(self, task: Dict[str, Any]) -> Dict[str, Any]:
        title = task.get("title") or task.get("task_id") or task.get("id") or "task"
        return {
            "status": "blocked",
            "summary": f"unity_control_agent is not implemented for {title}",
            "error": "unity_control_agent is reserved for future runtime integration.",
        }

    def _run_artifact_summarizer_agent(self, task: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = list(task.get("artifacts") or [])
        return {
            "status": "completed",
            "summary": f"artifact_summarizer_agent processed {len(artifacts)} artifacts",
            "details": {"artifact_count": len(artifacts)},
            "artifacts": artifacts,
        }

    def _sleep_if_requested(self, task: Dict[str, Any]) -> None:
        try:
            delay_seconds = float(task.get("simulated_delay_seconds", 0) or 0)
        except (TypeError, ValueError):
            delay_seconds = 0.0
        if delay_seconds > 0:
            sleep(delay_seconds)