---
Task ID: 0023
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Capture a visual proof of the DropZone spawn point (JSON + PNG) so design can compare before/after drops.
Constraints:
  - Operate only on workspace copies; artifacts must land in scripts/logs/.
  - Touch Assets/Editor/CI/, Assets/DropZone/, scripts/logs/, or Tools/ only.
  - Unity must run with -batchmode/-nographics.
Allowed Scope:
  - Tools/
  - scripts/
  - Assets/Editor/CI/
  - Assets/DropZone/
Definition of Done:
  - Babylon.CI.ZombieSpawnScreenshotProbe runs in scene "Babylon FPS game".
  - Artifact scripts/logs/zombie_spawn_preview.json exists, parses as JSON, and status != error.
  - Preview PNG scripts/logs/zombie_spawn_preview.png exists (>4 KB).
  - Log scripts/logs/zombie_spawn_preview.log captured.
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
  - name: Run Zombie Spawn Preview Probe
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_zombie_spawn_preview.ps1\" -ProjectPath \"E:\\AI projects 2025\\BABYLON VER 2\" -SceneName \"Babylon FPS game\" -ManifestPath \"Assets/DropZone/Incoming/enemy_manifest.json\" -ArtifactPath \"scripts\\logs\\zombie_spawn_preview.json\" -PreviewPath \"scripts\\logs\\zombie_spawn_preview.png\" -LogPath \"scripts\\logs\\zombie_spawn_preview.log\" -TimeoutSec 420 -MinArtifactBytes 512 -Width 1280 -Height 720"
    type: build
  - name: Validate Zombie Spawn Preview
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$json='scripts\\logs\\zombie_spawn_preview.json'; $png='scripts\\logs\\zombie_spawn_preview.png'; if (-not (Test-Path $json)) { throw 'JSON missing'; } if (-not (Test-Path $png)) { throw 'PNG missing'; } $data = Get-Content $json -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Probe reported error'; } $size = (Get-Item $png).Length; if ($size -lt 4096) { throw 'PNG too small'; } Write-Output ('Zombie spawn preview captured (status={0}, bytes={1})' -f $data.status, $size);\""
    type: test
Artifacts Required:
  - scripts/logs/zombie_spawn_preview.json
  - scripts/logs/zombie_spawn_preview.png
Requires Unity Log: true
Risk Notes:
  - Preview probe creates temporary objects only; failure to clean up indicates the launcher should block promotion.
---

# Contract 0023 — Zombie Spawn Visual Proof

Emit JSON + PNG evidence showing where the next DropZone batch will appear so design has a deterministic screenshot to review.
