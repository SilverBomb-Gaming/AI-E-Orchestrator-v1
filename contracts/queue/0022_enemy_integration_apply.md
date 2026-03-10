---
Task ID: 0022
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Map DropZone manifest entries to EnemySpawner instances and record what still needs wiring.
Constraints:
  - Operate only on workspace copies; scene saves must remain local.
  - Touch Assets/Editor/CI/, Assets/DropZone/, scripts/logs/, or Tools/ only.
  - Unity must run with -batchmode/-nographics.
Allowed Scope:
  - Tools/
  - scripts/
  - Assets/Editor/CI/
  - Assets/DropZone/
  - Assets/Spawning/
Definition of Done:
  - Babylon.CI.ApplyEnemyIntegration runs in scene "Babylon FPS game".
  - Artifact scripts/logs/enemy_apply_probe.json exists, parses as JSON, and status != error.
  - Log scripts/logs/enemy_apply_probe.log captured.
  - Report lists every manifest entry with prefab + spawner match status.
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
  - name: Run DropZone Apply Probe
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_enemy_apply_integration.ps1\" -ProjectPath \"E:\\AI projects 2025\\BABYLON VER 2\" -SceneName \"Babylon FPS game\" -ManifestPath \"Assets/DropZone/Incoming/enemy_manifest.json\" -ArtifactPath \"scripts\\logs\\enemy_apply_probe.json\" -LogPath \"scripts\\logs\\enemy_apply_probe.log\" -TimeoutSec 420 -MinArtifactBytes 512"
    type: build
  - name: Validate DropZone Apply Artifact
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$path='scripts\\logs\\enemy_apply_probe.json'; if (-not (Test-Path $path)) { throw 'Artifact missing'; } $data = Get-Content $path -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Probe reported error'; } $assigned = ($data.integrations | Where-Object { $_.prefabMatchesSpawner }).Count; Write-Output ('DropZone apply status: {0} (assigned={1})' -f $data.status, $assigned);\""
    type: test
Artifacts Required:
  - scripts/logs/enemy_apply_probe.json
Requires Unity Log: true
Risk Notes:
  - Probe should never mutate scenes; it only reports whether assignments exist so humans can stage follow-up work.
---

# Contract 0022 — DropZone Enemy Integration Report

Surface a deterministic apply report so operators know which spawners are wired before promoting new zombies.
