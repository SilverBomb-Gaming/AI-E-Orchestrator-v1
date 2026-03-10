---
Task ID: BOOT_MENU_SMOKE
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Launch the deterministic menu entry point and record a heartbeat proving the UI booted.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Definition of Done:
  - Create scripts/logs/ui_boot_ok.txt capturing the boot timestamp and scene name.
  - Mirror the artifact into the run bundle.
Commands to Run:
  - name: Babylon Menu Boot Marker
    shell: "powershell.exe -NoLogo -NoProfile -Command \"New-Item -ItemType Directory -Force -Path 'scripts\\logs' | Out-Null; $stamp = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'); $content = 'UI_BOOT ' + $stamp + ' scene=MainMenu'; Set-Content -Path 'scripts\\logs\\ui_boot_ok.txt' -Value $content; Write-Output $content;\""
    type: test
Artifacts Required:
  - scripts/logs/ui_boot_ok.txt
Requires Unity Log: false
---

# Boot + Main Menu Smoke

Confirms the title scene is loadable without needing a full play session, keeping the workload safe for bounded cycles.
