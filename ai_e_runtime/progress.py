from __future__ import annotations

from typing import Any, Mapping

PHASE_MODE = "phase_based"
PHASE_TOTAL = 7
PHASE_SEQUENCE = (
    ("intake", 1, "Intake"),
    ("policy_check", 2, "Policy Check"),
    ("approval_auto_decision", 3, "Approval / Auto-Decision"),
    ("execution", 4, "Execution"),
    ("validation", 5, "Validation"),
    ("rollback_finalization", 6, "Rollback / Finalization"),
    ("complete", 7, "Complete"),
)
_PHASE_MAP = {name: (index, label) for name, index, label in PHASE_SEQUENCE}


def phase_payload(
    phase_name: str,
    *,
    waiting_reason: str | None = None,
    blocked_reason: str | None = None,
    progress_percent: int | None = None,
) -> dict[str, Any]:
    index, label = _PHASE_MAP[phase_name]
    return {
        "session_phase": phase_name,
        "phase_index": index,
        "phase_total": PHASE_TOTAL,
        "phase_label": label,
        "progress_mode": PHASE_MODE,
        "progress_percent": progress_percent,
        "waiting_reason": waiting_reason,
        "blocked_reason": blocked_reason,
    }


def format_progress_line(payload: Mapping[str, Any]) -> str:
    phase_index = int(payload.get("phase_index", 0) or 0)
    phase_total = int(payload.get("phase_total", PHASE_TOTAL) or PHASE_TOTAL)
    phase_label = str(payload.get("phase_label") or "Unknown")
    bar = _render_bar(phase_index, phase_total)
    line = f"Progress: {bar} {phase_index}/{phase_total} - {phase_label}"
    waiting_reason = str(payload.get("waiting_reason") or "").strip()
    blocked_reason = str(payload.get("blocked_reason") or "").strip()
    if blocked_reason:
        return f"{line} (blocked: {blocked_reason})"
    if waiting_reason:
        return f"{line} (waiting: {waiting_reason})"
    return line


def _render_bar(phase_index: int, phase_total: int) -> str:
    safe_total = max(1, int(phase_total or PHASE_TOTAL))
    safe_index = max(0, min(int(phase_index or 0), safe_total))
    filled = "#" * safe_index
    empty = "-" * (safe_total - safe_index)
    return f"[{filled}{empty}]"


__all__ = ["PHASE_MODE", "PHASE_TOTAL", "PHASE_SEQUENCE", "format_progress_line", "phase_payload"]
