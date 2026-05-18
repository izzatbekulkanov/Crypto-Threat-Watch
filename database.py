"""Foydalanuvchilar va so'rovlar ma'lumotlar bazasi (SQLite) — Professional."""

import sqlite3
import time
from pathlib import Path
from typing import Optional

_DB_PATH: Path = Path(__file__).resolve().parent / "bot_data.db"


def _get_connection() -> sqlite3.Connection:
    """Ma'lumotlar bazasiga ulanish."""
    conn: sqlite3.Connection = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Jadvallarni yaratish."""
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            alias TEXT NOT NULL,
            language TEXT DEFAULT 'uz',
            is_admin INTEGER DEFAULT 0,
            query_count INTEGER DEFAULT 0,
            last_query_at REAL DEFAULT 0,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            network TEXT NOT NULL,
            address TEXT NOT NULL,
            result_summary TEXT,
            risk_level TEXT DEFAULT 'low',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_logs(created_at)
    """)

    conn.commit()
    conn.close()


def register_user(user_id: int, username: Optional[str], alias: str, language: str = "uz") -> None:
    """Yangi foydalanuvchini ro'yxatdan o'tkazish."""
    conn = _get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO users (user_id, username, alias, language) VALUES (?, ?, ?, ?)",
        (user_id, username, alias, language),
    )
    conn.commit()
    conn.close()


def get_user(user_id: int) -> Optional[dict]:
    """Foydalanuvchi ma'lumotlarini olish."""
    conn = _get_connection()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_language(user_id: int, language: str) -> None:
    """Foydalanuvchi tilini o'zgartirish."""
    conn = _get_connection()
    conn.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
    conn.commit()
    conn.close()


def increment_query_count(user_id: int) -> None:
    """So'rovlar sonini oshirish va vaqtni yangilash."""
    conn = _get_connection()
    conn.execute(
        "UPDATE users SET query_count = query_count + 1, last_query_at = ? WHERE user_id = ?",
        (time.time(), user_id),
    )
    conn.commit()
    conn.close()


def check_rate_limit(user_id: int, limit_per_minute: int) -> bool:
    """Rate limit tekshiruvi. True = ruxsat, False = limit oshgan."""
    conn = _get_connection()
    row = conn.execute("SELECT last_query_at, query_count FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return True
    last_time: float = row["last_query_at"] or 0
    elapsed: float = time.time() - last_time
    return elapsed > (60.0 / limit_per_minute)


def set_admin(user_id: int) -> None:
    """Foydalanuvchini admin qilish."""
    conn = _get_connection()
    conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def toggle_admin(user_id: int) -> bool:
    """Admin holatini o'zgartirish (yoqish/o'chirish)."""
    conn = _get_connection()
    row = conn.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        new_status = 0 if row["is_admin"] else 1
        conn.execute("UPDATE users SET is_admin = ? WHERE user_id = ?", (new_status, user_id))
        conn.commit()
        conn.close()
        return bool(new_status)
    conn.close()
    return False

def update_alias(user_id: int, new_alias: str) -> bool:
    """Foydalanuvchi taxallusini o'zgartirish."""
    conn = _get_connection()
    conn.execute("UPDATE users SET alias = ? WHERE user_id = ?", (new_alias, user_id))
    rows_affected = conn.total_changes
    conn.commit()
    conn.close()
    return rows_affected > 0


def is_admin(user_id: int) -> bool:
    """Admin ekanligini tekshirish."""
    user = get_user(user_id)
    return bool(user["is_admin"]) if user else False


def get_all_users() -> list[dict]:
    """Barcha foydalanuvchilar."""
    conn = _get_connection()
    rows = conn.execute("SELECT * FROM users ORDER BY query_count DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Umumiy statistika."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as total_users, COALESCE(SUM(query_count),0) as total_queries FROM users"
    ).fetchone()
    audit_row = conn.execute("SELECT COUNT(*) as total_audits FROM audit_logs").fetchone()
    conn.close()
    return {
        "total_users": row["total_users"],
        "total_queries": row["total_queries"],
        "total_audits": audit_row["total_audits"],
    }


def log_audit(user_id: int, network: str, address: str, summary: str, risk_level: str) -> None:
    """Audit logini saqlash."""
    conn = _get_connection()
    conn.execute(
        "INSERT INTO audit_logs (user_id, network, address, result_summary, risk_level) VALUES (?, ?, ?, ?, ?)",
        (user_id, network, address, summary, risk_level),
    )
    conn.commit()
    conn.close()


def get_recent_audits(limit: int = 20) -> list[dict]:
    """Oxirgi auditlar."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT a.*, u.alias FROM audit_logs a JOIN users u ON a.user_id = u.user_id ORDER BY a.created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_audits(user_id: int, limit: int = 10) -> list[dict]:
    """Foydalanuvchining oxirgi auditleri."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT * FROM audit_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
