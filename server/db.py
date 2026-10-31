"""طبقة الاتصال بقاعدة البيانات SQLite.

• اتصال لكل خيط (thread-local) مع تفعيل المفاتيح الخارجية ووضع WAL.
• كل عمليات الكتابة تمر عبر write() التي تبدأ معاملة BEGIN IMMEDIATE
  وتُسلسل الكتابات بقفل واحد، فإما أن يُحفظ المستند كاملاً أو لا يُحفظ شيء.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA_VERSION = 1
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

DEFAULT_SETTINGS = {
    "system_name": "جاديت — نظام حسابات العملاء",
    "working_karat": "18",
    "wage_unit": "ريال",
    "diamond_unit": "قيراط",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Database:
    def __init__(self, path: str):
        self.path = path
        self._local = threading.local()
        self._write_lock = threading.RLock()
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------ الاتصال
    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._open()
            self._local.conn = c
        return c

    def close_all(self):
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    def reset_connections(self):
        """يُستدعى بعد الاستعادة من نسخة احتياطية حتى تُفتح اتصالات جديدة."""
        self._local = threading.local()

    @contextmanager
    def read(self):
        yield self.conn()

    @contextmanager
    def write(self):
        """معاملة كتابة ذرية: كل شيء أو لا شيء."""
        with self._write_lock:
            c = self.conn()
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
            except BaseException:
                c.execute("ROLLBACK")
                raise
            else:
                c.execute("COMMIT")

    # ------------------------------------------------------------ المخطط
    def _init_schema(self):
        c = self._open()
        try:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                with open(SCHEMA_PATH, encoding="utf-8") as f:
                    c.executescript(f.read())
                now = utcnow()
                for k, v in DEFAULT_SETTINGS.items():
                    c.execute(
                        "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                        (k, v, now),
                    )
                c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version > SCHEMA_VERSION:
                raise RuntimeError("قاعدة البيانات من إصدار أحدث من البرنامج")
        finally:
            c.close()


def next_seq(c: sqlite3.Connection, name: str, start: int = 1) -> int:
    """عداد فريد داخل نفس المعاملة (آمن لأن الكتابة مسلسلة بـ BEGIN IMMEDIATE)."""
    row = c.execute("SELECT last_value FROM sequences WHERE name = ?", (name,)).fetchone()
    if row is None:
        value = start
        c.execute("INSERT INTO sequences(name, last_value) VALUES (?, ?)", (name, value))
    else:
        value = row[0] + 1
        c.execute("UPDATE sequences SET last_value = ? WHERE name = ?", (value, name))
    return value


def peek_seq(c: sqlite3.Connection, name: str, start: int = 1) -> int:
    row = c.execute("SELECT last_value FROM sequences WHERE name = ?", (name,)).fetchone()
    return start if row is None else row[0] + 1
