import pytest

from ai_e_runtime.conversation_router import ConversationResponse
from ai_e_runtime.control_commands import ControlCommandResult
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.request_schema_loader import validate_request_payload
from orchestrator.time_utils import is_standard_timestamp, normalize_timestamp, parse_timestamp


pytestmark = pytest.mark.fast


def test_timestamp_utility_normalizes_legacy_iso_utc_string():
    normalized = normalize_timestamp("2026-03-15T00:00:00Z")

    assert normalized == "2026-03-14 20:00:00 -04:00 (Eastern Time — New York)"
    assert is_standard_timestamp(normalized) is True


def test_request_schema_loader_normalizes_created_at_field():
    request = validate_request_payload(
        {
            "request_id": "REQ_TEST_001",
            "session_id": "SESSION_TEST_001",
            "channel": "cli_chat",
            "operator_prompt": "Inspect the runtime state.",
            "created_at": "2026-03-15T00:00:00Z",
        }
    )

    assert request.created_at == "2026-03-14 20:00:00 -04:00 (Eastern Time — New York)"


def test_operator_report_normalizes_timestamp_and_validator_enforces_format():
    report = format_operator_report(
        summary="Report generated.",
        facts=["One fact."],
        assumptions=["One assumption."],
        recommendations=["One recommendation."],
        timestamp="2026-03-15T18:00:00Z",
    )

    assert report.strip().endswith("2026-03-15 14:00:00 -04:00 (Eastern Time — New York)")
    assert validate_operator_report(report).is_valid is True


def test_operator_report_validator_rejects_nonstandard_timestamp():
    invalid_report = (
        "SUMMARY\n\nReady.\n\n"
        "FACTS\n\n- One fact\n\n"
        "ASSUMPTIONS\n\n- One assumption\n\n"
        "RECOMMENDATIONS\n\n- One recommendation\n\n"
        "TIMESTAMP\n\n2026-03-15T18:00:00Z\n"
    )

    result = validate_operator_report(invalid_report)

    assert result.is_valid is False
    assert "TIMESTAMP section must use the standardized AI-E timestamp format" in result.errors


def test_runtime_text_surfaces_append_timestamp_field():
    response = ConversationResponse(
        title="AI-E STATUS REPORT",
        answer="Current Task: idle",
        recommendation="Inject a task.",
        query_type="general_status",
        payload={},
    )
    command = ControlCommandResult(title="AI-E COMMAND", body="Body text")

    assert "TIMESTAMP: " in response.to_text()
    assert response.to_text().splitlines()[-1].startswith("TIMESTAMP: ")
    assert "TIMESTAMP: " in command.to_text()
    assert command.to_text().splitlines()[-1].startswith("TIMESTAMP: ")


def test_parse_timestamp_accepts_standardized_format():
    parsed = parse_timestamp("2026-03-14 20:00:00 -04:00 (Eastern Time — New York)")

    assert parsed.isoformat() == "2026-03-14T20:00:00-04:00"