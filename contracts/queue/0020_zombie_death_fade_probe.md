---
Task ID: 0020
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Snapshot enemy death/collapse readiness (renderers, ragdolls, destroy-on-death flags) so fade requirements are backed by CI data.
Constraints:
  - Operate only on workspace copies; no persistent scene saves.
  - Touch Assets/Editor/CI/ and scripts/logs/ only.
  - Unity must run with -batchmode/-nographics.
Allowed Scope:
  - Tools/
  - scripts/
  - Assets/Editor/CI/
  - Assets/Converted/Scripts/Systems/
Definition of Done:
  - Babylon.CI.ZombieDeathFadeProbe executes on scene "Babylon FPS game".
  - Artifact scripts/logs/zombie_death_fade_probe.json exists, parses as JSON, and status != error.
  - Log scripts/logs/zombie_death_fade_probe.log captured.
  - Validation reports enemy count + status.
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
  - name: Run Zombie Death Fade Probe
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_ci_probe.ps1\" -ProjectPath \"E:\\AI projects 2025\\BABYLON VER 2\" -SceneName \"Babylon FPS game\" -ArtifactPath \"scripts\\logs\\zombie_death_fade_probe.json\" -LogPath \"scripts\\logs\\zombie_death_fade_probe.log\" -MethodName \"Babylon.CI.ZombieDeathFadeProbe.Run\" -TimeoutSec 420 -MinArtifactBytes 256"
    type: build
  - name: Validate Zombie Death Fade Artifact
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$path='scripts\\logs\\zombie_death_fade_probe.json'; if (-not (Test-Path $path)) { throw 'Artifact missing'; } $data = Get-Content $path -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Probe reported error'; } $count = ($data.enemies | Measure-Object).Count; Write-Output ('Zombie death fade probe status: {0} (enemies={1})' -f $data.status, $count);\""
    type: test
Artifacts Required:
  - scripts/logs/zombie_death_fade_probe.json
Requires Unity Log: true
Risk Notes:
  - Probe inspects EnemyController hierarchies; unexpected runtime-only rigs may not appear in edit-time scenes.
---

# Contract 0020 — Zombie Death Collapse + Fade Probe

Capture renderer + rig metadata for every EnemyController so collapse/fade work can be reasoned about before runtime implementations begin.
