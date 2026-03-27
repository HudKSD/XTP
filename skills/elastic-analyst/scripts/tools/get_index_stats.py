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
    time_field = str(payload.get("time_field") or settings.default_time_field)
    body = {"size": 0, "aggs": {"min_time": {"min": {"field": time_field}}, "max_time": {"max": {"field": time_field}}}}

    client = ESHttp(settings)
    try:
        count_data = client.post(f"/{safe_index_path(index_pattern)}/_search", json=body)
    finally:
        client.close()

    hits_total = count_data.get("hits", {}).get("total", {})
    docs = hits_total.get("value", 0) if isinstance(hits_total, dict) else hits_total
    write_json({"ok": True, "index_pattern": index_pattern, "time_field": time_field, "doc_count": docs, "min_time": count_data.get("aggregations", {}).get("min_time", {}).get("value_as_string"), "max_time": count_data.get("aggregations", {}).get("max_time", {}).get("value_as_string"), "summary": f"Computed index stats for {index_pattern} using time field {time_field}."})


if __name__ == "__main__":
    main()
