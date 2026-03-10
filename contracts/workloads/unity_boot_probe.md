---
Task ID: 0013
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Boot the MainMenu scene in Unity batchmode and capture a proof artifact.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Definition of Done:
  - Use Tools/run_unity_boot.ps1 to launch MainMenu via Babylon.CI.BootProbe.
  - Capture scripts/logs/ui_boot_result.json plus Editor.log in the run bundle.
  - Fail loudly if the scene cannot be located or Unity exits non-zero.
Commands to Run:
  - name: Unity Boot Probe
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_boot.ps1\" -ProjectPath \".\" -SceneName \"MainMenu\" -ArtifactPath \"scripts\\logs\\ui_boot_result.json\" -LogPath \"scripts\\logs\\Editor.log\" -TimeoutSec 360"
    type: test
Artifacts Required:
  - scripts/logs/ui_boot_result.json
  - scripts/logs/Editor.log
Requires Unity Log: true
---

# Unity Boot Probe

Verifies that the deterministic MainMenu entry point loads in batchmode, writes a heartbeat artifact, and produces a Unity log suitable for downstream regression gates.
