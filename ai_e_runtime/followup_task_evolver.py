from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class InteractionFinding:
    finding_type: str
    summary: str
    evidence: str = ""
    severity: str = "medium"

    def to_payload(self) -> dict[str, str]:
        return {
            "finding_type": self.finding_type,
            "summary": self.summary,
            "evidence": self.evidence,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class EvolvedFollowupTask:
    title: str
    task_type: str
    priority: int
    rationale: str

    def to_payload(self) -> dict[str, object]:
        return {
            "title": self.title,
            "task_type": self.task_type,
            "priority": self.priority,
            "rationale": self.rationale,
        }


class FollowupTaskEvolver:
    """Deterministic rule-based follow-up task generation from interaction findings."""

    def evolve(self, findings: Iterable[InteractionFinding]) -> List[EvolvedFollowupTask]:
        evolved: List[EvolvedFollowupTask] = []
        seen_titles: set[str] = set()
        for finding in findings:
            for task in self._tasks_for_finding(finding):
                if task.title in seen_titles:
                    continue
                seen_titles.add(task.title)
                evolved.append(task)
        return evolved

    def _tasks_for_finding(self, finding: InteractionFinding) -> List[EvolvedFollowupTask]:
        normalized = f"{finding.finding_type} {finding.summary}".lower()
        tasks: List[EvolvedFollowupTask] = []
        if any(token in normalized for token in ("pathway", "route", "navigation", "confusing")):
            tasks.append(
                EvolvedFollowupTask(
                    title="Generate navigation cleanup task",
                    task_type="navigation_cleanup",
                    priority=25,
                    rationale=f"Navigation friction observed: {finding.summary}",
                )
            )
        if any(token in normalized for token in ("zombie never reaches player", "enemy never reaches player", "approach", "enemy idle")):
            tasks.append(
                EvolvedFollowupTask(
                    title="Generate enemy approach tuning task",
                    task_type="enemy_approach_tuning",
                    priority=20,
                    rationale=f"Enemy engagement gap observed: {finding.summary}",
                )
            )
        if any(token in normalized for token in ("weapon does not fire", "weapon bootstrap", "weapon failed", "no projectile")):
            tasks.append(
                EvolvedFollowupTask(
                    title="Generate weapon bootstrap repair task",
                    task_type="weapon_bootstrap_repair",
                    priority=15,
                    rationale=f"Weapon interaction failure observed: {finding.summary}",
                )
            )
        if any(token in normalized for token in ("stuck", "geometry", "collider", "collision snag")):
            tasks.append(
                EvolvedFollowupTask(
                    title="Generate collider cleanup task",
                    task_type="collider_cleanup",
                    priority=20,
                    rationale=f"Traversal obstruction observed: {finding.summary}",
                )
            )
        if any(token in normalized for token in ("damage", "health", "no hit feedback")):
            tasks.append(
                EvolvedFollowupTask(
                    title="Generate damage pipeline verification task",
                    task_type="damage_pipeline_verification",
                    priority=20,
                    rationale=f"Damage or health inconsistency observed: {finding.summary}",
                )
            )
        return tasks


__all__ = ["EvolvedFollowupTask", "FollowupTaskEvolver", "InteractionFinding"]