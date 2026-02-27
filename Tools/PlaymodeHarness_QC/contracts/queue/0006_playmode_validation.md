---
Task ID: 0006
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Validate that the CI Play Mode harness emits tick proofs and exits cleanly.
Execution Mode: playmode_required
Allowed Scope:
  - Tools/CI/
  - scripts/
  - Assets/Scripts/CI/
Definition of Done:
  - Play Mode harness executes and logs both "[PLAYMODE] entered" and "[PLAYMODE] tick_ok" markers.
  - Resulting Editor.log is copied into the workspace artifacts bucket for inspection.
Commands to Run:
  - name: Verify Play Mode Ticking
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$workspace = Get-Location; $unityExe = 'D:\\Program Files\\Unity Hub\\Editor\\6000.2.8f1\\Editor\\Unity.exe'; if (-not (Test-Path $unityExe)) { throw 'Unity editor not found at expected path.' }; $projectPath = 'E:\\AI projects 2025\\BABYLON VER 2'; $logDir = Join-Path $workspace 'scripts\\logs'; New-Item -ItemType Directory -Force -Path $logDir | Out-Null; $logFile = Join-Path $logDir 'Editor.log'; & $unityExe -batchmode -nographics -projectPath $projectPath -executeMethod Babylon.CI.PlaymodeHarness.RunFromCommandLine -logFile $logFile; $waited = 0; while (($waited -lt 45) -and (-not (Test-Path $logFile))) { Start-Sleep -Seconds 1; $waited++; } if (-not (Test-Path $logFile)) { throw 'Unity did not generate Editor.log'; }\""
    type: build
  - name: Validate Unity Logs
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$logPath = 'scripts\\logs\\Editor.log'; if (-not (Test-Path $logPath)) { throw 'Log missing'; } $size = (Get-Item $logPath).Length; Write-Output ('Unity log captured: {0} bytes' -f $size);\""
    type: test
Artifacts Required:
  - scripts/logs/Editor.log
Requires Unity Log: true
---

# Contract 0006 — Play Mode Harness Validation

Use this validation contract whenever we need to confirm that the deterministic Play Mode harness is healthy before running heavier gameplay probes.
