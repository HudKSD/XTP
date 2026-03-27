from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceLogger:
    def __init__(self, traces_dir: Path, enabled: bool = True) -> None:
        self.traces_dir = traces_dir
        self.enabled = enabled
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    def write(self, chat_id: str, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        now = datetime.now(timezone.utc)
        file_path = self.traces_dir / f"{now:%Y-%m-%d}_{chat_id}.jsonl"
        payload = {
            "timestamp": now.isoformat(),
            **event,
        }
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
