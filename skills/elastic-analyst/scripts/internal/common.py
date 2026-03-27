from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any
from urllib.parse import quote

import httpx


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class ESSettings:
    url: str
    default_index: str
    default_time_field: str
    allowed_index_patterns: list[str]
    verify_certs: bool
    ca_certs: str
    api_key: str
    username: str
    password: str
    timeout_seconds: float = 30.0


def load_settings() -> ESSettings:
    return ESSettings(
        url=os.getenv("ES_URL", "http://localhost:9200").strip().rstrip("/"),
        default_index=os.getenv("ES_DEFAULT_INDEX", "news-*").strip(),
        default_time_field=os.getenv("ES_DEFAULT_TIME_FIELD", "Timestamp").strip() or "Timestamp",
        allowed_index_patterns=env_list("ES_ALLOWED_INDEX_PATTERNS", "news-*"),
        verify_certs=env_bool("ES_VERIFY_CERTS", False),
        ca_certs=os.getenv("ES_CA_CERTS", "").strip(),
        api_key=os.getenv("ES_API_KEY", "").strip(),
        username=os.getenv("ES_USERNAME", "").strip(),
        password=os.getenv("ES_PASSWORD", "").strip(),
        timeout_seconds=float(os.getenv("ES_TIMEOUT_SECONDS", "30")),
    )


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str))


def write_error(message: str, details: Any | None = None, exit_code: int = 1) -> None:
    payload = {"ok": False, "error": message}
    if details is not None:
        payload["details"] = details
    print(json.dumps(payload, ensure_ascii=False, default=str), file=sys.stderr)
    raise SystemExit(exit_code)


def is_allowed_index_pattern(index_pattern: str, allowed_patterns: list[str]) -> bool:
    requested = (index_pattern or "").strip()
    if not requested:
        return False
    if not allowed_patterns:
        return True
    return any(fnmatchcase(requested, allowed) for allowed in allowed_patterns)


def resolve_index_pattern(payload: dict[str, Any], settings: ESSettings) -> str:
    index_pattern = (
        payload.get("index_pattern")
        or payload.get("index")
        or settings.default_index
    )
    if not isinstance(index_pattern, str):
        write_error("index_pattern must be a string")
    index_pattern = index_pattern.strip()
    if not index_pattern:
        index_pattern = settings.default_index

    if not is_allowed_index_pattern(index_pattern, settings.allowed_index_patterns):
        write_error(
            f"Index pattern '{index_pattern}' is not allowed.",
            {"allowed_index_patterns": settings.allowed_index_patterns},
        )

    return index_pattern


def build_verify(settings: ESSettings) -> bool | str:
    if settings.ca_certs:
        return settings.ca_certs
    return settings.verify_certs


class ESHttp:
    def __init__(self, settings: ESSettings) -> None:
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.url,
            timeout=settings.timeout_seconds,
            verify=build_verify(settings),
            auth=(settings.username, settings.password) if settings.username and settings.password else None,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.settings.api_key:
            headers["Authorization"] = f"ApiKey {self.settings.api_key}"
        return headers

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                body = response.json()
            except Exception:
                body = response.text
            write_error(
                f"Elasticsearch request failed: {response.status_code}",
                {"path": path, "response": body},
            )
            raise exc
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)


def safe_index_path(index_pattern: str) -> str:
    return quote(index_pattern, safe="*,-_./")
