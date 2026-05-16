"""SQLite schema + helpers (single connection per request, async)."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

DB_PATH = Path(__file__).parent.parent / "data" / "pcb.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  agent_provider TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  user_message TEXT NOT NULL,
  exit_code INTEGER,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  run_id INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_project_seq
  ON messages(project_id, seq);

CREATE INDEX IF NOT EXISTS idx_runs_project
  ON runs(project_id, started_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        # SQLite lacks IF NOT EXISTS on ADD COLUMN; legacy DBs created before
        # agent_provider was added need a one-shot migration. Detect via the
        # column list and ignore any "duplicate column" race.
        cur = await db.execute("PRAGMA table_info(projects)")
        cols = {row[1] for row in await cur.fetchall()}
        if "agent_provider" not in cols:
            try:
                await db.execute("ALTER TABLE projects ADD COLUMN agent_provider TEXT")
            except aiosqlite.OperationalError:
                pass
        await db.commit()


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


async def insert_project(
    project_id: str, name: str, agent_provider: str | None = None
) -> dict[str, Any]:
    now = _now()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at, agent_provider) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, name, now, now, agent_provider),
        )
        await db.commit()
    return {
        "id": project_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "agent_provider": agent_provider,
    }


async def list_projects() -> list[dict[str, Any]]:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT id, name, created_at, updated_at, agent_provider "
            "FROM projects ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


async def get_project(project_id: str) -> dict[str, Any] | None:
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT id, name, created_at, updated_at, agent_provider "
                "FROM projects WHERE id = ?",
                (project_id,),
            )
        ).fetchone()
    return dict(row) if row else None


async def delete_project(project_id: str) -> bool:
    async with get_db() as db:
        cur = await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()
        return cur.rowcount > 0


async def create_run(project_id: str, user_message: str) -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO runs (project_id, started_at, user_message) VALUES (?, ?, ?)",
            (project_id, _now(), user_message),
        )
        await db.commit()
        return cur.lastrowid


async def finish_run(run_id: int, exit_code: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE runs SET ended_at = ?, exit_code = ? WHERE id = ?",
            (_now(), exit_code, run_id),
        )
        await db.commit()


async def list_runs(project_id: str) -> list[dict[str, Any]]:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT id, started_at, ended_at, user_message, exit_code "
            "FROM runs WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        )
    return [dict(r) for r in rows]


async def insert_message(
    project_id: str, run_id: int, seq: int, payload: dict[str, Any]
) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO messages (project_id, run_id, seq, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, run_id, seq, json.dumps(payload, ensure_ascii=False), _now()),
        )
        await db.commit()


async def get_max_seq(project_id: str) -> int:
    """Largest seq stored for this project, or 0 if no messages yet.

    Used by the runner so each new run continues the seq counter from where
    the previous run left off, rather than restarting at 1 (which would make
    cross-run ordering broken when sorted by seq).
    """
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM messages WHERE project_id = ?",
                (project_id,),
            )
        ).fetchone()
    return int(row["m"]) if row else 0


async def list_messages(
    project_id: str, since_seq: int = 0
) -> list[dict[str, Any]]:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT seq, payload, created_at FROM messages "
            "WHERE project_id = ? AND seq > ? ORDER BY seq ASC",
            (project_id, since_seq),
        )
    return [
        {"seq": r["seq"], "payload": json.loads(r["payload"]), "created_at": r["created_at"]}
        for r in rows
    ]
