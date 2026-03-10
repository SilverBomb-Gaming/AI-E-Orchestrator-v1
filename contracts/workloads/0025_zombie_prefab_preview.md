---
Task ID: 0025
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Instantiate the newly created zombie prefab, capture a deterministic PNG preview, and log bounds/camera metadata for operator review.
Execution Mode: editor
Allowed Scope:
  - Assets/Prefabs/Enemies/
  - Assets/Editor/CI/
  - Tools/
  - scripts/
Definition of Done:
  - Babylon.CI.ZombiePrefabPreviewProbe finishes with status ok/warn and `instantiated=true`.
  - Preview PNG and JSON artifacts exist under `scripts/logs/` with non-trivial sizes.
  - Unity log from the run is captured for regression review.
Commands to Run:
  - name: Capture Zombie Prefab Preview
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_zombie_prefab_preview.ps1\" -ProjectPath \".\" -PrefabPath \"Assets/Prefabs/Enemies/Zombie_001.prefab\" -PreviewPath \"scripts\\logs\\zombie_prefab_preview.png\" -ArtifactPath \"scripts\\logs\\zombie_prefab_preview.json\" -LogPath \"scripts\\logs\\zombie_prefab_preview.log\" -TimeoutSec 720 -Width 1280 -Height 720 -MinPreviewBytes 4096 -MinArtifactBytes 256"
    type: build
  - name: Validate Preview Outputs
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$json='scripts\\logs\\zombie_prefab_preview.json'; $png='scripts\\logs\\zombie_prefab_preview.png'; if (-not (Test-Path $json)) { throw 'JSON missing'; } if (-not (Test-Path $png)) { throw 'PNG missing'; } $data = Get-Content $json -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Preview reported error'; } if (-not $data.instantiated) { throw 'Prefab instantiation flag was false'; } $bytes = (Get-Item $png).Length; if ($bytes -lt 4096) { throw 'Preview PNG too small'; } Write-Output ('Preview ok (status={0}, bytes={1})' -f $data.status, $bytes);\""
    type: test
Artifacts Required:
  - scripts/logs/zombie_prefab_preview.json
  - scripts/logs/zombie_prefab_preview.png
  - scripts/logs/zombie_prefab_preview.log
Requires Unity Log: true
---

# Contract 0025 — Zombie Prefab Preview Proof

Builds visual proof that the prefab saved in workload 0024 exists, renders correctly in a staging scene, and can be shared with operators before gameplay integration proceeds.
