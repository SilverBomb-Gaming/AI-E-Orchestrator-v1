from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .utils import read_json, write_json, utc_timestamp

DEFAULT_COMPARISON_FIELDS: List[str] = [
    "status",
    "prefab_created",
    "preview_generated",
    "prefab_path",
    "preview_png_path",
    "preview_validation",
    "log_counts",
    "cleanup_hygiene",
]


def compare_entity_runs(
    *,
    current_run_dir: Path | str,
    comparison_run_dir: Path | str,
    fields: Sequence[str] | None = None,
    current_validation: Dict[str, Any] | None = None,
    comparison_validation: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compare two entity validation payloads and return a repeatability report."""

    current_dir = Path(current_run_dir)
    comparison_dir = Path(comparison_run_dir)
    field_list = list(fields) if fields else list(DEFAULT_COMPARISON_FIELDS)
    current_payload = current_validation or _load_validation(current_dir)
    comparison_payload = comparison_validation or _load_validation(comparison_dir)
    if not current_payload:
        raise ValueError(f"entity_validation.json missing or empty for {current_dir}")
    if not comparison_payload:
        raise ValueError(f"entity_validation.json missing or empty for {comparison_dir}")

    differences: List[Dict[str, Any]] = []
    for field in field_list:
        current_value = current_payload.get(field)
        previous_value = comparison_payload.get(field)
        if not _values_equal(current_value, previous_value):
            differences.append(
                {
                    "field": field,
                    "current": current_value,
                    "previous": previous_value,
                }
            )

    report = {
        "current_run_id": current_dir.name,
        "previous_run_id": comparison_dir.name,
        "fields": field_list,
        "match": not differences,
        "differences": differences,
        "generated_at": utc_timestamp(compact=False),
        "entity_name": current_payload.get("entity_name", ""),
        "entity_type": current_payload.get("entity_type", ""),
        "comparison_entity_name": comparison_payload.get("entity_name", ""),
        "comparison_entity_type": comparison_payload.get("entity_type", ""),
    }
    return report


def write_repeatability_report(
    report: Dict[str, Any],
    *,
    current_run_dir: Path | str,
    destination: Path | None = None,
) -> Path:
    """Write a repeatability report payload to disk and return its path."""

    run_dir = Path(current_run_dir)
    target = destination or (run_dir / "entity" / "repeatability_report.json")
    write_json(target, report)
    return target


def _values_equal(current: Any, previous: Any) -> bool:
    return _normalize_value(current) == _normalize_value(previous)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _load_validation(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "entity" / "entity_validation.json"
    return read_json(path, default=None)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two entity runs for repeatability")
    parser.add_argument("--current", required=True, help="Path to the current run directory")
    parser.add_argument("--previous", required=True, help="Path to the comparison run directory")
    parser.add_argument(
        "--fields",
        nargs="*",
        default=None,
        help="Specific top-level fields to compare (defaults to the standard field list)",
    )
    parser.add_argument(
        "--out",
        dest="output",
        help="Optional output path for repeatability_report.json (defaults to runs/<current>/entity/)",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    report = compare_entity_runs(
        current_run_dir=Path(args.current),
        comparison_run_dir=Path(args.previous),
        fields=args.fields,
    )
    output_path = write_repeatability_report(
        report,
        current_run_dir=Path(args.current),
        destination=Path(args.output) if args.output else None,
    )
    print(f"Repeatability report written to {output_path}")


if __name__ == "__main__":
    main()
