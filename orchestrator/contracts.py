from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .utils import safe_write_text


UNITY_LOG_PATH = "scripts/logs/Editor.log"
UNITY_LOG_SUMMARY_PATH = "Tools/CI/unity_log_summary.json"
UNITY_ERROR_CLASSIFICATION_PATH = "Tools/CI/unity_error_classification.json"
_ARTIFACT_ALIAS_MAP = {
    "unity_editor_log": UNITY_LOG_PATH,
    "unity_log": UNITY_LOG_PATH,
    "unity_editor_log_json": UNITY_LOG_SUMMARY_PATH,
    "unity_log_summary": UNITY_LOG_SUMMARY_PATH,
    "unity_editor_log_summary": UNITY_LOG_SUMMARY_PATH,
    "unity_error_classification": UNITY_ERROR_CLASSIFICATION_PATH,
}
_DEFAULT_EXECUTION_MODE = "editor"
_EXECUTION_MODE_ALIASES = {
    "editor": "editor",
    "editormode": "editor",
    "edit_mode": "editor",
    "edit": "editor",
    "playmode": "playmode_required",
    "play_mode": "playmode_required",
    "playmode_required": "playmode_required",
    "playmode-required": "playmode_required",
    "runtime": "playmode_required",
    "runtime_required": "playmode_required",
    "either": "either",
    "auto": "either",
}
_TRUTHY = {"1", "true", "yes", "y"}
_FALSY = {"0", "false", "no", "n"}


def _parse_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized in _TRUTHY:
            return True
        if normalized in _FALSY:
            return False
        return None
    return None


def _coerce_artifact_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in value]
    return [value]


def _normalize_artifact_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    slug = text.lower().replace(" ", "_").replace("-", "_")
    slug = slug.replace("\\", "/")
    if slug in _ARTIFACT_ALIAS_MAP:
        return _ARTIFACT_ALIAS_MAP[slug]
    normalized = text.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


@dataclass(frozen=True)
class Contract:
    path: Path
    metadata: Dict[str, Any]
    body: str

    @property
    def task_id(self) -> str:
        value = self.metadata.get("Task ID", "UNKNOWN")
        if isinstance(value, int):
            return f"{value:04d}"
        return str(value)

    @property
    def allowed_scope(self) -> List[str]:
        scope = self.metadata.get("Allowed Scope", [])
        if isinstance(scope, list):
            return [str(item) for item in scope]
        if isinstance(scope, str):
            return [scope]
        return []

    @property
    def commands(self) -> List[Dict[str, Any]]:
        items = self.metadata.get("Commands to Run", [])
        if not isinstance(items, list):
            return []
        normalized = []
        for raw in items:
            if isinstance(raw, str):
                normalized.append({"name": raw, "shell": raw, "type": "utility"})
            elif isinstance(raw, dict):
                normalized.append(
                    {
                        "name": raw.get("name", "command"),
                        "shell": raw.get("shell", ""),
                        "type": raw.get("type", "utility"),
                        "timeout": raw.get("timeout"),
                    }
                )
        return normalized

    @property
    def artifact_requirements(self) -> List[str]:
        requirements = self._artifact_entries()
        explicit = self._explicit_requires_unity_flag()
        if explicit:
            defaults = [UNITY_LOG_PATH, UNITY_LOG_SUMMARY_PATH, UNITY_ERROR_CLASSIFICATION_PATH]
            existing_keys = {item.lower() for item in requirements}
            for default in defaults:
                if default.lower() not in existing_keys:
                    requirements.append(default)
                    existing_keys.add(default.lower())
        return requirements

    @property
    def requires_unity_log(self) -> bool:
        explicit = self._explicit_requires_unity_flag()
        if explicit is not None:
            return explicit
        entries = self._artifact_entries()
        required_suffix = UNITY_LOG_PATH.lower()
        return any(entry.lower().endswith(required_suffix) for entry in entries)

    @property
    def execution_mode(self) -> str:
        return _resolve_execution_mode(self.metadata)

    def _artifact_entries(self) -> List[str]:
        sources = [
            self.metadata.get("Artifacts Required"),
            self.metadata.get("Artifact Requirements"),
            self.metadata.get("artifact_requirements"),
        ]
        normalized: List[str] = []
        seen: set[str] = set()
        for source in sources:
            for entry in _coerce_artifact_list(source):
                candidate = _normalize_artifact_value(entry)
                if not candidate:
                    continue
                key = candidate.lower()
                if key in seen:
                    continue
                seen.add(key)
                normalized.append(candidate)
        return normalized

    def _explicit_requires_unity_flag(self) -> Optional[bool]:
        for key in ("Requires Unity Log", "requires_unity_log", "Require Unity Log", "require_unity_log"):
            if key in self.metadata:
                parsed = _parse_optional_bool(self.metadata.get(key))
                if parsed is not None:
                    return parsed
        return None

def _resolve_execution_mode(metadata: Dict[str, Any]) -> str:
    if not metadata:
        return _DEFAULT_EXECUTION_MODE
    for key in ("execution_mode", "Execution Mode", "executionMode"):
        if key in metadata:
            return _normalize_execution_mode_value(metadata.get(key))
    return _DEFAULT_EXECUTION_MODE


def _normalize_execution_mode_value(value: Any) -> str:
    if value is None:
        return _DEFAULT_EXECUTION_MODE
    text = str(value).strip()
    if not text:
        return _DEFAULT_EXECUTION_MODE
    normalized = text.lower().replace("-", "_").replace(" ", "")
    return _EXECUTION_MODE_ALIASES.get(normalized, _DEFAULT_EXECUTION_MODE)


def load_contract(path: Path) -> Contract:
    text = path.read_text(encoding="utf-8")
    metadata, body = _extract_front_matter(text)
    return Contract(path=path, metadata=metadata, body=body)


def _extract_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    text = text.lstrip()
    if not text.startswith("---"):
        return {}, text
    _, _, remainder = text.partition("---\n")
    yaml_block, _, body = remainder.partition("---\n")
    metadata = yaml.safe_load(yaml_block) or {}
    return metadata, body.strip()


def write_contract_copy(source: Path, destination: Path) -> None:
    safe_write_text(destination, source.read_text(encoding="utf-8"))
