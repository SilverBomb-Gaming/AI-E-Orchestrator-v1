---
Task ID: 0015
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Apply the AI-E demo overlay to MainMenu and collect before/after screenshot proof.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Policy Overrides:
  allow_desktop_capture: true
Definition of Done:
  - Capture a baseline MainMenu screenshot before edits.
  - Apply the demo overlay via the editor automation and emit a JSON artifact.
  - Capture a second screenshot showing the applied overlay.
  - Preserve Unity logs for each step.
Commands to Run:
  - name: Screenshot Before Overlay
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_screenshot.ps1\" -ProjectPath \".\" -SceneName \"MainMenu\" -OutPng \"scripts\\logs\\mainmenu_before.png\" -LogPath \"scripts\\logs\\unity_screenshot_before.log\" -Width 1280 -Height 720 -TimeoutSec 360"
    type: test
  - name: Apply Demo Overlay
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_apply_demo_overlay.ps1\" -ProjectPath \".\" -SceneName \"MainMenu\" -ArtifactPath \"scripts\\logs\\demo_overlay_applied.json\" -LogPath \"scripts\\logs\\demo_overlay_editor.log\" -TimeoutSec 360"
    type: test
  - name: Screenshot After Overlay
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_screenshot.ps1\" -ProjectPath \".\" -SceneName \"MainMenu\" -OutPng \"scripts\\logs\\mainmenu_after.png\" -LogPath \"scripts\\logs\\unity_screenshot_after.log\" -Width 1280 -Height 720 -TimeoutSec 360"
    type: test
Artifacts Required:
  - scripts/logs/mainmenu_before.png
  - scripts/logs/demo_overlay_applied.json
  - scripts/logs/mainmenu_after.png
  - scripts/logs/unity_screenshot_before.log
  - scripts/logs/unity_screenshot_after.log
  - scripts/logs/demo_overlay_editor.log
Requires Unity Log: true
---

# Demo Overlay Proof

Runs a before/after sequence to demonstrate a visible gameplay UI change. The workflow captures the pristine MainMenu, applies the AI-E demo overlay, and then records a second screenshot plus structured JSON evidence for auditing.
