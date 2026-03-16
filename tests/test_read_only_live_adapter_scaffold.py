import json
from pathlib import Path

import pytest

from orchestrator.read_only_live_adapter_interface import ReadOnlyAdapterRequestContract, ReadScopeContract, read_only_response_states
from read_only_live_adapter_dry_run import default_read_scope, execute_bounded_read_only_inspection, run_read_only_live_adapter_dry_run


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_read_only_live_adapter_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "read_only_live_adapter_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["read_only_request"]["adapter_id"] == "local_read_only_adapter"
    assert payload["read_only_request"]["read_scope"]["max_file_count"] == 2
    assert payload["read_only_response"]["response_state"] == "read_completed"
    assert payload["response_states"] == [
        "read_requested",
        "read_completed",
        "read_blocked",
        "read_denied",
        "read_failed",
        "read_partial",
    ]


def test_read_only_scope_is_explicit_and_bounded():
    scope = default_read_scope()
    assert isinstance(scope, ReadScopeContract)
    assert scope.allowed_extensions == [".py"]
    assert scope.max_file_count == 2
    assert scope.max_total_bytes == 16384
    assert scope.recursive_allowed is False
    assert scope.hidden_files_allowed is False
    assert read_only_response_states()[-1] == "read_partial"


def test_read_only_execution_path_produces_deterministic_outputs(tmp_path):
    artifacts = run_read_only_live_adapter_dry_run(tmp_path / "aie_read_only_adapter_test")

    request_payload = json.loads(artifacts.read_only_request_path.read_text(encoding="utf-8"))
    response_payload = json.loads(artifacts.read_only_response_path.read_text(encoding="utf-8"))
    artifact_registry = json.loads(artifacts.read_only_artifact_registry_path.read_text(encoding="utf-8"))
    operator_report = artifacts.operator_report_path.read_text(encoding="utf-8")

    assert request_payload["read_only_request"]["adapter_id"] == "local_read_only_adapter"
    assert response_payload["read_only_response"]["response_state"] == "read_completed"
    assert len(response_payload["read_only_response"]["inspected_paths"]) == 2
    assert response_payload["read_only_response"]["inspected_paths"][1] == "orchestrator/utils.py"
    assert len(artifact_registry["read_only_artifacts"]) == 2
    assert all(artifact["artifact_type"] == "inspection_report" for artifact in artifact_registry["read_only_artifacts"])
    assert "first bounded real-world capability" in operator_report
    assert "No write-capable live execution, no Unity invocation" in operator_report
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in operator_report


def test_read_only_execution_blocks_if_scope_is_exceeded():
    scope = default_read_scope()
    request = ReadOnlyAdapterRequestContract(
        adapter_request_id="READ_ONLY_REQ_BLOCKED",
        session_id="SESSION_TASK_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        target_paths=[
            str((ROOT / "orchestrator" / "report_contract.py").resolve()),
            str((ROOT / "orchestrator" / "utils.py").resolve()),
            str((ROOT / "orchestrator" / "policy.py").resolve()),
        ],
        read_scope=scope,
        dry_run=False,
        requested_at="2026-03-16T00:00:00Z",
    )

    response, artifacts = execute_bounded_read_only_inspection(request)

    assert response.response_state == "read_blocked"
    assert response.read_completed is False
    assert not artifacts


def test_read_only_execution_denies_disallowed_root():
    request = ReadOnlyAdapterRequestContract(
        adapter_request_id="READ_ONLY_REQ_DENIED_ROOT",
        session_id="SESSION_TASK_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        target_paths=[str((ROOT / "contracts" / "templates" / "post_dispatch_audit_template.json").resolve())],
        read_scope=ReadScopeContract(
            allowed_roots=[str((ROOT / "orchestrator").resolve())],
            allowed_extensions=[".json"],
            max_file_count=1,
            max_total_bytes=16384,
            recursive_allowed=False,
            hidden_files_allowed=False,
        ),
        dry_run=False,
        requested_at="2026-03-16T00:00:00Z",
    )

    response, artifacts = execute_bounded_read_only_inspection(request)

    assert response.response_state == "read_denied"
    assert response.errors
    assert not artifacts


def test_read_only_execution_denies_disallowed_extension():
    request = ReadOnlyAdapterRequestContract(
        adapter_request_id="READ_ONLY_REQ_DENIED_EXT",
        session_id="SESSION_TASK_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        target_paths=[str((ROOT / "README.md").resolve())],
        read_scope=ReadScopeContract(
            allowed_roots=[str(ROOT.resolve())],
            allowed_extensions=[".py"],
            max_file_count=1,
            max_total_bytes=16384,
            recursive_allowed=False,
            hidden_files_allowed=False,
        ),
        dry_run=False,
        requested_at="2026-03-16T00:00:00Z",
    )

    response, artifacts = execute_bounded_read_only_inspection(request)

    assert response.response_state == "read_denied"
    assert response.errors
    assert not artifacts


def test_read_only_execution_blocks_max_total_bytes():
    request = ReadOnlyAdapterRequestContract(
        adapter_request_id="READ_ONLY_REQ_BLOCKED_BYTES",
        session_id="SESSION_TASK_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        target_paths=[str((ROOT / "orchestrator" / "report_contract.py").resolve())],
        read_scope=ReadScopeContract(
            allowed_roots=[str((ROOT / "orchestrator").resolve())],
            allowed_extensions=[".py"],
            max_file_count=1,
            max_total_bytes=10,
            recursive_allowed=False,
            hidden_files_allowed=False,
        ),
        dry_run=False,
        requested_at="2026-03-16T00:00:00Z",
    )

    response, artifacts = execute_bounded_read_only_inspection(request)

    assert response.response_state == "read_blocked"
    assert response.errors
    assert not artifacts


def test_read_only_execution_denies_directory_traversal_when_recursive_false():
    request = ReadOnlyAdapterRequestContract(
        adapter_request_id="READ_ONLY_REQ_DENIED_DIR",
        session_id="SESSION_TASK_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        target_paths=[str((ROOT / "orchestrator").resolve())],
        read_scope=ReadScopeContract(
            allowed_roots=[str((ROOT / "orchestrator").resolve())],
            allowed_extensions=[".py"],
            max_file_count=1,
            max_total_bytes=16384,
            recursive_allowed=False,
            hidden_files_allowed=False,
        ),
        dry_run=False,
        requested_at="2026-03-16T00:00:00Z",
    )

    response, artifacts = execute_bounded_read_only_inspection(request)

    assert response.response_state == "read_denied"
    assert response.errors
    assert not artifacts


def test_read_only_execution_denies_hidden_file_when_hidden_false():
    hidden_target = ROOT / ".status_entity_run_output.json"
    request = ReadOnlyAdapterRequestContract(
        adapter_request_id="READ_ONLY_REQ_DENIED_HIDDEN",
        session_id="SESSION_TASK_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        target_paths=[str(hidden_target.resolve())],
        read_scope=ReadScopeContract(
            allowed_roots=[str(ROOT.resolve())],
            allowed_extensions=[".json"],
            max_file_count=1,
            max_total_bytes=16384,
            recursive_allowed=False,
            hidden_files_allowed=False,
        ),
        dry_run=False,
        requested_at="2026-03-16T00:00:00Z",
    )

    response, artifacts = execute_bounded_read_only_inspection(request)

    assert response.response_state == "read_denied"
    assert response.errors
    assert not artifacts