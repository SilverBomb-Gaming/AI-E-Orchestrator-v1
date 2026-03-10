---
Task ID: 0021
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Validate the new DropZone manifest + prefabs before wiring them into gameplay.
Constraints:
  - Operate only on workspace copies; no manual edits to upstream scenes.
  - Touch Assets/DropZone/, Assets/Editor/CI/, scripts/logs/, or Tools/ only.
  - Unity must run with -batchmode/-nographics.
Allowed Scope:
  - Tools/
  - scripts/
  - Assets/Editor/CI/
  - Assets/DropZone/
Definition of Done:
  - Babylon.CI.EnemyIngestProbe runs in scene "Babylon FPS game".
  - Artifact scripts/logs/enemy_ingest_probe.json exists, parses as JSON, and status != error.
  - Log scripts/logs/enemy_ingest_probe.log captured.
  - Probe reports every manifest entry with prefab + renderer/collider metadata.
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
  - name: Run DropZone Ingest Probe
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_enemy_ingest_probe.ps1\" -ProjectPath \"E:\\AI projects 2025\\BABYLON VER 2\" -SceneName \"Babylon FPS game\" -ManifestPath \"Assets/DropZone/Incoming/enemy_manifest.json\" -ArtifactPath \"scripts\\logs\\enemy_ingest_probe.json\" -LogPath \"scripts\\logs\\enemy_ingest_probe.log\" -TimeoutSec 420 -MinArtifactBytes 512"
    type: build
  - name: Validate DropZone Ingest Artifact
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$path='scripts\\logs\\enemy_ingest_probe.json'; if (-not (Test-Path $path)) { throw 'Artifact missing'; } $data = Get-Content $path -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Probe reported error'; } $count = ($data.entries | Measure-Object).Count; if ($count -lt 1) { throw 'No manifest entries recorded.'; } Write-Output ('DropZone ingest status: {0} (entries={1})' -f $data.status, $count);\""
    type: test
Artifacts Required:
  - scripts/logs/enemy_ingest_probe.json
Requires Unity Log: true
Risk Notes:
  - Missing prefabs or colliders should surface as WARN (status != error) so integrators can triage quickly.
---

# Contract 0021 — DropZone Enemy Ingest

Run the manifest validation probe so every drag-and-drop batch is backed by structured evidence before it hits gameplay.
