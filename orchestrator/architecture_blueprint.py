from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Protocol, Sequence


PolicyVerdict = Literal["ALLOW", "ASK", "DENY", "TIMEOUT"]
RiskLevel = Literal["low", "medium", "high", "critical"]
TaskStatus = Literal["pending", "planned", "running", "completed", "failed", "blocked"]


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    return value


@dataclass(frozen=True)
class ConversationalRequest:
    request_id: str
    session_id: str
    channel: str
    operator_prompt: str
    created_at: str
    intent: str = "unspecified"
    clarification_needed: bool = False
    context: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    requested_artifacts: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "channel": self.channel,
            "operator_prompt": self.operator_prompt,
            "created_at": self.created_at,
            "intent": self.intent,
            "clarification_needed": self.clarification_needed,
            "context": _stable_value(self.context),
            "constraints": list(self.constraints),
            "requested_artifacts": list(self.requested_artifacts),
        }


@dataclass(frozen=True)
class ValidationRule:
    rule_id: str
    description: str
    evidence: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retry_on: List[str] = field(default_factory=list)
    operator_approval_required: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "retry_on": list(self.retry_on),
            "operator_approval_required": self.operator_approval_required,
        }


@dataclass(frozen=True)
class TaskContract:
    task_id: str
    request_id: str
    task_type: str
    objective: str
    dependencies: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_outputs: List[str] = field(default_factory=list)
    validation_rules: List[ValidationRule] = field(default_factory=list)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    policy_level: str = "standard"
    risk_level: RiskLevel = "medium"
    assigned_agent: str = "PlannerAgent"
    status: TaskStatus = "pending"

    def to_payload(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "request_id": self.request_id,
            "task_type": self.task_type,
            "objective": self.objective,
            "dependencies": sorted(self.dependencies),
            "inputs": _stable_value(self.inputs),
            "expected_outputs": list(self.expected_outputs),
            "validation_rules": [rule.to_payload() for rule in self.validation_rules],
            "retry_policy": self.retry_policy.to_payload(),
            "policy_level": self.policy_level,
            "risk_level": self.risk_level,
            "assigned_agent": self.assigned_agent,
            "status": self.status,
        }


@dataclass(frozen=True)
class TaskGraph:
    request: ConversationalRequest
    tasks: List[TaskContract]

    def task_ids(self) -> List[str]:
        return [task.task_id for task in self.tasks]

    def dependency_map(self) -> Dict[str, List[str]]:
        return {task.task_id: sorted(task.dependencies) for task in self.tasks}

    def to_payload(self) -> Dict[str, Any]:
        return {
            "request": self.request.to_payload(),
            "tasks": [task.to_payload() for task in self.tasks],
            "dependency_map": self.dependency_map(),
        }


@dataclass(frozen=True)
class PolicyDecision:
    verdict: PolicyVerdict
    reason: str
    approval_required: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "approval_required": self.approval_required,
            "evidence": _stable_value(self.evidence),
        }


@dataclass(frozen=True)
class ArtifactRecord:
    name: str
    path: str
    kind: str

    def to_payload(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class OperatorReport:
    request_id: str
    summary: str
    facts: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    timestamp: str = ""
    task_outcomes: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[ArtifactRecord] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "summary": self.summary,
            "facts": list(self.facts),
            "assumptions": list(self.assumptions),
            "timestamp": self.timestamp,
            "task_outcomes": [_stable_value(item) for item in self.task_outcomes],
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
            "validation_results": [_stable_value(item) for item in self.validation_results],
            "recommendations": list(self.recommendations),
        }


@dataclass(frozen=True)
class RemoteWorkPhase:
    phase_id: str
    name: str
    objective: str
    deliverables: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "name": self.name,
            "objective": self.objective,
            "deliverables": list(self.deliverables),
        }


class RuntimeProvider(Protocol):
    def get_provider_info(self) -> Mapping[str, Any]:
        ...

    def health_check(self) -> Mapping[str, Any]:
        ...

    def get_capabilities(self) -> Mapping[str, Any]:
        ...

    def get_limits(self) -> Mapping[str, Any]:
        ...

    def run_task(self, task_bundle: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def cancel_task(self, run_id: str) -> Mapping[str, Any]:
        ...


class ChatGateway(Protocol):
    def receive_message(self, raw_input: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def normalize_request(self) -> Mapping[str, Any]:
        ...

    def send_response(self, response_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def send_approval_request(self, response_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def bind_session(self, session_id: str) -> Mapping[str, Any]:
        ...


def default_remote_work_constraints() -> List[str]:
    return [
        "Do not create new Python environments.",
        "Do not modify orchestrator baseline architecture.",
        "Do not redesign the main menu.",
        "Do not start LEVEL_0002.",
        "Do not restructure the Unity project.",
        "Do not modify gameplay systems.",
        "Do not regenerate assets.",
        "Do not introduce experimental frameworks.",
        "Do not bypass policy or validation layers.",
    ]


def default_allowed_work_types() -> List[str]:
    return [
        "AI-E architecture development",
        "planning agent systems",
        "task graph design",
        "orchestration logic design",
        "runtime provider integration planning",
        "chatbot gateway integration planning",
        "memory and learning architecture design",
        "reporting system architecture",
    ]


def default_agent_roles() -> List[str]:
    return [
        "PlannerAgent",
        "BuilderAgent",
        "ValidatorAgent",
        "ReportAgent",
        "RecoveryAgent",
        "PolicyAgent",
        "ResearchAgent",
        "PerceptionAgent",
    ]


def default_remote_work_phases() -> List[RemoteWorkPhase]:
    return [
        RemoteWorkPhase(
            phase_id="PHASE_1",
            name="Conversational command schema",
            objective="Normalize natural language requests into deterministic AI-E request payloads.",
            deliverables=["request schema", "session metadata model", "clarification rules"],
        ),
        RemoteWorkPhase(
            phase_id="PHASE_2",
            name="PlannerAgent architecture",
            objective="Translate operator requests into bounded, reviewable plans.",
            deliverables=["planning inputs", "risk labels", "plan output contract"],
        ),
        RemoteWorkPhase(
            phase_id="PHASE_3",
            name="Task graph system design",
            objective="Represent work as dependency-aware contracts instead of flat queue steps.",
            deliverables=["task node schema", "dependency map", "retry metadata"],
        ),
        RemoteWorkPhase(
            phase_id="PHASE_4",
            name="Agent role definitions",
            objective="Define logical agent roles without binding them to separate models.",
            deliverables=["role catalog", "handoff rules", "responsibility matrix"],
        ),
        RemoteWorkPhase(
            phase_id="PHASE_5",
            name="Tool adapter architecture",
            objective="Define safe environment interfaces for editors, filesystems, and artifact tools.",
            deliverables=["adapter boundaries", "tool capability schema", "execution guards"],
        ),
        RemoteWorkPhase(
            phase_id="PHASE_6",
            name="Runtime provider system",
            objective="Standardize bounded execution across local and future remote providers.",
            deliverables=["provider protocol", "health model", "capability model"],
        ),
        RemoteWorkPhase(
            phase_id="PHASE_7",
            name="Chat gateway system",
            objective="Normalize inbound messages from multiple chat interfaces without bypassing policy.",
            deliverables=["gateway protocol", "session binding contract", "approval routing"],
        ),
        RemoteWorkPhase(
            phase_id="PHASE_8",
            name="Learning and memory system",
            objective="Record reproducible lessons, failures, and operator preferences.",
            deliverables=["memory taxonomy", "retention rules", "report feedback loop"],
        ),
    ]


def required_run_log_fields() -> List[str]:
    return [
        "run_id",
        "timestamp",
        "task_list",
        "policy_decisions",
        "artifacts",
        "validation_results",
        "recommendations",
    ]


def required_response_sections() -> List[str]:
    return [
        "SUMMARY",
        "FACTS",
        "ASSUMPTIONS",
        "RECOMMENDATIONS",
        "TIMESTAMP",
    ]


__all__ = [
    "ArtifactRecord",
    "ChatGateway",
    "ConversationalRequest",
    "OperatorReport",
    "PolicyDecision",
    "RetryPolicy",
    "RuntimeProvider",
    "TaskContract",
    "TaskGraph",
    "ValidationRule",
    "default_agent_roles",
    "default_allowed_work_types",
    "default_remote_work_constraints",
    "default_remote_work_phases",
    "required_response_sections",
    "required_run_log_fields",
]