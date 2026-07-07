"""SQLite 持久化存储 — 诊断会话 + 审计日志。

取代进程内 dict 缓存，重启后诊断历史仍可回溯。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "raredx.db"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS diagnostic_sessions (
        session_id      TEXT PRIMARY KEY,
        user_message    TEXT NOT NULL,
        state_json      TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      TEXT NOT NULL,
        round_n         INTEGER,
        step            TEXT NOT NULL,
        data_json       TEXT,
        timestamp       TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES diagnostic_sessions(session_id)
    );

    CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_created ON diagnostic_sessions(created_at);
    """)
    conn.commit()


# ===== 诊断会话 =====

def save_session(session_id: str, user_message: str, state: dict) -> None:
    """保存或更新诊断会话状态。"""
    now = datetime.now().isoformat()
    state_json = json.dumps(_serialize(state), ensure_ascii=False, default=str)
    with _lock:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO diagnostic_sessions (session_id, user_message, state_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 user_message = excluded.user_message,
                 state_json   = excluded.state_json,
                 updated_at   = excluded.updated_at""",
            (session_id, user_message, state_json, now, now),
        )
        conn.commit()


def load_session(session_id: str) -> dict | None:
    """加载诊断会话完整状态。返回 dict 或 None。"""
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT state_json FROM diagnostic_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row["state_json"])


def list_sessions(limit: int = 20) -> list[dict]:
    """列出最近的诊断会话（元数据，不含完整 state）。"""
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT session_id, user_message, created_at, updated_at
               FROM diagnostic_sessions
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(session_id: str) -> bool:
    """删除会话 + 关联审计日志。返回是否删除。"""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "DELETE FROM diagnostic_sessions WHERE session_id = ?", (session_id,)
        )
        conn.execute("DELETE FROM audit_log WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0


# ===== 审计日志 =====

def log_audit(session_id: str, round_n: int, step: str, data: dict) -> None:
    """写入审计日志（取代文件式 audit/logger.py）。"""
    now = datetime.now().isoformat()
    data_json = json.dumps(_serialize(data), ensure_ascii=False, default=str)
    with _lock:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO audit_log (session_id, round_n, step, data_json, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, round_n, step, data_json, now),
        )
        conn.commit()


def get_audit(session_id: str) -> list[dict]:
    """获取某会话的全部审计日志（按时间序）。"""
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT session_id, round_n, step, data_json, timestamp
               FROM audit_log WHERE session_id = ? ORDER BY timestamp ASC""",
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        try:
            item["data"] = json.loads(item.pop("data_json"))
        except Exception:
            item["data"] = None
        out.append(item)
    return out


# ===== 工具 =====

def _serialize(obj: Any) -> Any:
    """把 Pydantic model / dataclass / enum 递归转成可 JSON 序列化结构。"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {k: _serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return obj


def close() -> None:
    """进程退出时调用。"""
    global _conn
    if _conn:
        _conn.close()
        _conn = None
