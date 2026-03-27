from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

JsonDict = dict[str, Any]
Emitter = Callable[[str, JsonDict], Awaitable[None]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: JsonDict
    skill_name: str
    script_rel_path: str


class ToolExecutionError(RuntimeError):
    pass


class ToolRegistry:
    def __init__(self, skills_root: Path, timeout_seconds: int = 45) -> None:
        self.skills_root = skills_root
        self.timeout_seconds = timeout_seconds
        self.tools: dict[str, ToolSpec] = {
            "list_indices": ToolSpec(
                name="list_indices",
                description="List Elasticsearch indices matching a pattern with health and document counts.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string", "description": "Index pattern like news-*"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/list_indices.py",
            ),
            "get_schema_catalog": ToolSpec(
                name="get_schema_catalog",
                description="Return a compact schema digest using field capabilities, flattened mappings, and sample documents.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "sample_size": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/get_schema_catalog.py",
            ),
            "get_field_caps": ToolSpec(
                name="get_field_caps",
                description="Get field capabilities such as searchable and aggregatable flags.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "fields": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                            ]
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/get_field_caps.py",
            ),
            "get_mappings": ToolSpec(
                name="get_mappings",
                description="Get flattened mappings for an index pattern.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "field_filter": {"type": "string", "description": "Optional substring filter for field names"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/get_mappings.py",
            ),
            "get_sample_docs": ToolSpec(
                name="get_sample_docs",
                description="Fetch a few representative documents from an index pattern.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "size": {"type": "integer", "minimum": 1, "maximum": 5},
                        "fields": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/get_sample_docs.py",
            ),
            "get_index_stats": ToolSpec(
                name="get_index_stats",
                description="Get basic doc counts and time-range statistics for an index pattern.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "time_field": {"type": "string"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/get_index_stats.py",
            ),
            "resolve_semantic_fields": ToolSpec(
                name="resolve_semantic_fields",
                description="Resolve verified candidate fields for business concepts like CVEs, threat actors, malware, vendors, products, countries, or techniques.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "concept": {"type": "string", "description": "Business concept such as cve, threat actor, malware, vendor, product, country, sector, technique."},
                        "max_candidates": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["concept"],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/resolve_semantic_fields.py",
            ),
            "get_top_values": ToolSpec(
                name="get_top_values",
                description="Get top values for a field using a terms aggregation.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "field": {"type": "string"},
                        "size": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "required": ["field"],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/get_top_values.py",
            ),
            "validate_dsl_query": ToolSpec(
                name="validate_dsl_query",
                description="Validate an Elasticsearch Query DSL body without executing the search.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "query_body": {"type": "object"},
                    },
                    "required": ["query_body"],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/validate_dsl_query.py",
            ),
            "run_dsl_query": ToolSpec(
                name="run_dsl_query",
                description="Execute a read-only Elasticsearch Query DSL search.",
                parameters={
                    "type": "object",
                    "properties": {
                        "index_pattern": {"type": "string"},
                        "query_body": {"type": "object"},
                    },
                    "required": ["query_body"],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/run_dsl_query.py",
            ),
            "run_esql_query": ToolSpec(
                name="run_esql_query",
                description="Execute a read-only ES|QL query against Elasticsearch.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                skill_name="elastic-analyst",
                script_rel_path="scripts/tools/run_esql_query.py",
            ),
        }

    def openai_tool_definitions(self) -> list[JsonDict]:
        return [
            {
                "type": "function",
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
            for spec in self.tools.values()
        ]

    def get_script_path(self, tool_name: str) -> Path:
        spec = self.tools[tool_name]
        return self.skills_root / spec.skill_name / spec.script_rel_path

    def load_skill_markdown(self) -> list[str]:
        skill_docs: list[str] = []
        for skill_dir in sorted(self.skills_root.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                skill_docs.append(skill_md.read_text(encoding="utf-8"))
        return skill_docs

    async def execute(self, tool_name: str, arguments: JsonDict, emit: Emitter) -> JsonDict:
        if tool_name not in self.tools:
            raise ToolExecutionError(f"Unknown tool: {tool_name}")

        spec = self.tools[tool_name]
        script_path = self.get_script_path(tool_name)
        if not script_path.exists():
            raise ToolExecutionError(f"Script not found for tool {tool_name}: {script_path}")

        await emit(
            "tool_start",
            {
                "tool_name": tool_name,
                "skill_name": spec.skill_name,
                "script_path": str(script_path.relative_to(self.skills_root.parent)),
                "arguments": arguments,
            },
        )

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(script_path.parent),
        )

        payload = json.dumps(arguments, ensure_ascii=False).encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(payload), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise ToolExecutionError(f"Tool {tool_name} timed out after {self.timeout_seconds}s") from exc

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            await emit(
                "tool_error",
                {
                    "tool_name": tool_name,
                    "skill_name": spec.skill_name,
                    "script_path": str(script_path.relative_to(self.skills_root.parent)),
                    "stderr": stderr_text,
                    "stdout": stdout_text,
                },
            )
            raise ToolExecutionError(
                f"Tool {tool_name} failed with exit code {process.returncode}: {stderr_text or stdout_text}"
            )

        if stdout_text:
            try:
                parsed = json.loads(stdout_text)
            except json.JSONDecodeError as exc:
                raise ToolExecutionError(
                    f"Tool {tool_name} returned invalid JSON: {stdout_text[:400]}"
                ) from exc
        else:
            parsed = {"ok": True, "message": "Tool returned no payload."}

        await emit(
            "tool_result",
            {
                "tool_name": tool_name,
                "skill_name": spec.skill_name,
                "script_path": str(script_path.relative_to(self.skills_root.parent)),
                "summary": parsed.get("summary") or parsed.get("message") or "Tool completed.",
                "result_preview": _preview_json(parsed),
            },
        )
        return parsed


def _preview_json(payload: JsonDict, max_len: int = 1000) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, default=str)
    if len(rendered) <= max_len:
        return rendered
    return rendered[: max_len - 1] + "…"
