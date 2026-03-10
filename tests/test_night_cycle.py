import copy
import json
from pathlib import Path
from typing import Dict, List

import pytest

from orchestrator.night_cycle import CycleOptions, NightCycle
from orchestrator.runner import TaskResult, TaskRunner


FIXTURE_DIR = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.fast


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def now(self) -> float:
        self.current += 1.0
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += max(seconds, 0.0)


class FakeQueue:
    def __init__(self, payload: Dict[str, object]) -> None:
        tasks = payload.get("tasks", [])
        self.tasks = copy.deepcopy(tasks) if isinstance(tasks, list) else []

    def all_tasks(self):
        return self.tasks

    def mark_status(self, task_id: str, status: str) -> None:
        for task in self.tasks:
            if task.get("id") == task_id:
                task["status"] = status
                break


class SequencedExecutor:
    def __init__(self, tmp_path: Path, queue: FakeQueue, plan: Dict[str, List[str]]) -> None:
        self.tmp_path = tmp_path
        self.queue = queue
        self.plan = {task_id: list(statuses) for task_id, statuses in plan.items()}
        self.counter = 0

    def __call__(self, task):
        task_id = task.get("id", "UNKNOWN")
        sequence = self.plan.get(task_id)
        if not sequence:
            raise AssertionError(f"No execution plan for task {task_id}")
        status = sequence.pop(0)
        self.counter += 1
        run_id = f"20260227_00000{self.counter}_{task_id}"
        run_dir = self.tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        result = TaskResult(
            task_id=task_id,
            run_id=run_id,
            run_dir=run_dir,
            gate_report={"overall_status": status, "gates": []},
            command_results=[],
            status=status,
        )
        if status.upper() == "ALLOW":
            self.queue.mark_status(task_id, "completed")
        return result


class AllowlistFailureExecutor:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.calls = 0

    def __call__(self, task):
        self.calls += 1
        task_id = task.get("id", "UNKNOWN")
        run_id = f"allowlist_{self.calls:02d}_{task_id}"
        run_dir = self.tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        reason = (
            f"Task {task_id} encountered an unexpected error: Command 'Generate Movement Feature Report'"
            " is not on the allowlist (tests/allowlist.json)."
        )
        gate_report = {
            "overall_status": "BLOCK",
            "overall_score": 0.0,
            "gates": [
                {
                    "name": "scheduler",
                    "status": "BLOCK",
                    "score": 0.0,
                    "reasons": [reason],
                }
            ],
            "policy": {
                "verdict": "BLOCK",
                "allowed": False,
                "violations": [
                    {
                        "rule": "allowlist",
                        "detail": "Command 'Generate Movement Feature Report' is not on the allowlist.",
                        "evidence": "scheduler",
                        "severity": "hard",
                    }
                ],
            },
        }
        return TaskResult(
            task_id=task_id,
            run_id=run_id,
            run_dir=run_dir,
            gate_report=gate_report,
            command_results=[],
            status="FAILED",
        )


class AlwaysFailExecutor:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.calls = 0

    def __call__(self, task):
        self.calls += 1
        task_id = task.get("id", "UNKNOWN")
        run_id = f"alwaysfail_{self.calls:02d}_{task_id}"
        run_dir = self.tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        gate_report = {
            "overall_status": "BLOCK",
            "overall_score": 0.0,
            "gates": [
                {
                    "name": "scheduler",
                    "status": "BLOCK",
                    "score": 0.0,
                    "reasons": [f"Attempt {self.calls} failed"],
                }
            ],
            "policy": {"verdict": "BLOCK", "allowed": False, "violations": []},
        }
        return TaskResult(
            task_id=task_id,
            run_id=run_id,
            run_dir=run_dir,
            gate_report=gate_report,
            command_results=[],
            status="FAILED",
        )


def load_queue(name: str) -> Dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_dry_run_plans_tasks_without_execution(cycle_config, tmp_path):
    payload = load_queue("queue_with_pending_then_completed.json")
    queue = FakeQueue(payload)
    clock = FakeClock()
    options = CycleOptions(
        max_runs=5,
        max_minutes=30,
        stop_on_ask=True,
        stop_on_deny=True,
        retry_per_task=0,
        cooldown_seconds=0,
        dry_run=True,
    )

    def executor(_):
        raise AssertionError("Dry run should not execute tasks")

    cycle = NightCycle(
        config=cycle_config,
        task_supplier=queue.all_tasks,
        executor=executor,
        options=options,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    exit_code = cycle.run()
    assert exit_code == 0
    assert any(record.get("outcome") == "PLANNED" for record in cycle.records)
    run_index_path = cycle_config.root_dir / "runs_index.jsonl"
    assert not run_index_path.exists()
    report_paths = list((cycle_config.root_dir / "reports").glob("night_cycle_*.md"))
    assert report_paths, "Expected summary report to be written."
    assert "DRY RUN" in report_paths[0].read_text(encoding="utf-8")


def test_cycle_stops_on_needs_approval(cycle_config, tmp_path):
    payload = load_queue("queue_first_needs_approval.json")
    queue = FakeQueue(payload)
    clock = FakeClock()
    options = CycleOptions(stop_on_ask=True, cooldown_seconds=0)

    def executor(_):
        raise AssertionError("needs_approval tasks should not execute")

    cycle = NightCycle(
        config=cycle_config,
        task_supplier=queue.all_tasks,
        executor=executor,
        options=options,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    exit_code = cycle.run()
    assert exit_code == 1
    matching = [record for record in cycle.records if record.get("outcome") == "BLOCKED_NEEDS_APPROVAL"]
    assert matching, "Expected a needs-approval block record."
    run_index_path = cycle_config.root_dir / "runs_index.jsonl"
    assert run_index_path.exists(), "Night cycle should log blockers to the run index."
    lines = run_index_path.read_text(encoding="utf-8").strip().splitlines()
    last_entry = json.loads(lines[-1])
    assert last_entry["outcome"] == "BLOCKED_NEEDS_APPROVAL"


def test_retry_and_max_runs_limit(cycle_config, tmp_path):
    payload = load_queue("queue_with_pending_then_completed.json")
    queue = FakeQueue(payload)
    clock = FakeClock()
    options = CycleOptions(
        max_runs=2,
        retry_per_task=1,
        cooldown_seconds=0,
        stop_on_ask=True,
        stop_on_deny=True,
    )
    plan = {"0001": ["FAILED", "ALLOW"], "0002": ["ALLOW"]}
    executor = SequencedExecutor(tmp_path, queue, plan)
    cycle = NightCycle(
        config=cycle_config,
        task_supplier=queue.all_tasks,
        executor=executor,
        options=options,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    exit_code = cycle.run()
    assert exit_code == 0
    assert executor.counter == 2, "Second task should be deferred due to max_runs limit."
    success_records = [record for record in cycle.records if record.get("outcome") == "SUCCESS_ALLOW"]
    assert success_records, "Expected at least one successful record."
    # Task 0002 remains pending because limit prevented its execution
    remaining = [task for task in queue.tasks if task.get("id") == "0002"][0]
    assert remaining["status"] == "pending"
    run_index_path = cycle_config.root_dir / "runs_index.jsonl"
    lines = run_index_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_policy_failure_stops_without_retry(cycle_config, tmp_path):
    payload = load_queue("queue_with_pending_then_completed.json")
    queue = FakeQueue(payload)
    queue.tasks = queue.tasks[:1]
    clock = FakeClock()
    options = CycleOptions(
        max_runs=3,
        retry_per_task=2,
        cooldown_seconds=0,
        stop_on_deny=True,
    )
    executor = AllowlistFailureExecutor(tmp_path)
    cycle = NightCycle(
        config=cycle_config,
        task_supplier=queue.all_tasks,
        executor=executor,
        options=options,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    exit_code = cycle.run()
    assert exit_code == 1
    assert executor.calls == 1
    policy_records = [
        record
        for record in cycle.records
        if record.get("task_id") == "0001" and record.get("outcome") == "FAILED_POLICY"
    ]
    assert policy_records, "Expected FAILED_POLICY record for allowlist rejection"


def test_task_retry_cap_applies_across_cycle(cycle_config, tmp_path):
    payload = load_queue("queue_with_pending_then_completed.json")
    queue = FakeQueue(payload)
    queue.tasks = queue.tasks[:1]
    clock = FakeClock()
    options = CycleOptions(
        max_runs=5,
        retry_per_task=1,
        cooldown_seconds=0,
        stop_on_deny=False,
    )
    executor = AlwaysFailExecutor(tmp_path)
    cycle = NightCycle(
        config=cycle_config,
        task_supplier=queue.all_tasks,
        executor=executor,
        options=options,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    exit_code = cycle.run()
    assert exit_code == 0
    assert executor.calls == options.retry_per_task + 1
    exhaustion = [
        record
        for record in cycle.records
        if record.get("task_id") == "0001" and record.get("outcome") == "FAILED_MAX_RETRIES"
    ]
    assert exhaustion, "Expected FAILED_MAX_RETRIES record after retries exhausted"


def test_retention_disabled_skips_purge(cycle_config, monkeypatch):
    runner = TaskRunner(
        cycle_config,
        agent_registry=object(),
        workspace_manager=object(),
        gatekeeper=object(),
        retention_enabled=False,
    )
    monkeypatch.setattr(TaskRunner, "MAX_RUN_BUNDLES", 1)
    run_ids = ["20260227_010101_0001", "20260227_010102_0002"]
    for run_id in run_ids:
        path = cycle_config.runs_dir / run_id
        path.mkdir(parents=True, exist_ok=True)
    info = runner._apply_retention(run_ids[-1])
    assert info["deleted"] == []
    assert info["kept"] == len(run_ids)
    for run_id in run_ids:
        assert (cycle_config.runs_dir / run_id).exists()

