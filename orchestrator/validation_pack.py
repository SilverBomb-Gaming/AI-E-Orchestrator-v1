#!/usr/bin/env python3
"""Validation Pack loader and executor for Night Cycle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from .config import OrchestratorConfig
from .runner import TaskResult
from .utils import ensure_dir, write_json


@dataclass
class PackTaskDefinition:
    task_id: str
    title: str
    contract_path: str
    scenario: str
    notes: str = ""
    status_sequence: List[str] = field(default_factory=list)

    def as_task_record(self) -> Dict[str, object]:
        return {
            "id": self.task_id,
            "title": self.title,
            "status": "pending",
            "contract_path": self.contract_path,
            "agents": ["builder", "qa", "auditor"],
            "hold_state": None,
        }


@dataclass
class ValidationPack:
    pack_id: str
    tasks: List[PackTaskDefinition]

    @property
    def task_map(self) -> Dict[str, PackTaskDefinition]:
        return {task.task_id: task for task in self.tasks}


@dataclass
class PackRunContext:
    pack: ValidationPack
    task_supplier: Callable[[], Iterable[Dict[str, object]]]
    executor: Callable[[Dict[str, object]], Optional[TaskResult]]
    cleanup: Callable[[], None]
    tasks: List[Dict[str, object]]


class ValidationPackLoader:
    MANIFEST_NAME = "pack_manifest.json"

    def __init__(self, pack_root: Path) -> None:
        self.pack_root = pack_root

    def load(self, *, pack_id_override: Optional[str] = None) -> ValidationPack:
        manifest_path = self.pack_root / self.MANIFEST_NAME
        if not manifest_path.exists():
            raise FileNotFoundError(f"Validation pack manifest missing: {manifest_path}")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        pack_id = pack_id_override or data.get("pack_id") or self.pack_root.name
        tasks = []
        for entry in data.get("tasks", []):
            task_id = str(entry.get("id", "")).strip()
            if not task_id:
                continue
            title = entry.get("title") or f"Validation Task {task_id}"
            contract_path = entry.get("contract_path") or ""
            scenario = str(entry.get("scenario", "allow")).strip().lower()
            notes = entry.get("notes", "")
            sequence = entry.get("status_sequence") or []
            tasks.append(
                PackTaskDefinition(
                    task_id=task_id,
                    title=title,
                    contract_path=contract_path,
                    scenario=scenario,
                    notes=notes,
                    status_sequence=[str(status).upper() for status in sequence],
                )
            )
        if not tasks:
            raise ValueError(f"Validation pack at {self.pack_root} does not define any tasks.")
        return ValidationPack(pack_id=pack_id, tasks=tasks)


class ValidationPackExecutor:
    def __init__(
        self,
        config: OrchestratorConfig,
        pack: ValidationPack,
        cycle_id: str,
    ) -> None:
        self.config = config
        self.pack = pack
        self.cycle_id = cycle_id
        self.state: Dict[str, int] = {task.task_id: 0 for task in pack.tasks}

    def __call__(self, task: Dict[str, object]) -> Optional[TaskResult]:
        task_id = str(task.get("id", "UNKNOWN"))
        definition = self.pack.task_map.get(task_id)
        if not definition:
            raise KeyError(f"Task {task_id} not defined in validation pack {self.pack.pack_id}.")
        self.state[task_id] += 1
        attempt_index = self.state[task_id]
        status_sequence = definition.status_sequence or [self._status_for_scenario(definition.scenario)]
        status = status_sequence[min(attempt_index - 1, len(status_sequence) - 1)]
        gate_status = status
        run_id = f"{self.cycle_id}_{task_id}_attempt{attempt_index:02d}"
        run_dir = self.config.runs_dir / run_id
        ensure_dir(run_dir)
        gate_report = {
            "overall_status": gate_status,
            "overall_score": 1.0 if gate_status == "ALLOW" else 0.0,
            "gates": [
                {
                    "name": "validation_pack",
                    "status": gate_status,
                    "score": 1.0 if gate_status == "ALLOW" else 0.0,
                    "reasons": [definition.notes or f"Scenario {definition.scenario}"],
                }
            ],
            "policy": {
                "verdict": gate_status,
                "allowed": gate_status == "ALLOW",
                "violations": [] if gate_status == "ALLOW" else [
                    {
                        "rule": "validation_pack",
                        "detail": definition.notes or f"Scenario {definition.scenario}",
                        "evidence": definition.task_id,
                        "severity": "info" if gate_status == "ASK" else "hard",
                    }
                ],
                "risk_score": 0.0 if gate_status == "ALLOW" else 1.0,
            },
            "gates_count": 1,
        }
        write_json(run_dir / "gate_report.json", gate_report)
        return TaskResult(
            task_id=task_id,
            run_id=run_id,
            run_dir=run_dir,
            gate_report=gate_report,
            command_results=[],
            status=gate_status,
        )

    @staticmethod
    def _status_for_scenario(scenario: str) -> str:
        mapping = {
            "allow": "ALLOW",
            "ask": "ASK",
            "deny": "BLOCK",
            "timeout": "FAILED",
            "retry_exhaust": "FAILED",
        }
        return mapping.get(scenario, "FAILED")


def prepare_pack_context(
    *,
    config: OrchestratorConfig,
    pack_path: Path,
    pack_mode: str,
    cycle_id: str,
    pack_id_override: Optional[str] = None,
) -> PackRunContext:
    loader = ValidationPackLoader(pack_path)
    pack = loader.load(pack_id_override=pack_id_override)
    normalized_mode = pack_mode or "snapshot"
    if normalized_mode != "snapshot":
        raise SystemExit("Only snapshot pack mode is supported in v1.1; use --pack-mode snapshot.")
    task_records = [task.as_task_record() for task in pack.tasks]

    def supplier() -> Iterable[Dict[str, object]]:
        return task_records
    executor = ValidationPackExecutor(config=config, pack=pack, cycle_id=cycle_id)

    def cleanup() -> None:
        return None

    return PackRunContext(
        pack=pack,
        task_supplier=supplier,
        executor=executor,
        cleanup=cleanup,
        tasks=task_records,
    )
