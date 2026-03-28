from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from app.agent.prompts import build_conversation_input, build_instructions
from app.agent.tool_registry import ToolExecutionError, ToolRegistry
from app.agent.tracing import TraceLogger
from app.config import Settings

Emitter = Callable[[str, dict[str, Any]], Awaitable[None]]


class ElasticAgent:
    def __init__(self, settings: Settings, tool_registry: ToolRegistry, trace_logger: TraceLogger) -> None:
        self.settings = settings
        self.tool_registry = tool_registry
        self.trace_logger = trace_logger
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

        skill_docs = self.tool_registry.load_skill_markdown()
        self.instructions = build_instructions(
            app_name=settings.app_name,
            default_index=settings.es_default_index,
            default_time_field=settings.es_default_time_field,
            allowed_patterns=settings.es_allowed_index_patterns,
            skills_markdown=skill_docs,
        )

    async def run_turn(
        self,
        chat_id: str,
        history: list[dict[str, Any]],
        latest_user_message: str,
        emit: Emitter,
    ) -> tuple[str, dict[str, Any]]:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        await emit(
            "status",
            {
                "message": "Loaded skill: elastic-analyst",
                "phase": "skill_load",
            },
        )
        self.trace_logger.write(chat_id, {"type": "skill_load", "skill": "elastic-analyst"})

        preflight_context = await self._build_preflight_context(chat_id, latest_user_message, emit)
        router_context = _build_router_context(latest_user_message)

        conversation_input = build_conversation_input(
            history=history,
            latest_user_message=latest_user_message,
            limit=self.settings.transcript_message_limit,
        )
        if preflight_context:
            conversation_input = preflight_context + "\n\n" + conversation_input

        await emit("status", {"message": "Thinking...", "phase": "reasoning"})

        response = await self.client.responses.create(
            model=self.settings.openai_model,
            input=conversation_input,
            instructions=self.instructions,
            tools=self.tool_registry.openai_tool_definitions(),
            reasoning={"effort": self.settings.openai_reasoning_effort},
            max_output_tokens=self.settings.openai_max_output_tokens,
        )

        tool_trace: list[dict[str, Any]] = []
        max_rounds = max(1, self.settings.tool_loop_max_rounds)
        repeat_limit = max(1, self.settings.tool_repeat_limit)
        rounds = 0
        call_fingerprints: dict[str, int] = defaultdict(int)

        while True:
            rounds += 1
            if rounds > max_rounds:
                await emit(
                    "status",
                    {
                        "message": f"Tool round budget reached ({max_rounds}). Finalizing with best effort...",
                        "phase": "answering",
                    },
                )
                self.trace_logger.write(
                    chat_id,
                    {
                        "type": "tool_loop_budget_reached",
                        "max_rounds": max_rounds,
                        "tool_trace": tool_trace,
                    },
                )
                return await self._force_finalize(
                    chat_id=chat_id,
                    history=history,
                    latest_user_message=latest_user_message,
                    preflight_context="\n\n".join(part for part in [router_context, preflight_context] if part),
                    tool_trace=tool_trace,
                )

            function_calls = [
                item for item in getattr(response, "output", [])
                if getattr(item, "type", "") == "function_call"
            ]
            if not function_calls:
                final_text = _extract_output_text(response)
                followups = await self._generate_followups(latest_user_message, final_text, tool_trace)
                meta = {
                    "model": self.settings.openai_model,
                    "tools_used": [entry["tool_name"] for entry in tool_trace],
                    "tool_trace": tool_trace,
                    "followups": followups,
                }
                self.trace_logger.write(
                    chat_id,
                    {
                        "type": "assistant_final",
                        "tools_used": meta["tools_used"],
                        "answer": final_text,
                    },
                )
                return final_text, meta

            outputs_for_model: list[dict[str, Any]] = []

            for call in function_calls:
                tool_name = call.name
                try:
                    args = json.loads(call.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Model returned invalid tool args for {tool_name}: {call.arguments}") from exc

                fingerprint = self._fingerprint_tool_call(tool_name, args)
                call_fingerprints[fingerprint] += 1
                if call_fingerprints[fingerprint] > repeat_limit:
                    repeat_error = {
                        "ok": False,
                        "tool_name": tool_name,
                        "arguments": args,
                        "error": (
                            f"Repeated tool call blocked: {tool_name} with identical arguments was already used "
                            f"{call_fingerprints[fingerprint] - 1} time(s) in this turn."
                        ),
                        "retry_hint": (
                            "Reuse prior tool output. If you already have verified schema or semantic field candidates, "
                            "move on to validation, execution, or final answer instead of repeating the same tool call."
                        ),
                    }
                    self.trace_logger.write(
                        chat_id,
                        {
                            "type": "tool_repeat_blocked",
                            "tool_name": tool_name,
                            "arguments": args,
                            "count": call_fingerprints[fingerprint],
                        },
                    )
                    tool_trace.append(
                        {
                            "tool_name": tool_name,
                            "arguments": args,
                            "summary": f"repeat_blocked: identical call attempted {call_fingerprints[fingerprint]} times",
                        }
                    )
                    outputs_for_model.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(repeat_error, ensure_ascii=False, default=str),
                        }
                    )
                    continue

                self.trace_logger.write(
                    chat_id,
                    {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "arguments": args,
                    },
                )

                try:
                    result = await self.tool_registry.execute(tool_name, args, emit)
                except ToolExecutionError as exc:
                    error_payload = {
                        "ok": False,
                        "tool_name": tool_name,
                        "arguments": args,
                        "error": str(exc),
                        "retry_hint": (
                            "Inspect the tool schema and retry with corrected arguments. "
                            "For validate_dsl_query and run_dsl_query, always send a full query_body object."
                        ),
                    }
                    self.trace_logger.write(
                        chat_id,
                        {
                            "type": "tool_error",
                            "tool_name": tool_name,
                            "arguments": args,
                            "error": str(exc),
                        },
                    )
                    tool_trace.append(
                        {
                            "tool_name": tool_name,
                            "arguments": args,
                            "summary": f"error: {str(exc)}",
                        }
                    )
                    outputs_for_model.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(error_payload, ensure_ascii=False, default=str),
                        }
                    )
                    continue

                tool_trace.append(
                    {
                        "tool_name": tool_name,
                        "arguments": args,
                        "summary": result.get("summary") or result.get("message") or ("error" if not result.get("ok", True) else "ok"),
                        "limitations": self._extract_limitations(tool_name, result),
                        "query_preview": self._extract_query_preview(tool_name, args, result),
                    }
                )
                outputs_for_model.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

            await emit("status", {"message": "Synthesizing answer...", "phase": "answering"})

            response = await self.client.responses.create(
                model=self.settings.openai_model,
                previous_response_id=response.id,
                input=outputs_for_model,
                instructions=self.instructions,
                tools=self.tool_registry.openai_tool_definitions(),
                reasoning={"effort": self.settings.openai_reasoning_effort},
                max_output_tokens=self.settings.openai_max_output_tokens,
            )

    async def _build_preflight_context(self, chat_id: str, latest_user_message: str, emit: Emitter) -> str:
        concepts = _extract_semantic_concepts(latest_user_message)
        if not concepts:
            return ""

        sections: list[str] = []
        index_pattern = self.settings.es_default_index
        for concept in concepts[:3]:
            await emit("status", {"message": f"Preflighting semantic fields for '{concept}'...", "phase": "preflight"})
            try:
                result = await self.tool_registry.execute(
                    "resolve_semantic_fields",
                    {"index_pattern": index_pattern, "concept": concept, "max_candidates": 6},
                    emit,
                )
            except Exception as exc:
                self.trace_logger.write(
                    chat_id,
                    {
                        "type": "preflight_error",
                        "concept": concept,
                        "error": str(exc),
                    },
                )
                continue

            self.trace_logger.write(
                chat_id,
                {
                    "type": "preflight_semantic_fields",
                    "concept": concept,
                    "result": result,
                },
            )

            candidate_lines = []
            for item in result.get("candidate_fields", [])[:4]:
                candidate_lines.append(
                    f"  - {item.get('field')} | types={','.join(item.get('types', []))} | searchable={item.get('searchable')} | aggregatable={item.get('aggregatable')} | reasons={','.join(item.get('reasons', []))}"
                )
            if not candidate_lines:
                candidate_lines.append("  - none")

            sections.append(
                "\n".join([
                    f"Verified semantic field candidates for concept '{concept}' on {index_pattern}:",
                    f"- structured_match_found: {result.get('structured_match_found')}",
                    f"- recommended_agg_fields: {result.get('recommended_agg_fields', [])}",
                    f"- recommended_search_fields: {result.get('recommended_search_fields', [])}",
                    f"- fallback_text_fields: {result.get('fallback_text_fields', [])}",
                    "- top candidates:",
                    *candidate_lines,
                ])
            )

        if not sections:
            return ""
        return "Preflight context (verified by tools; prefer these fields over guessed names):\n\n" + "\n\n".join(sections)

    def _fingerprint_tool_call(self, tool_name: str, args: dict[str, Any]) -> str:
        return f"{tool_name}::{json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)}"

    def _extract_query_preview(self, tool_name: str, args: dict[str, Any], result: dict[str, Any]) -> str:
        if tool_name == "run_esql_query":
            return str(result.get("query") or args.get("query") or "")
        if tool_name in {"run_dsl_query", "validate_dsl_query"}:
            body = result.get("query_body") or args.get("query_body")
            if isinstance(body, dict):
                return json.dumps(body, ensure_ascii=False, default=str)
        return ""

    def _extract_limitations(self, tool_name: str, result: dict[str, Any]) -> list[str]:
        flags: list[str] = []
        row_count = result.get("row_count")
        if tool_name == "run_esql_query" and isinstance(row_count, int):
            if row_count >= 100:
                flags.append("truncated")
                flags.append("sampled")
        warnings = result.get("warnings") or []
        if isinstance(warnings, list):
            warning_text = " ".join(str(item).lower() for item in warnings)
            if "unmapped" in warning_text or "conflict" in warning_text or "type" in warning_text:
                flags.append("schema_conflict")
            if "limit" in warning_text:
                flags.append("truncated")
        return sorted(set(flags))

    async def _force_finalize(
        self,
        chat_id: str,
        history: list[dict[str, Any]],
        latest_user_message: str,
        preflight_context: str,
        tool_trace: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        history_text = build_conversation_input(
            history=history,
            latest_user_message=latest_user_message,
            limit=self.settings.transcript_message_limit,
        )
        trace_lines = []
        for idx, entry in enumerate(tool_trace[-16:], start=1):
            trace_lines.append(
                f"{idx}. tool={entry.get('tool_name')} args={json.dumps(entry.get('arguments', {}), ensure_ascii=False, default=str)} summary={entry.get('summary', '')}"
            )
        trace_text = "\n".join(trace_lines) if trace_lines else "No tool results were collected."

        final_input = "\n\n".join(
            part for part in [
                preflight_context.strip(),
                "Conversation snapshot:\n" + history_text,
                "Tool trace summary:\n" + trace_text,
                (
                    "You have reached the tool round budget. Do not call tools. Provide the best possible answer using only the evidence above. "
                    "Be explicit about uncertainty. If a field was not verified, say so. If you cannot fully answer, explain what was confirmed and the most likely reason the query stalled."
                ),
            ] if part
        )

        response = await self.client.responses.create(
            model=self.settings.openai_model,
            input=final_input,
            instructions="You are a read-only Elasticsearch analyst. No tools are available in this step. Summarize clearly and honestly.",
            reasoning={"effort": "minimal"},
            max_output_tokens=self.settings.openai_max_output_tokens,
        )
        final_text = _extract_output_text(response)
        followups = await self._generate_followups(latest_user_message, final_text, tool_trace)
        meta = {
            "model": self.settings.openai_model,
            "tools_used": [entry["tool_name"] for entry in tool_trace],
            "tool_trace": tool_trace,
            "forced_finalization": True,
            "followups": followups,
        }
        self.trace_logger.write(
            chat_id,
            {
                "type": "assistant_final_forced",
                "tools_used": meta["tools_used"],
                "answer": final_text,
            },
        )
        return final_text, meta

    async def _generate_followups(
        self,
        latest_user_message: str,
        assistant_answer: str,
        tool_trace: list[dict[str, Any]],
    ) -> list[str]:
        tools_used = [entry.get("tool_name") for entry in tool_trace if entry.get("tool_name")]
        prompt = (
            "Generate exactly 5 concise, actionable follow-up prompts for a cybersecurity threat hunter.\n"
            "Requirements:\n"
            "- Must be specific to the user request and assistant answer.\n"
            "- Must be pivot-oriented (next investigative steps on IOC, actor, malware, infra, timeline, or sector).\n"
            "- Must avoid generic wording and avoid markdown symbols (*, **, backticks).\n"
            "- Each prompt must be a single line under 110 characters.\n"
            "- Return JSON only: {\"followups\":[\"...\",\"...\",\"...\",\"...\",\"...\"]}\n\n"
            f"User request:\n{latest_user_message}\n\n"
            f"Assistant answer:\n{assistant_answer}\n\n"
            f"Tools used:\n{', '.join(tools_used) if tools_used else 'none'}"
        )
        try:
            response = await self.client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
                instructions="You produce strict JSON only.",
                reasoning={"effort": "minimal"},
                max_output_tokens=320,
            )
            raw = _extract_output_text(response)
            items = _parse_followups_payload(raw)
            if not isinstance(items, list):
                return []
            cleaned: list[str] = []
            for value in items:
                text = _clean_followup_text(str(value or ""))
                if text and text not in cleaned:
                    cleaned.append(text[:110])
                if len(cleaned) >= 5:
                    break
            return cleaned
        except Exception:
            return []


def _extract_output_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text.strip()

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", "") != "message":
            continue
        for block in getattr(item, "content", []) or []:
            block_type = getattr(block, "type", "")
            if block_type in {"output_text", "text"}:
                value = getattr(block, "text", "")
                if value:
                    parts.append(value)

    return "\n".join(part.strip() for part in parts if part and part.strip()).strip()


def _parse_followups_payload(raw: str) -> list[str] | None:
    text = (raw or "").strip()
    if not text:
        return None

    def _get_list(candidate: Any) -> list[str] | None:
        if isinstance(candidate, dict) and isinstance(candidate.get("followups"), list):
            return [str(item) for item in candidate["followups"]]
        if isinstance(candidate, list):
            return [str(item) for item in candidate]
        return None

    try:
        direct = json.loads(text)
        parsed = _get_list(direct)
        if parsed is not None:
            return parsed
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fenced:
        try:
            parsed = _get_list(json.loads(fenced.group(1).strip()))
            if parsed is not None:
                return parsed
        except Exception:
            pass

    object_match = re.search(r"\{[\s\S]*\}", text)
    if object_match:
        try:
            parsed = _get_list(json.loads(object_match.group(0)))
            if parsed is not None:
                return parsed
        except Exception:
            pass
    return None


def _clean_followup_text(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(^|\W)\*([^*]+)\*(?=\W|$)", r"\1\2", text)
    text = re.sub(r"(^|\W)_([^_]+)_(?=\W|$)", r"\1\2", text)
    text = re.sub(r"^[-*•\d.)\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text




def _build_router_context(text: str) -> str:
    lower = (text or "").lower()

    table_words = ["table", "tabular", "columns", "compare", "correlate", "join", "pipeline", "esql", "group rows"]
    retrieval_verbs = ["list", "show", "find", "get", "return", "give me", "which", "what are"]
    recency_words = ["recent", "latest", "newest", "last", "past", "today", "yesterday", "this week", "this month"]
    aggregation_words = ["top", "count", "how many", "most", "least", "trend", "average", "avg", "sum", "min", "max"]
    document_words = ["article", "articles", "document", "documents", "attack", "attacks", "incident", "incidents", "story", "stories", "news", "post", "posts", "report", "reports"]
    text_search_words = ["about", "related", "mention", "mentions", "mentioning", "contains", "containing", "matching", "with keyword", "keyword", "topic", "phrase"]

    has_table_intent = any(word in lower for word in table_words)
    has_quoted_phrase = bool(re.search(r'"[^"]+"|\'[^\']+\'', text or ""))
    has_retrieval_shape = any(word in lower for word in retrieval_verbs) and (
        any(word in lower for word in document_words)
        or any(word in lower for word in text_search_words)
        or has_quoted_phrase
    )
    has_recent_filter = any(word in lower for word in recency_words) or bool(
        re.search(r"\b(last|past) \d+ (day|days|week|weeks|month|months|year|years|hour|hours)\b", lower)
    )
    has_aggregation_shape = any(word in lower for word in aggregation_words)

    prefer_esql = has_table_intent
    prefer_dsl = not prefer_esql and (has_retrieval_shape or has_recent_filter or has_aggregation_shape)

    if prefer_esql:
        return (
            "Router hint: prefer ES|QL only if the user clearly wants a table, comparison, correlation, selected columns, or pipeline-style output. "
            "If you need text search in ES|QL, use MATCH/MATCH_PHRASE/QSTR and ES|QL date math like NOW() - 30 day."
        )

    if prefer_dsl:
        return (
            "Router hint: prefer Query DSL for this request. Route document retrieval, topic/phrase search, recent-item listing, top-N analytics, and bounded aggregations to DSL unless the user explicitly asks for a table or pipeline. "
            "Use simple_query_string, multi_match, or structured DSL filters. Avoid ES|QL LIKE and avoid SQL INTERVAL syntax."
        )

    return ""

def _extract_semantic_concepts(text: str) -> list[str]:
    lower = (text or "").lower()
    concept_patterns = [
        ("cve", [r"\bcves?\b", r"\bvulnerabilit(?:y|ies)\b", r"\bkev\b"]),
        ("threat actor", [r"threat actor", r"\bactors?\b", r"\badversar(?:y|ies)\b", r"\bgroups?\b", r"campaigns?"]),
        ("malware", [r"\bmalware\b", r"ransomware", r"trojan", r"backdoor"]),
        ("vendor", [r"\bvendors?\b", r"supplier", r"publisher"]),
        ("product", [r"\bproducts?\b", r"software", r"application", r"platform"]),
        ("country", [r"\bcountries?\b", r"geography", r"locations?"]),
        ("sector", [r"\bsectors?\b", r"industr(?:y|ies)"]),
        ("technique", [r"\btechniques?\b", r"\bttps?\b", r"mitre"]),
        ("tactic", [r"\btactics?\b", r"kill chain", r"stage"]),
    ]
    found: list[str] = []
    for concept, patterns in concept_patterns:
        if any(re.search(pattern, lower) for pattern in patterns):
            found.append(concept)
    return found
