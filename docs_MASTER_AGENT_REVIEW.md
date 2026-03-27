# Master Agent Review

## Main failure modes addressed in this build

1. **Index allowlist bypass**
   - Previous logic could incorrectly allow broader patterns because it matched both directions.
   - Fixed by enforcing one-way matching: the requested pattern must match an allowed pattern.

2. **Fragile DSL text search**
   - Model-generated `query_string` payloads can break on punctuation or reserved characters.
   - Fixed by sanitizing DSL before validation/execution and rewriting `query_string` to `simple_query_string`.

3. **Unbounded or overly expensive requests**
   - Large `size`, large `terms.size`, or huge `_source` lists can bloat responses and slow the app.
   - Fixed by capping top-level hit count, aggregation size, `_source` field count, and `track_total_hits`.

4. **ES|QL source drift**
   - Raw ES|QL `FROM` clauses could target index patterns outside the intended scope.
   - Fixed by parsing `FROM` sources and enforcing the same allowlist used by DSL tools.

5. **UI resilience and stability**
   - The shell is now fixed-height with independent scroll regions for history, chat, and console.
   - Browser-native confirm/prompt patterns were already replaced with custom UI; this version keeps that but tightens the visual system and interaction flow.

6. **Database durability**
   - Enabled WAL mode and foreign key enforcement for better local persistence behavior.

7. **Input safety**
   - Added a configurable maximum message length.

## Recommended next upgrades

- Add a deterministic query-builder tool for the most common intent families (top-N, count-by-field, recent docs).
- Add optional schema caching to reduce repeated `_field_caps` and `_mapping` calls on large index patterns.
- Add per-turn trace IDs and exportable trace bundles for debugging production issues.
- Add a read-only “saved views” system once the master-agent behavior stabilizes.
