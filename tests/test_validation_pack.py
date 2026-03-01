import json
from pathlib import Path
from typing import List

import pytest

from orchestrator.night_cycle import CycleOptions, NightCycle
from orchestrator.validation_pack import prepare_pack_context


ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "contracts" / "validation_pack"


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def now(self) -> float:
        self.current += 1.0
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += max(seconds, 0.0)


@pytest.mark.parametrize("scenario_filter, expected_outcome", [
    ("V002", "BLOCKED_NEEDS_APPROVAL"),
    ("V003", "FAILED"),
])
def test_validation_pack_snapshot_stops_on_blockers(cycle_config, tmp_path, scenario_filter, expected_outcome):
    original_queue = {"tasks": [{"id": "0001", "status": "pending"}]}
    ensure_parent = cycle_config.queue_path.parent
    ensure_parent.mkdir(parents=True, exist_ok=True)
    cycle_config.queue_path.write_text(json.dumps(original_queue), encoding="utf-8")
    cycle_id = "packtest"
    context = prepare_pack_context(
        config=cycle_config,
        pack_path=PACK_DIR,
        pack_mode="snapshot",
        cycle_id=cycle_id,
        pack_id_override="validation-pack-test",
    )
    clock = FakeClock()
    options = CycleOptions(
        max_runs=2,
        max_minutes=5,
        stop_on_ask=True,
        stop_on_deny=True,
        retry_per_task=0,
        cooldown_seconds=0,
        task_filter=scenario_filter,
    )
    cycle = NightCycle(
        config=cycle_config,
        task_supplier=context.task_supplier,
        executor=context.executor,
        options=options,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
        cycle_id=cycle_id,
        pack_id=context.pack.pack_id,
        pack_mode="snapshot",
        pack_tasks=context.tasks,
    )
    exit_code = cycle.run()
    context.cleanup()
    if expected_outcome == "BLOCKED_NEEDS_APPROVAL":
        assert exit_code == 1
    queue_after = json.loads(cycle_config.queue_path.read_text(encoding="utf-8"))
    assert queue_after == original_queue
    outcomes = [record.get("outcome") for record in cycle.records if record]
    assert expected_outcome in outcomes


def test_validation_pack_retry_respects_limit(cycle_config, tmp_path):
    cycle_id = "retry-test"
    context = prepare_pack_context(
        config=cycle_config,
        pack_path=PACK_DIR,
        pack_mode="snapshot",
        cycle_id=cycle_id,
    )
    clock = FakeClock()
    options = CycleOptions(
        max_runs=5,
        max_minutes=5,
        stop_on_ask=True,
        stop_on_deny=True,
        retry_per_task=2,
        cooldown_seconds=0,
        task_filter="V005",
    )
    cycle = NightCycle(
        config=cycle_config,
        task_supplier=context.task_supplier,
        executor=context.executor,
        options=options,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
        cycle_id=cycle_id,
        pack_id=context.pack.pack_id,
        pack_mode="snapshot",
        pack_tasks=context.tasks,
    )
    exit_code = cycle.run()
    context.cleanup()
    assert exit_code == 1  # stop_on_deny triggers after retries exhaust
    attempts: List[int] = [
        record["attempt"]
        for record in cycle.records
        if record.get("task_id") == "V005" and record.get("outcome") == "FAILED"
    ]
    assert len(attempts) == options.retry_per_task + 1


def test_validation_pack_dry_run_plans_tasks(cycle_config):
    context = prepare_pack_context(
        config=cycle_config,
        pack_path=PACK_DIR,
        pack_mode="snapshot",
        cycle_id="dry-run-pack",
    )
    clock = FakeClock()
    options = CycleOptions(
        max_runs=3,
        max_minutes=5,
        dry_run=True,
        cooldown_seconds=0,
    )
    cycle = NightCycle(
        config=cycle_config,
        task_supplier=context.task_supplier,
        executor=context.executor,
        options=options,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
        cycle_id="dry-run-pack",
        pack_id=context.pack.pack_id,
        pack_mode="snapshot",
        pack_tasks=context.tasks,
    )
    exit_code = cycle.run()
    context.cleanup()
    assert exit_code == 0
    assert any(record.get("outcome") == "PLANNED" for record in cycle.records)
