---
Task ID: 0005
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Prepare the groundwork for the wall-jump feature by describing current movement inputs, listing candidate surfaces, and outlining code touchpoints.
Constraints:
  - No physics tuning outside the movement controller folders.
  - Emit a movement_feature_report.json artifact for downstream planners.
  - Keep experimental toggles disabled by default.
Allowed Scope:
  - Assets/Scripts/Gameplay/Movement/
  - Assets/Scripts/Player/
  - Tools/CI/
  - scripts/
Definition of Done:
  - Movement controller highlights the functions that will host wall-jump entry/exit logic and marks TODOs with breadcrumbs.
  - Reporter script inventories player input bindings, cooldown considerations, and targeted map volumes, then writes movement_feature_report.json.
  - Project remains compilable with zero regression outside the allowed scope.
Stop Conditions:
  - 3 failed attempts to complete commands.
  - 30 minute wall-clock cap.
Fix Loop Controller:
  Enabled: true
  Max Attempts: 3
  Max Minutes: 30
Regression:
  NoChangeVerdict: ALLOW
Commands to Run:
  - name: Capture Unity Logs
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$workspace = Get-Location; $unityExe = 'D:\\Program Files\\Unity Hub\\Editor\\6000.2.8f1\\Editor\\Unity.exe'; if (-not (Test-Path $unityExe)) { throw 'Unity editor not found at expected path.' }; $projectPath = 'E:\\AI projects 2025\\BABYLON VER 2'; $logDir = Join-Path $workspace 'scripts\\logs'; New-Item -ItemType Directory -Force -Path $logDir | Out-Null; $logFile = Join-Path $logDir 'Editor.log'; & $unityExe -batchmode -nographics -quit -projectPath $projectPath -logFile $logFile; $waited = 0; while (($waited -lt 30) -and (-not (Test-Path $logFile))) { Start-Sleep -Seconds 1; $waited++; } if (-not (Test-Path $logFile)) { throw 'Unity did not generate Editor.log'; }\""
    type: build
  - name: Validate Unity Logs
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$logPath = 'scripts\\logs\\Editor.log'; if (-not (Test-Path $logPath)) { throw 'Log missing'; } $size = (Get-Item $logPath).Length; Write-Output ('Unity log captured: {0} bytes' -f $size);\""
    type: test
  - name: Generate Movement Feature Report
    shell: "powershell.exe -NoLogo -NoProfile -Command \"& python '.\\Tools\\CI\\movement_feature_report.py' --output 'Tools/CI/movement_feature_report.json'\""
    type: test
Artifacts Required:
  - scripts/logs/Editor.log
  - Tools/CI/movement_feature_report.json
Requires Unity Log: true
Risk Notes:
  - Keep the existing movement pipeline stable; no experimental physics toggles should ship enabled.
  - Report must clearly call out any blockers so later contracts can pick them up.
---

# Contract 0005 — Wall-Jump Enablement

Document the movement touchpoints, generate an auditable feature report, and leave code breadcrumbs for a future wall-jump implementation.
