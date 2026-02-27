---
Task ID: 0004
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Stabilize the first-person viewmodel so weapon poses, camera offsets, and animation layers remain consistent between map loads.
Execution Mode: playmode_required
Constraints:
  - Treat animation clips as read-only; duplicate before editing.
  - Keep all changes within the allowed scope folders.
  - Document any temporary telemetry that gets added for auditing purposes.
Allowed Scope:
  - Assets/Scripts/Gameplay/Viewmodel/
  - Assets/Scripts/Weapons/
  - Assets/Animations/Viewmodel/
  - Tools/CI/
  - scripts/
Definition of Done:
  - Deterministic viewmodel configuration routine runs on scene load and reapplies the expected camera offsets.
  - A CI helper script produces viewmodel_audit.json summarizing offsets, animation layers, and any detected drift for operator review.
  - No regressions outside the allowed scope and all edits include inline rationale where non-obvious.
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
  - name: Verify Play Mode Ticking
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$workspace = Get-Location; $unityExe = 'D:\\Program Files\\Unity Hub\\Editor\\6000.2.8f1\\Editor\\Unity.exe'; if (-not (Test-Path $unityExe)) { throw 'Unity editor not found at expected path.' }; $projectPath = 'E:\\AI projects 2025\\BABYLON VER 2'; $logDir = Join-Path $workspace 'scripts\\logs'; New-Item -ItemType Directory -Force -Path $logDir | Out-Null; $logFile = Join-Path $logDir 'Editor.log'; & $unityExe -batchmode -nographics -projectPath $projectPath -executeMethod Babylon.CI.PlaymodeHarness.RunFromCommandLine -logFile $logFile; $waited = 0; while (($waited -lt 45) -and (-not (Test-Path $logFile))) { Start-Sleep -Seconds 1; $waited++; } if (-not (Test-Path $logFile)) { throw 'Unity did not generate Editor.log'; }\""
    type: build
  - name: Validate Unity Logs
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$logPath = 'scripts\\logs\\Editor.log'; if (-not (Test-Path $logPath)) { throw 'Log missing'; } $size = (Get-Item $logPath).Length; Write-Output ('Unity log captured: {0} bytes' -f $size);\""
    type: test
  - name: Generate Viewmodel Audit
    shell: "powershell.exe -NoLogo -NoProfile -Command \"& python '.\\Tools\\CI\\viewmodel_audit.py' --output 'Tools/CI/viewmodel_audit.json'\""
    type: test
Artifacts Required:
  - scripts/logs/Editor.log
  - Tools/CI/viewmodel_audit.json
Requires Unity Log: true
Risk Notes:
  - Avoid touching gameplay systems outside the viewmodel path; coordinate future work through queued contracts.
  - Keep audit data deterministic so diffing stays meaningful.
---

# Contract 0004 — Viewmodel Stabilization

Produce a repeatable audit plus targeted fixes that keep the weapon/camera viewmodel aligned every time a scene loads.
