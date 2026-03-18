from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List

from .capability_intelligence import assess_capability_intelligence, assess_mutation_without_capability
from .capability_registry import CapabilityRegistry, RuntimeCapability
from .content_policy import ensure_project_content_profile, evaluate_content_policy, load_project_content_profile
from orchestrator.architecture_blueprint import ConversationalRequest
from orchestrator.config import OrchestratorConfig
from orchestrator.request_schema_loader import validate_request_payload
from orchestrator.utils import ensure_dir, read_json, utc_timestamp, write_json

from .planner import RuleBasedPlanner
from .planner_task_graph import build_plan_task_graph
from .state_store import StateStore


_DEFAULT_CHANNEL = "operator_console"
_DEFAULT_SESSION_ID = "operator_session"
_DEFAULT_REQUESTED_ARTIFACTS = [
    "request_analysis.json",
    "task_graph.json",
    "runtime_task.json",
]


@dataclass(frozen=True)
class IntakeArtifacts:
    request_payload_path: Path
    task_graph_path: Path

    runtime_task_payload_paths: List[Path]

    @property
    def runtime_task_payload_path(self) -> Path:
        return self.runtime_task_payload_paths[0]


@dataclass(frozen=True)
class IntakeRouting:
    requested_intent: str
    resolved_intent: str
    requested_execution_lane: str
    execution_lane: str
    downgraded: bool
    downgrade_reason: str | None
    approval_required: bool
    mutation_capable: bool
    capability_id: str | None = None
    capability_title: str | None = None
    handler_name: str | None = None
    target_level: str | None = None
    target_scene: str | None = None
    trust_score: int = 0
    trust_band: str | None = None
    policy_state: str | None = None
    execution_decision: str | None = None
    recommended_action: str | None = None
    sandbox_first_required: bool = False
    auto_execution_enabled: bool = False
    auto_execution_reason: str | None = None
    missing_evidence: List[str] | None = None
    intelligence_summary: str | None = None
    maturity_stage: str | None = None
    evidence_state: str | None = None
    eligible_for_auto: bool = False
    times_attempted: int = 0
    times_passed: int = 0
    last_validation_result: str | None = None
    last_rollback_result: str | None = None
    sandbox_verified: bool = False
    real_target_verified: bool = False
    rollback_verified: bool = False
    rating_system: str | None = None
    rating_target: str | None = None
    rating_locked: bool = False
    content_policy_match: str | None = None
    content_policy_decision: str | None = None
    required_rating_upgrade: str | None = None
    requested_content_dimensions: Dict[str, Any] | None = None
    content_policy_summary: str | None = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "requested_intent": self.requested_intent,
            "resolved_intent": self.resolved_intent,
            "requested_execution_lane": self.requested_execution_lane,
            "execution_lane": self.execution_lane,
            "downgraded": self.downgraded,
            "downgrade_reason": self.downgrade_reason,
            "approval_required": self.approval_required,
            "mutation_capable": self.mutation_capable,
            "capability_id": self.capability_id,
            "capability_title": self.capability_title,
            "handler_name": self.handler_name,
            "target_level": self.target_level,
            "target_scene": self.target_scene,
            "trust_score": self.trust_score,
            "trust_band": self.trust_band,
            "policy_state": self.policy_state,
            "execution_decision": self.execution_decision,
            "recommended_action": self.recommended_action,
            "sandbox_first_required": self.sandbox_first_required,
            "auto_execution_enabled": self.auto_execution_enabled,
            "auto_execution_reason": self.auto_execution_reason,
            "missing_evidence": list(self.missing_evidence or []),
            "intelligence_summary": self.intelligence_summary,
            "maturity_stage": self.maturity_stage or self.evidence_state,
            "evidence_state": self.evidence_state,
            "eligible_for_auto": self.eligible_for_auto,
            "times_attempted": self.times_attempted,
            "times_passed": self.times_passed,
            "last_validation_result": self.last_validation_result,
            "last_rollback_result": self.last_rollback_result,
            "sandbox_verified": self.sandbox_verified,
            "real_target_verified": self.real_target_verified,
            "rollback_verified": self.rollback_verified,
            "rating_system": self.rating_system,
            "rating_target": self.rating_target,
            "rating_locked": self.rating_locked,
            "content_policy_match": self.content_policy_match,
            "content_policy_decision": self.content_policy_decision,
            "required_rating_upgrade": self.required_rating_upgrade,
            "requested_content_dimensions": dict(self.requested_content_dimensions or {}),
            "content_policy_summary": self.content_policy_summary,
        }


@dataclass(frozen=True)
class IntakeResult:
    task_id: str
    task_ids: List[str]
    request_id: str
    plan_id: str
    title: str
    task_type: str
    target_repo: str
    queue_entry: Dict[str, Any]
    queue_entries: List[Dict[str, Any]]
    artifacts: IntakeArtifacts
    created: bool
    plan_summary: str
    plan_step_titles: List[str]
    routing: IntakeRouting

    @property
    def is_multi_step(self) -> bool:
        return len(self.task_ids) > 1


class ConversationalTaskIntake:
    """Converts operator messages into deterministic, runnable queue tasks."""

    _TASK_REQUEST_VERBS = (
        "stabilize",
        "fix",
        "restore",
        "repair",
        "inspect",
        "audit",
        "review",
        "report",
        "expand",
        "improve",
        "make",
        "enable",
        "build",
        "create",
        "add",
        "investigate",
        "analyze",
        "validate",
        "check",
    )
    _PLAN_REQUEST_VERBS = (
        "plan",
        "outline",
        "decompose",
        "map out",
        "brainstorm",
    )
    _MUTATION_REQUEST_VERBS = (
        "stabilize",
        "fix",
        "restore",
        "repair",
        "expand",
        "improve",
        "make",
        "enable",
        "build",
        "create",
        "add",
        "generate",
        "place",
        "patch",
        "modify",
    )

    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config
        self.requests_dir = ensure_dir(self.config.contracts_dir / "intake" / "requests")
        self.task_graphs_dir = ensure_dir(self.config.contracts_dir / "intake" / "task_graphs")
        self.runtime_tasks_dir = ensure_dir(self.config.contracts_dir / "intake" / "runtime_tasks")
        ensure_project_content_profile(config)
        self.planner = RuleBasedPlanner()
        self.capability_registry = CapabilityRegistry(config)

    def accept_message(
        self,
        operator_message: str,
        *,
        session_id: str = _DEFAULT_SESSION_ID,
        channel: str = _DEFAULT_CHANNEL,
        target_repo: str | None = None,
        simulated_delay_seconds: float | None = None,
    ) -> IntakeResult:
        normalized_prompt = self._normalize_prompt(operator_message)
        if not normalized_prompt:
            raise ValueError("operator message must not be empty")

        resolved_target_repo = target_repo or self._derive_target_repo(normalized_prompt)
        routing = self._resolve_intake_routing(normalized_prompt)
        task_type = self._derive_task_type(normalized_prompt, routing=routing)
        request_id = self._derive_request_id(normalized_prompt, resolved_target_repo, task_type)
        title = self._derive_title(normalized_prompt)
        request_payload = self._build_request_payload(
            normalized_prompt,
            request_id=request_id,
            session_id=session_id,
            channel=channel,
            target_repo=resolved_target_repo,
            task_type=task_type,
                routing=routing,
        )
        request = validate_request_payload(request_payload)
        plan = self.planner.plan(
            request.operator_prompt,
            target_repo=resolved_target_repo,
            request_id=request_id,
        )

        queue_payload = read_json(self.config.queue_path, default={"tasks": []})
        tasks = list(queue_payload.get("tasks", []))
        task_id_prefix = self._derive_task_id_prefix(request_id, tasks, multi_step=len(plan.steps) > 1)

        request_path = self.requests_dir / f"{request_id}.json"
        task_graph_path = self.task_graphs_dir / f"{request_id}.json"
        task_graph = build_plan_task_graph(plan, request_id=request_id, task_id_prefix=task_id_prefix)
        runtime_task_payload_paths: List[Path] = []

        request_wrapper = {"conversational_request": request.to_payload()}
        task_graph_wrapper = {"task_graph": task_graph.to_payload()}

        write_json(request_path, request_wrapper)
        write_json(task_graph_path, task_graph_wrapper)

        queue_entries: List[Dict[str, Any]] = []
        created = False
        single_step = len(task_graph.nodes) == 1
        queue_status = "blocked" if routing.content_policy_decision == "blocked" else (
            "needs_approval" if routing.approval_required and routing.execution_lane == "approval_required_mutation" else "pending"
        )
        auto_execution_enabled = routing.execution_decision == "auto_execute"
        approval_state = "blocked" if queue_status == "blocked" else (
            "awaiting_approval" if queue_status == "needs_approval" else ("auto_approved" if auto_execution_enabled else "not_required")
        )
        approved_by = "system_intelligence_v1" if auto_execution_enabled else None
        approved_at = utc_timestamp(compact=False) if auto_execution_enabled else None
        approval_notes = routing.auto_execution_reason if auto_execution_enabled else ""
        for node in task_graph.nodes:
            runtime_task_payload_path = self.runtime_tasks_dir / f"{node.task_id}.json"
            runtime_task_payload_paths.append(runtime_task_payload_path)
            runtime_task_wrapper = {
                "runtime_task": {
                    "task_id": node.task_id,
                    "request_id": request_id,
                    "plan_id": plan.plan_id,
                    "plan_step_index": node.step_index,
                    "plan_step_title": node.title,
                    "plan_total_steps": len(plan.steps),
                    "plan_summary": plan.summary_text(),
                    "title": title if single_step else node.title,
                    "task_type": task_type if single_step else node.task_type,
                    "target_repo": resolved_target_repo,
                    "agent_type": routing.handler_name and "level_0001_grass_mutation_agent" or "read_only_inspector_agent",
                    "execution_mode": routing.execution_lane if routing.mutation_capable else node.execution_mode,
                    "requested_intent": routing.requested_intent,
                    "resolved_intent": routing.resolved_intent,
                    "requested_execution_lane": routing.requested_execution_lane,
                    "execution_lane": routing.execution_lane,
                    "downgraded": routing.downgraded,
                    "downgrade_reason": routing.downgrade_reason,
                    "approval_required": routing.approval_required,
                    "mutation_capable": routing.mutation_capable,
                    "capability_id": routing.capability_id,
                    "capability_title": routing.capability_title,
                    "handler_name": routing.handler_name,
                    "maturity_stage": routing.maturity_stage or routing.evidence_state,
                    "trust_score": routing.trust_score,
                    "trust_band": routing.trust_band,
                    "policy_state": routing.policy_state,
                    "execution_decision": routing.execution_decision,
                    "recommended_action": routing.recommended_action,
                    "sandbox_first_required": routing.sandbox_first_required,
                    "auto_execution_enabled": routing.auto_execution_enabled,
                    "auto_execution_reason": routing.auto_execution_reason,
                    "missing_evidence": list(routing.missing_evidence or []),
                    "intelligence_summary": routing.intelligence_summary,
                    "evidence_state": routing.evidence_state,
                    "eligible_for_auto": routing.eligible_for_auto,
                    "times_attempted": routing.times_attempted,
                    "times_passed": routing.times_passed,
                    "last_validation_result": routing.last_validation_result,
                    "last_rollback_result": routing.last_rollback_result,
                    "sandbox_verified": routing.sandbox_verified,
                    "real_target_verified": routing.real_target_verified,
                    "rollback_verified": routing.rollback_verified,
                    "rating_system": routing.rating_system,
                    "rating_target": routing.rating_target,
                    "rating_locked": routing.rating_locked,
                    "content_policy_match": routing.content_policy_match,
                    "content_policy_decision": routing.content_policy_decision,
                    "required_rating_upgrade": routing.required_rating_upgrade,
                    "requested_content_dimensions": dict(routing.requested_content_dimensions or {}),
                    "content_policy_summary": routing.content_policy_summary,
                    "approval_state": approval_state,
                    "approved_by": approved_by,
                    "approved_at": approved_at,
                    "approval_notes": approval_notes,
                    "target_level": routing.target_level,
                    "target_scene": routing.target_scene,
                    "capability_evidence_path": str(self.capability_registry.evidence_path),
                    "operator_prompt": normalized_prompt,
                    "created_at": utc_timestamp(compact=False),
                    "requested_artifacts": list(_DEFAULT_REQUESTED_ARTIFACTS),
                    "task_graph_path": self._relative(task_graph_path),
                    "request_payload_path": self._relative(request_path),
                    "dependencies": list(node.dependencies),
                    "simulated_delay_seconds": self._resolve_simulated_delay_seconds(simulated_delay_seconds),
                }
            }
            write_json(runtime_task_payload_path, runtime_task_wrapper)

            queue_entry = self._build_queue_entry(
                task_id=node.task_id,
                request=request,
                title=title if single_step else node.title,
                task_type=task_type if single_step else node.task_type,
                target_repo=resolved_target_repo,
                runtime_task_payload_path=runtime_task_payload_path,
                request_path=request_path,
                task_graph_path=task_graph_path,
                plan_id=plan.plan_id,
                plan_step_index=node.step_index,
                plan_total_steps=len(plan.steps),
                plan_step_title=node.title,
                dependencies=node.dependencies,
                priority=self._derive_priority(task_type, request.operator_prompt) if single_step else node.priority,
                routing=routing,
                status=queue_status,
            )

            existing = self._find_existing_task(tasks, node.task_id)
            if existing is None:
                tasks.append(queue_entry)
                queue_entries.append(queue_entry)
                created = True
            else:
                queue_entries.append(dict(existing))

        queue_payload["tasks"] = tasks
        write_json(self.config.queue_path, queue_payload)
        self._register_plan_state(
            session_id=session_id,
            plan_id=plan.plan_id,
            plan_summary=plan.summary_text(),
            plan_steps=plan.plan_step_titles(),
        )

        return IntakeResult(
            task_id=queue_entries[0]["task_id"],
            task_ids=[entry["task_id"] for entry in queue_entries],
            request_id=request_id,
            plan_id=plan.plan_id,
            title=title,
            task_type=task_type,
            target_repo=resolved_target_repo,
            queue_entry=queue_entries[0],
            queue_entries=queue_entries,
            artifacts=IntakeArtifacts(
                request_payload_path=request_path,
                task_graph_path=task_graph_path,
                runtime_task_payload_paths=runtime_task_payload_paths,
            ),
            created=created,
            plan_summary=plan.summary_text(),
            plan_step_titles=plan.plan_step_titles(),
            routing=routing,
        )

    def classify_message(self, operator_message: str) -> str:
        normalized = self._normalize_prompt(operator_message).lower()
        if not normalized:
            return "empty"
        if normalized.endswith("?"):
            return "not_task_request"
        if normalized.startswith(self._TASK_REQUEST_VERBS):
            return "task_request"
        if any(token in normalized for token in ("level_0001", "zombie", "kbm", "weapon", "babylon", "unity")):
            return "task_request"
        return "not_task_request"

    def _build_request_payload(
        self,
        normalized_prompt: str,
        *,
        request_id: str,
        session_id: str,
        channel: str,
        target_repo: str,
        task_type: str,
        routing: IntakeRouting,
    ) -> Dict[str, Any]:
        return {
            "request_id": request_id,
            "session_id": session_id,
            "channel": channel,
            "operator_prompt": normalized_prompt,
            "created_at": utc_timestamp(compact=False),
            "intent": task_type,
            "clarification_needed": False,
            "context": {
                "target_repo": target_repo,
                "execution_mode": routing.execution_lane if routing.mutation_capable else "bounded_read_only",
                "source": "ai_e_runtime.task_intake",
                "routing": routing.to_payload(),
            },
            "constraints": [
                "Preserve deterministic queue behavior.",
                "Remain bounded to the declared execution lane.",
                "Do not mutate outside the capability scope when mutation is enabled.",
            ],
            "requested_artifacts": list(_DEFAULT_REQUESTED_ARTIFACTS),
        }

    def _build_queue_entry(
        self,
        *,
        task_id: str,
        request: ConversationalRequest,
        title: str,
        task_type: str,
        target_repo: str,
        runtime_task_payload_path: Path,
        request_path: Path,
        task_graph_path: Path,
        plan_id: str,
        plan_step_index: int,
        plan_total_steps: int,
        plan_step_title: str,
        dependencies: List[str],
        priority: int,
        routing: IntakeRouting,
        status: str,
    ) -> Dict[str, Any]:
        return {
            "id": task_id,
            "task_id": task_id,
            "title": title,
            "task_type": task_type,
            "status": status,
            "priority": priority,
            "target_repo": target_repo,
            "agent_type": "level_0001_grass_mutation_agent" if routing.mutation_capable else "read_only_inspector_agent",
            "agents": [
                "level_0001_grass_mutation_agent" if routing.mutation_capable else "read_only_inspector_agent",
                "validator_agent",
                "artifact_summarizer_agent",
            ],
            "contract_path": self._relative(runtime_task_payload_path),
            "request_payload_path": self._relative(request_path),
            "task_graph_path": self._relative(task_graph_path),
            "request_id": request.request_id,
            "request_fingerprint": self._prompt_fingerprint(request.operator_prompt, target_repo, task_type),
            "execution_mode": routing.execution_lane if routing.mutation_capable else "bounded_read_only",
            "requested_intent": routing.requested_intent,
            "resolved_intent": routing.resolved_intent,
            "requested_execution_lane": routing.requested_execution_lane,
            "execution_lane": routing.execution_lane,
            "downgraded": routing.downgraded,
            "downgrade_reason": routing.downgrade_reason,
            "approval_required": routing.approval_required,
            "mutation_capable": routing.mutation_capable,
            "capability_id": routing.capability_id,
            "capability_title": routing.capability_title,
            "handler_name": routing.handler_name,
            "trust_score": routing.trust_score,
            "trust_band": routing.trust_band,
            "policy_state": routing.policy_state,
            "execution_decision": routing.execution_decision,
            "recommended_action": routing.recommended_action,
            "sandbox_first_required": routing.sandbox_first_required,
            "auto_execution_enabled": routing.auto_execution_enabled,
            "auto_execution_reason": routing.auto_execution_reason,
            "missing_evidence": list(routing.missing_evidence or []),
            "intelligence_summary": routing.intelligence_summary,
            "maturity_stage": routing.maturity_stage or routing.evidence_state,
            "evidence_state": routing.evidence_state,
            "eligible_for_auto": routing.eligible_for_auto,
            "times_attempted": routing.times_attempted,
            "times_passed": routing.times_passed,
            "last_validation_result": routing.last_validation_result,
            "last_rollback_result": routing.last_rollback_result,
            "sandbox_verified": routing.sandbox_verified,
            "real_target_verified": routing.real_target_verified,
            "rollback_verified": routing.rollback_verified,
            "rating_system": routing.rating_system,
            "rating_target": routing.rating_target,
            "rating_locked": routing.rating_locked,
            "content_policy_match": routing.content_policy_match,
            "content_policy_decision": routing.content_policy_decision,
            "required_rating_upgrade": routing.required_rating_upgrade,
            "requested_content_dimensions": dict(routing.requested_content_dimensions or {}),
            "content_policy_summary": routing.content_policy_summary,
            "approval_state": "blocked" if status == "blocked" else ("awaiting_approval" if status == "needs_approval" else ("auto_approved" if routing.execution_decision == "auto_execute" else "not_required")),
            "approved_by": "system_intelligence_v1" if routing.execution_decision == "auto_execute" else None,
            "approved_at": utc_timestamp(compact=False) if routing.execution_decision == "auto_execute" else None,
            "approval_notes": routing.auto_execution_reason or "" if routing.execution_decision == "auto_execute" else "",
            "plan_id": plan_id,
            "plan_step_index": plan_step_index,
            "plan_total_steps": plan_total_steps,
            "plan_step_title": plan_step_title,
            "dependencies": list(dependencies),
            "retry_count": 0,
            "current_session_id": None,
            "last_error": "",
        }

    def _derive_request_id(self, prompt: str, target_repo: str, task_type: str) -> str:
        digest = self._prompt_fingerprint(prompt, target_repo, task_type)[:12].upper()
        return f"REQ_{digest}"

    def _derive_task_id_prefix(self, request_id: str, tasks: List[Dict[str, Any]], *, multi_step: bool) -> str:
        base = f"INTAKE_{request_id.split('_', 1)[1]}"
        existing_ids = {
            str(task.get("task_id") or task.get("id") or "")
            for task in tasks
        }
        if not multi_step and base not in existing_ids:
            return base
        prefix_matches = {task_id for task_id in existing_ids if task_id == base or task_id.startswith(base + "__")}
        if not prefix_matches:
            return base
        index = 1
        while True:
            candidate = f"{base}__RERUN_{index:02d}"
            if not any(task_id == candidate or task_id.startswith(candidate + "__") for task_id in existing_ids):
                return candidate
            index += 1

    def _derive_title(self, prompt: str) -> str:
        text = re.sub(r"\s+", " ", prompt).strip()
        if len(text) <= 88:
            return text[0].upper() + text[1:]
        return text[:85].rstrip() + "..."

    def _derive_target_repo(self, prompt: str) -> str:
        lower = prompt.lower()
        babylon_markers = ("level_0001", "babylon", "zombie", "kbm", "weapon", "unity")
        if any(token in lower for token in babylon_markers):
            return "E:/AI projects 2025/BABYLON VER 2"
        return str(self.config.root_dir).replace("\\", "/")

    def _derive_task_type(self, prompt: str, *, routing: IntakeRouting | None = None) -> str:
        if routing is not None and routing.mutation_capable:
            return "mutation_request"
        lower = prompt.lower()
        if any(token in lower for token in ("stabilize", "fix", "restore", "repair")):
            return "stabilization_request"
        if any(token in lower for token in ("inspect", "audit", "review", "report")):
            return "read_only_inspection_request"
        if any(token in lower for token in ("expand", "improve", "make", "enable")):
            return "bounded_activation_request"
        return "general_request"

    def _resolve_intake_routing(self, prompt: str) -> IntakeRouting:
        normalized = self._normalize_prompt(prompt).lower()
        requested_intent = self._classify_requested_intent(normalized)
        requested_execution_lane = self._requested_lane_for_intent(requested_intent)
        capability = self.capability_registry.match(normalized)
        if capability is not None:
            return self._apply_content_policy(prompt=normalized, routing=self._routing_for_capability(capability), capability=capability)
        if requested_intent == "mutate":
            intelligence = assess_mutation_without_capability()
            return self._apply_content_policy(prompt=normalized, routing=IntakeRouting(
                requested_intent="mutate",
                resolved_intent="inspect",
                requested_execution_lane=requested_execution_lane,
                execution_lane="read_only_inspection",
                downgraded=True,
                downgrade_reason="No write-capable mutation handler is available in the current runtime; routing to bounded read-only inspection.",
                approval_required=False,
                mutation_capable=False,
                trust_score=intelligence.trust_score,
                trust_band=intelligence.trust_band,
                policy_state=intelligence.policy_state,
                execution_decision=intelligence.execution_decision,
                recommended_action=intelligence.recommended_action,
                sandbox_first_required=intelligence.sandbox_first_required,
                auto_execution_enabled=intelligence.auto_execution_enabled,
                auto_execution_reason=intelligence.auto_execution_reason,
                missing_evidence=list(intelligence.missing_evidence),
                intelligence_summary=intelligence.summary,
            ))
        if requested_intent == "plan":
            return self._apply_content_policy(prompt=normalized, routing=IntakeRouting(
                requested_intent="plan",
                resolved_intent="inspect",
                requested_execution_lane=requested_execution_lane,
                execution_lane="read_only_inspection",
                downgraded=True,
                downgrade_reason="No dedicated plan-only execution lane is available in the current runtime; routing to bounded read-only inspection.",
                approval_required=False,
                mutation_capable=False,
            ))
        if requested_intent == "inspect":
            return self._apply_content_policy(prompt=normalized, routing=IntakeRouting(
                requested_intent="inspect",
                resolved_intent="inspect",
                requested_execution_lane="read_only_inspection",
                execution_lane="read_only_inspection",
                downgraded=False,
                downgrade_reason=None,
                approval_required=False,
                mutation_capable=False,
            ))
        return self._apply_content_policy(prompt=normalized, routing=IntakeRouting(
            requested_intent="ambiguous",
            resolved_intent="inspect",
            requested_execution_lane="read_only_inspection",
            execution_lane="read_only_inspection",
            downgraded=False,
            downgrade_reason=None,
            approval_required=False,
            mutation_capable=False,
        ))

    def _routing_for_capability(self, capability: RuntimeCapability) -> IntakeRouting:
        intelligence = assess_capability_intelligence(capability)
        effective_approval_required = capability.approval_required
        effective_eligible_for_auto = capability.eligible_for_auto
        if intelligence.execution_decision == "auto_execute":
            effective_approval_required = False
            effective_eligible_for_auto = True
        return IntakeRouting(
            requested_intent="mutate",
            resolved_intent="mutate",
            requested_execution_lane=capability.requested_execution_lane,
            execution_lane=capability.requested_execution_lane,
            downgraded=False,
            downgrade_reason=None,
            approval_required=effective_approval_required,
            mutation_capable=True,
            capability_id=capability.capability_id,
            capability_title=capability.title,
            handler_name=capability.handler_name,
            target_level=capability.target_level,
            target_scene=capability.target_scene,
            trust_score=intelligence.trust_score,
            trust_band=intelligence.trust_band,
            policy_state=intelligence.policy_state,
            execution_decision=intelligence.execution_decision,
            recommended_action=intelligence.recommended_action,
            sandbox_first_required=intelligence.sandbox_first_required,
            auto_execution_enabled=intelligence.auto_execution_enabled,
            auto_execution_reason=intelligence.auto_execution_reason,
            missing_evidence=list(intelligence.missing_evidence),
            intelligence_summary=intelligence.summary,
            maturity_stage=capability.evidence_state,
            evidence_state=capability.evidence_state,
            eligible_for_auto=effective_eligible_for_auto,
            times_attempted=capability.times_attempted,
            times_passed=capability.times_passed,
            last_validation_result=capability.last_validation_result,
            last_rollback_result=capability.last_rollback_result,
            sandbox_verified=capability.sandbox_verified,
            real_target_verified=capability.real_target_verified,
            rollback_verified=capability.rollback_verified,
        )

    def _apply_content_policy(
        self,
        *,
        prompt: str,
        routing: IntakeRouting,
        capability: RuntimeCapability | None = None,
    ) -> IntakeRouting:
        profile = load_project_content_profile(self.config)
        assessment = evaluate_content_policy(
            prompt,
            profile=profile,
            capability_tags=capability.content_tags if capability is not None else None,
        )

        execution_decision = routing.execution_decision
        recommended_action = routing.recommended_action
        approval_required = routing.approval_required
        auto_execution_enabled = routing.auto_execution_enabled
        auto_execution_reason = routing.auto_execution_reason

        if routing.requested_intent == "mutate" or routing.mutation_capable:
            if assessment.content_policy_decision == "requires_review":
                execution_decision = "approval_required"
                recommended_action = "requires_review"
                approval_required = True
                auto_execution_enabled = False
                auto_execution_reason = None
            elif assessment.content_policy_decision == "blocked":
                execution_decision = "blocked"
                recommended_action = "blocked"
                approval_required = False
                auto_execution_enabled = False
                auto_execution_reason = None

        return replace(
            routing,
            approval_required=approval_required,
            execution_decision=execution_decision,
            recommended_action=recommended_action,
            auto_execution_enabled=auto_execution_enabled,
            auto_execution_reason=auto_execution_reason,
            rating_system=assessment.rating_system,
            rating_target=assessment.rating_target,
            rating_locked=assessment.rating_locked,
            content_policy_match=assessment.content_policy_match,
            content_policy_decision=assessment.content_policy_decision,
            required_rating_upgrade=assessment.required_rating_upgrade,
            requested_content_dimensions=dict(assessment.requested_content_dimensions),
            content_policy_summary=assessment.summary,
        )

    def _classify_requested_intent(self, normalized_prompt: str) -> str:
        if any(self._contains_phrase(normalized_prompt, phrase) for phrase in self._PLAN_REQUEST_VERBS):
            return "plan"
        if any(self._contains_phrase(normalized_prompt, phrase) for phrase in self._MUTATION_REQUEST_VERBS):
            return "mutate"
        if any(self._contains_phrase(normalized_prompt, phrase) for phrase in ("inspect", "audit", "review", "report", "investigate", "analyze", "validate", "check")):
            return "inspect"
        return "ambiguous"

    def _requested_lane_for_intent(self, requested_intent: str) -> str:
        if requested_intent == "mutate":
            return "approval_required_mutation"
        if requested_intent == "plan":
            return "plan_only"
        if requested_intent == "inspect":
            return "read_only_inspection"
        return "unsupported_intent"

    def _contains_phrase(self, normalized_prompt: str, phrase: str) -> bool:
        if " " in phrase:
            return phrase in normalized_prompt
        return re.search(rf"\b{re.escape(phrase)}\b", normalized_prompt) is not None

    def _derive_priority(self, task_type: str, prompt: str) -> int:
        lower = prompt.lower()
        if "urgent" in lower or "critical" in lower:
            return 10
        if task_type == "stabilization_request":
            return 25
        if task_type == "read_only_inspection_request":
            return 40
        return 50

    def _find_existing_task(self, tasks: List[Dict[str, Any]], task_id: str) -> Dict[str, Any] | None:
        for task in tasks:
            if str(task.get("task_id") or task.get("id") or "") == task_id:
                return task
        return None

    def _normalize_prompt(self, operator_message: str) -> str:
        return re.sub(r"\s+", " ", str(operator_message or "")).strip()

    def _resolve_simulated_delay_seconds(self, simulated_delay_seconds: float | None) -> float:
        if simulated_delay_seconds is not None:
            return max(0.0, float(simulated_delay_seconds))
        raw = os.getenv("AI_E_TASK_INTAKE_SIMULATED_DELAY_SECONDS", "0")
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return 0.0

    def _prompt_fingerprint(self, prompt: str, target_repo: str, task_type: str) -> str:
        key = "|".join([prompt.strip().lower(), target_repo.strip().lower(), task_type.strip().lower()])
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self.config.root_dir)).replace("\\", "/")

    def _register_plan_state(
        self,
        *,
        session_id: str,
        plan_id: str,
        plan_summary: str,
        plan_steps: List[str],
    ) -> None:
        state_store = StateStore(self.config.runs_dir, session_id)
        if not state_store.state_path.exists():
            return
        state = state_store.load()
        state_store.register_generated_plan(
            state,
            plan_id=plan_id,
            plan_summary=plan_summary,
            plan_steps=plan_steps,
        )


__all__ = ["ConversationalTaskIntake", "IntakeArtifacts", "IntakeResult", "IntakeRouting"]