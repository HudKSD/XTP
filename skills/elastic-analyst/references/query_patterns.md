# Query Routing Hints

Use Query DSL when the question sounds like:

- how many
- top 10
- count docs where
- group by
- min / max / avg
- trend over time
- recent documents matching X
- list/show/find recent documents about a topic or phrase
- search-box style retrieval over article/document text
- search-box style questions over article text

Use ES|QL when the question sounds like:

- show me a table
- compare A and B
- correlate these fields
- keep only these columns
- sort the result rows
- multi-step pipe-friendly analysis

ES|QL notes:

- For time filters, use ES|QL date math like `NOW() - 30 day`, not SQL `INTERVAL 30 DAY`.
- `LIKE` in ES|QL uses `*` and `?` wildcards, not SQL `%` and `_`.
- For full-text search in ES|QL, prefer `MATCH`, `MATCH_PHRASE`, or `QSTR` rather than `LIKE`.
- If fields may be missing across indices, `SET unmapped_fields="nullify";` can reduce failures.

Avoid using raw `query_string` as the main search-box strategy. Prefer structured Query DSL, `simple_query_string`, `multi_match`, or ES|QL search functions.
