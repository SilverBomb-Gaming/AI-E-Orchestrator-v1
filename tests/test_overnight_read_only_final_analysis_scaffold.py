import json

import pytest

from overnight_read_only_final_analysis_dry_run import run_overnight_read_only_final_analysis


pytestmark = pytest.mark.fast


def test_overnight_read_only_final_analysis_writes_deterministic_outputs(tmp_path):
    artifacts = run_overnight_read_only_final_analysis(tmp_path / "aie_overnight_read_only_final_analysis")

    readiness_payload = json.loads(artifacts.readiness_summary_json_path.read_text(encoding="utf-8"))[
        "overnight_readiness_summary"
    ]
    readiness_markdown = artifacts.readiness_summary_markdown_path.read_text(encoding="utf-8")

    assert readiness_payload["shared_read_only_scope"]["allowed_extensions"] == [".py"]
    assert readiness_payload["success_paths_stable"] is True
    assert readiness_payload["partial_outcomes_classified_correctly"] is True
    assert readiness_payload["retryable_failures_safe_and_bounded"] is True
    assert readiness_payload["terminal_failures_halt_safely"] is True
    assert readiness_payload["morning_handoffs_deterministic"] is True
    assert readiness_payload["no_write_capable_execution"] is True
    assert readiness_payload["read_only_loop_stable_across_tested_outcomes"] is True
    assert readiness_payload["mixed_outcome_summary"]["attempted_scenarios"] == [
        "read_completed",
        "read_partial",
        "read_failed_retryable",
    ]
    assert readiness_payload["validator_classes_exercised"] == [
        "partial_success",
        "passed",
        "retryable_failure",
        "terminal_failure",
    ]
    assert readiness_payload["final_readiness_verdict"] == "bounded read-only overnight production remains rehearsal-only"

    assert "Final bounded read-only overnight readiness audit completed" in readiness_markdown
    assert "Final readiness verdict: bounded read-only overnight production remains rehearsal-only" in readiness_markdown
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in readiness_markdown