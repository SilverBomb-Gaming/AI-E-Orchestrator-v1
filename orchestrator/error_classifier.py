from __future__ import annotations

import re
from typing import Any, Dict, List

from .utils import utc_timestamp


class UnityErrorClassifier:
    """Categorize Unity log error signatures for regression decisions."""

    DEFAULT_NOISE_PATTERNS: tuple[str, ...] = (
        "curl error 42",
        "error: access token is unavailable",
        "logassemblyerrors",
    )
    ACTIONABLE_KEYWORDS: tuple[str, ...] = (
        "exception",
        "missing script",
        "failed to load",
        "could not load",
        "cs",
        "nullreference",
        "argument",
        "invalidoperation",
        "stacktrace",
        "crash",
        "assert",
    )
    _CS_ERROR_RE = re.compile(r"\bcs\d{4}\b", re.IGNORECASE)

    def __init__(
        self,
        noise_patterns: List[str] | None = None,
        *,
        treat_unknown_as_actionable: bool = True,
    ) -> None:
        patterns = noise_patterns or []
        normalized = [pattern.strip().lower() for pattern in patterns if pattern.strip()]
        self.noise_patterns = tuple({*normalized, *self.DEFAULT_NOISE_PATTERNS})
        self.treat_unknown_as_actionable = treat_unknown_as_actionable

    def classify(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        entries = summary.get("top_errors", []) or []
        actionable: List[str] = []
        noise: List[str] = []
        unknown: List[str] = []
        signatures: List[Dict[str, Any]] = []
        actionable_error_total = 0
        for entry in entries:
            message = str(entry.get("message", "")).strip()
            normalized = message.lower()
            count = int(entry.get("count", 0) or 0)
            first_line = entry.get("first_line")
            last_line = entry.get("last_line")
            category = self._categorize(message, normalized)
            signatures.append(
                {
                    "message": message,
                    "category": category,
                    "count": count,
                    "first_line": first_line,
                    "last_line": last_line,
                }
            )
            if category == "noise":
                noise.append(message)
            elif category == "actionable":
                actionable.append(message)
                actionable_error_total += count
            else:
                unknown.append(message)
                if self.treat_unknown_as_actionable:
                    actionable_error_total += count
        payload = {
            "generated_at": utc_timestamp(compact=False),
            "summary_log_path": summary.get("log_path"),
            "total_error_count": summary.get("error_count", 0),
            "total_error_signatures": len(entries),
            "signatures": signatures,
            "actionable_signatures": actionable,
            "noise_signatures": noise,
            "unknown_signatures": unknown,
            "actionable_error_count": actionable_error_total if entries else 0,
            "unknown_considered_actionable": self.treat_unknown_as_actionable,
        }
        return payload

    def _categorize(self, original: str, normalized: str) -> str:
        if not normalized:
            return "unknown"
        if self._matches_noise(normalized):
            return "noise"
        if self._is_actionable(original, normalized):
            return "actionable"
        return "unknown"

    def _matches_noise(self, normalized: str) -> bool:
        return any(pattern in normalized for pattern in self.noise_patterns)

    def _is_actionable(self, original: str, normalized: str) -> bool:
        if self._CS_ERROR_RE.search(original):
            return True
        return any(keyword in normalized for keyword in self.ACTIONABLE_KEYWORDS)
