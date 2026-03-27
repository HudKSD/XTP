from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INTERNAL_DIR = SCRIPT_DIR.parent / "internal"
if str(INTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERNAL_DIR))

from common import ESHttp, load_settings, read_payload, resolve_index_pattern, safe_index_path, write_json
from dsl_guardrails import sanitize_query_body


def main() -> None:
    settings = load_settings()
    payload = read_payload()
    index_pattern = resolve_index_pattern(payload, settings)
    query_body = payload.get("query_body")
    if not isinstance(query_body, dict):
        write_json({
            "ok": False,
            "index_pattern": index_pattern,
            "error": "query_body must be an object",
            "expected_example": {
                "index_pattern": index_pattern,
                "query_body": {
                    "size": 10,
                    "query": {
                        "bool": {
                            "filter": [
                                {"range": {settings.default_time_field: {"gte": "now-30d/d", "lte": "now"}}}
                            ]
                        }
                    }
                }
            },
            "summary": "Search could not run because query_body was missing or not an object.",
        })
        return

    body, warnings = sanitize_query_body(query_body)

    client = ESHttp(settings)
    try:
        data = client.post(f"/{safe_index_path(index_pattern)}/_search", json=body)
    finally:
        client.close()

    hits = data.get("hits", {}).get("hits", [])
    trimmed_hits = [
        {
            "_index": hit.get("_index"),
            "_id": hit.get("_id"),
            "_score": hit.get("_score"),
            "_source": hit.get("_source"),
            "fields": hit.get("fields", {}),
        }
        for hit in hits
    ]
    total = data.get("hits", {}).get("total", {})
    total_value = total.get("value", 0) if isinstance(total, dict) else total
    write_json(
        {
            "ok": True,
            "index_pattern": index_pattern,
            "query_body": body,
            "warnings": warnings,
            "total_hits": total_value,
            "took_ms": data.get("took"),
            "hits": trimmed_hits,
            "aggregations": data.get("aggregations", {}),
            "summary": f"Ran DSL query on {index_pattern}. Returned {len(trimmed_hits)} hits and total {total_value}.",
        }
    )


if __name__ == "__main__":
    main()
