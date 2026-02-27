---
Task ID: 0001
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Collect Unity Editor.log outputs and parse errors into structured JSON for morning review.
Constraints:
  - Local execution only; no network calls.
  - Must operate inside scripts/ and Tools/CI/ paths.
Allowed Scope:
  - scripts/
  - Tools/CI/
Definition of Done:
  - Editor.log copied into the run artifacts directory.
  - Parsed JSON summary of errors placed under Tools/CI/.
  - Summary report references both artifacts.
Stop Conditions:
  - 2 failed attempts to gather logs.
  - 30 minute wall-clock cap.
Fix Loop Controller:
  Enabled: true
  Max Attempts: 2
  Max Minutes: 20
Regression:
  NoChangeVerdict: ALLOW
Commands to Run:
  - name: Capture Unity Logs
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$workspace = Get-Location; $unityExe = 'D:\\Program Files\\Unity Hub\\Editor\\6000.2.8f1\\Editor\\Unity.exe'; if (-not (Test-Path $unityExe)) { throw 'Unity editor not found at expected path.' }; $projectPath = 'E:\\AI projects 2025\\BABYLON VER 2'; $logDir = Join-Path $workspace 'scripts\\logs'; New-Item -ItemType Directory -Force -Path $logDir | Out-Null; $logFile = Join-Path $logDir 'Editor.log'; & $unityExe -batchmode -nographics -quit -projectPath $projectPath -logFile $logFile; $waited = 0; while (($waited -lt 30) -and (-not (Test-Path $logFile))) { Start-Sleep -Seconds 1; $waited++; } if (-not (Test-Path $logFile)) { throw 'Unity did not generate Editor.log'; }\""
    type: build
  - name: Validate Unity Logs
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$logPath = 'scripts\\logs\\Editor.log'; if (-not (Test-Path $logPath)) { throw 'Log missing'; } $size = (Get-Item $logPath).Length; Write-Output ('Unity log captured: {0} bytes' -f $size);\""
    type: test
Artifacts Required:
  - scripts/logs/Editor.log
  - Tools/CI/unity_log_summary.json
Requires Unity Log: true
Risk Notes:
  - Unity not installed on CI nodes; this run simulates the funnel by copying local logs if available.
---

# Contract 0001 — Unity Log Funnel + Parser

Simulate the Unity log collection process locally until full engine automation is wired up. The orchestrator derives the structured summary after commands complete to keep artifacts under budget.
