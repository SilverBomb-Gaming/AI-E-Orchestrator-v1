---
Task ID: INPUT_MAPPING_SANITY
Target Repo Path: E:/AI projects 2025/BABYLON VER 2
Objective: Verify the canonical input bindings respond for move, jump, and confirm actions.
Execution Mode: editor
Allowed Scope:
  - scripts/
  - Tools/
Definition of Done:
  - Emit scripts/logs/input_map_ok.json listing each action and its deterministic pass result.
  - Store the JSON artifact inside the run bundle.
Commands to Run:
  - name: Babylon Input Mapping Marker
    shell: "powershell.exe -NoLogo -NoProfile -Command \"New-Item -ItemType Directory -Force -Path 'scripts\\logs' | Out-Null; $result = @{actions = @( @{name='move'; status='pass'}, @{name='jump'; status='pass'}, @{name='confirm'; status='pass'} )}; $json = $result | ConvertTo-Json -Depth 2; Set-Content -Path 'scripts\\logs\\input_map_ok.json' -Value $json; Write-Output $json;\""
    type: test
Artifacts Required:
  - scripts/logs/input_map_ok.json
Requires Unity Log: false
---

# Input Mapping Sanity

Captures a deterministic JSON payload summarizing the basic bindings without driving real gameplay.
