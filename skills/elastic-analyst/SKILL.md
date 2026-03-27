---
name: elastic-analyst
description: Read-only Elasticsearch analyst skill for schema discovery, Query DSL, and ES|QL.
tags: [elasticsearch, esql, query-dsl, schema, analytics]
---

# RBTN DB Analyst Skill

Use this skill when the user wants to explore, search, count, compare, correlate, or summarize data stored in Elasticsearch.

## What this skill can do

- Inspect index patterns and list available indices
- Discover field names and capabilities
- Resolve semantic field candidates for concepts like CVEs, actors, malware, vendors, products, sectors, and countries
- Flatten mappings into agent-friendly field catalogs
- Fetch representative sample documents
- Run read-only Query DSL searches
- Validate DSL before execution
- Run ES|QL for analyst-style, table-shaped queries
- Get top values for a field
- Estimate counts and time-range coverage

## Recommended tool order

1. Start with `get_schema_catalog` when:
   - the field names are unclear
   - the user asks about “fields” or “schema”
   - the index is new to you

2. Use `resolve_semantic_fields` when the user asks about business concepts like CVEs, threat actors, malware, vendors, products, techniques, tactics, sectors, or countries.

3. Use `get_field_caps` or `get_mappings` only when you need more detail than the schema catalog provides.

4. Choose `run_dsl_query` for:
   - counts
   - top-N rankings
   - exact aggregations
   - time-bounded filtering
   - precision over specific fields

5. Choose `run_esql_query` for:
   - row/table-style answers
   - comparisons
   - multi-step analyst workflows
   - clear tabular output

6. Use `validate_dsl_query` before executing non-trivial DSL.

## Safety rules

- This skill is **read-only**.
- Never ask for write, update, delete, or reindex actions.
- Never invent field names. Discover them first.
- For semantic concepts, prefer `resolve_semantic_fields` so you use verified candidate fields.
- Keep result sets bounded.
- Prefer exact `.keyword` fields for aggregations when available.

## Common patterns

- “What fields exist?” → `get_schema_catalog`
- “How many X in the last 7 days?” → resolve semantic fields if X is a business concept, then DSL
- “Show top vendors this month” → DSL aggregation
- “Compare actors and CVEs mentioned together” → ES|QL or DSL depending on the shape of the answer
- “List recent documents about a topic” → DSL


## DSL tool argument examples

When calling `validate_dsl_query` or `run_dsl_query`, always pass a full `query_body` object.

Example: count documents in the last 30 days

```json
{
  "index_pattern": "data_cached_*",
  "query_body": {
    "size": 0,
    "query": {
      "bool": {
        "filter": [
          {
            "range": {
              "Timestamp": {
                "gte": "now-30d/d",
                "lte": "now"
              }
            }
          }
        ]
      }
    }
  }
}
```

Example: top 3 values for a field in the last 30 days

```json
{
  "index_pattern": "data_cached_*",
  "query_body": {
    "size": 0,
    "query": {
      "bool": {
        "filter": [
          {
            "range": {
              "Timestamp": {
                "gte": "now-30d/d",
                "lte": "now"
              }
            }
          }
        ]
      }
    },
    "aggs": {
      "top_values": {
        "terms": {
          "field": "Extracted_Entities.CVEs.keyword",
          "size": 3
        }
      }
    }
  }
}
```

If the exact field is unknown, call `resolve_semantic_fields` first and verify the actual field name before running DSL. For CVE questions, do not assume `cveID`; inspect schema first and use the confirmed CVE field. If no structured CVE field exists, say that explicitly and fall back to text fields for mention-level searches only.


## ES|QL safety notes

- Use ES|QL only when the user clearly wants a table/pipeline style result.
- For free-text search over article text, prefer Query DSL with `simple_query_string` or `multi_match`.
- If ES|QL is used, do **not** write SQL-style `INTERVAL 30 DAY`; write `NOW() - 30 day`.
- If ES|QL is used, do **not** write SQL `%term%` patterns with `LIKE`; ES|QL `LIKE` uses `*` and `?`, and full-text search is usually better handled by `MATCH`, `MATCH_PHRASE`, or `QSTR`.
- When fields may be unmapped across some indices, use `SET unmapped_fields="nullify";` or rely on the `run_esql_query` tool to add it automatically.
