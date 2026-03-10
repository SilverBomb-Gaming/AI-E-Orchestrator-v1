---
Task ID: 0016
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Inject the new player lifebar HUD and prove it with before/after screenshots plus audit JSON.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Policy Overrides:
  allow_desktop_capture: true
Definition of Done:
  - Capture a baseline MainMenu screenshot before the HUD is injected.
  - Run the ApplyHealthBar automation to bind the HealthBarBinder to the gameplay health target and emit JSON proof.
  - Capture an after screenshot that clearly shows the lifebar anchored to the lower-left corner (1280x720).
  - Preserve Unity logs for each step.
Commands to Run:
  - name: Screenshot Before HealthBar
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_screenshot.ps1\" -ProjectPath \".\" -SceneName \"MainMenu\" -OutPng \"scripts\\logs\\healthbar_before.png\" -LogPath \"scripts\\logs\\healthbar_before.log\" -Width 1280 -Height 720 -TimeoutSec 360"
    type: test
  - name: Apply HealthBar HUD
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_apply_healthbar.ps1\" -ProjectPath \".\" -SceneName \"MainMenu\" -ArtifactPath \"scripts\\logs\\healthbar_applied.json\" -LogPath \"scripts\\logs\\healthbar_apply.log\" -TimeoutSec 360"
    type: test
  - name: Screenshot After HealthBar
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_screenshot.ps1\" -ProjectPath \".\" -SceneName \"MainMenu\" -OutPng \"scripts\\logs\\healthbar_after.png\" -LogPath \"scripts\\logs\\healthbar_after.log\" -Width 1280 -Height 720 -TimeoutSec 360"
    type: test
Artifacts Required:
  - scripts/logs/healthbar_before.png
  - scripts/logs/healthbar_applied.json
  - scripts/logs/healthbar_after.png
Requires Unity Log: true
---

# HealthBar Before/After Proof

Run a deterministic sequence that captures the pristine MainMenu, injects the lifebar HUD via the CI hook, and then captures an after screenshot plus the JSON artifact describing the binding. This ensures the player health bar is visible to ScreenshotProbe when rendered through the gameplay camera.
