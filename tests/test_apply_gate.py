import subprocess
from pathlib import Path

import pytest

from orchestrator.apply_gate import ApplyGate

pytestmark = pytest.mark.fast


@pytest.fixture()
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    def run_git(args):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
    run_git(["init"])
    run_git(["config", "user.email", "tester@example.com"])
    run_git(["config", "user.name", "Test Runner"])
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "tests").mkdir()
    (repo / "docs" / "guide.md").write_text("v1\n", encoding="utf-8")
    (repo / "tests" / "sample.txt").write_text("v1\n", encoding="utf-8")
    run_git(["add", "README.md", "docs", "tests"])
    run_git(["commit", "-m", "init"])
    return repo


def test_apply_gate_allows_docs_and_tests_changes(git_repo, tmp_path):
    repo = git_repo
    gate = ApplyGate(repo_root=repo, mode="docs_tests", cycle_id="cycle-123")
    precheck = gate.ensure_clean_worktree()
    assert not precheck.blocked
    (repo / "docs" / "guide.md").write_text("v2\n", encoding="utf-8")
    (repo / "tests" / "sample.txt").write_text("v2\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    decision = gate.process_success("0001", run_dir)
    assert decision.applied is True
    assert decision.blocked is False
    assert (run_dir / "artifacts" / "patch.diff").exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout.strip() == ""


def test_apply_gate_blocks_disallowed_paths(git_repo, tmp_path):
    repo = git_repo
    orchestrator_dir = repo / "orchestrator"
    orchestrator_dir.mkdir(exist_ok=True)
    target_file = orchestrator_dir / "core.py"
    target_file.write_text("print('hi')\n", encoding="utf-8")
    gate = ApplyGate(repo_root=repo, mode="docs_tests", cycle_id="cycle-456")
    run_dir = tmp_path / "run_block"
    run_dir.mkdir()
    decision = gate.process_success("0002", run_dir)
    assert decision.blocked is True
    assert decision.blocked_path == "orchestrator/core.py"
    patch_file = run_dir / "artifacts" / "patch.diff"
    assert patch_file.exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "orchestrator" in status.stdout


def test_apply_gate_requires_clean_worktree(git_repo):
    repo = git_repo
    dirty = repo / "README.md"
    dirty.write_text("dirty\n", encoding="utf-8")
    gate = ApplyGate(repo_root=repo, mode="docs_tests", cycle_id="cycle-789")
    precheck = gate.ensure_clean_worktree()
    assert precheck.blocked is True