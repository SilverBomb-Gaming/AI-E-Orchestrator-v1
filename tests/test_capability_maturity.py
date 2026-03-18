import json

import pytest

from ai_e_runtime.capability_registry import CapabilityRegistry
from ai_e_runtime.task_intake import ConversationalTaskIntake
from orchestrator.config import OrchestratorConfig


pytestmark = pytest.mark.fast


def test_capability_registry_derives_reference_maturity_from_proof_artifacts(tmp_path):
    config = _make_config(tmp_path / "capability_maturity")
    _seed_reference_capability_proof(config)

    registry = CapabilityRegistry(config)
    capability = registry.match("make grass for level_0001")

    assert capability is not None
    assert capability.evidence_state == "rollback_verified"
    assert capability.sandbox_verified is True
    assert capability.real_target_verified is True
    assert capability.rollback_verified is True
    assert capability.last_validation_result == "passed"
    assert capability.last_rollback_result == "passed"

    evidence = registry.evidence_store().get("level_0001_add_grass")
    assert evidence is not None
    assert evidence["evidence_state"] == "rollback_verified"
    assert evidence["evidence_progression"] == [
        "experimental",
        "sandbox_verified",
        "real_target_verified",
        "rollback_verified",
    ]


def test_task_intake_surfaces_reference_maturity_in_payloads(tmp_path):
    config = _make_config(tmp_path / "intake_maturity")
    _seed_reference_capability_proof(config)
    intake = ConversationalTaskIntake(config)

    result = intake.accept_message(
        "make grass for level_0001",
        session_id="operator-session-maturity",
    )

    runtime_payload = json.loads(result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))

    assert result.routing.maturity_stage == "rollback_verified"
    assert result.routing.evidence_state == "rollback_verified"
    assert result.routing.sandbox_verified is True
    assert result.routing.real_target_verified is True
    assert result.routing.rollback_verified is True
    assert result.routing.last_validation_result == "passed"
    assert result.routing.last_rollback_result == "passed"
    assert result.routing.trust_score >= 80
    assert result.routing.policy_state == "proven"
    assert result.routing.execution_decision == "approval_required"
    assert result.routing.recommended_action == "approval_required"
    assert result.routing.sandbox_first_required is False
    assert runtime_payload["runtime_task"]["maturity_stage"] == "rollback_verified"
    assert runtime_payload["runtime_task"]["trust_score"] >= 80
    assert runtime_payload["runtime_task"]["policy_state"] == "proven"
    assert runtime_payload["runtime_task"]["execution_decision"] == "approval_required"
    assert runtime_payload["runtime_task"]["recommended_action"] == "approval_required"
    assert runtime_payload["runtime_task"]["sandbox_verified"] is True
    assert runtime_payload["runtime_task"]["real_target_verified"] is True
    assert runtime_payload["runtime_task"]["rollback_verified"] is True


def test_task_intake_auto_promotes_reference_maturity_when_thresholds_are_met(tmp_path):
    config = _make_config(tmp_path / "intake_maturity_autonomy")
    _seed_reference_capability_proof(config)

    evidence_path = config.contracts_dir / "capabilities" / "evidence.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["capabilities"]["level_0001_add_grass"]["times_attempted"] = 4
    payload["capabilities"]["level_0001_add_grass"]["times_passed"] = 4
    evidence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    intake = ConversationalTaskIntake(config)
    result = intake.accept_message(
        "make grass for level_0001",
        session_id="operator-session-autonomy",
    )

    runtime_payload = json.loads(result.artifacts.runtime_task_payload_path.read_text(encoding="utf-8"))

    assert result.queue_entry["status"] == "pending"
    assert result.queue_entry["approval_state"] == "auto_approved"
    assert result.routing.execution_decision == "auto_execute"
    assert result.routing.recommended_action == "auto_execute"
    assert result.routing.auto_execution_enabled is True
    assert result.routing.approval_required is False
    assert result.routing.eligible_for_auto is True
    assert runtime_payload["runtime_task"]["execution_decision"] == "auto_execute"
    assert runtime_payload["runtime_task"]["auto_execution_enabled"] is True
    assert runtime_payload["runtime_task"]["approval_state"] == "auto_approved"


def _seed_reference_capability_proof(config: OrchestratorConfig) -> None:
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
                        "times_attempted": 1,
                        "times_passed": 1,
                        "last_validation_result": "passed",
                        "last_rollback_result": "none",
                        "artifact_requirements_met": True,
                        "eligible_for_auto": False,
                        "requires_approval": True,
                        "evidence_state": "experimental",
                        "sandbox_verified": False,
                        "real_target_verified": False,
                        "rollback_verified": False,
                        "notes": "Reference capability evidence seeded for maturity derivation.",
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