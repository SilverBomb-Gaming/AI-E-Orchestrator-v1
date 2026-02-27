# Operator Override Protocol (Design Draft)

Phase E introduces a mandatory human-in-the-loop checkpoint for any task that ends in an `ASK` verdict. The runtime changes implemented in this phase halt the queue whenever a prior task is still pending operator review. This document captures the proposed mechanism for resuming blocked work without modifying the scheduler core.

## Goals
- Preserve forensic evidence for every halted run bundle.
- Require an explicit, auditable approval signal before continuing.
- Allow operators to scope approvals to a single run (bundle_id) and task.
- Keep the implementation local-first so it can evolve into UI integrations later.

## Approval Artifact
Operators create `backlog/operator_approval.json` when they decide to resume a halted task. The JSON document is append-only and keyed by `run_id`:
```json
{
  "approvals": [
    {
      "run_id": "20260218_014445_0002",
      "task_id": "0002",
      "verdict": "ASK",
      "approved_by": "initials",
      "approved_at": "2026-02-18T02:30:00Z",
      "notes": "Validated policy violations; safe to resume",
      "expires_after": "2026-02-19T00:00:00Z"
    }
  ]
}
```

## Scheduler Integration (future work)
1. During startup the queue loader reads `operator_approval.json` (if present) and stores valid approvals in memory.
2. When a task finishes with an `ASK` verdict the queue is halted until a matching approval exists for that `run_id` and `task_id`.
3. A follow-up invocation of `run_once`/`run_nightly` checks for approvals before dequeuing the next task. If the approval exists and is unexpired, the queue transition occurs and the approval is marked as consumed.
4. Approvals are one-time use and must be regenerated for each new `ASK` verdict to prevent stale overrides.

## Operational Playbook
1. Operator reviews `runs/<run_id>/summary.md`, `gate_report.json`, and `policy` violations.
2. If the run should continue, they append an approval entry as shown above.
3. They rerun `scripts/run_once.ps1` or `scripts/run_nightly.ps1` (depending on workflow). The scheduler acknowledges the approval, logs the decision in the next `summary.md`, and proceeds to the next pending task.
4. If the operator declines, they update `backlog/queue.json` to keep the task in `failed` state or remove it entirely.

This protocol keeps the override signal out of the main queue file, maintains an immutable audit trail, and gives future UI layers a clean contract to build on.
