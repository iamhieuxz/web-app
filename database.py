"""Module quản lý SQLite database cho danh sách tài khoản IG/X và settings.

Tính năng chính:
- Tự động migration schema (thêm cột `platform` nếu thiếu)
- WAL mode + autocommit cho PRAGMA/ALTER an toàn
- check_same_thread=False để chia sẻ connection giữa các thread
- Logging lỗi thay vì print + nuốt hoàn toàn
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from typing import Any

logger = logging.getLogger("database")

# ==========================================
# CẤU HÌNH ĐƯỜNG DẪN
# ==========================================
# Thứ tự ưu tiên:
# 1. Env var GALLERY_DL_HOME
# 2. E:\gallery-dl (mặc định — chứa data IG/X)
# 3. Fallback vào thư mục home
def _resolve_default_base() -> str:
    env_override = os.environ.get("GALLERY_DL_HOME")
    if env_override:
        return os.path.normpath(env_override)
    # Railway: dùng /data nếu tồn tại
    if os.path.exists("/data"):
        return "/data/gallery-dl"
    return os.path.join(os.path.expanduser("~"), "gallery-dl")


BASE_DIR = _resolve_default_base()
os.makedirs(BASE_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "ig_accounts.db")


def get_connection() -> sqlite3.Connection:
    """Tạo kết nối SQLite an toàn, dùng được từ nhiều thread.

    - timeout=30s chống khóa DB khi concurrent write
    - check_same_thread=False cho phép dùng connection từ thread khác
    - row_factory=Row để trả về dict-like
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Khởi tạo và nâng cấp cấu trúc Database ở chế độ autocommit an toàn."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.isolation_level = None  # Autocommit để thực thi PRAGMA và ALTER TABLE
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY,
                platform TEXT DEFAULT 'instagram',
                is_active INTEGER DEFAULT 1,
                last_synced TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Migration: thêm cột platform nếu bảng cũ chưa có
        cursor = conn.execute("PRAGMA table_info(accounts)")
        columns = [col[1] for col in cursor.fetchall()]
        if "platform" not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN platform TEXT DEFAULT 'instagram'")
            logger.info("Migration: thêm cột 'platform' vào bảng accounts")
    except Exception as e:
        logger.exception("Lỗi khởi tạo DB: %s", e)
    finally:
        conn.close()


# ==========================================
# SETTINGS
# ==========================================
def get_setting(key: str, default: str = "") -> str:
    try:
        with get_connection() as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default
    except Exception:
        logger.exception("Lỗi get_setting('%s')", key)
        return default


def set_setting(key: str, value: str) -> None:
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
    except Exception:
        logger.exception("Lỗi set_setting('%s')", key)
        raise


# ==========================================
# ACCOUNTS CRUD
# ==========================================
def get_all_accounts() -> list[dict[str, Any]]:
    """Lấy danh sách tài khoản an toàn, tự điền platform nếu thiếu."""
    try:
        with get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(accounts)")
            columns = [col[1] for col in cursor.fetchall()]

            if "platform" in columns:
                cursor = conn.execute("SELECT * FROM accounts ORDER BY platform, username")
            else:
                cursor = conn.execute("SELECT * FROM accounts ORDER BY username")

            rows = cursor.fetchall()
            result: list[dict[str, Any]] = []
            for r in rows:
                item = dict(r)
                if not item.get("platform"):
                    item["platform"] = "instagram"
                result.append(item)
            return result
    except Exception:
        logger.exception("Lỗi get_all_accounts")
        return []


def get_active_accounts(platform: str = "instagram") -> list[str]:
    try:
        with get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(accounts)")
            columns = [col[1] for col in cursor.fetchall()]
            if "platform" in columns:
                cursor = conn.execute(
                    "SELECT username FROM accounts WHERE is_active = 1 AND platform = ?",
                    (platform,),
                )
            else:
                cursor = conn.execute("SELECT username FROM accounts WHERE is_active = 1")
            return [row[0] for row in cursor.fetchall()]
    except Exception:
        logger.exception("Lỗi get_active_accounts('%s')", platform)
        return []


def add_account(username: str, platform: str = "instagram") -> bool:
    if not username:
        logger.warning("add_account bị gọi với username rỗng")
        return False
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO accounts (username, platform, is_active) VALUES (?, ?, 1)",
                (username, platform),
            )
            conn.commit()
        return True
    except Exception:
        logger.exception("Lỗi add_account('%s', '%s')", username, platform)
        return False


def toggle_account_status(username: str, is_active: int) -> None:
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE accounts SET is_active = ? WHERE username = ?",
                (is_active, username),
            )
            conn.commit()
    except Exception:
        logger.exception("Lỗi toggle_account_status('%s', %s)", username, is_active)
        raise


def update_last_synced(username: str) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE accounts SET last_synced = ? WHERE username = ?",
                (now_str, username),
            )
            conn.commit()
    except Exception:
        logger.exception("Lỗi update_last_synced('%s')", username)


def rename_account(old_username: str, new_username: str) -> None:
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE accounts SET username = ? WHERE username = ?",
                (new_username, old_username),
            )
            conn.commit()
    except Exception:
        logger.exception("Lỗi rename_account('%s' -> '%s')", old_username, new_username)
        raise


def delete_account(username: str) -> None:
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM accounts WHERE username = ?", (username,))
            conn.commit()
    except Exception:
        logger.exception("Lỗi delete_account('%s')", username)
        raise
