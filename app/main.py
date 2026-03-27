from __future__ import annotations

import json
import uuid
from typing import Any

from dotenv import load_dotenv
from quart import Quart, jsonify, render_template, request, websocket

from app.agent.prompts import build_chat_title
from app.agent.runner import ElasticAgent
from app.agent.tool_registry import ToolRegistry
from app.agent.tracing import TraceLogger
from app.config import load_settings
from app.db import add_message, create_chat, delete_chat, get_chat, get_messages, init_db, list_chats, update_chat_title

load_dotenv()

settings = load_settings()
trace_logger = TraceLogger(settings.traces_dir, enabled=settings.trace_enabled)
tool_registry = ToolRegistry(settings.skills_root, timeout_seconds=settings.tool_timeout_seconds)
agent = ElasticAgent(settings, tool_registry, trace_logger)

app = Quart(__name__, template_folder="templates", static_folder="static")


def _safe_error_message(exc: Exception) -> str:
    raw = str(exc or "").strip()
    lowered = raw.lower()
    if "invalid_api_key" in lowered or "incorrect api key provided" in lowered:
        return (
            "OpenAI API authentication failed. "
            "Set a valid OPENAI_API_KEY in your environment and restart the app."
        )
    if "openai_api_key is not configured" in lowered:
        return (
            "OPENAI_API_KEY is not configured. "
            "Add it to your environment (or .env) and restart the app."
        )
    if not raw:
        return "Unexpected error while processing the request."
    return raw


@app.before_serving
async def startup() -> None:
    await init_db(str(settings.db_path))


@app.get("/")
async def index():
    return await render_template("index.html", app_name=settings.app_name)


@app.get("/api/health")
async def health():
    return jsonify(
        {
            "ok": True,
            "app_name": settings.app_name,
            "default_index": settings.es_default_index,
        }
    )


@app.get("/api/chats")
async def api_list_chats():
    chats = await list_chats(str(settings.db_path))
    return jsonify({"items": chats})


@app.post("/api/chats")
async def api_create_chat():
    payload = await request.get_json(force=False, silent=True) or {}
    title = (payload.get("title") or "New chat").strip()[:180] or "New chat"
    chat_id = uuid.uuid4().hex
    chat = await create_chat(str(settings.db_path), chat_id, title=title)
    return jsonify(chat), 201


@app.patch("/api/chats/<chat_id>")
async def api_patch_chat(chat_id: str):
    chat = await get_chat(str(settings.db_path), chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    payload = await request.get_json(force=False, silent=True) or {}
    title = (payload.get("title") or "").strip()[:180]
    if not title:
        return jsonify({"error": "title is required"}), 400

    await update_chat_title(str(settings.db_path), chat_id, title)
    updated = await get_chat(str(settings.db_path), chat_id)
    return jsonify(updated)


@app.delete("/api/chats/<chat_id>")
async def api_delete_chat(chat_id: str):
    chat = await get_chat(str(settings.db_path), chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    await delete_chat(str(settings.db_path), chat_id)
    return jsonify({"ok": True, "deleted_chat_id": chat_id})


@app.get("/api/chats/<chat_id>/messages")
async def api_get_messages(chat_id: str):
    chat = await get_chat(str(settings.db_path), chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    messages = await get_messages(str(settings.db_path), chat_id)
    return jsonify({"chat": chat, "items": messages})


@app.websocket("/ws/chat/<chat_id>")
async def ws_chat(chat_id: str):
    chat = await get_chat(str(settings.db_path), chat_id)
    if not chat:
        await websocket.send(json.dumps({"type": "error", "message": "Chat not found"}))
        return

    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, **payload}
        trace_logger.write(chat_id, {"type": event_type, **payload})
        await websocket.send(json.dumps(event, ensure_ascii=False, default=str))

    while True:
        raw = await websocket.receive()
        try:
            incoming = json.loads(raw)
        except json.JSONDecodeError:
            await emit("error", {"message": "Invalid JSON payload"})
            continue

        if incoming.get("type") == "ping":
            await emit("pong", {"message": "pong"})
            continue

        if incoming.get("type") != "user_message":
            await emit("error", {"message": "Unsupported message type"})
            continue

        content = (incoming.get("content") or "").strip()
        if not content:
            await emit("error", {"message": "Message cannot be empty"})
            continue
        if len(content) > settings.max_message_chars:
            await emit(
                "error",
                {
                    "message": f"Message exceeds {settings.max_message_chars} characters. Please shorten it.",
                },
            )
            continue

        chat_state = await get_chat(str(settings.db_path), chat_id)
        if chat_state and chat_state["title"] == "New chat":
            new_title = build_chat_title(content)
            await update_chat_title(str(settings.db_path), chat_id, new_title)
            await emit("chat_title", {"chat_id": chat_id, "title": new_title})

        saved_user = await add_message(str(settings.db_path), chat_id, "user", content)
        await emit("message_saved", saved_user)
        await emit("status", {"message": "Queued message.", "phase": "queued"})

        history = await get_messages(str(settings.db_path), chat_id)

        try:
            assistant_text, meta = await agent.run_turn(
                chat_id=chat_id,
                history=history,
                latest_user_message=content,
                emit=emit,
            )
        except Exception as exc:  # noqa: BLE001
            await emit("error", {"message": _safe_error_message(exc)})
            continue

        saved_assistant = await add_message(
            str(settings.db_path),
            chat_id,
            "assistant",
            assistant_text,
            meta=meta,
        )
        await emit(
            "assistant_final",
            {
                "content": assistant_text,
                "message_id": saved_assistant["id"],
                "meta": meta,
            },
        )


if __name__ == "__main__":
    app.run(port=settings.app_port, debug=settings.app_debug)
