import json
from pathlib import Path

import pytest

from orchestrator.planner_stub import PlannerAgentStub
from orchestrator.report_contract import format_operator_report, validate_operator_report
from orchestrator.request_schema_loader import RequestSchemaValidationError, load_request_file, validate_request_payload
from orchestrator.task_graph_emitter import emit_task_graph


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def _request_payload() -> dict:
    template_path = ROOT / "contracts" / "templates" / "conversational_request_template.json"
    return json.loads(template_path.read_text(encoding="utf-8"))


def test_schema_loader_success_path():
    request = validate_request_payload(_request_payload())

    assert request.request_id == "REQ_20260315_0001"
    assert request.channel == "cli_chat"
    assert request.intent == "create_sandbox"


def test_schema_loader_failure_path():
    payload = _request_payload()
    payload.pop("operator_prompt")

    with pytest.raises(RequestSchemaValidationError) as exc:
        validate_request_payload(payload)

    assert "operator_prompt: is required" in str(exc.value)


def test_schema_loader_from_file(tmp_path):
    payload_path = tmp_path / "request.json"
    payload_path.write_text(json.dumps(_request_payload(), indent=2), encoding="utf-8")

    request = load_request_file(payload_path)

    assert request.session_id == "SESSION_LOCAL_001"


def test_planner_stub_deterministic_output_shape():
    planner = PlannerAgentStub()
    payload = _request_payload()

    result_a = planner.plan_from_payload(payload).to_payload()
    result_b = planner.plan_from_payload(payload).to_payload()

    assert result_a == result_b
    assert result_a["request_type"] == "create_sandbox"
    assert [task["task_type"] for task in result_a["task_graph"]["tasks"]] == [
        "request_analysis",
        "task_graph_emission",
        "report_contract_preparation",
    ]


def test_task_graph_emitter_structure_validity():
    request = validate_request_payload(_request_payload())
    graph = emit_task_graph(request).to_payload()

    assert graph["request"]["request_id"] == request.request_id
    assert graph["dependency_map"]["REQ_20260315_0001_GRAPH"] == ["REQ_20260315_0001_INTAKE"]
    assert graph["dependency_map"]["REQ_20260315_0001_REPORT"] == ["REQ_20260315_0001_GRAPH"]
    assert graph["tasks"][1]["policy_level"] == "architecture_only"
    assert graph["tasks"][2]["validation_rules"][0]["rule_id"] == "VR_REPORT_ORDER_001"


def test_report_formatter_section_ordering():
    report = format_operator_report(
        summary="Architecture scaffolding landed.",
        facts=["Schema loader created.", "Planner stub created."],
        assumptions=["Runtime remains untouched."],
        recommendations=["Keep future work additive."],
        timestamp="2026-03-15T18:00:00Z",
    )

    assert report.index("SUMMARY") < report.index("FACTS") < report.index("ASSUMPTIONS") < report.index("RECOMMENDATIONS") < report.index("TIMESTAMP")
    assert report.strip().endswith("2026-03-15T18:00:00Z")


def test_report_validator_pass_case():
    report = format_operator_report(
        summary="Architecture scaffolding landed.",
        facts=["Schema loader created."],
        assumptions=["Runtime remains untouched."],
        recommendations=["Keep future work additive."],
        timestamp="2026-03-15T18:00:00Z",
    )

    result = validate_operator_report(report)

    assert result.is_valid is True
    assert result.errors == []


def test_report_validator_fail_case():
    invalid_report = "FACTS\n\n- Wrong start\n\nSUMMARY\n\nLate summary\n\nTIMESTAMP\n\n2026-03-15T18:00:00Z\n"

    result = validate_operator_report(invalid_report)

    assert result.is_valid is False
    assert any("missing required section: ASSUMPTIONS" == error for error in result.errors)
    assert any("missing required section: RECOMMENDATIONS" == error for error in result.errors)
