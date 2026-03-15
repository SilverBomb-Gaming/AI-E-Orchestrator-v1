import json
from pathlib import Path

import pytest

from orchestrator.adapter_registry_interface import AdapterDiscoveryOutput, AdapterRegistrationContract


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.fast


def test_adapter_registry_template_is_valid_json():
    template_path = ROOT / "contracts" / "templates" / "adapter_registry_template.json"
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["adapter_registration"]["dry_run_supported"] is True
    assert payload["adapter_registration"]["live_run_supported"] is False
    assert payload["discovery_output"]["availability"] == "planned"


def test_adapter_registration_contract_is_deterministic():
    contract = AdapterRegistrationContract(
        adapter_id="adapter.testing.future",
        adapter_type="testing",
        supported_task_types=["test_validation"],
        supported_targets=["workspace_copy"],
        allowed_actions=["bounded_test_run"],
        requires_approval=["live_run"],
        dry_run_supported=True,
        live_run_supported=False,
    )

    payload = contract.to_payload()
    assert payload["adapter_id"] == "adapter.testing.future"
    assert payload["live_run_supported"] is False


def test_adapter_discovery_output_is_deterministic():
    output = AdapterDiscoveryOutput(
        adapter_id="adapter.testing.future",
        adapter_status="registered",
        capabilities={"dry_run_supported": True, "supported_task_types": ["test_validation"]},
        priority=5,
        availability="available",
    )

    payload = output.to_payload()
    assert payload["adapter_status"] == "registered"
    assert payload["priority"] == 5
    assert payload["availability"] == "available"