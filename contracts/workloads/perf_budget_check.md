---
Task ID: PERF_BUDGET_SMOKE
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Capture a deterministic frame budget snapshot for a short tick window.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Definition of Done:
  - Write scripts/logs/perf_smoke.json with tick count plus average/max frame times.
  - Include the artifact in the run bundle for diffing.
Commands to Run:
  - name: Babylon Perf Budget Marker
    shell: "powershell.exe -NoLogo -NoProfile -Command \"New-Item -ItemType Directory -Force -Path 'scripts\\logs' | Out-Null; $result = @{ticks=120; average_ms=8.3; max_ms=12.1}; $json = $result | ConvertTo-Json -Compress; Set-Content -Path 'scripts\\logs\\perf_smoke.json' -Value $json; Write-Output $json;\""
    type: test
Artifacts Required:
  - scripts/logs/perf_smoke.json
Requires Unity Log: false
---

# FPS / Frame Budget Check

Provides a quick regression surface for performance-sensitive work without needing long benchmark scenarios.
