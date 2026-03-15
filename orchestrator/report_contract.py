from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

from .architecture_blueprint import required_response_sections


def format_operator_report(
    *,
    summary: str,
    facts: Iterable[str],
    assumptions: Iterable[str],
    recommendations: Iterable[str],
    timestamp: str,
) -> str:
    sections = [
        ("SUMMARY", _normalize_paragraph(summary)),
        ("FACTS", _normalize_bullets(facts)),
        ("ASSUMPTIONS", _normalize_bullets(assumptions)),
        ("RECOMMENDATIONS", _normalize_bullets(recommendations)),
        ("TIMESTAMP", _normalize_paragraph(timestamp)),
    ]
    blocks: List[str] = []
    for title, body in sections:
        blocks.append(title)
        blocks.append("")
        blocks.append(body)
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


@dataclass(frozen=True)
class ReportValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)


def validate_operator_report(text: str) -> ReportValidationResult:
    normalized = text.replace("\r\n", "\n")
    expected = required_response_sections()
    positions: list[tuple[str, int]] = []
    errors: list[str] = []
    for title in expected:
        marker = f"{title}\n"
        index = normalized.find(marker)
        if index == -1:
            errors.append(f"missing required section: {title}")
            continue
        positions.append((title, index))

    if len(positions) == len(expected):
        ordered_titles = [title for title, _ in sorted(positions, key=lambda item: item[1])]
        if ordered_titles != expected:
            errors.append("sections are not in the required order")
        last_title, last_position = sorted(positions, key=lambda item: item[1])[-1]
        if last_title != "TIMESTAMP":
            errors.append("TIMESTAMP must be the final section")
        else:
            trailing = normalized[last_position:].strip()
            lines = [line for line in trailing.split("\n") if line.strip()]
            if len(lines) < 2:
                errors.append("TIMESTAMP section must include a timestamp value")
    return ReportValidationResult(is_valid=not errors, errors=errors)


def _normalize_bullets(items: Iterable[str]) -> str:
    normalized = [str(item).strip() for item in items if str(item).strip()]
    if not normalized:
        return "- None"
    return "\n".join(f"- {item}" for item in normalized)


def _normalize_paragraph(value: str) -> str:
    text = str(value).strip()
    return text or "None"


__all__ = ["ReportValidationResult", "format_operator_report", "validate_operator_report"]