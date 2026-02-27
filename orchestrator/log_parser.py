from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .utils import ensure_dir

_ERROR_CODE_RE = re.compile(r"\bcs\d{4}\b", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(r"^\[[^\]]+\]\s*")


@dataclass
class _SignatureStats:
    count: int = 0
    first_line: Optional[int] = None
    last_line: Optional[int] = None

    def update(self, line_number: int) -> None:
        self.count += 1
        if self.first_line is None or line_number < self.first_line:
            self.first_line = line_number
        if self.last_line is None or line_number > self.last_line:
            self.last_line = line_number


class UnityLogParser:
    def __init__(self, *, max_entries: int = 10, max_message_chars: int = 200) -> None:
        self.max_entries = max_entries
        self.max_message_chars = max_message_chars

    def parse(self, log_path: Path) -> Dict[str, object]:
        if not log_path.exists():
            raise FileNotFoundError(f"Unity log missing at {log_path}")
        log_size = log_path.stat().st_size
        error_stats: Dict[str, _SignatureStats] = {}
        warning_stats: Dict[str, _SignatureStats] = {}
        error_count = 0
        warning_count = 0
        first_error_line: int | None = None
        last_error_line: int | None = None
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for idx, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                classification = self._classify_line(line)
                if classification == "error":
                    error_count += 1
                    if first_error_line is None:
                        first_error_line = idx
                    last_error_line = idx
                    signature = self._signature(line)
                    if signature:
                        error_stats.setdefault(signature, _SignatureStats()).update(idx)
                elif classification == "warning":
                    warning_count += 1
                    signature = self._signature(line)
                    if signature:
                        warning_stats.setdefault(signature, _SignatureStats()).update(idx)
        summary: Dict[str, object] = {
            "log_path": log_path.name,
            "log_size_bytes": log_size,
            "error_count": error_count,
            "warning_count": warning_count,
            "unique_error_count": len(error_stats),
            "unique_warning_count": len(warning_stats),
            "top_errors": self._format_top(error_stats),
            "top_warnings": self._format_top(warning_stats),
            "first_error_line": first_error_line,
            "last_error_line": last_error_line,
        }
        return summary

    def write_summary(self, log_path: Path, destination: Path, *, max_bytes: int = 200_000) -> Dict[str, object]:
        summary = self.parse(log_path)
        ensure_dir(destination.parent)
        text = json.dumps(summary, indent=2)
        encoded = text.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError(
                f"Unity log summary exceeds {max_bytes} bytes (actual {len(encoded)}); reduce log noise before retry."
            )
        destination.write_bytes(encoded)
        return summary

    def _classify_line(self, line: str) -> str | None:
        lowered = line.lower()
        if "warning" in lowered and "error" not in lowered and "exception" not in lowered:
            return "warning"
        if "error" in lowered or "exception" in lowered or _ERROR_CODE_RE.search(line):
            return "error"
        return None

    def _signature(self, line: str) -> str:
        stripped = _TIMESTAMP_RE.sub("", line)
        stripped = stripped.strip()
        if not stripped:
            stripped = line.strip()
        if len(stripped) > self.max_message_chars:
            stripped = stripped[: self.max_message_chars].rstrip()
        return stripped

    def _format_top(self, stats: Dict[str, _SignatureStats]) -> List[Dict[str, object]]:
        if not stats:
            return []
        sorted_items = sorted(stats.items(), key=lambda item: (-item[1].count, item[0]))
        top_items = sorted_items[: self.max_entries]
        formatted: List[Dict[str, object]] = []
        for message, record in top_items:
            formatted.append(
                {
                    "message": message,
                    "count": record.count,
                    "first_line": record.first_line,
                    "last_line": record.last_line,
                }
            )
        return formatted
