# Module Boundaries (Stability Core v1)

AI-E Orchestrator is converging on four long-lived domains. Locking the boundaries now keeps Stability Core lean and makes future splits predictable.

## 1. Core
- **Includes**: `orchestrator/` package, gate logic, regression/diff tooling, contract loading, retention policies, approvals store, workspace lifecycle, and policy enforcement.
- **Automation**: `orchestrator/night_cycle.py` lives here; Night Cycle drives unattended execution but never mutates adapters/workloads.
- **Responsibilities**: deterministic execution, evidence capture, queue consumption, gate scoring, and policy verdicts.
- **Excludes**: UI layers, incident tooling, workload-specific scripts, or adapters for third-party engines.

## 2. Ops
- **Includes**: `Tools/queue_ops.py`, `scripts/approve_run.py`, `scripts/operator_dashboard.py`, any future incident/runbook helpers, log summarizers, and CI health checks.
- **Responsibilities**: operator-facing recovery, approvals, dashboards, and maintenance scripts (backups, purges, unblock helpers).
- **Expectations**: may depend on Core data formats but must not change queue semantics (only use documented fields and guard-rails such as backups/dry-runs).

## 3. Adapters
- **Includes**: engine-specific harnesses (Unity Playmode, Blender, proprietary simulators), log parsers under `Tools/CI`, and validation harnesses under `Tools/PlaymodeHarness_QC/`.
- **Responsibilities**: translate Core contracts into engine/runtime invocations and emit deterministic markers so gates can reason about external tooling.
- **Future Split**: adapters become optional packages so projects can swap Unity for other stacks without touching Core/Ops.

## 4. Workloads
- **Includes**: workload repositories such as `BABYLON VER 2`, Unity scenes/assets, and any repo-specific automation stored under `workspaces/`.
- **Responsibilities**: provide code/assets that Core operates on. Workloads define contracts, supply Unity projects, and surface domain bugs.
- **Explicitly NOT Core**: workload repos stay outside AI-E Core, even if colocated in this mono-root today. Upgrades to workloads must not require Core renames, and vice versa.

Keeping these domains separate (conceptually now, physically later) preserves local-first guarantees while letting Ops/Adapters evolve independently of Stability Core.
