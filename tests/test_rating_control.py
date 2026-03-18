import json

import pytest

from ai_e_runtime.content_policy import load_profile
from ai_e_runtime.control_commands import ControlCommandHandler
from ai_e_runtime.conversation_router import ConversationRouter
from ai_e_runtime.runtime_state import RuntimeState
from ai_e_runtime.supervisor import Supervisor, SupervisorConfig
from ai_e_runtime.task_intake import ConversationalTaskIntake
from orchestrator.config import OrchestratorConfig


pytestmark = pytest.mark.fast


def test_rating_control_switches_profile_from_m_to_t(tmp_path):
    config = _make_config(tmp_path / "rating_switch")
    _write_content_profile(config, rating_system="ESRB", rating_target="M", rating_locked=True)
    handler = _make_handler(config, session_id="rating-switch-session")

    result = handler.execute("set_rating_profile T")
    profile = load_profile(config)

    assert result.title == "AI-E RATING PROFILE UPDATED"
    assert "Rating profile updated: ESRB -> T (locked: true)" in result.body
    assert "Rating System: ESRB" in result.body
    assert "Rating Target: T" in result.body
    assert profile.rating_system == "ESRB"
    assert profile.rating_target == "T"
    assert profile.rating_locked is True


def test_rating_control_rejects_invalid_rating_value(tmp_path):
    config = _make_config(tmp_path / "rating_invalid")
    _write_content_profile(config, rating_system="ESRB", rating_target="M", rating_locked=True)
    handler = _make_handler(config, session_id="rating-invalid-session")

    result = handler.execute("set_rating_profile INVALID")
    profile = load_profile(config)

    assert result.title == "AI-E RATING PROFILE ERROR"
    assert "not valid for ESRB" in result.body
    assert profile.rating_target == "M"


def test_rating_control_lock_toggle_changes_content_policy_enforcement(tmp_path):
    config = _make_config(tmp_path / "rating_lock")
    _write_content_profile(config, rating_system="ESRB", rating_target="T", rating_locked=True)
    _write_finisher_capability_contract(config)
    handler = _make_handler(config, session_id="rating-lock-session")
    intake = ConversationalTaskIntake(config)

    locked_result = intake.accept_message(
        "add finisher system for level_0001",
        session_id="rating-lock-session",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
    )
    unlock_result = handler.execute("set_rating_lock false")
    unlocked_result = intake.accept_message(
        "add finisher system for level_0001",
        session_id="rating-lock-session",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
    )

    assert locked_result.queue_entry["status"] == "blocked"
    assert locked_result.routing.content_policy_decision == "blocked"
    assert unlock_result.title == "AI-E RATING LOCK UPDATED"
    assert "locked: false" in unlock_result.body
    assert unlocked_result.queue_entry["status"] == "needs_approval"
    assert unlocked_result.routing.content_policy_decision == "requires_review"
    assert unlocked_result.routing.required_rating_upgrade == "M"


def test_rating_control_updates_runtime_and_new_tasks_immediately(tmp_path):
    config = _make_config(tmp_path / "rating_propagation")
    _write_content_profile(config, rating_system="ESRB", rating_target="M", rating_locked=True)
    handler = _make_handler(config, session_id="rating-propagation-session")
    runtime_state = RuntimeState(config, "rating-propagation-session")
    intake = ConversationalTaskIntake(config)
    router = ConversationRouter(runtime_state)

    command_result = handler.execute("set_rating_profile E10+")
    snapshot = runtime_state.get_snapshot()
    intake_result = intake.accept_message(
        "make grass for level_0001",
        session_id="rating-propagation-session",
        target_repo="E:/AI projects 2025/BABYLON VER 2",
    )
    get_result = handler.execute("get_rating_profile")

    assert command_result.title == "AI-E RATING PROFILE UPDATED"
    assert snapshot.rating_system == "ESRB"
    assert snapshot.rating_target == "E10+"
    assert snapshot.rating_locked is True
    assert intake_result.routing.rating_target == "E10+"
    assert intake_result.routing.rating_system == "ESRB"
    assert get_result.title == "AI-E RATING PROFILE"
    assert "Rating Target: E10+" in get_result.body
    assert router.classify_prompt("set_rating_profile T") == "CONTROL_COMMAND"
    assert router.classify_prompt("get_rating_profile") == "CONTROL_COMMAND"


def _make_handler(config: OrchestratorConfig, *, session_id: str) -> ControlCommandHandler:
    supervisor = Supervisor(
        config,
        SupervisorConfig(
            session_limit_seconds=5,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=1,
            session_id=session_id,
            stop_when_queue_empty=True,
        ),
    )
    return ControlCommandHandler(supervisor, RuntimeState(config, session_id))


def _write_content_profile(config: OrchestratorConfig, *, rating_system: str, rating_target: str, rating_locked: bool) -> None:
    content_policy_dir = config.contracts_dir / "content_policy"
    content_policy_dir.mkdir(parents=True, exist_ok=True)
    (content_policy_dir / "project_content_profile.json").write_text(
        json.dumps(
            {
                "content_mode": "GAME_DEV",
                "rating_system": rating_system,
                "rating_target": rating_target,
                "rating_locked": rating_locked,
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

    for path in [runs_dir, workspaces_dir, queue_contracts_dir, templates_dir, approvals_path.parent, agent_registry_path.parent, root_dir / "logs"]:
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