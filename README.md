# AI-E Orchestrator v1

AI-E Orchestrator v1 is a local-first scheduler that executes overnight, auditable multi-agent workflows under the AI-E security operating system. Every task runs inside an isolated workspace that copies the target repository, executes a deterministic sequence of agent steps, captures artifacts, and emits gate scores before humans review the results each morning.

## Core Guarantees
- **Workspace isolation**: every task clones/copies the target repo into `workspaces/<task_id>/<timestamp>` before any command runs.
- **Written contracts only**: no workspace is created without a Markdown contract drafted from `contracts/templates/contract_template.md` and stored under `contracts/active/`.
- **Auditable artifacts**: each run records patches, logs, plans, gate verdicts, and summaries inside `runs/<timestamp>_<taskid>/`.
- **Gated outputs**: build/test/diff/policy gates emit `ALLOW`, `ASK`, or `BLOCK` outcomes with reasons; failed gates downgrade the run to "report only".
- **Local execution**: v1 never requires outbound network calls; agents operate on local repos only.

## Repository Layout
```
AI-E-Orchestrator/
  orchestrator/                # Python package that implements queue loading, runner, gates, reports
  agents/                      # Registry of agent profiles and prompt placeholders
  contracts/                   # Templated contracts plus active/completed/failed instances
  backlog/                     # Task queue metadata and frozen backlog notes
  scripts/                     # Entry-point PowerShell scripts for once/nightly execution
  runs/, workspaces/           # Timestamped artifacts and isolated repo copies (git-kept)
```

## Quick Start
1. Create and activate a Python 3.10+ virtual environment under `.venv-2` (the canonical interpreter used by the PowerShell entrypoints):
   ```powershell
   python -m venv .venv-2
   .\.venv-2\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -e .
   ```
3. Update `backlog/queue.json` with local repository paths and ensure the referenced contracts exist under `contracts/active/`.
4. Execute a single pass:
   ```powershell
   scripts/run_once.ps1
   ```
5. Inspect the newest folder under `runs/` for `summary.md`, `gate_report.json`, logs, and generated patches.

## Nightly Automation
Use `scripts/run_nightly.ps1` from Windows Task Scheduler to launch the orchestrator with the `--nightly` flag. The runner processes every pending task in `backlog/queue.json`, rotating artifacts by timestamp without overwriting prior evidence.

## Policy Engine
Every run produces a policy decision alongside build/test/diff/log gates. The policy layer enforces network bans, patch size limits, forbidden path lists, and agent-profile permissions before a run can advance:
- `policy.verdict` is always `ALLOW`, `ASK`, or `BLOCK` and is mirrored into `gate_report.json`, `summary.md`, and `run_meta.json`.
- Violations enumerate the rule, detail, and evidence reference so auditors can determine why enforcement triggered.
- Contracts may declare `Policy Overrides` to request additional permissions (for example, a higher LOC budget), but the policy engine validates the override against agent capabilities before honoring it.

Operator approvals for `ASK` verdicts are design-documented in [docs/override_protocol.md](docs/override_protocol.md) so that future UI hooks can resume halted tasks only after explicit authorization.

## Command Allowlist
Every shell command declared in a contract must be explicitly allowed. The runner enforces a default-deny policy backed by [backlog/command_allowlist.json](backlog/command_allowlist.json):
- `exact`: lower-cased, whitespace-normalized commands that must match the `shell` field verbatim.
- `prefix`: trusted prefixes (for example `powershell.exe -nologo -noprofile -file scripts/`) that may precede arguments such as script names.

Populate the allowlist before scheduling work; otherwise runs will fail with a `PermissionError` before any subprocess executes. The file is created automatically during bootstrap so operators just need to edit it under version control.

## Fix Loop Controller & Regression Gate
Contracts may opt into the bounded fix-loop controller by adding a `Fix Loop Controller` metadata block with `Enabled: true`. Safe defaults permit two attempts or 20 minutes of wall time, and the orchestrator will never exceed three attempts or 30 minutes even if a contract asks for more. Each iteration produces a `fix_loop_report.json` (now including `stop_reason`, per-attempt `no_change_detected`, and a top-level `retry_performed` flag) alongside normal run artifacts.

Regression behavior is configurable per contract via an optional `Regression` block:

```
Regression:
   NoChangeVerdict: ALLOW   # or ASK/BLOCK
```

During diffing, the orchestrator compares the current bundle against the most recent run:

- **No change detected**: obeys `NoChangeVerdict` (defaults to `ALLOW`). When `ALLOW`, the fix loop records `stop_reason: no_change_detected`, skips additional attempts, and keeps the queue in the `completed` state with no operator action required.
- **Soft regressions** (new signatures, higher error count, risk spikes, or patch explosions) downgrade the regression gate to `ASK`, place the queue entry into `needs_approval`, and pause unattended execution until an operator records approval.
- **Hard regressions** (policy/pipeline violations) emit `BLOCK` and mark the queue item as `failed`.

Every `diff_report.json` and `run_meta.json` now includes `no_change_detected` plus the resolved regression configuration so future tooling (dashboards, overrides) can display or adjust the policy.

## Queue Status Values
Queue entries now distinguish between execution outcomes:

- `pending`: ready to run
- `running`: actively executing
- `completed`: most recent run allowed all gates (including no-change scenarios)
- `needs_approval`: gated on an `ASK` verdict and awaiting `approve_run.py` / dashboard approval
- `failed`: hard failures (BLOCK verdicts or runtime exceptions)
- `aborted`: operator manually halted the task via queue tooling

## Operator Tooling
- `python scripts/approve_run.py --list` prints queued approvals. Add a new approval with `--task-id`, `--run-id`, and optional `--notes`; the CLI writes through the same `OperatorApprovalStore` used by the runner.
- `python scripts/operator_dashboard.py` launches a lightweight Tkinter UI that shows queue progress, recent artifacts, pending approvals, and exposes a one-click "Approve" button wired to the same store.
- `python tools/queue_ops.py list|reset|resume|abort|delete|unblock` provides guard-railed queue recovery actions. Every write makes a timestamped backup of `backlog/queue.json` (and `approvals.json` when touched), all mutating commands accept `--dry-run`, and destructive flags such as `--purge-runs` require `--force` so operators can safely recover stuck tasks without hand-editing JSON.
- `python tools/verify_stability_core.py` runs the local file/layout verifier (add `--json` for machine-readable output) so operators can confirm Stability Core v1 prerequisites before queue work begins.

These tools eliminate ad-hoc JSON editing while keeping the audit trail centralized.

## Current Limitations
- Agents are deterministic placeholders; hook them up to LLM backends later.
- Repository copies use `shutil.copytree` by default; replace with lightweight worktrees if needed.
- Gate heuristics are conservative and rely on metadata from agent profiles and contracts.

Contributions should maintain local-only execution, preserve evidence immutability, and extend gates/contracts before expanding agent autonomy.
