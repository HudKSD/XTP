from __future__ import annotations

import compileall
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTERNAL_DIR = ROOT / "skills" / "elastic-analyst" / "scripts" / "internal"
TOOLS_DIR = ROOT / "skills" / "elastic-analyst" / "scripts" / "tools"
APP_DIR = ROOT / "app"

sys.path.insert(0, str(INTERNAL_DIR))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(ROOT))

from common import is_allowed_index_pattern  # type: ignore
from dsl_guardrails import sanitize_query_body  # type: ignore
from run_esql_query import extract_from_sources, sanitize_query  # type: ignore


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_allowlist() -> None:
    allowed = ["data_cached_*", "alerts-*"]
    assert_true(is_allowed_index_pattern("data_cached_compute", allowed), "expected allowed concrete index")
    assert_true(not is_allowed_index_pattern("*", allowed), "wildcard '*' should not bypass allowlist")
    assert_true(not is_allowed_index_pattern("data_*", allowed), "broader pattern should not bypass allowlist")


def test_dsl_sanitizer() -> None:
    body = {
        "size": 500,
        "_source": [f"field_{i}" for i in range(60)],
        "query": {
            "bool": {
                "should": [
                    {
                        "query_string": {
                            "query": 'AI OR "prompt injection"',
                            "fields": ["Title^3", "doc_summary^2"],
                        }
                    }
                ]
            }
        },
        "aggs": {"top_terms": {"terms": {"field": "search_topics.keyword", "size": 500}}},
    }
    sanitized, warnings = sanitize_query_body(body)
    assert_true(sanitized["size"] == 25, "top-level size should be capped")
    assert_true(len(sanitized["_source"]) == 40, "_source field list should be trimmed")
    should_clause = sanitized["query"]["bool"]["should"][0]
    assert_true("simple_query_string" in should_clause, "query_string should be rewritten")
    assert_true(sanitized["aggs"]["top_terms"]["terms"]["size"] == 50, "terms agg size should be capped")
    assert_true(bool(warnings), "sanitizer should emit warnings")


def test_esql_sanitizer() -> None:
    query = 'FROM data_cached_* | WHERE Timestamp >= NOW() - INTERVAL 30 DAY AND Title LIKE "%AI%" | LIMIT 2000'
    sanitized, warnings = sanitize_query(query)
    sources = extract_from_sources(sanitized)
    assert_true(sources == ["data_cached_*"], "should extract FROM source")
    assert_true("30 days" in sanitized.lower(), "interval syntax should be rewritten")
    assert_true('LIKE "*AI*"' in sanitized, "LIKE wildcards should be rewritten")
    assert_true(re.search(r"\|\s*LIMIT\s+100\b", sanitized, flags=re.IGNORECASE) is not None, "limit should be capped")
    assert_true(not sanitized.lower().startswith("set "), "sanitizer should stay compatible with clusters that reject SET preambles")
    assert_true(bool(warnings), "sanitizer should emit at least one warning when rewrites occur")


def test_template_contract() -> None:
    html = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'getElementById\("([^"]+)"\)', js))
    missing = [element_id for element_id in ids if f'id="{element_id}"' not in html]
    assert_true(not missing, f"missing HTML ids for JS contract: {missing}")


def test_python_compiles() -> None:
    ok = compileall.compile_dir(str(APP_DIR), quiet=1)
    ok = compileall.compile_dir(str(ROOT / "skills"), quiet=1) and ok
    assert_true(ok, "python sources should compile")


def main() -> None:
    tests = [
        test_allowlist,
        test_dsl_sanitizer,
        test_esql_sanitizer,
        test_template_contract,
        test_python_compiles,
    ]
    results = []
    for test in tests:
        test()
        results.append({"test": test.__name__, "ok": True})
    print(json.dumps({"ok": True, "results": results}, indent=2))


if __name__ == "__main__":
    main()
