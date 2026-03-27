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
    size = max(1, min(int(payload.get("size", 3)), 5))
    fields = payload.get("fields") or []
    body = {"size": size, "query": {"match_all": {}}, "sort": [{"_doc": "asc"}]}
    if fields:
        body["_source"] = fields

    client = ESHttp(settings)
    try:
        data = client.post(f"/{safe_index_path(index_pattern)}/_search", json=body)
    finally:
        client.close()

    hits = data.get("hits", {}).get("hits", [])
    items = [{"_index": hit.get("_index"), "_id": hit.get("_id"), "_source": hit.get("_source", {})} for hit in hits]
    write_json({"ok": True, "index_pattern": index_pattern, "count": len(items), "items": items, "summary": f"Fetched {len(items)} sample docs from {index_pattern}."})


if __name__ == "__main__":
    main()
