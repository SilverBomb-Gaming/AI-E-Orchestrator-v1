---
Task ID: V005
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Exercise retry-per-task handling by failing deterministically.
Execution Mode: editor
Allowed Scope:
  - scripts/
Definition of Done:
  - Produce a marker file noting that retries were attempted.
Commands to Run:
  - name: Emit retry exhaust marker
    shell: "powershell.exe -NoLogo -NoProfile -Command \"New-Item -ItemType Directory -Force -Path 'scripts\\logs' | Out-Null; Set-Content -Path 'scripts\\logs\\validation_retry.txt' -Value 'retry';\""
    type: test
Artifacts Required:
  - scripts/logs/validation_retry.txt
Requires Unity Log: false
---

# V005 — Validation Pack Retry Exhaust Scenario

Always fails so the cycle can confirm that bounded retries behave as expected.
