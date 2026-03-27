from __future__ import annotations

from typing import Any


def flatten_properties(properties: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, meta in (properties or {}).items():
        path = f"{prefix}.{name}" if prefix else name
        field_type = meta.get("type", "object")
        rows.append(
            {
                "field": path,
                "type": field_type,
                "searchable": meta.get("index", True),
                "aggregatable": field_type in {"keyword", "date", "long", "integer", "float", "double", "ip", "boolean"},
                "fields": list((meta.get("fields") or {}).keys()),
            }
        )
        if "properties" in meta:
            rows.extend(flatten_properties(meta["properties"], prefix=path))
    return rows


def choose_interesting_fields(flattened: list[dict[str, Any]], max_fields: int = 120) -> list[dict[str, Any]]:
    preferred_order = []
    keywordish = []
    textish = []
    dated = []
    numeric = []
    other = []

    for item in flattened:
        field_type = item.get("type")
        name = item.get("field", "")
        if "timestamp" in name.lower() or name.startswith("@timestamp"):
            dated.append(item)
        elif field_type in {"keyword", "constant_keyword"}:
            keywordish.append(item)
        elif field_type in {"text", "match_only_text"}:
            textish.append(item)
        elif field_type in {"integer", "long", "float", "double", "date"}:
            numeric.append(item)
        else:
            other.append(item)

    preferred_order.extend(dated)
    preferred_order.extend(keywordish)
    preferred_order.extend(textish)
    preferred_order.extend(numeric)
    preferred_order.extend(other)

    seen = set()
    result = []
    for item in preferred_order:
        key = item["field"]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= max_fields:
            break
    return result
