from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    expected = (repo_root / ".venv-2" / "Scripts" / "python.exe").resolve()
    active = Path(sys.executable).resolve()
    status = "PASS" if active == expected else "WARN"

    print(f"sys.executable: {active}")
    print(f"sys.version: {sys.version.splitlines()[0]}")
    print(f"cwd: {Path(os.getcwd()).resolve()}")
    print(f"expected: {expected}")
    print(f"policy_match: {active == expected}")
    print(status)

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
