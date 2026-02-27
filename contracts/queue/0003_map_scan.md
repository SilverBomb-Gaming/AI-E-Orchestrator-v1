---
Task ID: 0003
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Implement automated discovery for playable maps/scenes so the map selector stays in sync without manual edits.
Constraints:
  - Local execution only; no GUI automation.
  - Modify code strictly within map selector folders (listed in Allowed Scope).
  - Prefer deterministic scans; avoid random ordering or non-repeatable filters.
Allowed Scope:
  - scripts/
  - Tools/CI/
  - Assets/Map/
  - Assets/Scripts/Maps/
  - Assets/UI/MapSelector/
  - Assets/Data/Maps/
  - Assets/Scenes/
Definition of Done:
  - Scene/map discovery logic scans the allowed directories and produces a canonical list used by the selector.
  - Generated map_scan_summary.json enumerates all discovered scenes, counts, and any missing metadata flags.
  - Resources/InputSystem_Actions.inputactions stays mirrored if map scripts depend on it (no regressions outside scope).
  - Changes are limited to allowed scope and include sufficient inline comments for reviewers.
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
  - name: Generate Map Scan Summary
    shell: "powershell.exe -NoLogo -NoProfile -Command \"& python '.\\Tools\\CI\\map_scan.py' --output 'Tools/CI/map_scan_summary.json'\""
    type: test
Artifacts Required:
  - scripts/logs/Editor.log
  - Tools/CI/map_scan_summary.json
Requires Unity Log: true
Risk Notes:
  - Keep scans read-only; do not auto-create or delete scenes.
  - Map selector consumers should read the generated summary rather than ad-hoc lists.
---

# Contract 0003 — Map/Scene Catalog

Discover playable maps automatically by scanning the allowed folders, produce an auditable summary JSON, and leave enough hooks for the map selector UI to consume the newly generated list.
