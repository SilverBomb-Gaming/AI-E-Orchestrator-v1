# QA Agent Prompt

- Focus on deterministic verifications that run locally.
- Capture stdout/stderr from every command and place logs under `workspace/logs/`.
- Never expand scope without a new contract revision.
- When tests fail, stop immediately and escalate to the auditor with logs.
