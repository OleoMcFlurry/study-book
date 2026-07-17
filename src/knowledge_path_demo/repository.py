"""SQLite 会话仓储。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class SessionRecord:
    id: str
    goal: str
    background: str
    known_keywords: list[str]
    status: str
    graph_json: dict[str, Any] | None
    mastery_json: dict[str, str]
    path_json: list[dict[str, Any]] | None
    created_at: str
    updated_at: str


class SessionRepository:
    """基于 SQLite 的会话持久化。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    background TEXT NOT NULL,
                    known_keywords TEXT NOT NULL,
                    status TEXT NOT NULL,
                    graph_json TEXT,
                    mastery_json TEXT NOT NULL,
                    path_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create(
        self,
        goal: str,
        background: str,
        known_keywords: list[str] | None = None,
    ) -> SessionRecord:
        sid = str(uuid.uuid4())
        now = _utc_now()
        kw = known_keywords or []
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, goal, background, known_keywords, status,
                    graph_json, mastery_json, path_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?)
                """,
                (
                    sid,
                    goal,
                    background,
                    json.dumps(kw, ensure_ascii=False),
                    "created",
                    json.dumps({}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get(sid)  # type: ignore[return-value]

    def get(self, session_id: str) -> SessionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def save_graph(self, session_id: str, graph: dict[str, Any]) -> SessionRecord:
        # 重新生成图时清空旧路径
        return self._update(
            session_id,
            graph_json=json.dumps(graph, ensure_ascii=False),
            status="graph_ready",
            path_json=json.dumps(None),
        )

    def save_mastery(self, session_id: str, mastery: dict[str, str]) -> SessionRecord:
        return self._update(
            session_id,
            mastery_json=json.dumps(mastery, ensure_ascii=False),
        )

    def save_path(self, session_id: str, path: list[dict[str, Any]]) -> SessionRecord:
        return self._update(
            session_id,
            path_json=json.dumps(path, ensure_ascii=False),
            status="path_ready",
        )

    def _update(self, session_id: str, **fields: Any) -> SessionRecord:
        if not fields:
            rec = self.get(session_id)
            if rec is None:
                raise KeyError(session_id)
            return rec
        now = _utc_now()
        cols = list(fields.keys()) + ["updated_at"]
        values = list(fields.values()) + [now, session_id]
        assignments = ", ".join(f"{c} = ?" for c in cols)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE sessions SET {assignments} WHERE id = ?",
                values,
            )
            if cur.rowcount == 0:
                raise KeyError(session_id)
            conn.commit()
        return self.get(session_id)  # type: ignore[return-value]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SessionRecord:
        graph_raw = row["graph_json"]
        path_raw = row["path_json"]
        return SessionRecord(
            id=row["id"],
            goal=row["goal"],
            background=row["background"],
            known_keywords=json.loads(row["known_keywords"]),
            status=row["status"],
            graph_json=json.loads(graph_raw) if graph_raw else None,
            mastery_json=json.loads(row["mastery_json"]),
            path_json=json.loads(path_raw) if path_raw else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
