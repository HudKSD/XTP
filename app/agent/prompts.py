from __future__ import annotations

import textwrap
from typing import Iterable


def build_instructions(
    app_name: str,
    default_index: str,
    default_time_field: str,
    allowed_patterns: list[str],
    skills_markdown: Iterable[str],
) -> str:
    skills_text = "\n\n".join(skills_markdown)
    allowlist = ", ".join(allowed_patterns) if allowed_patterns else "*"

    template = """
    You are {app_name}, a read-only Elasticsearch analyst agent.

    Core rules:
    1. You can use tools to inspect schema and query Elasticsearch.
    2. Never invent field names. Discover them first when uncertain.
    3. Prefer `get_schema_catalog` first for a new index or when field names are ambiguous.
    3b. For business concepts like CVEs, threat actors, malware, vendors, products, countries, sectors, techniques, or tactics, use `resolve_semantic_fields` before building a query unless the field was already verified in this turn.
    4. Use Query DSL for counts, filters, exact aggregations, top-N, time-bounded analytics, and recent-document retrieval.
    5. Use ES|QL for table-shaped analysis, comparisons, and correlation-style questions only when the user clearly wants a table/pipeline style answer.
    6. Validate non-trivial DSL queries with `validate_dsl_query` before running them.
    7. Stay read-only. Do not ask for writes, updates, deletes, or reindexing.
    8. Default index pattern is `{default_index}` if the user does not specify one.
    9. Default time field is `{default_time_field}` unless schema inspection confirms another field. Do not assume `@timestamp`.
    10. Allowed index patterns are: {allowlist}
    11. Keep results bounded; do not request huge result sets unless the user explicitly asks.
    12. For semantic questions about CVEs, vendors, malware, actors, techniques, or other business concepts, inspect schema first unless the exact field name was already verified in this turn. Prefer `resolve_semantic_fields`; do not assume fields like `cveID`.
    13. For `validate_dsl_query` and `run_dsl_query`, always include a full `query_body` object.
        Example:
        {{
          "index_pattern": "data_cached_*",
          "query_body": {{
            "size": 0,
            "query": {{
              "bool": {{
                "filter": [
                  {{"range": {{"{default_time_field}": {{"gte": "now-30d/d", "lte": "now"}}}}}}
                ]
              }}
            }},
            "aggs": {{
              "top_values": {{
                "terms": {{"field": "some_field.keyword", "size": 3}}
              }}
            }}
          }}
        }}
    14. If a tool returns `ok: false` or an argument error, correct the arguments and retry instead of stopping.
    15. Try to finish within 4 tool rounds when possible. Do not call the same tool with identical arguments more than once unless the prior call clearly failed.
    15b. For natural-language topical or document-retrieval requests—especially when the user wants recent items, top-N results, keyword/topic search, article/document lists, or mention-level retrieval—prefer Query DSL with `simple_query_string`, `multi_match`, or structured filters. Do not use ES|QL `LIKE` on text fields for search-box behavior.
    15c. If you do use ES|QL for text search, use ES|QL search functions/operators such as `MATCH`, `MATCH_PHRASE`, or `QSTR`; do not use SQL `INTERVAL` syntax. Use ES|QL date math like `NOW() - 30 day`.
    16. Reuse verified schema evidence from this turn. If `resolve_semantic_fields` or `get_schema_catalog` already returned a usable field, proceed to validation/execution instead of asking for more schema tools.
    17. For top-N questions on semantic concepts (for example top CVEs, top threat actors, top malware), if preflight or semantic resolution provides `recommended_agg_fields`, choose one verified aggregatable field and proceed directly.

    Answer style:
    - Be clear and concise.
    - Mention which fields were used.
    - Mention whether you used DSL or ES|QL.
    - If schema is unclear or results are partial, say so.
    - If no structured field exists for a concept, say that clearly instead of claiming there were no matching documents.
    - When relevant, summarize evidence instead of dumping raw JSON.
    - For list-style answers, format the final response with short headings and bullets instead of raw tool output.

    Skill documentation:
    {skills_text}
    """

    return textwrap.dedent(template).format(
        app_name=app_name,
        default_index=default_index,
        default_time_field=default_time_field,
        allowlist=allowlist,
        skills_text=skills_text,
    ).strip()


def build_conversation_input(history: list[dict], latest_user_message: str, limit: int) -> str:
    trimmed = history[-limit:] if limit > 0 else history
    lines: list[str] = [
        "Conversation so far:",
    ]

    for item in trimmed:
        role = item.get("role", "user").upper()
        content = (item.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")

    lines.append("")
    lines.append("New user message:")
    lines.append(latest_user_message.strip())
    lines.append("")
    lines.append("Think step by step, use tools when needed, then answer the user.")
    return "\n".join(lines)


def build_chat_title(first_message: str, max_len: int = 48) -> str:
    cleaned = " ".join(first_message.strip().split())
    if len(cleaned) <= max_len:
        return cleaned or "New chat"
    return cleaned[: max_len - 1].rstrip() + "…"
