from __future__ import annotations

from copy import deepcopy
from typing import Any

MAX_HITS = 25
MAX_TERMS_BUCKETS = 50
MAX_SOURCE_FIELDS = 40
MAX_TRACK_TOTAL_HITS = 10000


def sanitize_query_body(query_body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    body = deepcopy(query_body)
    warnings: list[str] = []

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            rewritten: dict[str, Any] = {}
            for key, child in value.items():
                if key == "query_string" and isinstance(child, dict):
                    rewritten["simple_query_string"] = _rewrite_query_string(child, warnings)
                    continue

                if key == "terms" and isinstance(child, dict):
                    child = _cap_terms_agg(child, warnings)

                rewritten[key] = walk(child)
            return rewritten
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    body = walk(body)

    if isinstance(body, dict):
        size = body.get("size", 10)
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 10
            warnings.append("Normalised invalid top-level size to 10.")
        bounded_size = max(0, min(size, MAX_HITS))
        if bounded_size != size:
            warnings.append(f"Capped top-level size from {size} to {bounded_size}.")
        body["size"] = bounded_size

        source_fields = body.get("_source")
        if isinstance(source_fields, list) and len(source_fields) > MAX_SOURCE_FIELDS:
            warnings.append(
                f"Trimmed _source field list from {len(source_fields)} to {MAX_SOURCE_FIELDS} to keep responses bounded."
            )
            body["_source"] = source_fields[:MAX_SOURCE_FIELDS]

        track_total_hits = body.get("track_total_hits")
        if isinstance(track_total_hits, int) and track_total_hits > MAX_TRACK_TOTAL_HITS:
            body["track_total_hits"] = MAX_TRACK_TOTAL_HITS
            warnings.append(
                f"Capped track_total_hits from {track_total_hits} to {MAX_TRACK_TOTAL_HITS}."
            )

    return body, warnings


def _rewrite_query_string(payload: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    rewritten = deepcopy(payload)
    warnings.append(
        "Rewrote query_string to simple_query_string to make search input more tolerant of punctuation and reserved characters."
    )
    return rewritten


def _cap_terms_agg(payload: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    rewritten = {key: value for key, value in payload.items()}
    if "size" in rewritten:
        try:
            original_size = int(rewritten["size"])
        except (TypeError, ValueError):
            original_size = MAX_TERMS_BUCKETS
            warnings.append("Normalised invalid terms aggregation size to a safe default.")
        bounded_size = max(1, min(original_size, MAX_TERMS_BUCKETS))
        if bounded_size != original_size:
            warnings.append(
                f"Capped terms aggregation size from {original_size} to {bounded_size}."
            )
        rewritten["size"] = bounded_size
    return rewritten
