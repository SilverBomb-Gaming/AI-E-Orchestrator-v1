---
Task ID: 0017
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Capture the current grenade-throw readiness (input bindings, GrenadeThrower wiring, inventory counts) via a deterministic CI probe.
Constraints:
  - Operate only inside the Babylon workspace copy produced by the orchestrator.
  - Do not modify assets outside Assets/Editor/CI/ or scripts/logs/.
  - Unity must run in batchmode; no interactive editors.
Allowed Scope:
  - Tools/
  - scripts/
  - Assets/Editor/CI/
  - Assets/Weapons/
Definition of Done:
  - Babylon.CI.ApplyGrenadeThrowProbe executes against scene "Babylon FPS game" and exits cleanly.
  - Artifact scripts/logs/grenade_throw_probe.json exists, parses as JSON, and reports status ok|warn (never error).
  - Probe log scripts/logs/grenade_throw_probe.log captured for audit.
  - Validation command surfaces the reported status in the run summary.
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
  - name: Run Grenade Throw Probe
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_ci_probe.ps1\" -ProjectPath \"E:\\AI projects 2025\\BABYLON VER 2\" -SceneName \"Babylon FPS game\" -ArtifactPath \"scripts\\logs\\grenade_throw_probe.json\" -LogPath \"scripts\\logs\\grenade_throw_probe.log\" -MethodName \"Babylon.CI.ApplyGrenadeThrowProbe.Run\" -TimeoutSec 420 -MinArtifactBytes 256"
    type: build
  - name: Validate Grenade Throw Artifact
    shell: "powershell.exe -NoLogo -NoProfile -Command \"$path='scripts\\logs\\grenade_throw_probe.json'; if (-not (Test-Path $path)) { throw 'Artifact missing'; } $data = Get-Content $path -Raw | ConvertFrom-Json; if ($data.status -eq 'error') { throw 'Probe reported error'; } Write-Output ('Grenade throw probe status: {0}' -f $data.status);\""
    type: test
Artifacts Required:
  - scripts/logs/grenade_throw_probe.json
Requires Unity Log: true
Risk Notes:
  - Probe opens gameplay scenes in the editor; always operate on disposable workspace copies.
---

# Contract 0017 — Grenade Throw Probe

Document the grenade gameplay inputs so the next automation step can gate R1 (right bumper) throws with confidence. The probe emits a machine-readable summary of the Player input map plus all GrenadeThrower components found in the gameplay scene.
