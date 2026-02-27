from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Set

from .utils import ensure_dir, read_json, write_json


@dataclass
class AllowlistPayload:
    exact: Set[str]
    prefix: Set[str]


class CommandAllowlist:
    """Enforces a default-deny policy for contract commands."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._payload = AllowlistPayload(exact=set(), prefix=set())
        self.reload()

    def reload(self) -> None:
        ensure_dir(self.path.parent)
        if not self.path.exists():
            write_json(self.path, {"exact": [], "prefix": []})
        payload = read_json(self.path, default={"exact": [], "prefix": []})
        self._payload = AllowlistPayload(
            exact={self._normalize(entry) for entry in payload.get("exact", []) if self._normalize(entry)},
            prefix={self._normalize(entry) for entry in payload.get("prefix", []) if self._normalize(entry)},
        )

    def is_allowed(self, shell_command: str | None) -> bool:
        normalized = self._normalize(shell_command)
        if not normalized:
            return True
        if normalized in self._payload.exact:
            return True
        return any(normalized.startswith(prefix) for prefix in self._payload.prefix)

    def describe(self) -> dict:
        return {
            "path": str(self.path),
            "exact": sorted(self._payload.exact),
            "prefix": sorted(self._payload.prefix),
        }

    def _normalize(self, value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.strip().split()).lower()
