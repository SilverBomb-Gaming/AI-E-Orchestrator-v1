import json
from pathlib import Path

import pytest

from orchestrator.execution_artifact_interface import (
    ArtifactRetentionRecordContract,
    ExecutionArtifactRecordContract,
    artifact_classes,
)


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_execution_artifact_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "execution_artifact_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["execution_artifact_record"]["retention_class"] == "retained_output"
    assert payload["artifact_retention_record"]["retained"] is True
    assert payload["artifact_retention_record"]["cleanup_required"] is False


def test_execution_artifact_record_and_retention_are_deterministic():
    artifact = ExecutionArtifactRecordContract(
        artifact_id="ART_001",
        session_id="SESSION_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        artifact_type="operator_report",
        artifact_source="execution_closeout_dry_run",
        artifact_path="runs/test/operator_report.md",
        produced_by_adapter="adapter.testing.future",
        produced_timestamp="2026-03-15T00:00:00Z",
        retention_class="retained_output",
        cleanup_required=False,
        summary="Deterministic closeout report.",
    )
    retention = ArtifactRetentionRecordContract(
        artifact_id="ART_001",
        retained=True,
        retention_reason="Needed for closeout review.",
        retention_policy="closeout_record_retention",
        expires_at="2026-03-22T00:00:00Z",
        cleanup_required=False,
        cleanup_reason="",
    )

    assert artifact.to_payload()["retention_class"] == "retained_output"
    assert retention.to_payload()["retained"] is True
    assert "retained_output" in artifact_classes()
