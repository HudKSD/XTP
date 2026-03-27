# LidarKinesis IntelChat

A Quart-based master-agent shell for natural-language investigations over **RBTN DB**.

## What this build focuses on

- natural-language chat over Elasticsearch data
- visible tool execution and live console telemetry
- grouped conversation history with rename/delete
- read-only Elasticsearch skills
- Dockerfile + docker-compose build context
- local SQLite chat persistence
- stronger query guardrails and safer routing
- fixed, production-style 3-pane workspace UI

## Robustness improvements in this version

- one-way allowlist enforcement for index patterns
- DSL sanitizer that rewrites fragile `query_string` to `simple_query_string`
- bounded hit counts, `_source` field counts, terms aggregation sizes, and `track_total_hits`
- ES|QL source validation against the same index allowlist used by DSL tools
- ES|QL sanitizer for common SQL-style mistakes and over-large `LIMIT`
- WAL-enabled SQLite with foreign keys on
- configurable maximum user message length
- local simulation tests for the main guardrails

## Quick start

1. Copy `.env.example` to `.env`
2. Fill in your OpenAI and Elasticsearch settings
3. Run:

```bash
docker compose up --build
```

4. Open `http://localhost:8000`

## Environment

- `OPENAI_API_KEY` - required
- `OPENAI_MODEL` - defaults to `gpt-5.4-mini`
- `ES_URL` - Elasticsearch base URL
- `ES_DEFAULT_INDEX` - default index pattern used when the user does not specify one
- `ES_DEFAULT_TIME_FIELD` - default time field for date-range analytics, e.g. `Timestamp`
- `ES_ALLOWED_INDEX_PATTERNS` - comma-separated allowlist, e.g. `data_cached_*,alerts-*`
- `ES_API_KEY` - optional Elasticsearch API key
- `ES_USERNAME` / `ES_PASSWORD` - optional basic auth
- `ES_VERIFY_CERTS` - `true` or `false`
- `ES_CA_CERTS` - optional CA file path inside the container
- `TOOL_TIMEOUT_SECONDS` - timeout for each tool script
- `MAX_MESSAGE_CHARS` - maximum user message length accepted by the websocket

## Local validation

Run the local simulation suite:

```bash
python tests/run_local_simulations.py
```

It checks:
- allowlist safety
- DSL sanitization
- ES|QL sanitization
- HTML/JS DOM contract
- Python compile health
