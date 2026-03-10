import json
from pathlib import Path

import pytest

from orchestrator.repeatability import compare_entity_runs, write_repeatability_report

pytestmark = pytest.mark.fast


def _write_validation(run_dir: Path, payload: dict) -> None:
    entity_dir = run_dir / "entity"
    entity_dir.mkdir(parents=True, exist_ok=True)
    (entity_dir / "entity_validation.json").write_text(json.dumps(payload), encoding="utf-8")


def _base_payload() -> dict:
    return {
        "entity_name": "zombie_basic",
        "entity_type": "zombie",
        "status": "allow",
        "prefab_created": True,
        "preview_generated": True,
        "prefab_path": "Assets/Zombies/Zombie.prefab",
        "preview_png_path": "entity/entity_preview.png",
        "preview_validation": {"status": "ok", "width": 512, "height": 512},
        "log_counts": {"fatal": 0, "warnings": 0},
        "cleanup_hygiene": {"status": "clean"},
    }


def test_compare_entity_runs_reports_match(tmp_path: Path) -> None:
    previous = tmp_path / "20260309_165301_ENTITY_0001"
    current = tmp_path / "20260310_010101_ENTITY_0001"
    payload = _base_payload()
    _write_validation(previous, payload)
    _write_validation(current, payload)

    report = compare_entity_runs(current_run_dir=current, comparison_run_dir=previous)

    assert report["match"] is True
    assert report["differences"] == []
    assert report["current_run_id"] == current.name
    assert report["previous_run_id"] == previous.name


def test_compare_entity_runs_detects_differences(tmp_path: Path) -> None:
    previous = tmp_path / "20260309_165301_ENTITY_0001"
    current = tmp_path / "20260310_020202_ENTITY_0001"
    base = _base_payload()
    _write_validation(previous, base)
    modified = dict(base)
    modified["prefab_path"] = "Assets/Zombies/ZombieVariant.prefab"
    modified["log_counts"] = {"fatal": 1}
    _write_validation(current, modified)

    report = compare_entity_runs(current_run_dir=current, comparison_run_dir=previous)

    assert report["match"] is False
    fields = {entry["field"] for entry in report["differences"]}
    assert fields == {"prefab_path", "log_counts"}


def test_write_repeatability_report_persists_payload(tmp_path: Path) -> None:
    current = tmp_path / "20260310_030303_ENTITY_0001"
    report = {
        "current_run_id": current.name,
        "previous_run_id": "20260309_165301_ENTITY_0001",
        "fields": ["status"],
        "match": True,
        "differences": [],
        "generated_at": "2026-03-09T00:00:00Z",
        "entity_name": "zombie_basic",
        "entity_type": "zombie",
    }

    destination = write_repeatability_report(report, current_run_dir=current)

    assert destination.exists()
    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored["match"] is True
    assert stored["current_run_id"] == current.name
