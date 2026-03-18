from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_e_runtime.real_target_rollback import rollback_first_real_target_grass_proof
from orchestrator.config import OrchestratorConfig


def main() -> int:
    config = OrchestratorConfig.load()
    result = rollback_first_real_target_grass_proof(config)
    print(
        json.dumps(
            {
                "session_id": result.session_id,
                "status": result.status,
                "restored": result.restored,
                "report_path": str(result.report_path),
                "target_scene": str(result.target_scene),
                "backup_path": str(result.backup_path),
                "restored_sha1": result.restored_sha1,
                "marker_present_after": result.marker_present_after,
                "message": result.message,
            },
            indent=2,
        )
    )
    return 0 if result.restored else 1


if __name__ == "__main__":
    raise SystemExit(main())