import json

import pytest

from overnight_read_only_comparison_dry_run import run_overnight_read_only_comparison


pytestmark = pytest.mark.fast


def test_overnight_read_only_comparison_writes_deterministic_outputs(tmp_path):
    artifacts = run_overnight_read_only_comparison(tmp_path / "aie_overnight_read_only_comparison")

    comparison_payload = json.loads(artifacts.comparison_json_path.read_text(encoding="utf-8"))[
        "overnight_rehearsal_comparison"
    ]
    comparison_markdown = artifacts.comparison_markdown_path.read_text(encoding="utf-8")

    assert comparison_payload["shared_read_only_scope"]["allowed_extensions"] == [".py"]
    assert comparison_payload["shared_read_only_scope"]["max_file_count"] == 2
    assert comparison_payload["retryable_variant"]["attempted_scenarios"] == [
        "read_completed",
        "read_failed_retryable",
    ]
    assert comparison_payload["terminal_variant"]["attempted_scenarios"] == [
        "read_completed",
        "read_failed_terminal",
    ]
    assert comparison_payload["retryable_variant"]["failure_path_results"]["validation_class"] == "retryable_failure"
    assert comparison_payload["terminal_variant"]["failure_path_results"]["validation_class"] == "terminal_failure"
    assert comparison_payload["retryable_variant"]["failure_path_results"]["retry_recommended"] is True
    assert comparison_payload["terminal_variant"]["failure_path_results"]["retry_recommended"] is False
    assert comparison_payload["retryable_variant"]["recommended_next_action"].startswith("Repeat retryable failed reads")
    assert comparison_payload["terminal_variant"]["recommended_next_action"].startswith("Do not retry the same bounded request")
    assert comparison_payload["retryable_variant"]["operator_attention_level"] == "medium"
    assert comparison_payload["terminal_variant"]["operator_attention_level"] == "high"
    assert comparison_payload["differences"]["recommended_next_action_difference"]["retryable_failure"] != comparison_payload["differences"]["recommended_next_action_difference"]["terminal_failure"]
    assert comparison_payload["differences"]["operator_attention_level_difference"] == {
        "retryable_failure": "medium",
        "terminal_failure": "high",
    }
    assert comparison_payload["production_ready"] is False
    assert comparison_payload["readiness_verdict"] == "bounded read-only overnight production remains rehearsal-only"

    assert "retryable-failure and terminal-failure variants" in comparison_markdown
    assert "Readiness verdict: bounded read-only overnight production remains rehearsal-only" in comparison_markdown
    for section in ["SUMMARY", "FACTS", "ASSUMPTIONS", "RECOMMENDATIONS", "TIMESTAMP"]:
        assert section in comparison_markdown