from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from orchestrator.read_only_live_adapter_interface import (
    ReadOnlyAdapterRequestContract,
    ReadOnlyAdapterResponseContract,
    ReadOnlyArtifactContract,
    ReadScopeContract,
)
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.utils import safe_write_text, write_json


SIMULATION_TIMESTAMP = "2026-03-16T00:00:00Z"
REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "runs" / "aie_read_only_adapter_test"
APPROVED_TARGETS = [
    REPO_ROOT / "orchestrator" / "report_contract.py",
    REPO_ROOT / "contracts" / "templates" / "post_dispatch_audit_template.json",
]


@dataclass(frozen=True)
class ReadOnlyLiveAdapterArtifacts:
    output_dir: Path
    read_only_request_path: Path
    read_only_response_path: Path
    read_only_artifact_registry_path: Path
    operator_report_path: Path


def default_read_scope() -> ReadScopeContract:
    return ReadScopeContract(
        allowed_roots=[
            str((REPO_ROOT / "orchestrator").resolve()),
            str((REPO_ROOT / "contracts" / "templates").resolve()),
        ],
        allowed_extensions=[".py", ".json"],
        max_file_count=2,
        max_total_bytes=16384,
        recursive_allowed=False,
        hidden_files_allowed=False,
    )


def run_read_only_live_adapter_dry_run(output_dir: Path | None = None) -> ReadOnlyLiveAdapterArtifacts:
    destination = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    scope = default_read_scope()
    request = ReadOnlyAdapterRequestContract(
        adapter_request_id="READ_ONLY_REQ_001",
        session_id="SESSION_TASK_001",
        permit_id="PERMIT_001",
        authorization_id="AUTH_001",
        request_id="REQ_001",
        execution_id="EXEC_001",
        task_id="TASK_001",
        adapter_id="local_read_only_adapter",
        target_paths=[str(path.resolve()) for path in APPROVED_TARGETS],
        read_scope=scope,
        dry_run=False,
        requested_at=SIMULATION_TIMESTAMP,
    )

    response, artifacts = execute_bounded_read_only_inspection(request)

    report_text = format_operator_report(
        summary="Read-only live adapter dry-run completed as the first bounded real-world capability without any write-capable execution.",
        facts=[
            f"Adapter ID: {request.adapter_id}",
            f"Response state: {response.response_state}",
            f"Inspected paths: {len(response.inspected_paths)}",
            f"Artifacts generated: {len(artifacts)}",
            f"Read scope max bytes: {request.read_scope.max_total_bytes}",
        ],
        assumptions=[
            "The first bounded live capability remains strictly read-only and limited to explicitly approved local paths.",
            "No write-capable live execution, no Unity invocation, no Blender invocation, and no gameplay mutation occurred.",
        ],
        recommendations=[
            "Keep the first live adapter limited to deterministic inspection outputs until a later approved write-capable phase exists.",
            "Use the bounded read-only scope as the baseline for future adapter hardening and policy review.",
        ],
        timestamp=SIMULATION_TIMESTAMP,
    )
    report_validation = validate_operator_report(report_text)
    if not report_validation.is_valid:
        raise ValueError("operator report failed validation: " + "; ".join(report_validation.errors))

    read_only_request_path = destination / "read_only_request.json"
    read_only_response_path = destination / "read_only_response.json"
    read_only_artifact_registry_path = destination / "read_only_artifact_registry.json"
    operator_report_path = destination / "operator_report.md"

    write_json(read_only_request_path, {"read_only_request": request.to_payload()})
    write_json(read_only_response_path, {"read_only_response": response.to_payload()})
    write_json(
        read_only_artifact_registry_path,
        {"read_only_artifacts": [artifact.to_payload() for artifact in artifacts]},
    )
    safe_write_text(operator_report_path, report_text)

    return ReadOnlyLiveAdapterArtifacts(
        output_dir=destination,
        read_only_request_path=read_only_request_path,
        read_only_response_path=read_only_response_path,
        read_only_artifact_registry_path=read_only_artifact_registry_path,
        operator_report_path=operator_report_path,
    )


def execute_bounded_read_only_inspection(
    request: ReadOnlyAdapterRequestContract,
) -> tuple[ReadOnlyAdapterResponseContract, list[ReadOnlyArtifactContract]]:
    scope = request.read_scope
    resolved_roots = [Path(root).resolve() for root in scope.allowed_roots]
    if len(request.target_paths) > scope.max_file_count:
        return _blocked_response(request, ["Requested file count exceeds bounded read scope."], [])

    resolved_targets = [Path(path).resolve() for path in request.target_paths]
    total_bytes = 0
    warnings: list[str] = []
    errors: list[str] = []
    inspected_paths: list[str] = []
    artifacts: list[ReadOnlyArtifactContract] = []

    for index, target in enumerate(resolved_targets, start=1):
        if not target.exists() or not target.is_file():
            errors.append(f"Target does not exist or is not a file: {target}")
            continue
        if not any(_is_within_root(target, root) for root in resolved_roots):
            errors.append(f"Target is outside the approved roots: {target}")
            continue
        if target.suffix.lower() not in {suffix.lower() for suffix in scope.allowed_extensions}:
            errors.append(f"Target extension is not allowed: {target.suffix}")
            continue
        if not scope.hidden_files_allowed and any(part.startswith(".") for part in target.relative_to(REPO_ROOT).parts):
            errors.append(f"Hidden targets are not allowed: {target}")
            continue

        raw_bytes = target.read_bytes()
        total_bytes += len(raw_bytes)
        if total_bytes > scope.max_total_bytes:
            errors.append("Bounded read scope exceeded the maximum total bytes.")
            break

        relative_path = target.relative_to(REPO_ROOT).as_posix()
        inspected_paths.append(relative_path)
        digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
        text = raw_bytes.decode("utf-8", errors="replace")
        excerpt = _safe_excerpt(text)
        artifacts.append(
            ReadOnlyArtifactContract(
                artifact_id=f"RO_ART_{index:03d}",
                artifact_type="inspection_report",
                source_path=relative_path,
                summary=(
                    f"bytes={len(raw_bytes)} sha256_16={digest} excerpt={excerpt}"
                ),
                captured_at=SIMULATION_TIMESTAMP,
            )
        )

    if errors and not inspected_paths:
        return _blocked_response(request, errors, warnings)

    response_state = "read_completed"
    if errors:
        response_state = "read_partial"
    response = ReadOnlyAdapterResponseContract(
        adapter_request_id=request.adapter_request_id,
        adapter_id=request.adapter_id,
        response_state=response_state,
        read_completed=not errors,
        inspected_paths=inspected_paths,
        warnings=warnings,
        errors=errors,
        artifacts_generated=[artifact.artifact_id for artifact in artifacts],
        completed_at=SIMULATION_TIMESTAMP,
    )
    return response, artifacts


def _blocked_response(
    request: ReadOnlyAdapterRequestContract,
    errors: list[str],
    warnings: list[str],
) -> tuple[ReadOnlyAdapterResponseContract, list[ReadOnlyArtifactContract]]:
    response = ReadOnlyAdapterResponseContract(
        adapter_request_id=request.adapter_request_id,
        adapter_id=request.adapter_id,
        response_state="read_blocked",
        read_completed=False,
        inspected_paths=[],
        warnings=warnings,
        errors=errors,
        artifacts_generated=[],
        completed_at=SIMULATION_TIMESTAMP,
    )
    return response, []


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_excerpt(text: str, max_chars: int = 120) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    excerpt = " ".join(lines[:3])
    excerpt = excerpt[:max_chars]
    return excerpt.replace("\n", " ")


def main() -> None:
    artifacts = run_read_only_live_adapter_dry_run()
    print(f"read_only_request: {artifacts.read_only_request_path}")
    print(f"read_only_response: {artifacts.read_only_response_path}")
    print(f"read_only_artifact_registry: {artifacts.read_only_artifact_registry_path}")
    print(f"operator_report: {artifacts.operator_report_path}")


if __name__ == "__main__":
    main()