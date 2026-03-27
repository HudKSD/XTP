from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_list(name: str, default: str = "") -> List[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_secret(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


@dataclass(slots=True)
class Settings:
    app_name: str
    app_port: int
    app_debug: bool
    data_dir: Path
    db_path: Path
    traces_dir: Path
    skills_root: Path
    trace_enabled: bool

    openai_api_key: str
    openai_model: str
    openai_reasoning_effort: str
    openai_max_output_tokens: int

    es_url: str
    es_default_index: str
    es_default_time_field: str
    es_allowed_index_patterns: list[str]
    es_verify_certs: bool
    es_ca_certs: str

    tool_timeout_seconds: int
    tool_loop_max_rounds: int
    tool_repeat_limit: int
    transcript_message_limit: int
    max_message_chars: int


def load_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "/app/data")).resolve()
    traces_dir = data_dir / "traces"
    skills_root = Path(os.getenv("SKILLS_ROOT", "/app/skills")).resolve()

    data_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)

    return Settings(
        app_name=os.getenv("APP_NAME", "LidarKinesis IntelChat"),
        app_port=_env_int("APP_PORT", 8000),
        app_debug=_env_bool("APP_DEBUG", False),
        data_dir=data_dir,
        db_path=data_dir / "chats.db",
        traces_dir=traces_dir,
        skills_root=skills_root,
        trace_enabled=_env_bool("TRACE_ENABLED", True),
        openai_api_key=_env_secret("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip(),
        openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "low").strip(),
        openai_max_output_tokens=_env_int("OPENAI_MAX_OUTPUT_TOKENS", 1400),
        es_url=os.getenv("ES_URL", "http://localhost:9200").strip().rstrip("/"),
        es_default_index=os.getenv("ES_DEFAULT_INDEX", "news-*").strip(),
        es_default_time_field=os.getenv("ES_DEFAULT_TIME_FIELD", "Timestamp").strip() or "Timestamp",
        es_allowed_index_patterns=_env_list("ES_ALLOWED_INDEX_PATTERNS", "news-*"),
        es_verify_certs=_env_bool("ES_VERIFY_CERTS", False),
        es_ca_certs=os.getenv("ES_CA_CERTS", "").strip(),
        tool_timeout_seconds=_env_int("TOOL_TIMEOUT_SECONDS", 45),
        tool_loop_max_rounds=_env_int("TOOL_LOOP_MAX_ROUNDS", 10),
        tool_repeat_limit=_env_int("TOOL_REPEAT_LIMIT", 2),
        transcript_message_limit=_env_int("TRANSCRIPT_MESSAGE_LIMIT", 24),
        max_message_chars=_env_int("MAX_MESSAGE_CHARS", 12000),
    )
