from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
INTERNAL_DIR = SCRIPT_DIR.parent / "internal"
if str(INTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERNAL_DIR))

from common import ESHttp, load_settings, read_payload, resolve_index_pattern, safe_index_path, write_json
from schema_digest import choose_interesting_fields, flatten_properties


def sample_examples(sample_docs, limit=8):
    examples = {}
    for item in sample_docs:
        source = item.get("_source") or item.get("source") or {}
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key in examples:
                continue
            examples[key] = value
            if len(examples) >= limit:
                return examples
    return examples


def main() -> None:
    settings = load_settings()
    payload = read_payload()
    index_pattern = resolve_index_pattern(payload, settings)
    sample_size = max(1, min(int(payload.get("sample_size", 3)), 5))

    client = ESHttp(settings)
    try:
        field_caps = client.post(f"/{safe_index_path(index_pattern)}/_field_caps", params={"fields": "*"})
        mappings = client.get(f"/{safe_index_path(index_pattern)}/_mapping")
        samples = client.post(f"/{safe_index_path(index_pattern)}/_search", json={"size": sample_size, "query": {"match_all": {}}, "sort": [{"_doc": "asc"}]})
    finally:
        client.close()

    flattened = []
    for _, index_data in mappings.items():
        props = (((index_data or {}).get("mappings") or {}).get("properties") or {})
        flattened.extend(flatten_properties(props))

    field_cap_rows = []
    type_counter = Counter()
    for field_name, type_map in (field_caps.get("fields") or {}).items():
        searchable = False
        aggregatable = False
        types = []
        for field_type, meta in type_map.items():
            types.append(field_type)
            type_counter[field_type] += 1
            searchable = searchable or bool(meta.get("searchable"))
            aggregatable = aggregatable or bool(meta.get("aggregatable"))
        field_cap_rows.append({"field": field_name, "types": sorted(types), "searchable": searchable, "aggregatable": aggregatable})

    field_cap_rows.sort(key=lambda x: x["field"])
    interesting_mapping_fields = choose_interesting_fields(flattened, max_fields=120)
    sample_hits = samples.get("hits", {}).get("hits", [])
    example_fields = sample_examples(sample_hits)
    suggested_time_fields = [item["field"] for item in field_cap_rows if item["field"].lower() in {"@timestamp", "timestamp"} or "timestamp" in item["field"].lower()][:5]
    suggested_text_fields = [item["field"] for item in field_cap_rows if any(t in {"text", "match_only_text"} for t in item["types"])][:10]
    suggested_keyword_fields = [item["field"] for item in field_cap_rows if any(t in {"keyword", "constant_keyword"} for t in item["types"])][:15]

    write_json({
        "ok": True,
        "index_pattern": index_pattern,
        "field_count": len(field_cap_rows),
        "type_counts": dict(type_counter),
        "suggested_time_fields": suggested_time_fields,
        "suggested_text_fields": suggested_text_fields,
        "suggested_keyword_fields": suggested_keyword_fields,
        "fields": field_cap_rows[:150],
        "mapping_digest": interesting_mapping_fields,
        "example_fields": example_fields,
        "sample_doc_ids": [hit.get("_id") for hit in sample_hits],
        "summary": f"Built schema catalog for {index_pattern} with {len(field_cap_rows)} fields.",
    })


if __name__ == "__main__":
    main()
