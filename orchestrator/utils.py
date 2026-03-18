from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable
from uuid import uuid4

from .time_utils import get_current_timestamp


def utc_timestamp(compact: bool = True) -> str:
    if compact:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return get_current_timestamp()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    temp_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.01)


def read_json(path: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not path.exists():
        return _clone_default(default)
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return _clone_default(default)
    if not raw.strip():
        return _clone_default(default)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[orchestrator] Warning: invalid JSON at {path}: {exc}")
        return _clone_default(default)


def _clone_default(default: Dict[str, Any] | None) -> Dict[str, Any]:
    if default is None:
        return {}
    if isinstance(default, dict):
        return default.copy()
    if hasattr(default, "copy"):
        try:
            return default.copy()
        except Exception:
            pass
    return {}


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
            files.add(line[6:].strip())
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


def append_live_event(payload: Dict[str, Any], root: Path | None = None) -> None:
    try:
        record = dict(payload or {})
    except TypeError:
        return
    if "ts_utc" not in record:
        record["ts_utc"] = get_current_timestamp()
    destination_root = Path(root) if root else Path(__file__).resolve().parents[1]
    destination = destination_root / "reports" / "live_events.jsonl"
    try:
        ensure_dir(destination.parent)
        with destination.open("a", encoding="utf-8") as handle:
            json.dump(record, handle)
            handle.write("\n")
    except Exception:
        # Event emission must never block orchestration.
        return
