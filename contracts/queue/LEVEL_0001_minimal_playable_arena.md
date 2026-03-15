---
Task ID: LEVEL_0001
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Assemble the first minimal playable sandbox scene, place the verified Zombie_001 prefab into it, and emit deterministic scene/screenshot/playmode proof.
Execution Mode: playmode_required
Constraints:
  - Reuse the validated Zombie_001 entity output; do not reopen entity generation logic.
  - Keep the scene intentionally small and deterministic.
  - Touch only AI_E test scenes, CI/editor automation, active prefabs, Tools/, and scripts/.
Allowed Scope:
  - Assets/AI_E_TestScenes/
  - Assets/Editor/CI/
  - Assets/Prefabs/
  - Assets/Prefabs/Enemies/
  - Assets/Scripts/CI/
  - Tools/
  - scripts/
Policy Overrides:
  max_patch_lines: 4000
  max_files_changed: 5
  allowed_extensions:
    - .cs
    - .json
    - .yaml
    - .yml
    - .md
    - .txt
    - .prefab
    - .meta
Definition of Done:
  - Scene Assets/AI_E_TestScenes/MinimalPlayableArena.unity exists and saves successfully.
  - Scene contains a valid player spawn, playable player rig, ground, basic lighting, and at least one Zombie_001 instance.
  - Screenshot scripts/logs/minimal_playable_arena.png exists and exceeds 4 KB.
  - Summary, validation, and playmode JSON artifacts exist and report success.
  - Playmode probe logs [PLAYMODE] entered and [PLAYMODE] tick_ok for MinimalPlayableArena.
Commands to Run:
  - name: Build Minimal Playable Arena
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_minimal_playable_arena.ps1\" -ProjectPath \".\" -SceneName \"MinimalPlayableArena\" -SceneAssetPath \"Assets/AI_E_TestScenes/MinimalPlayableArena.unity\" -SummaryPath \"scripts\\logs\\minimal_playable_arena_summary.json\" -ValidationPath \"scripts\\logs\\minimal_playable_arena_validation.json\" -PreviewPath \"scripts\\logs\\minimal_playable_arena.png\" -LogPath \"scripts\\logs\\minimal_playable_arena_build.log\" -Width 1280 -Height 720 -TimeoutSec 900"
    type: build
  - name: Run Minimal Arena Playmode Probe
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_scene_playmode_probe.ps1\" -ProjectPath \".\" -SceneName \"MinimalPlayableArena\" -ArtifactPath \"scripts\\logs\\minimal_playable_arena_playmode.json\" -LogPath \"scripts\\logs\\Editor.log\" -TargetTicks 120 -TimeoutSec 360"
    type: build
  - name: Validate Minimal Arena Artifacts
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$summary='scripts\\logs\\minimal_playable_arena_summary.json'; $validation='scripts\\logs\\minimal_playable_arena_validation.json'; $playmode='scripts\\logs\\minimal_playable_arena_playmode.json'; $png='scripts\\logs\\minimal_playable_arena.png'; foreach ($path in @($summary,$validation,$playmode,$png)) { if (-not (Test-Path $path)) { throw ('Missing artifact: ' + $path) } }; $summaryData = Get-Content $summary -Raw | ConvertFrom-Json; $validationData = Get-Content $validation -Raw | ConvertFrom-Json; $playmodeData = Get-Content $playmode -Raw | ConvertFrom-Json; if ($summaryData.status -eq 'error') { throw 'Summary reported error'; }; if ($validationData.status -eq 'error') { throw 'Validation reported error'; }; if (-not $validationData.playtest_ready) { throw 'Validation did not mark playtest_ready'; }; if ($playmodeData.status -eq 'error') { throw 'Playmode probe reported error'; }; $pngBytes = (Get-Item $png).Length; if ($pngBytes -lt 4096) { throw 'Arena screenshot too small'; }; Write-Output ('Minimal arena ready (scene={0}, playtest_ready={1}, ticks={2}, png={3})' -f $summaryData.scene, $validationData.playtest_ready, $playmodeData.ticks_observed, $pngBytes);\""
    type: test
Artifacts Required:
  - scripts/logs/minimal_playable_arena_summary.json
  - scripts/logs/minimal_playable_arena_validation.json
  - scripts/logs/minimal_playable_arena_playmode.json
  - scripts/logs/minimal_playable_arena.png
Requires Unity Log: true
Risk Notes:
  - The sandbox is intentionally hardcoded and minimal; it proves the assembly lane, not full gameplay coverage.
---

# Contract LEVEL_0001 — Minimal Playable Arena

Assemble the first deterministic combat sandbox using the already-verified Zombie_001 entity output and prove the scene can be built, opened, and launched into play mode.