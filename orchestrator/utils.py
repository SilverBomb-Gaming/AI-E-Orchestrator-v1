from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable


def utc_timestamp(compact: bool = True) -> str:
    fmt = "%Y%m%d_%H%M%S" if compact else "%Y-%m-%dT%H:%M:%SZ"
    return datetime.now(timezone.utc).strftime(fmt)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not path.exists():
        return default.copy() if default else {}
    return json.loads(path.read_text(encoding="utf-8"))


def safe_write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def parse_patch_stats(patch_text: str) -> Dict[str, Any]:
    files: set[str] = set()
    insertions = 0
    deletions = 0
    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            files.add(line[6:].strip())
        elif line.startswith("--- a/"):
            continue
        elif line.startswith("+") and not line.startswith("+++ "):
            insertions += 1
        elif line.startswith("-") and not line.startswith("--- "):
            deletions += 1
    return {
        "files_changed": len(files),
        "insertions": insertions,
        "deletions": deletions,
        "touched_files": sorted(files),
        "loc_delta": insertions + deletions,
    }


def within_scope(paths: Iterable[str], allowlist: Iterable[str]) -> bool:
    normalized_allowlist = [scope.strip("/") for scope in allowlist]
    for path in paths:
        normalized = path.strip("/")
        if not any(normalized.startswith(prefix) for prefix in normalized_allowlist):
            return False
    return True
