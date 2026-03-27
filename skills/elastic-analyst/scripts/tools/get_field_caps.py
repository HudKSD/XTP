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
    fields = payload.get("fields", "*")
    fields_param = ",".join(fields) if isinstance(fields, list) else str(fields or "*")

    client = ESHttp(settings)
    try:
        data = client.post(f"/{safe_index_path(index_pattern)}/_field_caps", params={"fields": fields_param})
    finally:
        client.close()

    fields_out = []
    for field_name, type_map in (data.get("fields") or {}).items():
        entry = {"field": field_name, "types": []}
        searchable = False
        aggregatable = False
        metadata_field = False
        for field_type, meta in type_map.items():
            entry["types"].append(field_type)
            searchable = searchable or bool(meta.get("searchable"))
            aggregatable = aggregatable or bool(meta.get("aggregatable"))
            metadata_field = metadata_field or bool(meta.get("metadata_field"))
        entry["searchable"] = searchable
        entry["aggregatable"] = aggregatable
        entry["metadata_field"] = metadata_field
        fields_out.append(entry)
    fields_out.sort(key=lambda x: x["field"])
    write_json({"ok": True, "index_pattern": index_pattern, "field_count": len(fields_out), "fields": fields_out[:200], "summary": f"Collected field capabilities for {len(fields_out)} fields from {index_pattern}."})


if __name__ == "__main__":
    main()
