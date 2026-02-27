---
Task ID: 0002
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Restore the keyboard/mouse (KBM) control scheme so PlayerInput, InputAction assets, and UI legends stay in sync while new bindings are added.
Constraints:
  - Operate only inside the specified input, player systems, UI, and CI folders.
  - Do not modify legacy scenes under Assets/_LEGACY_DO_NOT_TOUCH/.
  - No network access or package upgrades.
Allowed Scope:
  - scripts/
  - Tools/CI/
  - Assets/Input/
  - Assets/Resources/
  - Assets/Converted/Scripts/Systems/
  - Assets/UI/
Definition of Done:
  - Assets/InputSystem_Actions.inputactions (and mirrored Resources copy) expose KBM bindings for Move, Look, Interact, Sprint, Attack, Jump, and weapon cycling.
  - Player-prefab bootstrap scripts (WeaponManager, CameraController, AssignPlayerInputActions, etc.) load the refreshed asset without null-reference spam.
  - KBM legend UI references the same binding names so on-screen tips stay accurate.
  - A machine-readable summary (Tools/CI/kbm_input_summary.json) describes which actions map to which KBM bindings for audit.
Stop Conditions:
  - 2 failed attempts.
  - 30 minute cap.
Fix Loop Controller:
  Enabled: true
  Max Attempts: 2
  Max Minutes: 20
Regression:
  NoChangeVerdict: ALLOW
Commands to Run:
  - name: Repo Health Check
    shell: "powershell.exe -NoLogo -NoProfile -Command \"& '.\\scripts\\repro.ps1'\""
    type: utility
  - name: Summarize KBM InputActions
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$ErrorActionPreference='Stop'; $summaryDir='Tools/CI'; New-Item -ItemType Directory -Force -Path $summaryDir | Out-Null; $assetPath='Assets/InputSystem_Actions.inputactions'; if (-not (Test-Path $assetPath)) { throw 'Input action asset missing.' }; $json = Get-Content $assetPath -Raw | ConvertFrom-Json; $playerMap = $json.maps | Where-Object { $_.name -eq 'Player' }; if (-not $playerMap) { throw 'Player action map missing.' }; $required=@('Move','Look','Interact','Sprint','Attack'); $actionNames = @($playerMap.actions | ForEach-Object { $_.name }); $bindings = foreach ($action in $playerMap.actions) { $kbmBindings = @($playerMap.bindings | Where-Object { $_.action -eq $action.name -and (($_.groups -like '*Keyboard&Mouse*') -or ($_.path -like '<Keyboard>*') -or ($_.path -like '<Mouse>*')) } | Select-Object -ExpandProperty path); [pscustomobject]@{ name=$action.name; type=$action.type; keyboard_bindings=$kbmBindings } }; $payload = [ordered]@{ generated_at = (Get-Date).ToString('s'); asset = $assetPath; required_actions = $required; missing_required = @($required | Where-Object { $actionNames -notcontains $_ }); keyboard_mouse = $bindings }; $payload | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $summaryDir 'kbm_input_summary.json') -Encoding utf8\""
    type: test
Artifacts Required:
  - Tools/CI/kbm_input_summary.json
Requires Unity Log: false
Risk Notes:
  - InputAction edits can easily overwrite control schemes; duplicate the asset before large changes.
---

# Contract 0002 — KBM Input Line

Rebuild the KBM control path so keyboard and mouse players can move, look, sprint, and interact reliably. Update the Player action map, ensure the Resources copy stays mirrored, and refresh any gameplay/UI scripts that cache bindings. The included CI summary helps reviewers confirm which bindings shipped in each run.
