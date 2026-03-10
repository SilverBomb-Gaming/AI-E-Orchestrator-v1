import argparse
import json
from pathlib import Path

import pytest

from Tools import queue_ops


FIXTURE_DIR = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.fast


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    def _setup(queue_fixture="queue_minimal.json", approvals_fixture="approvals_minimal.json"):
        queue_path = tmp_path / "queue.json"
        approvals_path = tmp_path / "approvals.json"
        baselines_path = tmp_path / "baselines.json"
        queue_path.write_text((FIXTURE_DIR / queue_fixture).read_text(), encoding="utf-8")
        approvals_path.write_text((FIXTURE_DIR / approvals_fixture).read_text(), encoding="utf-8")
        baselines_path.write_text(json.dumps({"baselines": []}), encoding="utf-8")
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        (runs_dir / "20260225_135016_0006").mkdir()
        (runs_dir / "20260224_014138_0005").mkdir()

        monkeypatch.setattr(queue_ops, "QUEUE_PATH", queue_path)
        monkeypatch.setattr(queue_ops, "APPROVALS_PATH", approvals_path)
        monkeypatch.setattr(queue_ops, "RUNS_DIR", runs_dir)
        monkeypatch.setattr(queue_ops, "BASELINES_PATH", baselines_path)
        return queue_path, approvals_path, runs_dir

    return _setup


def test_list_runs_without_error(sandbox, capsys):
    sandbox()
    exit_code = queue_ops.cmd_list(argparse.Namespace())
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "First blocking task" in captured.out


def test_reset_dry_run_does_not_modify_files(sandbox):
    queue_path, _, _ = sandbox()
    before = queue_path.read_text(encoding="utf-8")
    args = argparse.Namespace(
        task="0006",
        purge_runs=False,
        clear_error=False,
        force=False,
        dry_run=True,
    )
    queue_ops.cmd_reset(args)
    after = queue_path.read_text(encoding="utf-8")
    assert after == before


def test_reset_clears_current_run_id_and_creates_backup(sandbox):
    queue_path, _, _ = sandbox()
    args = argparse.Namespace(
        task="0006",
        purge_runs=False,
        clear_error=False,
        force=False,
        dry_run=False,
    )
    queue_ops.cmd_reset(args)
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    task = next(item for item in payload["tasks"] if item["id"] == "0006")
    assert task["current_run_id"] is None
    backups = list(queue_path.parent.glob("queue.json.bak.*"))
    assert backups, "Expected queue backup to be created"


def test_abort_sets_status_aborted(sandbox):
    queue_path, _, _ = sandbox()
    args = argparse.Namespace(task="0006", reason="Manual abort", dry_run=False)
    queue_ops.cmd_abort(args)
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    task = next(item for item in payload["tasks"] if item["id"] == "0006")
    assert task["status"] == "aborted"
    assert task["last_error"] == "Manual abort"


def test_delete_requires_force(sandbox):
    sandbox()
    args = argparse.Namespace(task="0006", force=False, purge_runs=False, dry_run=False)
    with pytest.raises(SystemExit):
        queue_ops.cmd_delete(args)


def test_delete_with_force_and_dry_run_leaves_files(sandbox):
    queue_path, _, _ = sandbox()
    before = queue_path.read_text(encoding="utf-8")
    args = argparse.Namespace(task="0007", force=True, purge_runs=True, dry_run=True)
    queue_ops.cmd_delete(args)
    after = queue_path.read_text(encoding="utf-8")
    assert before == after


def test_purge_runs_requires_force_for_reset(sandbox):
    sandbox()
    args = argparse.Namespace(
        task="0006",
        purge_runs=True,
        clear_error=False,
        force=False,
        dry_run=False,
    )
    with pytest.raises(SystemExit):
        queue_ops.cmd_reset(args)


def test_delete_with_force_updates_queue_and_creates_backup(sandbox):
    queue_path, _, runs_dir = sandbox()
    args = argparse.Namespace(task="0007", force=True, purge_runs=True, dry_run=False)
    queue_ops.cmd_delete(args)
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    assert all(task["id"] != "0007" for task in payload["tasks"])
    backups = list(queue_path.parent.glob("queue.json.bak.*"))
    assert backups
    remaining_runs = [child.name for child in runs_dir.iterdir()]
    assert "20260224_014138_0005" in remaining_runs

def test_resume_consumes_approval_when_available(sandbox):
    queue_path, approvals_path, _ = sandbox("queue_blocked_needs_approval.json")
    args = argparse.Namespace(task="0006", force=False, dry_run=False)
    queue_ops.cmd_resume(args)
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    task = next(item for item in payload["tasks"] if item["id"] == "0006")
    assert task["status"] == "pending"
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    assert len(approvals["approvals"]) == 1


def test_resume_dry_run_leaves_files_untouched(sandbox):
    queue_path, approvals_path, _ = sandbox("queue_blocked_needs_approval.json")
    queue_before = queue_path.read_text(encoding="utf-8")
    approvals_before = approvals_path.read_text(encoding="utf-8")
    args = argparse.Namespace(task="0006", force=False, dry_run=True)
    queue_ops.cmd_resume(args)
    assert queue_before == queue_path.read_text(encoding="utf-8")
    assert approvals_before == approvals_path.read_text(encoding="utf-8")


def test_baseline_show_handles_empty_store(sandbox, capsys):
    sandbox()
    exit_code = queue_ops.cmd_baseline_show(argparse.Namespace())
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No baselines recorded." in captured.out


def test_baseline_set_records_entry(sandbox):
    queue_path, _, runs_dir = sandbox()
    run_id = "20260225_135016_0006"
    run_meta_path = runs_dir / run_id / "run_meta.json"
    run_meta_path.write_text(
        json.dumps({"task_id": "0006", "run_id": run_id}),
        encoding="utf-8",
    )
    args = argparse.Namespace(run_id=run_id, tag="stable_core", dry_run=False)
    queue_ops.cmd_baseline_set(args)
    baselines_path = queue_path.parent / "baselines.json"
    payload = json.loads(baselines_path.read_text(encoding="utf-8"))
    assert payload["baselines"]
    record = payload["baselines"][0]
    assert record["task_id"] == "0006"
    assert record["run_id"] == run_id
    assert record["tag"] == "stable_core"
