from __future__ import annotations

import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
INTERNAL_DIR = SCRIPT_DIR.parent / "internal"
if str(INTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERNAL_DIR))

from common import ESHttp, load_settings, read_payload, resolve_index_pattern, safe_index_path, write_json
from schema_digest import choose_interesting_fields, flatten_properties


def main() -> None:
    settings = load_settings()
    payload = read_payload()
    index_pattern = resolve_index_pattern(payload, settings)
    field_filter = str(payload.get("field_filter") or "").strip().lower()

    client = ESHttp(settings)
    try:
        mappings = client.get(f"/{safe_index_path(index_pattern)}/_mapping")
    finally:
        client.close()

    flattened = []
    for _, index_data in mappings.items():
        props = (((index_data or {}).get("mappings") or {}).get("properties") or {})
        flattened.extend(flatten_properties(props))
    dedup = {item["field"]: item for item in flattened}
    flattened = list(dedup.values())
    if field_filter:
        flattened = [item for item in flattened if field_filter in item["field"].lower()]
    flattened.sort(key=lambda x: x["field"])
    interesting = choose_interesting_fields(flattened, max_fields=150)
    write_json({"ok": True, "index_pattern": index_pattern, "field_count": len(flattened), "fields": interesting, "summary": f"Flattened mappings for {index_pattern}. Returned {len(interesting)} fields."})


if __name__ == "__main__":
    main()
