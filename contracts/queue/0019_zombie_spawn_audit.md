---
Task ID: 0019
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Produce a reachability audit for zombie/enemy spawners so designers can confirm every SpawnArea or spawn point lands on valid ground.
Constraints:
  - Limit edits to CI probe code under Assets/Editor/CI/ and artifact directories.
  - Do not save gameplay scenes from within the probe.
  - Run Unity headlessly in batchmode.
Allowed Scope:
  - Tools/
  - scripts/
  - Assets/Editor/CI/
  - Assets/Spawning/
Definition of Done:
  - Babylon.CI.ZombieSpawnAudit executes on scene "Babylon FPS game".
  - scripts/logs/zombie_spawn_audit.json exists, is valid JSON, and contains status ok|warn.
  - scripts/logs/zombie_spawn_audit.log captured for review.
  - Validation step emits a summary of spawner count and status.
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
  - name: Run Zombie Spawn Audit
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_ci_probe.ps1\" -ProjectPath \"E:\\AI projects 2025\\BABYLON VER 2\" -SceneName \"Babylon FPS game\" -ArtifactPath \"scripts\\logs\\zombie_spawn_audit.json\" -LogPath \"scripts\\logs\\zombie_spawn_audit.log\" -MethodName \"Babylon.CI.ZombieSpawnAudit.Run\" -TimeoutSec 480 -MinArtifactBytes 256"
    type: build
  - name: Validate Zombie Spawn Artifact
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$path='scripts\\logs\\zombie_spawn_audit.json'; if (-not (Test-Path $path)) { throw 'Artifact missing'; } $data = Get-Content $path -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Probe reported error'; } $count = ($data.spawners | Measure-Object).Count; Write-Output ('Zombie spawn audit status: {0} (spawners={1})' -f $data.status, $count);\""
    type: test
Artifacts Required:
  - scripts/logs/zombie_spawn_audit.json
Requires Unity Log: true
Risk Notes:
  - Probe performs ground raycasts; ensure physics layers stay deterministic across runs.
---

# Contract 0019 — Zombie Spawn Reachability Audit

Quantify whether every EnemySpawner and SpawnArea is grounded, uses prefabs, and respects player-distance constraints so spawn bugs can be triaged from CI output alone.
