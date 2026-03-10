---
Task ID: GOLDEN_PATH_MICRO_LOOP
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Simulate a scripted golden-path objective loop and capture a completion heartbeat.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Definition of Done:
  - Produce scripts/logs/golden_path_ok.txt that records the loop completion timestamp and objective label.
  - Archive the artifact alongside the run bundle.
Commands to Run:
  - name: Babylon Golden Path Marker
    shell: "powershell.exe -NoLogo -NoProfile -Command \"New-Item -ItemType Directory -Force -Path 'scripts\\logs' | Out-Null; $stamp = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'); $content = 'GOLDEN_PATH ' + $stamp + ' objective=MicroLoop'; Set-Content -Path 'scripts\\logs\\golden_path_ok.txt' -Value $content; Write-Output $content;\""
    type: test
Artifacts Required:
  - scripts/logs/golden_path_ok.txt
Requires Unity Log: false
---

# Golden Path Micro Loop

Tracks the most basic objective-complete loop so we always have a deterministic heartbeat for polish validation.
