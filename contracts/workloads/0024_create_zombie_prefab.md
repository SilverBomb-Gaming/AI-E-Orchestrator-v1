---
Task ID: 0024
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Inspect the imported Meshy zombie assets, auto-build a prefab shell, and emit JSON proof of rig/clip readiness.
Execution Mode: editor
Allowed Scope:
  - Assets/3D Assets/Characters/Zombies/
  - Assets/Editor/CI/
  - Assets/Prefabs/Enemies/
  - Tools/
  - scripts/
Definition of Done:
  - Babylon.CI.CreateZombiePrefabFromImport reports status ok/warn (never error) and `prefab_created=true`.
  - Artifact `scripts/logs/zombie_prefab_creation.json` lists clip names/count plus rig classification.
  - Prefab `Assets/Prefabs/Enemies/Zombie_001.prefab` exists and was regenerated during the run.
  - Unity log for the run is captured under `scripts/logs/`.
Commands to Run:
  - name: Create Zombie Prefab Shell
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_create_zombie_prefab.ps1\" -ProjectPath \".\" -SourceAsset \"Assets/3D Assets/Characters/Zombies/Meshy_AI_biped (zombie 001)/Meshy_AI_biped/Meshy_AI_Character_output.glb\" -AnimationAsset \"Assets/3D Assets/Characters/Zombies/Meshy_AI_biped (zombie 001)/Meshy_AI_biped/Meshy_AI_Meshy_Merged_Animations.glb\" -PrefabOut \"Assets/Prefabs/Enemies/Zombie_001.prefab\" -ArtifactPath \"scripts\\logs\\zombie_prefab_creation.json\" -LogPath \"scripts\\logs\\zombie_prefab_creation.log\" -TimeoutSec 600 -MinArtifactBytes 512 -MinPrefabBytes 256"
    type: build
  - name: Validate Prefab Artifact
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$json='scripts\\logs\\zombie_prefab_creation.json'; $prefab='Assets/Prefabs/Enemies/Zombie_001.prefab'; if (-not (Test-Path $json)) { throw 'JSON missing'; } $data = Get-Content $json -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Prefab creation reported error'; } if (-not $data.prefab_created) { throw 'prefab_created flag was false'; } if (-not (Test-Path $prefab)) { throw 'Prefab asset missing'; } Write-Output ('Prefab shell ready (status={0}, clips={1})' -f $data.status, $data.clip_count);\""
    type: test
Artifacts Required:
  - scripts/logs/zombie_prefab_creation.json
  - scripts/logs/zombie_prefab_creation.log
  - Assets/Prefabs/Enemies/Zombie_001.prefab
Requires Unity Log: true
---

# Contract 0024 — Create Meshy Zombie Prefab Shell

Automates the first ingestion step: load the Meshy GLB pair, inspect meshes/rig/animations, attach baseline components, and save a prefab shell with JSON evidence so downstream automation can decide how to proceed.
