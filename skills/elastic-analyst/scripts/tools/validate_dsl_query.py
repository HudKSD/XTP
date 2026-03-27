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
                    "size": 0,
                    "query": {
                        "bool": {
                            "filter": [
                                {"range": {settings.default_time_field: {"gte": "now-30d/d", "lte": "now"}}}
                            ]
                        }
                    }
                }
            },
            "summary": "Validation could not run because query_body was missing or not an object.",
        })
        return

    sanitized_body, warnings = sanitize_query_body(query_body)
    query = sanitized_body.get("query") if "query" in sanitized_body else sanitized_body

    client = ESHttp(settings)
    try:
        data = client.post(
            f"/{safe_index_path(index_pattern)}/_validate/query",
            params={"explain": "true"},
            json={"query": query},
        )
    finally:
        client.close()

    write_json(
        {
            "ok": True,
            "index_pattern": index_pattern,
            "valid": data.get("valid", False),
            "warnings": warnings,
            "sanitized_query_body": sanitized_body,
            "explanations": data.get("explanations", []),
            "summary": f"Validation completed for DSL query on {index_pattern}. Valid={data.get('valid', False)}.",
        }
    )


if __name__ == "__main__":
    main()
