from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class CacheStore:
    """简单的 key-value TTL 缓存（SQLite）。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def get(self, key: str, ttl_hours: float) -> Any | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, updated_at FROM kv_cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        value, updated_at = row
        if ttl_hours > 0 and (time.time() - updated_at) > ttl_hours * 3600:
            return None
        return json.loads(value)

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kv_cache(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, payload, time.time()),
            )

    def clear(self, prefix: str | None = None) -> int:
        with self._connect() as conn:
            if prefix:
                cur = conn.execute(
                    "DELETE FROM kv_cache WHERE key LIKE ?", (f"{prefix}%",)
                )
            else:
                cur = conn.execute("DELETE FROM kv_cache")
            return cur.rowcount
