# AI-E / BABYLON Remote Work Phase Handoff

Version: 1.1  
Date: 2026-03-15  
Project Root: `E:\AI projects 2025\`

## Summary
This handoff captures the approved remote-work architecture direction for AI-E while preserving current gameplay and runner behavior. The current phase is limited to additive architecture design, schema definition, adapter planning, and deterministic reporting rules.

## Facts
- `BABYLON VER 2` remains the active Unity workload for AI-E orchestration.
- `LEVEL_0001` is the first AI-generated playable sandbox level and remains the active proof point for the pipeline.
- Manual playtesting already confirmed a working first-person loop, arena geometry, zombie presence, and core UI in `Assets/AI_E_TestScenes/MinimalPlayableArena.unity`.
- The current operator constraint is remote-only work. Direct Unity gameplay testing is deferred until workstation access returns.
- The approved focus for this phase is architecture expansion only, not gameplay iteration.

## Remote Work Guardrails
The following are explicitly out of scope for this phase:

- Create new Python environments.
- Modify baseline orchestrator behavior.
- Redesign the main menu.
- Start `LEVEL_0002`.
- Restructure the Unity project.
- Modify gameplay systems.
- Regenerate assets.
- Introduce experimental frameworks.
- Bypass policy or validation layers.

The following work is in scope:

- Conversational command design.
- Planner and decomposition design.
- Task graph and contract design.
- Agent role architecture.
- Tool adapter architecture.
- Runtime provider planning.
- Chat gateway planning.
- Learning and reporting architecture.

## Architecture Intent
The target system state is a conversational development interface that accepts natural language requests, converts them into bounded execution plans, routes those plans through specialized roles, validates outcomes, and reports back to the operator under strict policy control.

The ten long-lived subsystems for that target state are:

1. Conversational Command Layer
2. Planning and Decomposition Layer
3. Task Contract / Task Graph Layer
4. Agent Execution Layer
5. Tool / Environment Interface Layer
6. Validation / Policy / Guardrail Layer
7. Memory / Learning Layer
8. Reporting / Operator Loop
9. Runtime Provider Layer
10. Chat Gateway Layer

These layers are additive to the current Stability Core boundaries in [docs/MODULE_BOUNDARIES.md](docs/MODULE_BOUNDARIES.md). They do not replace the current runner, gates, or policy engine during this phase.

## Landed Repo Artifacts
This handoff is now represented in-repo by the following additive assets:

- `orchestrator/architecture_blueprint.py`
  - Typed request, task, report, and policy payload models.
  - Runtime provider and chat gateway adapter protocols.
  - Default remote-work constraints, allowed work types, phase plan, and required run-log fields.
- `contracts/templates/conversational_request_template.json`
  - Canonical request shape for future CLI, local chat, web UI, or Discord ingress.
- `contracts/templates/task_graph_template.json`
  - Canonical task-graph shape for dependency-aware execution.
- `tests/test_architecture_blueprint.py`
  - Regression coverage for deterministic payloads and template validity.

## Phase Plan
The remote-work architecture sequence is intentionally staged:

1. Define conversational request schema and clarification model.
2. Define `PlannerAgent` outputs and decomposition rules.
3. Move from queue-only thinking to task graph contracts.
4. Lock logical agent roles and handoff semantics.
5. Standardize tool and environment adapters.
6. Standardize hardware-agnostic runtime providers.
7. Standardize policy-compliant chat gateways.
8. Standardize memory, learning, and operator report loops.

## Provider and Gateway Boundaries
Runtime providers are execution environments, not policy authorities. They must:

- Declare capabilities.
- Support health checks.
- Run bounded task bundles.
- Return structured outputs.
- Respect timeout and cancel controls.
- Emit deterministic logs.

Chat gateways are interfaces, not controllers. They must:

- Normalize inbound prompts.
- Bind requests to session metadata.
- Route through planning.
- Deliver reports and approval prompts.
- Never bypass the policy engine.

## Logging Contract
Every future conversational or overnight run should continue to produce deterministic, reproducible records containing:

- `run_id`
- `timestamp`
- `task_list`
- `policy_decisions`
- `artifacts`
- `validation_results`
- `recommendations`

## Assumptions
- The orchestrator remains the authority for policy, evidence capture, and final verdicts.
- Runtime provider integration must remain hardware-agnostic until the Tiiny Pocket AI device is actually available for testing.
- Chat interfaces remain thin ingress and egress adapters, not alternate execution paths.

## Recommendations
- Keep all phase-one work additive and schema-first until local gameplay validation resumes.
- Treat `orchestrator/architecture_blueprint.py` as the design contract for future implementation work, not as a live runtime dependency yet.
- Use the new JSON templates for future planning or gateway prototypes instead of inventing ad hoc payloads.

## Timestamp
2026-03-15T17:30:00Z