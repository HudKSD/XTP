from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INTERNAL_DIR = SCRIPT_DIR.parent / "internal"
if str(INTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERNAL_DIR))

from common import ESHttp, load_settings, read_payload, resolve_index_pattern, safe_index_path, write_json
from schema_digest import flatten_properties


CONCEPT_SYNONYMS = {
    "cve": ["cve", "cves", "vulnerability", "vulnerabilities", "kev"],
    "threat_actor": ["threat actor", "threat_actors", "actor", "actors", "adversary", "group", "groups", "campaign", "alias", "aliases"],
    "malware": ["malware", "malwares", "ransomware", "trojan", "backdoor", "botnet", "family", "families"],
    "vendor": ["vendor", "vendors", "publisher", "manufactur", "supplier"],
    "product": ["product", "products", "software", "application", "app", "service", "platform"],
    "country": ["country", "countries", "geography", "location", "nation", "nations"],
    "sector": ["sector", "sectors", "industry", "industries"],
    "technique": ["technique", "techniques", "ttp", "ttps", "mitre"],
    "tactic": ["tactic", "tactics", "stage", "kill chain"],
    "tool": ["tool", "tools", "framework", "utility"],
    "exploit": ["exploit", "exploits", "zero day", "zero_day", "0day"],
    "domain": ["domain", "domains", "fqdn"],
    "ip": ["ip", "ips", "ip address", "ip_addresses"],
    "company": ["company", "companies", "organization", "organisations", "org"],
}


def _normalize_concept(raw: str) -> str:
    text = (raw or "").strip().lower().replace("-", " ").replace("/", " ")
    if not text:
        return ""
    if any(term in text for term in ["cve", "vulnerability", "kev"]):
        return "cve"
    if any(term in text for term in ["threat actor", "adversary", "actor", "group", "campaign"]):
        return "threat_actor"
    if any(term in text for term in ["malware", "ransomware", "trojan", "family"]):
        return "malware"
    if any(term in text for term in ["vendor", "publisher", "supplier"]):
        return "vendor"
    if any(term in text for term in ["product", "software", "application", "service", "platform"]):
        return "product"
    if any(term in text for term in ["country", "geography", "location", "nation"]):
        return "country"
    if any(term in text for term in ["sector", "industry"]):
        return "sector"
    if any(term in text for term in ["technique", "ttp", "mitre"]):
        return "technique"
    if any(term in text for term in ["tactic", "stage", "kill chain"]):
        return "tactic"
    if any(term in text for term in ["tool", "framework", "utility"]):
        return "tool"
    if any(term in text for term in ["exploit", "zero day", "0day"]):
        return "exploit"
    if any(term in text for term in ["domain", "fqdn"]):
        return "domain"
    if any(term in text for term in ["ip", "ip address"]):
        return "ip"
    if any(term in text for term in ["company", "organization", "organisation", "org"]):
        return "company"
    return text.replace(" ", "_")


_ALIAS_LINE_RE = re.compile(r"^\s*-\s*(.*?)\s*->\s*(.*)$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")


def _load_alias_hints() -> list[tuple[str, list[str]]]:
    alias_file = SCRIPT_DIR.parent.parent / "references" / "field_aliases.md"
    rows: list[tuple[str, list[str]]] = []
    if not alias_file.exists():
        return rows
    for line in alias_file.read_text(encoding="utf-8").splitlines():
        match = _ALIAS_LINE_RE.match(line)
        if not match:
            continue
        left = match.group(1).strip().lower()
        fields = _BACKTICK_RE.findall(match.group(2))
        if fields:
            rows.append((left, fields))
    return rows


def _field_caps_rows(field_caps: dict) -> list[dict]:
    rows = []
    for field_name, type_map in (field_caps.get("fields") or {}).items():
        types = sorted(type_map.keys())
        searchable = any(bool(meta.get("searchable")) for meta in type_map.values())
        aggregatable = any(bool(meta.get("aggregatable")) for meta in type_map.values())
        rows.append({
            "field": field_name,
            "types": types,
            "searchable": searchable,
            "aggregatable": aggregatable,
        })
    rows.sort(key=lambda x: x["field"])
    return rows


def _score_field(field_name: str, synonyms: list[str], explicit_alias_targets: set[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    lower = field_name.lower()
    base = lower[:-8] if lower.endswith('.keyword') else lower

    if field_name in explicit_alias_targets:
        score += 100
        reasons.append("exact_alias_hint")
    elif base in {x.lower() for x in explicit_alias_targets}:
        score += 90
        reasons.append("alias_hint_parent")

    for syn in synonyms:
        syn_l = syn.lower().replace(" ", "_")
        if syn_l in lower:
            score += 35
            reasons.append(f"name_contains:{syn}")
        else:
            plain = syn.lower()
            if plain in lower.replace("_", " ").replace(".", " "):
                score += 25
                reasons.append(f"name_phrase:{syn}")

    if lower.endswith('.keyword'):
        score += 8
        reasons.append("keyword_subfield")

    if lower.endswith('.text'):
        score -= 2
    return score, reasons


def _fallback_text_fields(rows: list[dict]) -> list[str]:
    preferred = [
        "Title",
        "doc_summary",
        "summary",
        "Source",
        "article_url",
        "stats.topics.summary",
        "stats.topics.topic",
    ]
    available = {row["field"] for row in rows}
    result = [field for field in preferred if field in available]
    if result:
        return result[:6]
    text_like = [row["field"] for row in rows if any(t in {"text", "match_only_text", "keyword"} for t in row.get("types", []))]
    return text_like[:6]


def main() -> None:
    settings = load_settings()
    payload = read_payload()
    index_pattern = resolve_index_pattern(payload, settings)
    concept_raw = str(payload.get("concept") or payload.get("entity") or "").strip()
    if not concept_raw:
        write_json({
            "ok": False,
            "index_pattern": index_pattern,
            "error": "concept is required",
            "summary": "Semantic field resolution could not run because concept was missing.",
        })
        return

    max_candidates = max(1, min(int(payload.get("max_candidates", 8)), 20))
    concept = _normalize_concept(concept_raw)
    synonyms = CONCEPT_SYNONYMS.get(concept, [concept.replace("_", " "), concept])

    client = ESHttp(settings)
    try:
        field_caps = client.post(f"/{safe_index_path(index_pattern)}/_field_caps", params={"fields": "*"})
        mappings = client.get(f"/{safe_index_path(index_pattern)}/_mapping")
    finally:
        client.close()

    rows = _field_caps_rows(field_caps)

    alias_rows = _load_alias_hints()
    explicit_alias_targets: set[str] = set()
    for left, fields in alias_rows:
        left_norm = _normalize_concept(left)
        if left_norm == concept or any(syn in left for syn in synonyms):
            explicit_alias_targets.update(fields)

    scored: list[dict] = []
    for row in rows:
        score, reasons = _score_field(row["field"], synonyms, explicit_alias_targets)
        if score <= 0:
            continue
        scored.append({**row, "score": score, "reasons": reasons})

    scored.sort(key=lambda x: (-x["score"], x["field"]))

    recommended_agg = [row["field"] for row in scored if row.get("aggregatable")][:max_candidates]
    recommended_search = [row["field"] for row in scored if row.get("searchable")][:max_candidates]

    if not recommended_agg:
        # if an alias target exists for a parent field, prefer its keyword subfield when present
        for target in explicit_alias_targets:
            keyword_candidate = f"{target}.keyword"
            if any(row["field"] == keyword_candidate for row in rows):
                recommended_agg.append(keyword_candidate)
            elif any(row["field"] == target and row.get("aggregatable") for row in rows):
                recommended_agg.append(target)
        recommended_agg = recommended_agg[:max_candidates]

    mapping_paths = []
    for _, index_data in mappings.items():
        props = (((index_data or {}).get("mappings") or {}).get("properties") or {})
        mapping_paths.extend(flatten_properties(props))

    mapping_matches = [item for item in mapping_paths if any(syn.lower().replace(" ", "_") in item["field"].lower() for syn in synonyms)]
    mapping_matches = sorted(mapping_matches, key=lambda x: x["field"])[:max_candidates]

    fallback_text_fields = _fallback_text_fields(rows)
    structured_match_found = bool(scored)

    write_json({
        "ok": True,
        "index_pattern": index_pattern,
        "concept": concept,
        "concept_raw": concept_raw,
        "synonyms_used": synonyms,
        "structured_match_found": structured_match_found,
        "explicit_alias_targets": sorted(explicit_alias_targets),
        "candidate_fields": scored[:max_candidates],
        "recommended_agg_fields": recommended_agg[:max_candidates],
        "recommended_search_fields": recommended_search[:max_candidates],
        "fallback_text_fields": fallback_text_fields,
        "mapping_matches": mapping_matches,
        "summary": (
            f"Resolved semantic field candidates for concept '{concept_raw}' on {index_pattern}. "
            f"Structured matches found: {'yes' if structured_match_found else 'no'}."
        ),
    })


if __name__ == "__main__":
    main()
