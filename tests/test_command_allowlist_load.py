import json
from pathlib import Path

import pytest

from orchestrator.command_controls import CommandAllowlist

pytestmark = pytest.mark.fast


@pytest.fixture()
def allowlist_path(tmp_path: Path) -> Path:
    target = tmp_path / "command_allowlist.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def test_empty_file_raises_helpful_error(allowlist_path: Path) -> None:
    allowlist_path.write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="command_allowlist.json is empty"):
        CommandAllowlist(allowlist_path)


def test_invalid_json_reports_line_and_column(allowlist_path: Path) -> None:
    allowlist_path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse"):
        CommandAllowlist(allowlist_path)


def test_valid_json_loads_entries(allowlist_path: Path) -> None:
    allowlist_path.write_text(json.dumps({"exact": ["echo hello"], "prefix": []}), encoding="utf-8")
    allowlist = CommandAllowlist(allowlist_path)
    assert allowlist.is_allowed("echo hello")
    assert not allowlist.is_allowed("echo goodbye")
