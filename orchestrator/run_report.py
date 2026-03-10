from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .utils import read_json, safe_write_text


@dataclass(frozen=True)
class RunReportContext:
    run_id: str
    task_id: str
    contract_path: str
    task_type: str
    final_status: str
    final_status_detail: str
    command_results: Sequence[Dict[str, Any]]
    run_dir: Path
    validation_sources: Sequence[str] = ()


def write_run_report(context: RunReportContext) -> Path:
    run_dir = context.run_dir
    entity_validation = read_json(run_dir / "entity" / "entity_validation.json", default={})
    artifacts = _collect_entity_artifacts(run_dir / "entity")
    markdown = []
    markdown.append("# Run Summary")
    markdown.append("")
    markdown.append(f"- Run ID: {context.run_id}")
    markdown.append(f"- Task ID: {context.task_id}")
    markdown.append(f"- Type: {context.task_type or 'standard'}")
    markdown.append(f"- Contract: {context.contract_path}")
    markdown.append(f"- Status: {context.final_status.upper() if context.final_status else 'UNKNOWN'}")
    markdown.append("")
    markdown.extend(_validation_sources_section(context.validation_sources))
    markdown.extend(_command_section(context.command_results, run_dir))
    markdown.extend(_entity_section(entity_validation))
    markdown.extend(_artifact_section(artifacts))
    markdown.extend(_log_section(entity_validation))
    markdown.append("## Final Decision")
    markdown.append("")
    markdown.append(context.final_status.upper() if context.final_status else "UNKNOWN")
    detail = context.final_status_detail or ""
    if detail:
        markdown.append("")
        markdown.append(detail)
    markdown.append("")
    destination = run_dir / "report_last_run.md"
    safe_write_text(destination, "\n".join(markdown).strip() + "\n")
    return destination


def _validation_sources_section(sources: Sequence[str]) -> List[str]:
    lines: List[str] = ["## Validation Sources", ""]
    if not sources:
        lines.append("- No validation sources were recorded.")
        lines.append("")
        return lines
    friendly = {
        "entity_evidence": "Entity workflow evidence",
        "playmode_markers": "Legacy Play Mode markers",
    }
    for source in sources:
        label = friendly.get(source, source)
        lines.append(f"- {label}")
    lines.append("")
    return lines


def _command_section(command_results: Sequence[Dict[str, Any]], run_dir: Path) -> List[str]:
    lines: List[str] = ["## Command Summary", ""]
    if not command_results:
        lines.append("- No commands were executed for this run.")
        lines.append("")
        return lines
    lines.append("| Name | Type | Duration (s) | Return Code | Unity Exit | Unity Exit Reason | Stdout | Stderr |")
    lines.append("|------|------|--------------|-------------|------------|-------------------|--------|--------|")
    for result in command_results:
        name = result.get("name", "command")
        cmd_type = result.get("type", "utility")
        duration = result.get("duration_seconds", 0)
        returncode = result.get("returncode", 0)
        unity_exit_code = result.get("unity_exit_code", "") or ""
        unity_exit_reason = result.get("unity_exit_reason", "") or ""
        stdout = _relpath(result.get("stdout_log"), run_dir)
        stderr = _relpath(result.get("stderr_log"), run_dir)
        lines.append(
            f"| {name} | {cmd_type} | {duration:.2f} | {returncode} | {unity_exit_code} | {unity_exit_reason} | {stdout} | {stderr} |"
        )
    lines.append("")
    return lines


def _entity_section(entity_validation: Dict[str, Any]) -> List[str]:
    lines: List[str] = ["## Entity Validation Summary", ""]
    if not entity_validation:
        lines.append("- No entity validation artifacts were captured.")
        lines.append("")
        return lines
    lines.append(f"- Entity Name: {entity_validation.get('entity_name', 'unknown')}")
    lines.append(f"- Entity Type: {entity_validation.get('entity_type', 'unknown')}")
    lines.append(f"- Prefab Created: {entity_validation.get('prefab_created')}")
    lines.append(f"- Preview Generated: {entity_validation.get('preview_generated')}")
    lines.append(f"- Editor Log Present: {entity_validation.get('editor_log_present')}")
    warnings_count = len(entity_validation.get("warnings", []))
    errors_count = len(entity_validation.get("errors", []))
    lines.append(f"- Warning Count: {warnings_count}")
    lines.append(f"- Error Count: {errors_count}")
    preview_validation = entity_validation.get("preview_validation") or {}
    if preview_validation:
        lines.append(
            "- Preview Validation: {status}".format(status=preview_validation.get("status", "unknown"))
        )
        reason = preview_validation.get("reason")
        if reason:
            lines.append(f"  - Reason: {reason}")
        dimensions = []
        if preview_validation.get("width"):
            dimensions.append(f"width={preview_validation['width']}")
        if preview_validation.get("height"):
            dimensions.append(f"height={preview_validation['height']}")
        if dimensions:
            lines.append("  - Dimensions: " + ", ".join(dimensions))
    cleanup = entity_validation.get("cleanup_hygiene") or {}
    if cleanup:
        lines.append(f"- Cleanup Hygiene Status: {cleanup.get('status', 'unknown')}")
    repeatability = entity_validation.get("repeatability") or {}
    if repeatability:
        prev_run = repeatability.get("previous_run_id") or "n/a"
        verdict = "match" if repeatability.get("match", False) else "mismatch"
        lines.append(f"- Repeatability vs {prev_run}: {verdict}")
        diffs = repeatability.get("differences") or []
        if diffs:
            lines.append("  - Differences: " + ", ".join(sorted({entry.get('field', 'unknown') for entry in diffs})))
    lines.append(f"- Final Status: {entity_validation.get('status', 'unknown')}")
    lines.append("")
    return lines


def _artifact_section(artifacts: List[str]) -> List[str]:
    lines: List[str] = ["## Artifact Inventory", ""]
    if not artifacts:
        lines.append("- No entity artifacts were mirrored.")
    else:
        for rel_path in artifacts:
            lines.append(f"- {rel_path}")
    lines.append("")
    return lines


def _log_section(entity_validation: Dict[str, Any]) -> List[str]:
    lines: List[str] = ["## Log Classification Summary", ""]
    if not entity_validation:
        lines.append("- No log details captured.")
        lines.append("")
        return lines
    counts = entity_validation.get("log_counts", {})
    lines.append("- Counts: " + ", ".join(f"{key}={counts.get(key, 0)}" for key in ["fatal", "warnings", "environment_noise", "cleanup_issues", "unknown"]))
    classification = entity_validation.get("log_classification", {})
    for bucket in ["fatal", "warnings", "environment_noise", "cleanup_issues", "unknown"]:
        lines.append(f"### {bucket.replace('_', ' ').title()}")
        values = classification.get(bucket) or []
        if not values:
            lines.append("- none")
        else:
            for entry in values:
                lines.append(f"- {entry}")
        lines.append("")
    cleanup = entity_validation.get("cleanup_hygiene") or {}
    if cleanup:
        lines.append("### Cleanup Hygiene")
        for key, value in cleanup.items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    return lines


def _collect_entity_artifacts(entity_dir: Path) -> List[str]:
    if not entity_dir.exists():
        return []
    paths = []
    for path in sorted(p for p in entity_dir.rglob("*") if p.is_file()):
        paths.append(str(path.relative_to(entity_dir.parent)).replace("\\", "/"))
    return paths


def _relpath(value: Any, run_dir: Path) -> str:
    if not value:
        return ""
    try:
        candidate = Path(value)
        if candidate.exists():
            try:
                return str(candidate.relative_to(run_dir)).replace("\\", "/")
            except ValueError:
                pass
        return str(candidate).replace("\\", "/")
    except Exception:
        return str(value)
