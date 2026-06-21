"""Atomic campaign state persistence for Workflow 4."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CampaignState:
    """JSON state store with atomic replacement after each status transition."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {
            "schema_version": 1,
            "input_hash": "",
            "template_hash": "",
            "config_hash": "",
            "windows": {},
            "updated_at": "",
        }

    def load(self) -> bool:
        if not self.path.exists():
            return False
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        return True

    def initialize(self, *, input_hash: str, template_hash: str, config_hash: str) -> None:
        self.data.update(
            {
                "input_hash": input_hash,
                "template_hash": template_hash,
                "config_hash": config_hash,
            }
        )
        self.save()

    def hashes_match(
        self, *, input_hash: str, template_hash: str, config_hash: str
    ) -> bool:
        return (
            self.data.get("input_hash") == input_hash
            and self.data.get("template_hash") == template_hash
            and self.data.get("config_hash") == config_hash
        )

    def set_window(
        self,
        window_id: str,
        status: str,
        **extra: Any,
    ) -> None:
        record = dict(self.data.setdefault("windows", {}).get(window_id, {}))
        record.update(extra)
        record["status"] = status
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.data["windows"][window_id] = record
        self.save()

    def get_window(self, window_id: str) -> dict[str, Any]:
        return dict(self.data.get("windows", {}).get(window_id, {}))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
