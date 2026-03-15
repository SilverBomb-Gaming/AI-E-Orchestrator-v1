import json
from pathlib import Path

import pytest

from orchestrator.artifact_persistence_interface import ArtifactPersistenceRegistration, ArtifactPersistenceResult


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_artifact_persistence_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "artifact_registry_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["artifact_registration"]["artifact_source"] == "dry_run_execution_loop"
    assert payload["persistence_result"]["stored"] is False
    assert payload["persistence_result"]["validation_attached"] is True


def test_artifact_registration_contract_is_deterministic():
    contract = ArtifactPersistenceRegistration(
        artifact_id="ART_001",
        artifact_type="structured_report",
        artifact_source="dry_run_execution_loop",
        produced_by_task="REQ_001_GRAPH",
        produced_by_adapter="adapter.testing.future",
        artifact_path="runs/test/task_graph.json",
        artifact_timestamp="2026-03-15T00:00:00Z",
    )

    payload = contract.to_payload()
    assert payload["artifact_id"] == "ART_001"
    assert payload["produced_by_adapter"] == "adapter.testing.future"


def test_artifact_persistence_result_is_deterministic():
    result = ArtifactPersistenceResult(
        artifact_id="ART_001",
        stored=False,
        storage_location="contract_only",
        validation_attached=True,
        retention_policy="architecture_scaffold_only",
    )

    payload = result.to_payload()
    assert payload["stored"] is False
    assert payload["validation_attached"] is True
    assert payload["retention_policy"] == "architecture_scaffold_only"