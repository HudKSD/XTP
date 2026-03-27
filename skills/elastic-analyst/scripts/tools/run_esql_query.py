from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INTERNAL_DIR = SCRIPT_DIR.parent / "internal"
if str(INTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERNAL_DIR))

from common import ESHttp, is_allowed_index_pattern, load_settings, read_payload, write_error, write_json

MAX_LIMIT = 100


def _strip_leading_set_statements(query: str) -> str:
    working = query.lstrip()
    while working.lower().startswith("set "):
        if ";" not in working:
            return ""
        working = working.split(";", 1)[1].lstrip()
    return working


def extract_from_sources(query: str) -> list[str]:
    working = _strip_leading_set_statements(query)
    if not working:
        return []
    match = re.search(r"\bFROM\s+([^\n|]+)", working, flags=re.IGNORECASE)
    if not match:
        return []
    source_block = match.group(1).strip()
    source_block = re.split(r"\bMETADATA\b", source_block, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    sources: list[str] = []
    for token in source_block.split(","):
        cleaned = token.strip().strip('"').strip("'")
        if cleaned:
            sources.append(cleaned)
    return sources


def ensure_limit(query: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    match = re.search(r"(\|\s*LIMIT\s+)(\d+)", query, flags=re.IGNORECASE)
    if not match:
        return query.rstrip() + f" | LIMIT {MAX_LIMIT}", warnings

    original = int(match.group(2))
    bounded = max(1, min(original, MAX_LIMIT))
    if bounded == original:
        return query, warnings

    warnings.append(f"Capped ES|QL LIMIT from {original} to {bounded}.")
    rewritten = query[: match.start(2)] + str(bounded) + query[match.end(2) :]
    return rewritten, warnings


def _rewrite_sql_interval_syntax(query: str) -> tuple[str, list[str]]:
    warnings: list[str] = []

    def repl(match: re.Match[str]) -> str:
        value = match.group(1)
        unit = match.group(2).lower()
        if value != "1" and not unit.endswith("s"):
            unit = unit + "s"
        warnings.append(
            f"Rewrote SQL INTERVAL syntax to ES|QL date math: INTERVAL {value} {match.group(2)} -> {value} {unit}"
        )
        return f"{value} {unit}"

    rewritten = re.sub(
        r'INTERVAL\s+[\'\"]?(\d+)[\'\"]?\s+(DAY|DAYS|WEEK|WEEKS|MONTH|MONTHS|YEAR|YEARS|HOUR|HOURS|MINUTE|MINUTES|SECOND|SECONDS)\b',
        repl,
        query,
        flags=re.IGNORECASE,
    )
    return rewritten, warnings


def _rewrite_like_wildcards(query: str) -> tuple[str, list[str]]:
    warnings: list[str] = []

    def repl(match: re.Match[str]) -> str:
        pattern = match.group(1)
        converted = pattern.replace("%", "*").replace("_", "?")
        if converted != pattern:
            warnings.append(f"Rewrote SQL LIKE wildcards in pattern {pattern!r} to ES|QL wildcards {converted!r}")
        return f'LIKE "{converted}"'

    rewritten = re.sub(r'LIKE\s+"([^"\n]*)"', repl, query, flags=re.IGNORECASE)
    return rewritten, warnings


def _ensure_unmapped_fields_directive(query: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    lowered = query.lstrip().lower()
    if lowered.startswith("set ") and "unmapped_fields" in lowered.split(";", 1)[0]:
        return query, warnings
    warnings.append('Added ES|QL directive SET unmapped_fields="nullify" to reduce failures on optional fields.')
    return 'SET unmapped_fields="nullify";\n' + query.lstrip(), warnings


def sanitize_query(query: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    sanitized = query.strip()
    for fn in (_rewrite_sql_interval_syntax, _rewrite_like_wildcards, _ensure_unmapped_fields_directive):
        sanitized, extra = fn(sanitized)
        warnings.extend(extra)
    sanitized, limit_warnings = ensure_limit(sanitized)
    warnings.extend(limit_warnings)
    return sanitized, warnings


def rows_from_values(columns, values):
    names = [col.get("name") for col in columns]
    rows = []
    for row in values:
        rows.append({name: row[idx] if idx < len(row) else None for idx, name in enumerate(names)})
    return rows


def main() -> None:
    settings = load_settings()
    payload = read_payload()
    query = str(payload.get("query") or "").strip()
    if not query:
        write_error("query is required")

    query, warnings = sanitize_query(query)

    sources = extract_from_sources(query)
    if not sources:
        write_error("ES|QL query must include a FROM clause with an allowed index pattern.")
    for source in sources:
        if not is_allowed_index_pattern(source, settings.allowed_index_patterns):
            write_error(
                f"ES|QL source '{source}' is not allowed.",
                {"allowed_index_patterns": settings.allowed_index_patterns},
            )

    client = ESHttp(settings)
    try:
        data = client.post("/_query", params={"format": "json"}, json={"query": query})
    finally:
        client.close()

    columns = data.get("columns", [])
    if "values" in data:
        rows = rows_from_values(columns, data.get("values", []))
    elif "rows" in data:
        rows = data.get("rows", [])
    else:
        rows = []

    write_json(
        {
            "ok": True,
            "query": query,
            "sources": sources,
            "warnings": warnings,
            "columns": columns,
            "row_count": len(rows),
            "rows": rows[:MAX_LIMIT],
            "summary": f"Ran ES|QL query and returned {len(rows)} rows." + (f" Applied {len(warnings)} sanitizer fix(es)." if warnings else ""),
        }
    )


if __name__ == "__main__":
    main()
