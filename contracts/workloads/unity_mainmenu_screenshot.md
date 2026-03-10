---
Task ID: 0014
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Render the MainMenu scene in batchmode and capture a proof screenshot.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Policy Overrides:
  allow_desktop_capture: true
Definition of Done:
  - Capture a deterministic screenshot of MainMenu at 1280x720.
  - Record the Unity Editor log for traceability.
  - Store the PNG in scripts/logs and mirror it into the run artifacts bundle.
Commands to Run:
  - name: Capture MainMenu Screenshot
    shell: "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"Tools\\run_unity_screenshot.ps1\" -ProjectPath \".\" -SceneName \"MainMenu\" -OutPng \"scripts\\logs\\mainmenu_proof.png\" -LogPath \"scripts\\logs\\unity_screenshot_editor.log\" -Width 1280 -Height 720 -TimeoutSec 360"
    type: test
Artifacts Required:
  - scripts/logs/mainmenu_proof.png
  - scripts/logs/unity_screenshot_editor.log
Requires Unity Log: true
---

# Unity MainMenu Screenshot Proof

Ensures the deterministic MainMenu entry point renders successfully in batchmode, capturing a PNG artifact plus Unity logs for regression comparisons.
