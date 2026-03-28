from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id, id);
CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC);
"""


@asynccontextmanager
async def open_db(db_path: str):
    db = await aiosqlite.connect(db_path)
    try:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA synchronous = NORMAL")
        yield db
    finally:
        await db.close()


async def init_db(db_path: str) -> None:
    async with open_db(db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


async def create_chat(db_path: str, chat_id: str, title: str = "New chat") -> dict[str, Any]:
    now = utc_now()
    async with open_db(db_path) as db:
        await db.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, title, now, now),
        )
        await db.commit()
    return {"id": chat_id, "title": title, "created_at": now, "updated_at": now}


async def list_chats(db_path: str) -> list[dict[str, Any]]:
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, title, created_at, updated_at FROM chats ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_chat(db_path: str, chat_id: str) -> dict[str, Any] | None:
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, title, created_at, updated_at FROM chats WHERE id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_chat_title(db_path: str, chat_id: str, title: str) -> None:
    now = utc_now()
    async with open_db(db_path) as db:
        await db.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, chat_id),
        )
        await db.commit()


async def add_message(
    db_path: str,
    chat_id: str,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    async with open_db(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO messages (chat_id, role, content, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, role, content, meta_json, now),
        )
        await db.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (now, chat_id),
        )
        await db.commit()
        message_id = cursor.lastrowid
    return {
        "id": message_id,
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "meta": meta or {},
        "created_at": now,
    }


async def get_messages(db_path: str, chat_id: str) -> list[dict[str, Any]]:
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, chat_id, role, content, meta_json, created_at
            FROM messages
            WHERE chat_id = ?
            ORDER BY id ASC
            """,
            (chat_id,),
        )
        rows = await cursor.fetchall()

    messages: list[dict[str, Any]] = []
    for row in rows:
        meta = {}
        if row["meta_json"]:
            try:
                meta = json.loads(row["meta_json"])
            except json.JSONDecodeError:
                meta = {}
        messages.append(
            {
                "id": row["id"],
                "chat_id": row["chat_id"],
                "role": row["role"],
                "content": row["content"],
                "meta": meta,
                "created_at": row["created_at"],
            }
        )
    return messages


async def delete_chat(db_path: str, chat_id: str) -> None:
    async with open_db(db_path) as db:
        await db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        await db.commit()
