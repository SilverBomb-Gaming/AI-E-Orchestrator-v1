---
Task ID: 0018
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Audit the current player rig animation coverage for grenade throws so anim gaps can be triaged with real evidence.
Constraints:
  - Keep execution inside the Unity workspace copy.
  - Only touch Assets/Editor/CI/ code and scripts/logs/ artifacts.
  - No manual scene saves; probe must be read-only.
Allowed Scope:
  - Tools/
  - scripts/
  - Assets/Editor/CI/
  - Assets/Runtime/Character/
Definition of Done:
  - Babylon.CI.ApplyGrenadeAnimProbe runs on scene "Babylon FPS game".
  - Artifact scripts/logs/grenade_anim_probe.json captures rig + clip metadata and status != error.
  - Probe log scripts/logs/grenade_anim_probe.log is preserved.
  - Validation step surfaces the reported status for reviewers.
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
  - name: Run Grenade Animation Probe
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_ci_probe.ps1\" -ProjectPath \"E:\\AI projects 2025\\BABYLON VER 2\" -SceneName \"Babylon FPS game\" -ArtifactPath \"scripts\\logs\\grenade_anim_probe.json\" -LogPath \"scripts\\logs\\grenade_anim_probe.log\" -MethodName \"Babylon.CI.ApplyGrenadeAnimProbe.Run\" -TimeoutSec 420 -MinArtifactBytes 256"
    type: build
  - name: Validate Grenade Animation Artifact
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$path='scripts\\logs\\grenade_anim_probe.json'; if (-not (Test-Path $path)) { throw 'Artifact missing'; } $data = Get-Content $path -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Probe reported error'; } Write-Output ('Grenade animation probe status: {0}' -f $data.status);\""
    type: test
Artifacts Required:
  - scripts/logs/grenade_anim_probe.json
Requires Unity Log: true
Risk Notes:
  - Anim probes reflect current rig controllers; changing controller assignments mid-run invalidates the output.
---

# Contract 0018 — Grenade Animation Probe

Surface which animator controllers and clips currently cover grenade throws so animators can plan blending work (or highlight missing clips) with a single JSON artifact.
