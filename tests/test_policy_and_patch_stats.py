from pathlib import Path

from orchestrator.contracts import Contract
from orchestrator.policy import PolicyEngine
from orchestrator.utils import parse_patch_stats


def test_parse_patch_stats_counts_deleted_files() -> None:
    patch_text = """diff --git a/keep.txt b/keep.txt
--- a/keep.txt
+++ b/keep.txt
@@ -1 +1 @@
-old
+new
diff --git a/removed.prefab b/removed.prefab
--- a/removed.prefab
+++ /dev/null
@@ -1,2 +0,0 @@
-line1
-line2
"""

    stats = parse_patch_stats(patch_text)

    assert stats["files_changed"] == 2
    assert stats["insertions"] == 1
    assert stats["deletions"] == 3
    assert stats["loc_delta"] == 4
    assert stats["touched_files"] == ["keep.txt", "removed.prefab"]


def test_policy_ignores_screenshot_error_text() -> None:
    engine = PolicyEngine(orchestrator_root=Path("."))
    contract = Contract(
        path=Path("LEVEL_0001.md"),
        metadata={"Task ID": "LEVEL_0001", "Target Repo Path": "E:/repo"},
        body="",
    )

    decision = engine.evaluate(
        contract=contract,
        agent_profiles=[],
        patch_stats={"files_changed": 0, "loc_delta": 0, "touched_files": []},
        command_results=[
            {
                "name": "Validate Minimal Arena Artifacts",
                "shell": "powershell -Command \"throw 'Arena screenshot too small'\"",
                "stdout_log": "validate.out.log",
            }
        ],
    )

    assert all(violation.rule != "desktop_capture" for violation in decision.violations)


def test_policy_flags_actual_screenshot_runner() -> None:
    engine = PolicyEngine(orchestrator_root=Path("."))
    contract = Contract(
        path=Path("0014.md"),
        metadata={"Task ID": "0014", "Target Repo Path": "E:/repo"},
        body="",
    )

    decision = engine.evaluate(
        contract=contract,
        agent_profiles=[],
        patch_stats={"files_changed": 0, "loc_delta": 0, "touched_files": []},
        command_results=[
            {
                "name": "Capture MainMenu Screenshot",
                "shell": 'powershell.exe -File "Tools\\run_unity_screenshot.ps1" -OutPng "scripts\\logs\\mainmenu_proof.png"',
                "stdout_log": "capture.out.log",
            }
        ],
    )

    assert any(violation.rule == "desktop_capture" for violation in decision.violations)