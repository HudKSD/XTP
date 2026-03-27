from __future__ import annotations

import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
INTERNAL_DIR = SCRIPT_DIR.parent / "internal"
if str(INTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERNAL_DIR))

from common import ESHttp, load_settings, read_payload, resolve_index_pattern, safe_index_path, write_error, write_json


def main() -> None:
    settings = load_settings()
    payload = read_payload()
    index_pattern = resolve_index_pattern(payload, settings)
    field = str(payload.get("field") or "").strip()
    if not field:
        write_error("field is required")
    size = max(1, min(int(payload.get("size", 10)), 50))
    body = {"size": 0, "aggs": {"top_values": {"terms": {"field": field, "size": size}}}}

    client = ESHttp(settings)
    try:
        data = client.post(f"/{safe_index_path(index_pattern)}/_search", json=body)
    finally:
        client.close()

    buckets = data.get("aggregations", {}).get("top_values", {}).get("buckets", [])
    write_json({"ok": True, "index_pattern": index_pattern, "field": field, "buckets": buckets, "summary": f"Fetched top {len(buckets)} values for field {field}."})


if __name__ == "__main__":
    main()
