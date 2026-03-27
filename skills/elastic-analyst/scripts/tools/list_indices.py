from __future__ import annotations

import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
INTERNAL_DIR = SCRIPT_DIR.parent / "internal"
if str(INTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERNAL_DIR))

from common import ESHttp, load_settings, read_payload, resolve_index_pattern, safe_index_path, write_json


def main() -> None:
    settings = load_settings()
    payload = read_payload()
    index_pattern = resolve_index_pattern(payload, settings)

    client = ESHttp(settings)
    try:
        rows = client.get(
            f"/_cat/indices/{safe_index_path(index_pattern)}",
            params={"format": "json", "h": "index,health,status,docs.count,store.size"},
        )
    finally:
        client.close()

    items = [
        {
            "index": row.get("index"),
            "health": row.get("health"),
            "status": row.get("status"),
            "docs_count": row.get("docs.count"),
            "store_size": row.get("store.size"),
        }
        for row in rows
    ]
    write_json({"ok": True, "index_pattern": index_pattern, "count": len(items), "items": items, "summary": f"Listed {len(items)} indices for pattern {index_pattern}."})


if __name__ == "__main__":
    main()
