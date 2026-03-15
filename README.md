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
1. Use the validated interpreter at `E:\AI projects 2025\AI-E Orchestrator v1\.venv-2\Scripts\python.exe`. If VS Code prompts to create a new environment, do not create one for this repo; select the existing `.venv-2` interpreter instead.
2. Activate `.venv-2` if you want bare `python` in a shell to resolve to the validated interpreter:
   ```powershell
   .\.venv-2\Scripts\Activate.ps1
   ```
3. Install or refresh dependencies into the existing `.venv-2` only when needed:
   ```powershell
   .\.venv-2\Scripts\python.exe -m pip install -e .
   ```
4. Update `backlog/queue.json` with local repository paths and ensure the referenced contracts exist under `contracts/active/`.
5. Execute a single pass:
   ```powershell
   scripts/run_once.ps1
   ```
6. Inspect the newest folder under `runs/` for `summary.md`, `gate_report.json`, logs, and generated patches.
## Python Environment Policy
- This repo's validated interpreter is `E:\AI projects 2025\AI-E Orchestrator v1\.venv-2\Scripts\python.exe`.
- In VS Code, select the existing `.venv-2` interpreter if prompted. Do not create a new environment for this repo unless a future migration is explicitly documented.
- Run preflight, status, and orchestrator commands from `.venv-2` so the PowerShell entrypoints and Python tooling stay aligned.
- In shared umbrella workspaces, nested repo `.vscode` settings may be ignored. Prefer opening `E:\AI projects 2025\AI projects 2025.code-workspace` or the repo folder directly so this interpreter pin is applied consistently.
- For Copilot and operator automation, prefer explicit interpreter invocation (`.\.venv-2\Scripts\python.exe ...`) over bare `python`.
- Use `.\.venv-2\Scripts\python.exe .\scripts\show_python_env.py` for the direct Python check, or `powershell -ExecutionPolicy Bypass -File .\scripts\show_python_env.ps1` for a PowerShell-only fallback.
- This repo currently contains multiple `.venv*` folders; treat `.venv-2` as authoritative for the Option A workflow unless the README says otherwise.

## Option A â€” Entity Generation Pilot
The orchestrator now understands `entity_generation` contracts authored as JSON under `contracts/entities/`. When the queue references one of these contracts (for example `contracts/entities/zombie_basic.json` / `ENTITY_0001`), the runner routes execution through `orchestrator/entity_runner.py` instead of the traditional command list.

- **Contracts**: declare the entity metadata (`entity_name`, `entity_type`, category, required components/scripts, validation toggles, artifact list) plus standard fields such as `target_repo`, `allowed_scope`, and `execution_mode`. For `zombie_basic`, the contract also maps the Meshy GLB inputs, prefab output path, and the Unity launcher scripts needed for prefab + preview creation (`Tools/run_unity_create_zombie_prefab.ps1` and `Tools/run_unity_zombie_prefab_preview.ps1`).
- **Execution flow**: the entity runner now performs real Unity automation for the supported zombie laneâ€”invoking the prefab build script, validating the generated prefab, then running the preview probe to capture `zombie_prefab_preview.json/png`. All subprocess output is logged under `workspace/logs/` and mirrored into the run bundle alongside standard command metadata.
- **Unity harness**: the target repo ships with `Assets/AI_E_TestScenes/entity_test.unity`, a dedicated scene the harness can load while running play mode or preview probes. Additional harness scenes can be declared per-contract as future entity types come online.
- **Artifacts**: entity runs emit `entity/entity_summary.json`, `entity/entity_validation.json`, the prefab/preview artifacts, the preview PNG, `repeatability_report.json`, and the captured `Editor.log`. The orchestrator mirrors these into `runs/<run_id>/entity/` and records them in `gate_report.json` together with the raw `scripts/logs/zombie_prefab_*.json/png` files produced by the Unity scripts.
- **Logs & gating**: Unity logs are no longer synthesizedâ€”`run_unity_*` writes real Editor logs plus the existing `Tools/CI/unity_log_summary.json` and `unity_error_classification.json`, so the signal, regression, and play mode gates all see authentic data. Unsupported `entity_type` values return an explicit `unsupported` status instead of fabricating success.

This Option A foundation now reuses the proven zombie prefab pipeline, keeping the first entity lane honest while leaving room to stage additional categories without bypassing policy, workspace, or artifact guarantees.

### Entity Preflight Check
- Run `.\.venv-2\Scripts\python.exe scripts/preflight_entity_ready.py --contract contracts/entities/zombie_basic.json` before re-queuing ENTITY_0001. The script verifies `.venv-2`, queue metadata, entity contract shape, BABYLON repo paths, PowerShell launchers, log/artifact directories, Unity Editor resolution, and allowlist coverage, then emits a PASS/FAIL rollup (use `--json` for automation).
- Manual prerequisites the script cannot validate:
   - Sign in to the Unity Editor on this host and confirm the Babylon project opens without package prompts.
   - Keep `UNITY_EDITOR_EXE` or `Tools/unity_editor_path.txt` pointed at a licensed 6000.2.8f1 install.
   - Activate `.venv-2` in your shell (`.\.venv-2\Scripts\Activate.ps1`) so PowerShell entrypoints inherit the right interpreter.
   - Mount `E:/AI projects 2025/BABYLON VER 2` with read/write permissions and make sure large assets are synced locally.

### Checking Live Activity For Entity Runs
- Run `.\.venv-2\Scripts\python.exe scripts/status_entity_run.py --task-id ENTITY_0001 --json` to inspect the most recent bundle (use `--run-id` to target a specific bundle). The tool reports RUNNING/COMPLETED/PARTIAL/FAILED/STALLED/UNKNOWN states, surfaces missing finalization artifacts, and, when stalled, writes `runs/<run_id>/stuck_diagnostic.json` with the latest evidence.
- Interpretations:
   - **RUNNING**: Unity.exe detected or logs are still updatingâ€”wait before intervening.
   - **COMPLETED**: Gate report exists and resolved to ALLOW; `entity/entity_validation.json`, `report_last_run.md`, and `summary.md` are all present.
   - **PARTIAL/FAILED**: Outputs exist but gates are ASK/BLOCK or validation failed; review `gate_report.json`, `entity_validation.json`, and `report_last_run.md` inside the run bundle.
   - **STALLED**: No Unity process, logs stale past the threshold, and finalization artifacts missingâ€”the diagnostic JSON in the run folder calls out the suspected stage and evidence gaps.
- Manual inspection tips: open `workspaces/<task>/<timestamp>/logs/*.log` for live PowerShell output and `workspaces/<task>/<timestamp>/repo/scripts/logs/Editor.log` for raw Unity traces if deeper triage is needed.
- Old static logs viewed with `Get-Content -Wait` are not proof of a currently active run on their own; confirm with `.\.venv-2\Scripts\python.exe scripts/status_entity_run.py --task-id ENTITY_0001`, current log timestamps, and Unity process detection before assuming the workflow is still live.

### Repeatability & Determinism
- Every entity run now emits `entity/repeatability_report.json`. The report compares the freshly generated bundle with the prior ENTITY run, listing the fields inspected, whether they matched, and any mismatched values.
- Use `python -m orchestrator.repeatability --current runs/<latest> --previous runs/<baseline>` to regenerate a report manually or to point the tool at an arbitrary pair of bundles.
- The runner automatically injects the repeatability verdict back into `entity_validation.json -> repeatability`, so reporters, dashboards, and auditors can read a single file to see prefab/preview status *and* determinism evidence.
- When mismatches occur, the report enumerates the exact top-level fields (status, prefab paths, preview health, log buckets, cleanup hygiene) that drifted so Unity triage can focus on the failing stage.

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

## Three-Layer Architecture
- **Layer 1 â€” AI-E OS (Queue + Policy):** orchestrator daemons, policy gatekeepers, and contract metadata live here. They schedule work, enforce allowlists, and stamp decisions into immutable records.
- **Layer 2 â€” Workspace Execution Bubble:** each task receives a throwaway workspace cloned under `workspaces/<task>/<timestamp>`. All scripts, Unity CLI invocations, and artifact scrapes must stay inside this layer; it never mutates Layer 1 or the target repo directly.
- **Layer 3 â€” Target Simulation (Unity / Game Repo):** the BABYLON project plus Unity Editor runtime live here. Scripts such as `run_unity_create_zombie_prefab.ps1` interface with Layer 3 via controlled commands declared in the contract workflow.
- **Data Flow:** Layer 3 artifacts flow back to Layer 2 (logs, prefabs, probes), Layer 2 distills them into JSON/PNG bundles, and only finalized evidence crosses into Layer 1 for gating and archival. This separation guarantees deterministic replays and keeps queue metadata tamper-resistant.

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
- `.\.venv-2\Scripts\python.exe -m orchestrator.night_cycle --dry-run --max-runs 3 --pack contracts/validation_pack` runs the synthetic validation pack in snapshot mode, logging results into `runs_index.jsonl` and `reports/night_cycle_*.md` without mutating the main queue.
- `.\.venv-2\Scripts\python.exe -m orchestrator.night_cycle --max-runs 3 --max-minutes 10` performs a bounded depth run against the real queue (stopping on ASK/BLOCK by default). Use `--task-filter`, `--pack-id`, or `--cooldown-seconds` to further constrain automation.
- `python tools/verify_stability_core.py` runs the local file/layout verifier (add `--json` for machine-readable output) so operators can confirm Stability Core v1 prerequisites before queue work begins.

These tools eliminate ad-hoc JSON editing while keeping the audit trail centralized.

## Testing Profiles
- `pytest.mark.fast` covers validation logic, artifact inspectors, queue tooling, and repeatability utilities. Run them with `python -m pytest -m fast` to gate day-to-day edits in under five seconds.
- `pytest.mark.unity` is reserved for prefab creation, preview generation, and future integration probes that require the Unity editor or large assets. Trigger them explicitly with `python -m pytest -m unity` once the editor harness is available on the host.
- The default `python -m pytest` command honors these markers, so CI can run `-m fast` on every push and schedule Unity sweeps in a different lane without reconfiguring the suite.

## Timestamp Policy
- Every operator-facing Copilot report must use this exact top-to-bottom section order: `SUMMARY`, `FACTS`, `ASSUMPTIONS`, `RECOMMENDATIONS`, `TIMESTAMP`.
- `SUMMARY` is mandatory and must be the first section in the report.
- `TIMESTAMP` is mandatory and must be the final section in the report.
- Do not place timestamps at the top of the report.
- Use `orchestrator.utils.utc_timestamp(compact=False)` (or equivalent) when scripts need to generate the final ISO 8601 timestamp automatically.
- Run bundles already capture generation time in `run_meta.json`, but repeating the timestamp in the final report section keeps the policy visible and enforceable.

## Current Limitations
- Agents are deterministic placeholders; hook them up to LLM backends later.
- Repository copies use `shutil.copytree` by default; replace with lightweight worktrees if needed.
- Gate heuristics are conservative and rely on metadata from agent profiles and contracts.

Contributions should maintain local-only execution, preserve evidence immutability, and extend gates/contracts before expanding agent autonomy.

## Remote Work Architecture Pack
The current remote-work phase is architecture-only and intentionally avoids gameplay or project-structure changes. The repo now includes additive blueprint artifacts for the conversational AI-E expansion:

- [docs/REMOTE_WORK_PHASE_HANDOFF_2026-03-15.md](docs/REMOTE_WORK_PHASE_HANDOFF_2026-03-15.md) captures the approved architecture handoff, remote-work guardrails, and phase sequence.
- `orchestrator/architecture_blueprint.py` defines typed request, task-graph, reporting, provider, and gateway contracts for future implementation work.
- `contracts/templates/conversational_request_template.json` and `contracts/templates/task_graph_template.json` provide deterministic templates for conversational ingress and dependency-aware planning.
- `orchestrator/request_schema_loader.py` validates conversational request contracts and loads them into typed architecture objects.
- `orchestrator/planner_stub.py` and `orchestrator/task_graph_emitter.py` provide a non-runtime planning stub that emits deterministic task-graph contracts only.
- `orchestrator/report_contract.py` provides additive formatter and validator helpers for the canonical operator-facing report order.

These assets are documentation and design scaffolding only. They are not wired into the live runner yet, so baseline orchestrator behavior remains unchanged.


