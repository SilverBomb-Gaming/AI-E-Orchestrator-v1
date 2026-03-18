import json

import pytest

from ai_e_runtime.task_intake import ConversationalTaskIntake
from orchestrator.config import OrchestratorConfig


pytestmark = pytest.mark.fast


def test_task_intake_creates_deterministic_runtime_payload_and_pending_queue_entry(tmp_path):
    config = _make_config(tmp_path / "intake")
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "expand LEVEL_0001 a bit and make the zombie move and damage the player",
        session_id="operator-session-a",
    )

    assert result.task_id == "INTAKE_3335996CEC5B"
    assert result.request_id == "REQ_3335996CEC5B"
    assert result.task_type == "bounded_activation_request"
    assert result.target_repo == "E:/AI projects 2025/BABYLON VER 2"
    assert result.queue_entry["status"] == "pending"
    assert result.queue_entry["agent_type"] == "read_only_inspector_agent"
    assert result.routing.requested_intent == "mutate"
    assert result.routing.requested_execution_lane == "approval_required_mutation"
    assert result.routing.execution_lane == "read_only_inspection"
    assert result.routing.downgraded is True
    assert result.routing.mutation_capable is False

    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]
    assert len(queue) == 1
    assert queue[0]["task_id"] == result.task_id
    assert queue[0]["contract_path"] == "contracts/intake/runtime_tasks/INTAKE_3335996CEC5B.json"
    assert queue[0]["requested_intent"] == "mutate"
    assert queue[0]["execution_lane"] == "read_only_inspection"
    assert queue[0]["downgraded"] is True

    request_payload = json.loads(result.artifacts.request_payload_path.read_text(encoding="utf-8"))
    task_graph = json.loads(result.artifacts.task_graph_path.read_text(encoding="utf-8"))
    runtime_payload = json.loads(result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))

    assert request_payload["conversational_request"]["operator_prompt"] == "expand LEVEL_0001 a bit and make the zombie move and damage the player"
    assert task_graph["task_graph"]["request_id"] == result.request_id
    assert task_graph["task_graph"]["nodes"][0]["task_id"] == result.task_id
    assert runtime_payload["runtime_task"]["task_id"] == result.task_id
    assert runtime_payload["runtime_task"]["execution_mode"] == "bounded_read_only"
    assert request_payload["conversational_request"]["context"]["routing"]["requested_execution_lane"] == "approval_required_mutation"
    assert runtime_payload["runtime_task"]["execution_lane"] == "read_only_inspection"
    assert runtime_payload["runtime_task"]["downgraded"] is True


def test_task_intake_supports_real_stabilization_request(tmp_path):
    config = _make_config(tmp_path / "real_request")
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "Stabilize LEVEL_0001 zombie animation.",
        session_id="operator-session-b",
    )

    assert result.queue_entry["status"] == "pending"
    assert result.queue_entry["task_type"] == "stabilization_request"
    assert result.queue_entry["target_repo"] == "E:/AI projects 2025/BABYLON VER 2"
    assert result.queue_entry["contract_path"].startswith("contracts/intake/runtime_tasks/")
    assert result.routing.requested_intent == "mutate"
    assert result.routing.execution_lane == "read_only_inspection"
    assert result.routing.downgraded is True


def test_task_intake_expands_composite_request_into_multiple_queue_tasks(tmp_path):
    config = _make_config(tmp_path / "composite_request")
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "Fix LEVEL_0001 zombie animation, weapon bootstrap, and KBM controls",
        session_id="operator-session-c",
    )

    queue = json.loads(config.queue_path.read_text(encoding="utf-8"))["tasks"]

    assert result.is_multi_step is True
    assert result.plan_id == f"PLAN_{result.request_id.split('_', 1)[1]}"
    assert result.plan_step_titles == [
        "Inspect zombie animation pipeline",
        "Inspect weapon bootstrap",
        "Inspect KBM controls",
        "Validate integrated result",
        "Generate summary artifact",
    ]
    assert len(queue) == 5
    assert queue[0]["dependencies"] == []
    assert queue[1]["dependencies"] == [queue[0]["task_id"]]
    assert queue[4]["dependencies"] == [queue[3]["task_id"]]
    assert all(task["plan_id"] == result.plan_id for task in queue)


def test_task_intake_routes_freeform_grass_request_into_approval_required_mutation_lane(tmp_path):
    config = _make_config(tmp_path / "freeform_mutation_request")
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "make grass for level_0001",
        session_id="operator-session-d",
    )

    runtime_payload = json.loads(result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))

    assert result.routing.requested_intent == "mutate"
    assert result.routing.resolved_intent == "mutate"
    assert result.routing.requested_execution_lane == "approval_required_mutation"
    assert result.routing.execution_lane == "approval_required_mutation"
    assert result.routing.downgraded is False
    assert result.routing.downgrade_reason is None
    assert result.routing.approval_required is True
    assert result.routing.mutation_capable is True
    assert result.routing.capability_id == "level_0001_add_grass"
    assert runtime_payload["runtime_task"]["requested_execution_lane"] == "approval_required_mutation"
    assert runtime_payload["runtime_task"]["execution_lane"] == "approval_required_mutation"
    assert runtime_payload["runtime_task"]["approval_state"] == "awaiting_approval"


def test_task_intake_routes_supported_grass_mutation_into_approval_required_lane(tmp_path):
    config = _make_config(tmp_path / "supported_grass_mutation")
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "make grass for level_0001",
        session_id="operator-session-e",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
    )

    runtime_payload = json.loads(result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))

    assert result.task_type == "mutation_request"
    assert result.queue_entry["status"] == "needs_approval"
    assert result.queue_entry["agent_type"] == "level_0001_grass_mutation_agent"
    assert result.routing.requested_intent == "mutate"
    assert result.routing.resolved_intent == "mutate"
    assert result.routing.requested_execution_lane == "approval_required_mutation"
    assert result.routing.execution_lane == "approval_required_mutation"
    assert result.routing.downgraded is False
    assert result.routing.approval_required is True
    assert result.routing.mutation_capable is True
    assert result.routing.capability_id == "level_0001_add_grass"
    assert result.routing.evidence_state == "experimental"
    assert result.routing.trust_score == 0
    assert result.routing.policy_state == "test_only"
    assert result.routing.execution_decision == "sandbox_first"
    assert result.routing.recommended_action == "sandbox_first"
    assert result.routing.sandbox_first_required is True
    assert result.routing.rating_system == "ESRB"
    assert result.routing.rating_target == "M"
    assert result.routing.content_policy_match == "fits_rating"
    assert result.routing.content_policy_decision == "allowed"
    assert result.routing.required_rating_upgrade is None
    assert runtime_payload["runtime_task"]["approval_state"] == "awaiting_approval"
    assert runtime_payload["runtime_task"]["target_scene"] == "Assets/AI_E_TestScenes/MinimalPlayableArena.unity"


def test_task_intake_routes_supported_remove_grass_mutation_into_approval_required_lane(tmp_path):
    config = _make_config(tmp_path / "supported_remove_grass_mutation")
    _write_grass_capability_contracts(config)
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "remove grass for level_0001",
        session_id="operator-session-f",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
    )

    runtime_payload = json.loads(result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))

    assert result.task_type == "mutation_request"
    assert result.queue_entry["status"] == "needs_approval"
    assert result.queue_entry["agent_type"] == "level_0001_grass_mutation_agent"
    assert result.routing.requested_intent == "mutate"
    assert result.routing.resolved_intent == "mutate"
    assert result.routing.requested_execution_lane == "approval_required_mutation"
    assert result.routing.execution_lane == "approval_required_mutation"
    assert result.routing.downgraded is False
    assert result.routing.approval_required is True
    assert result.routing.mutation_capable is True
    assert result.routing.capability_id == "level_0001_remove_grass"
    assert result.routing.handler_name == "level_0001_remove_grass_handler"
    assert result.routing.target_level == "LEVEL_0001"
    assert result.routing.target_scene == "Assets/AI_E_TestScenes/MinimalPlayableArena.unity"
    assert result.routing.trust_score == 0
    assert result.routing.policy_state == "test_only"
    assert result.routing.execution_decision == "sandbox_first"
    assert result.routing.recommended_action == "sandbox_first"
    assert result.routing.sandbox_first_required is True
    assert result.routing.rating_system == "ESRB"
    assert result.routing.rating_target == "M"
    assert result.routing.content_policy_match == "fits_rating"
    assert result.routing.content_policy_decision == "allowed"
    assert runtime_payload["runtime_task"]["approval_state"] == "awaiting_approval"
    assert runtime_payload["runtime_task"]["target_level"] == "LEVEL_0001"
    assert runtime_payload["runtime_task"]["target_scene"] == "Assets/AI_E_TestScenes/MinimalPlayableArena.unity"


def test_task_intake_auto_promotes_reference_grass_capability_when_reference_evidence_is_present(tmp_path):
    config = _make_config(tmp_path / "auto_promoted_grass_mutation")
    _write_grass_capability_contracts(config)
    _seed_auto_promoted_reference_capability_proof(config)
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "make grass for level_0001",
        session_id="operator-session-auto",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
    )

    runtime_payload = json.loads(result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))

    assert result.queue_entry["status"] == "pending"
    assert result.queue_entry["approval_state"] == "auto_approved"
    assert result.queue_entry["approved_by"] == "system_intelligence_v1"
    assert result.routing.execution_decision == "auto_execute"
    assert result.routing.recommended_action == "auto_execute"
    assert result.routing.auto_execution_enabled is True
    assert result.routing.approval_required is False
    assert result.routing.eligible_for_auto is True
    assert runtime_payload["runtime_task"]["approval_state"] == "auto_approved"
    assert runtime_payload["runtime_task"]["execution_decision"] == "auto_execute"
    assert runtime_payload["runtime_task"]["auto_execution_enabled"] is True


def test_task_intake_blocks_mutation_that_exceeds_locked_project_rating(tmp_path):
    config = _make_config(tmp_path / "blocked_content_policy_mutation")
    _write_locked_content_profile(config, rating_system="ESRB", rating_target="T")
    _write_finisher_capability_contract(config)
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "add finisher system for level_0001",
        session_id="operator-session-rating-block",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
    )

    runtime_payload = json.loads(result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))

    assert result.queue_entry["status"] == "blocked"
    assert result.queue_entry["approval_state"] == "blocked"
    assert result.routing.capability_id == "level_0001_finisher_system"
    assert result.routing.content_policy_match == "exceeds_rating"
    assert result.routing.content_policy_decision == "blocked"
    assert result.routing.required_rating_upgrade == "M"
    assert result.routing.execution_decision == "blocked"
    assert result.routing.recommended_action == "blocked"
    assert runtime_payload["runtime_task"]["approval_state"] == "blocked"
    assert runtime_payload["runtime_task"]["requested_content_dimensions"]["gore_level"] == "extreme"
    assert runtime_payload["runtime_task"]["requested_content_dimensions"]["dismemberment"] is True


def _write_grass_capability_contracts(config: OrchestratorConfig) -> None:
    capabilities_dir = config.contracts_dir / "capabilities"
    capabilities_dir.mkdir(parents=True, exist_ok=True)
    (capabilities_dir / "level_0001_add_grass.json").write_text(
        json.dumps(
            {
                "capability_id": "level_0001_add_grass",
                "title": "LEVEL_0001 add grass",
                "intent": "mutate",
                "target_level": "LEVEL_0001",
                "target_scene": "Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
                "requested_execution_lane": "approval_required_mutation",
                "handler_name": "level_0001_grass_handler",
                "agent_type": "level_0001_grass_mutation_agent",
                "approval_required": True,
                "eligible_for_auto": False,
                "evidence_state": "experimental",
                "safety_class": "approval_gated_automation",
                "content_tags": {
                    "violence_level": "none",
                    "blood_level": "none",
                    "gore_level": "none",
                    "dismemberment": False,
                    "horror_intensity": "none",
                    "language_level": "none",
                    "sexual_content_level": "none",
                    "nudity_level": "none",
                    "substance_reference_level": "none",
                    "gambling_reference_level": "none",
                },
                "match_terms": ["level_0001", "grass"],
                "match_verbs": ["make", "add", "create", "generate", "place", "build"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (capabilities_dir / "level_0001_remove_grass.json").write_text(
        json.dumps(
            {
                "capability_id": "level_0001_remove_grass",
                "title": "LEVEL_0001 remove grass",
                "intent": "mutate",
                "target_level": "LEVEL_0001",
                "target_scene": "Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
                "requested_execution_lane": "approval_required_mutation",
                "handler_name": "level_0001_remove_grass_handler",
                "agent_type": "level_0001_grass_mutation_agent",
                "approval_required": True,
                "eligible_for_auto": False,
                "evidence_state": "experimental",
                "safety_class": "approval_gated_automation",
                "content_tags": {
                    "violence_level": "none",
                    "blood_level": "none",
                    "gore_level": "none",
                    "dismemberment": False,
                    "horror_intensity": "none",
                    "language_level": "none",
                    "sexual_content_level": "none",
                    "nudity_level": "none",
                    "substance_reference_level": "none",
                    "gambling_reference_level": "none",
                },
                "match_terms": ["level_0001", "grass"],
                "match_verbs": ["remove", "delete", "clear"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_locked_content_profile(config: OrchestratorConfig, *, rating_system: str, rating_target: str) -> None:
    content_policy_dir = config.contracts_dir / "content_policy"
    content_policy_dir.mkdir(parents=True, exist_ok=True)
    (content_policy_dir / "project_content_profile.json").write_text(
        json.dumps(
            {
                "content_mode": "GAME_DEV",
                "rating_system": rating_system,
                "rating_target": rating_target,
                "rating_locked": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_finisher_capability_contract(config: OrchestratorConfig) -> None:
    capabilities_dir = config.contracts_dir / "capabilities"
    capabilities_dir.mkdir(parents=True, exist_ok=True)
    (capabilities_dir / "level_0001_finisher_system.json").write_text(
        json.dumps(
            {
                "capability_id": "level_0001_finisher_system",
                "title": "LEVEL_0001 finisher system",
                "intent": "mutate",
                "target_level": "LEVEL_0001",
                "target_scene": "Assets/AI_E_TestScenes/MinimalPlayableArena.unity",
                "requested_execution_lane": "approval_required_mutation",
                "handler_name": "level_0001_finisher_handler",
                "agent_type": "level_0001_grass_mutation_agent",
                "approval_required": True,
                "eligible_for_auto": False,
                "evidence_state": "experimental",
                "safety_class": "approval_gated_automation",
                "content_tags": {
                    "violence_level": "intense",
                    "blood_level": "intense",
                    "gore_level": "extreme",
                    "dismemberment": True,
                    "horror_intensity": "none",
                    "language_level": "none",
                    "sexual_content_level": "none",
                    "nudity_level": "none",
                    "substance_reference_level": "none",
                    "gambling_reference_level": "none"
                },
                "match_terms": ["level_0001", "finisher"],
                "match_verbs": ["add", "create", "build"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _seed_auto_promoted_reference_capability_proof(config: OrchestratorConfig) -> None:
    capabilities_dir = config.contracts_dir / "capabilities"
    capabilities_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = capabilities_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "capabilities": {
                    "level_0001_add_grass": {
                        "capability_id": "level_0001_add_grass",
                        "handler_name": "level_0001_grass_handler",
                        "safety_class": "approval_gated_automation",
                        "times_attempted": 4,
                        "times_passed": 4,
                        "last_validation_result": "passed",
                        "last_rollback_result": "none",
                        "artifact_requirements_met": True,
                        "eligible_for_auto": False,
                        "requires_approval": True,
                        "evidence_state": "experimental",
                        "sandbox_verified": False,
                        "real_target_verified": False,
                        "rollback_verified": False,
                        "notes": "Reference capability evidence seeded for auto-promotion derivation.",
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    run_dir = config.runs_dir / "live_real_grass_validation_20260317"
    post_dir = run_dir / "post_mutation"
    rollback_dir = run_dir / "rollback"
    post_dir.mkdir(parents=True, exist_ok=True)
    rollback_dir.mkdir(parents=True, exist_ok=True)

    (post_dir / "real_target_validation_report.json").write_text(
        json.dumps(
            {
                "session_id": "live_real_grass_validation_20260317",
                "capability_id": "level_0001_add_grass",
                "validation_result": "passed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (rollback_dir / "rollback_validation_report.json").write_text(
        json.dumps(
            {
                "session_id": "live_real_grass_validation_20260317",
                "capability_id": "level_0001_add_grass",
                "rollback_validation_result": "passed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _make_config(tmp_path) -> OrchestratorConfig:
    root_dir = tmp_path / "repo_root"
    runs_dir = root_dir / "runs"
    workspaces_dir = root_dir / "workspaces"
    queue_path = root_dir / "backlog" / "queue.json"
    queue_contracts_dir = root_dir / "contracts" / "queue"
    agent_registry_path = root_dir / "agents" / "registry.json"
    contracts_dir = root_dir / "contracts"
    templates_dir = contracts_dir / "templates"
    approvals_path = root_dir / "backlog" / "approvals.json"
    command_allowlist_path = root_dir / "backlog" / "command_allowlist.json"

    for path in [runs_dir, workspaces_dir, queue_contracts_dir, templates_dir, approvals_path.parent, agent_registry_path.parent]:
        path.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps({"tasks": []}, indent=2), encoding="utf-8")
    approvals_path.write_text(json.dumps({"approvals": []}, indent=2), encoding="utf-8")
    command_allowlist_path.write_text(json.dumps({"exact": [], "prefix": []}, indent=2), encoding="utf-8")
    agent_registry_path.write_text(json.dumps({"agents": []}, indent=2), encoding="utf-8")

    return OrchestratorConfig(
        root_dir=root_dir,
        runs_dir=runs_dir,
        workspaces_dir=workspaces_dir,
        queue_path=queue_path,
        queue_contracts_dir=queue_contracts_dir,
        agent_registry_path=agent_registry_path,
        contracts_dir=contracts_dir,
        templates_dir=templates_dir,
        approvals_path=approvals_path,
        command_allowlist_path=command_allowlist_path,
    )