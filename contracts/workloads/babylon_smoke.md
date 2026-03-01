---
Task ID: BABYLON_SMOKE
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Run a deterministic smoke check that writes a small marker file without touching gameplay code.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Definition of Done:
  - Create scripts/logs/babylon_smoke.txt containing a timestamped heartbeat line.
  - Mirror the log into the run bundle artifacts.
Commands to Run:
  - name: Babylon Smoke Marker
    shell: "powershell.exe -NoLogo -NoProfile -Command \"New-Item -ItemType Directory -Force -Path 'scripts\\logs' | Out-Null; $stamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ'); $content = 'BABYLON_SMOKE ' + $stamp; Set-Content -Path 'scripts\\logs\\babylon_smoke.txt' -Value $content; Write-Output $content;\""
    type: test
Artifacts Required:
  - scripts/logs/babylon_smoke.txt
Requires Unity Log: false
---

# BABYLON Smoke Contract

This workload adapter keeps the integration lightweight by writing a timestamped heartbeat file and leaving gameplay assets untouched. It is safe to execute during Night Cycle runs when validating Stability Core upgrades.
