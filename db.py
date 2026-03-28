from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from config import (
    ADMIN_ID,
    DB_PATH,
    DEFAULT_FREE_IMAGE_LIMIT,
    DEFAULT_FREE_LIMIT,
    DEFAULT_HELP_TEXT,
    DEFAULT_MAINTENANCE_TEXT,
    DEFAULT_NEWS_CHANNEL_URL,
    DEFAULT_PAYWALL_TEXT,
    DEFAULT_REQUIRED_SUBSCRIPTION_TEXT,
    DEFAULT_RUB_PRICE_3,
    DEFAULT_RUB_PRICE_7,
    DEFAULT_RUB_PRICE_30,
    DEFAULT_STARS_PRICE_3,
    DEFAULT_STARS_PRICE_7,
    DEFAULT_STARS_PRICE_30,
    DEFAULT_SUPPORT_TEXT,
)


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init_db()
        self.ensure_admin_exists(ADMIN_ID)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _column_exists(self, conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        try:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        except sqlite3.OperationalError:
            return False
        return any(r[1] == column_name for r in rows)

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, definition_sql: str) -> None:
        if not self._column_exists(conn, table_name, column_name):
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition_sql}")

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    requests_left INTEGER DEFAULT 0,
                    is_premium INTEGER DEFAULT 0,
                    sub_until TEXT,
                    is_vip INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    total_requests INTEGER DEFAULT 0
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    external_id TEXT,
                    days INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    free_limit INTEGER NOT NULL,
                    stars_price_3 INTEGER NOT NULL,
                    stars_price_7 INTEGER NOT NULL,
                    stars_price_30 INTEGER NOT NULL,
                    rub_price_3 INTEGER NOT NULL,
                    rub_price_7 INTEGER NOT NULL,
                    rub_price_30 INTEGER NOT NULL,
                    help_text TEXT NOT NULL,
                    paywall_text TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    provider TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    invited_user_id INTEGER NOT NULL UNIQUE,
                    bonus_requests INTEGER NOT NULL DEFAULT 5,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            self._ensure_column(conn, "users", "is_banned", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "users", "ban_reason", "TEXT")
            self._ensure_column(conn, "users", "referred_by", "INTEGER")
            self._ensure_column(conn, "users", "bonus_requests_total", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "users", "images_left", f"INTEGER DEFAULT {DEFAULT_FREE_IMAGE_LIMIT}")
            self._ensure_column(conn, "users", "support_blocked", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "users", "last_activity_at", "TEXT")

            support_text_esc = DEFAULT_SUPPORT_TEXT.replace("'", "''")
            maintenance_text_esc = DEFAULT_MAINTENANCE_TEXT.replace("'", "''")
            required_sub_text_esc = DEFAULT_REQUIRED_SUBSCRIPTION_TEXT.replace("'", "''")

            self._ensure_column(conn, "settings", "free_image_limit", f"INTEGER NOT NULL DEFAULT {DEFAULT_FREE_IMAGE_LIMIT}")
            self._ensure_column(conn, "settings", "news_channel_url", f"TEXT NOT NULL DEFAULT '{DEFAULT_NEWS_CHANNEL_URL}'")
            self._ensure_column(conn, "settings", "support_text", f"TEXT NOT NULL DEFAULT '{support_text_esc}'")
            self._ensure_column(conn, "settings", "maintenance_mode", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "settings", "maintenance_text", f"TEXT NOT NULL DEFAULT '{maintenance_text_esc}'")
            self._ensure_column(conn, "settings", "required_channel_id", "TEXT")
            self._ensure_column(conn, "settings", "required_channel_username", "TEXT")
            self._ensure_column(conn, "settings", "required_subscription_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "settings", "required_subscription_text", f"TEXT NOT NULL DEFAULT '{required_sub_text_esc}'")
            self._ensure_column(conn, "settings", "ai_provider", "TEXT NOT NULL DEFAULT 'gemini'")
            self._ensure_column(conn, "settings", "ai_fallback_1", "TEXT NOT NULL DEFAULT 'groq'")
            self._ensure_column(conn, "settings", "ai_fallback_2", "TEXT NOT NULL DEFAULT 'openrouter'")
            self._ensure_column(conn, "settings", "ai_model", "TEXT")
            self._ensure_column(conn, "settings", "image_provider", "TEXT NOT NULL DEFAULT 'deepai'")
            self._ensure_column(conn, "settings", "system_prompt", "TEXT")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'admin',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    reward_type TEXT NOT NULL,
                    reward_value INTEGER NOT NULL,
                    max_activations INTEGER DEFAULT 0,
                    used_count INTEGER DEFAULT 0,
                    expires_at TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    promo_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    activated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(promo_id, user_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    message TEXT NOT NULL,
                    admin_reply TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    replied_at TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    reason TEXT,
                    banned_by INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS menu_buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    button_type TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_value TEXT,
                    is_active INTEGER DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_value TEXT,
                    is_active INTEGER DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feature_name TEXT NOT NULL UNIQUE,
                    is_enabled INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT,
                    channel_username TEXT,
                    channel_type TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS image_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    image_url TEXT,
                    provider TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    file_id TEXT,
                    extracted_text TEXT,
                    result_text TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            self._seed_defaults(conn)
            self._seed_feature_defaults(conn)

    def _seed_defaults(self, conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
        if existing:
            return
        conn.execute(
            """
            INSERT INTO settings (
                id, free_limit, stars_price_3, stars_price_7, stars_price_30,
                rub_price_3, rub_price_7, rub_price_30, help_text, paywall_text,
                free_image_limit, news_channel_url, support_text,
                maintenance_mode, maintenance_text,
                required_channel_id, required_channel_username,
                required_subscription_enabled, required_subscription_text,
                ai_provider, ai_fallback_1, ai_fallback_2, ai_model,
                image_provider, system_prompt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                DEFAULT_FREE_LIMIT,
                DEFAULT_STARS_PRICE_3,
                DEFAULT_STARS_PRICE_7,
                DEFAULT_STARS_PRICE_30,
                DEFAULT_RUB_PRICE_3,
                DEFAULT_RUB_PRICE_7,
                DEFAULT_RUB_PRICE_30,
                DEFAULT_HELP_TEXT,
                DEFAULT_PAYWALL_TEXT,
                DEFAULT_FREE_IMAGE_LIMIT,
                DEFAULT_NEWS_CHANNEL_URL,
                DEFAULT_SUPPORT_TEXT,
                0,
                DEFAULT_MAINTENANCE_TEXT,
                None,
                None,
                0,
                DEFAULT_REQUIRED_SUBSCRIPTION_TEXT,
                "gemini",
                "groq",
                "openrouter",
                None,
                "deepai",
                None,
            ),
        )

    def _seed_feature_defaults(self, conn: sqlite3.Connection) -> None:
        defaults = {
            "maintenance_mode": 0,
            "promocodes": 1,
            "support": 1,
            "news": 1,
            "materials": 1,
            "image_generation": 0,
            "solve_by_photo": 1,
            "referrals": 1,
        }
        for feature_name, enabled in defaults.items():
            row = conn.execute(
                "SELECT id FROM bot_features WHERE feature_name = ?",
                (feature_name,),
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO bot_features (feature_name, is_enabled) VALUES (?, ?)",
                    (feature_name, enabled),
                )

    def get_or_create_user(self, user_id: int, username: str | None) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row:
                if username != row["username"]:
                    conn.execute(
                        "UPDATE users SET username = ?, last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (username, user_id),
                    )
                    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                return dict(row)

            free_limit = self.get_setting("free_limit", DEFAULT_FREE_LIMIT)
            free_image_limit = self.get_setting("free_image_limit", DEFAULT_FREE_IMAGE_LIMIT)
            conn.execute(
                """
                INSERT INTO users (
                    id, username, requests_left, is_premium, sub_until, is_vip,
                    total_requests, bonus_requests_total, images_left, last_activity_at
                ) VALUES (?, ?, ?, 0, NULL, 0, 0, 0, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, username, free_limit, free_image_limit),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row)

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def update_user_requests(self, user_id: int, requests_left: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET requests_left = ?, last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                (requests_left, user_id),
            )

    def update_user_images(self, user_id: int, images_left: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET images_left = ?, last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                (images_left, user_id),
            )

    def increment_total_requests(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET total_requests = total_requests + 1, last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id,),
            )

    def activate_subscription(self, user_id: int, days: int) -> None:
        user = self.get_or_create_user(user_id, None)
        now = datetime.utcnow()
        current_until = None
        if user.get("sub_until"):
            try:
                current_until = datetime.fromisoformat(user["sub_until"])
            except ValueError:
                current_until = None
        base = current_until if current_until and current_until > now else now
        new_until = base + timedelta(days=days)
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 1, sub_until = ?, last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_until.isoformat(), user_id),
            )

    def remove_subscription(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 0, sub_until = NULL WHERE id = ?",
                (user_id,),
            )

    def set_vip(self, user_id: int, is_vip: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_vip = ? WHERE id = ?",
                (1 if is_vip else 0, user_id),
            )

    def add_requests(self, user_id: int, amount: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET requests_left = requests_left + ?, last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                (amount, user_id),
            )

    def add_bonus_requests_total(self, user_id: int, amount: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET bonus_requests_total = bonus_requests_total + ? WHERE id = ?",
                (amount, user_id),
            )

    def add_images(self, user_id: int, amount: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET images_left = images_left + ?, last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                (amount, user_id),
            )

    def log_request(self, user_id: int, provider: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO request_logs (user_id, provider) VALUES (?, ?)",
                (user_id, provider),
            )

    def log_image_generation(self, user_id: int, prompt: str, image_url: str | None, provider: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO image_logs (user_id, prompt, image_url, provider) VALUES (?, ?, ?, ?)",
                (user_id, prompt, image_url, provider),
            )

    def add_media_request(
        self,
        user_id: int,
        request_type: str,
        file_id: str | None,
        extracted_text: str | None,
        result_text: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO media_requests (user_id, type, file_id, extracted_text, result_text) VALUES (?, ?, ?, ?, ?)",
                (user_id, request_type, file_id, extracted_text, result_text),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        if not row:
            return default
        return row[key] if key in row.keys() else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._connect() as conn:
            conn.execute(f"UPDATE settings SET {key} = ? WHERE id = 1", (value,))

    def get_prices(self) -> dict[str, int]:
        return {
            "stars_3": int(self.get_setting("stars_price_3", DEFAULT_STARS_PRICE_3)),
            "stars_7": int(self.get_setting("stars_price_7", DEFAULT_STARS_PRICE_7)),
            "stars_30": int(self.get_setting("stars_price_30", DEFAULT_STARS_PRICE_30)),
            "rub_3": int(self.get_setting("rub_price_3", DEFAULT_RUB_PRICE_3)),
            "rub_7": int(self.get_setting("rub_price_7", DEFAULT_RUB_PRICE_7)),
            "rub_30": int(self.get_setting("rub_price_30", DEFAULT_RUB_PRICE_30)),
        }

    def set_price(self, key: str, value: int) -> None:
        self.set_setting(key, value)

    def create_payment(
        self,
        user_id: int,
        amount: float,
        payment_type: str,
        status: str,
        external_id: str | None = None,
        days: int = 0,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO payments (user_id, amount, type, status, external_id, days) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, amount, payment_type, status, external_id, days),
            )
            return int(cursor.lastrowid)

    def update_payment_status(self, external_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE payments SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE external_id = ?",
                (status, external_id),
            )

    def get_payment_by_external_id(self, external_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM payments WHERE external_id = ?",
                (external_id,),
            ).fetchone()
        return dict(row) if row else None

    def total_users(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
        return int(row["cnt"]) if row else 0

    def total_paid_users(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_premium = 1").fetchone()
        return int(row["cnt"]) if row else 0

    def requests_today(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM request_logs WHERE date(created_at) = date('now')"
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def total_revenue(self) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT type, COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'paid' GROUP BY type"
            ).fetchall()
        result = {"stars": 0.0, "yookassa": 0.0}
        for row in rows:
            payment_type = row["type"]
            result[payment_type] = float(row["total"] or 0)
        return result

    def add_referral(self, referrer_id: int, invited_user_id: int, bonus_requests: int = 5) -> bool:
        if referrer_id == invited_user_id:
            return False
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM referrals WHERE invited_user_id = ?",
                (invited_user_id,),
            ).fetchone()
            if existing:
                return False
            conn.execute(
                "INSERT INTO referrals (referrer_id, invited_user_id, bonus_requests) VALUES (?, ?, ?)",
                (referrer_id, invited_user_id, bonus_requests),
            )
            conn.execute(
                "UPDATE users SET referred_by = ? WHERE id = ?",
                (referrer_id, invited_user_id),
            )
        self.add_requests(referrer_id, bonus_requests)
        self.add_bonus_requests_total(referrer_id, bonus_requests)
        return True

    def get_referral_stats(self, user_id: int) -> dict[str, int]:
        with self._connect() as conn:
            invited_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM referrals WHERE referrer_id = ?",
                (user_id,),
            ).fetchone()
            bonus_row = conn.execute(
                "SELECT COALESCE(SUM(bonus_requests), 0) AS total FROM referrals WHERE referrer_id = ?",
                (user_id,),
            ).fetchone()
        return {
            "invited_count": int(invited_row["cnt"]) if invited_row else 0,
            "bonus_total": int(bonus_row["total"]) if bonus_row else 0,
        }

    def is_admin(self, user_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM admins WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None

    def ensure_admin_exists(self, user_id: int, role: str = "admin") -> None:
        if not user_id:
            return
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM admins WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO admins (user_id, role) VALUES (?, ?)",
                    (user_id, role),
                )

    def add_admin(self, user_id: int, role: str = "admin") -> None:
        self.ensure_admin_exists(user_id, role)

    def remove_admin(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))

    def list_admins(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM admins ORDER BY created_at ASC, id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def ban_user(self, user_id: int, reason: str | None, banned_by: int | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_banned = 1, ban_reason = ? WHERE id = ?",
                (reason, user_id),
            )
            conn.execute(
                "INSERT INTO bans (user_id, reason, banned_by, is_active) VALUES (?, ?, ?, 1)",
                (user_id, reason, banned_by),
            )

    def unban_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE id = ?",
                (user_id,),
            )
            conn.execute(
                "UPDATE bans SET is_active = 0 WHERE user_id = ? AND is_active = 1",
                (user_id,),
            )

    def is_user_banned(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return bool(user and user.get("is_banned"))

    def get_user_ban_reason(self, user_id: int) -> str | None:
        user = self.get_user(user_id)
        return user.get("ban_reason") if user else None

    def create_support_ticket(self, user_id: int, message: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO support_tickets (user_id, message, status) VALUES (?, ?, 'open')",
                (user_id, message),
            )
            return int(cursor.lastrowid)

    def list_support_tickets(self, only_open: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if only_open:
                rows = conn.execute(
                    "SELECT * FROM support_tickets WHERE status = 'open' ORDER BY id DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM support_tickets ORDER BY id DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_support_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM support_tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()
        return dict(row) if row else None

    def reply_support_ticket(self, ticket_id: int, reply_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE support_tickets SET admin_reply = ?, status = 'answered', replied_at = CURRENT_TIMESTAMP WHERE id = ?",
                (reply_text, ticket_id),
            )

    def close_support_ticket(self, ticket_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE support_tickets SET status = 'closed' WHERE id = ?",
                (ticket_id,),
            )

    def create_promo_code(
        self,
        code: str,
        reward_type: str,
        reward_value: int,
        max_activations: int = 0,
        expires_at: str | None = None,
        is_active: bool = True,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO promo_codes (code, reward_type, reward_value, max_activations, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code.upper(), reward_type, reward_value, max_activations, expires_at, 1 if is_active else 0),
            )
            return int(cursor.lastrowid)

    def list_promo_codes(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM promo_codes ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def get_promo_code(self, code: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM promo_codes WHERE code = ?",
                (code.upper(),),
            ).fetchone()
        return dict(row) if row else None

    def set_promo_active(self, code: str, is_active: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE promo_codes SET is_active = ? WHERE code = ?",
                (1 if is_active else 0, code.upper()),
            )

    def can_activate_promo(self, user_id: int, code: str) -> tuple[bool, str | None, dict[str, Any] | None]:
        promo = self.get_promo_code(code)
        if not promo:
            return False, "Промокод не найден.", None
        if not promo["is_active"]:
            return False, "Промокод отключён.", promo
        if promo.get("expires_at"):
            try:
                if datetime.fromisoformat(promo["expires_at"]) < datetime.utcnow():
                    return False, "Срок действия промокода истёк.", promo
            except ValueError:
                pass
        if promo["max_activations"] and promo["used_count"] >= promo["max_activations"]:
            return False, "Лимит активаций промокода исчерпан.", promo
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM promo_activations WHERE promo_id = ? AND user_id = ?",
                (promo["id"], user_id),
            ).fetchone()
        if row:
            return False, "Ты уже использовал этот промокод.", promo
        return True, None, promo

    def activate_promo(self, user_id: int, code: str) -> tuple[bool, str, dict[str, Any] | None]:
        ok, error, promo = self.can_activate_promo(user_id, code)
        if not ok or not promo:
            return False, error or "Не удалось активировать промокод.", None

        reward_type = promo["reward_type"]
        reward_value = int(promo["reward_value"])

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO promo_activations (promo_id, user_id) VALUES (?, ?)",
                (promo["id"], user_id),
            )
            conn.execute(
                "UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?",
                (promo["id"],),
            )

        if reward_type == "requests":
            self.add_requests(user_id, reward_value)
            text = f"Промокод активирован. Тебе начислено {reward_value} запросов."
        elif reward_type == "premium_days":
            self.activate_subscription(user_id, reward_value)
            text = f"Промокод активирован. Тебе выдана подписка на {reward_value} дней."
        elif reward_type == "vip":
            self.set_vip(user_id, True)
            text = "Промокод активирован. Тебе выдан VIP-статус."
        else:
            text = "Промокод активирован."

        return True, text, promo

    def get_all_features(self) -> dict[str, bool]:
        with self._connect() as conn:
            rows = conn.execute("SELECT feature_name, is_enabled FROM bot_features").fetchall()
        return {r["feature_name"]: bool(r["is_enabled"]) for r in rows}

    def is_feature_enabled(self, feature_name: str, default: bool = False) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM bot_features WHERE feature_name = ?",
                (feature_name,),
            ).fetchone()
        if row is None:
            return default
        return bool(row["is_enabled"])

    def set_feature_enabled(self, feature_name: str, enabled: bool) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM bot_features WHERE feature_name = ?",
                (feature_name,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE bot_features SET is_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE feature_name = ?",
                    (1 if enabled else 0, feature_name),
                )
            else:
                conn.execute(
                    "INSERT INTO bot_features (feature_name, is_enabled) VALUES (?, ?)",
                    (feature_name, 1 if enabled else 0),
                )

    def is_maintenance_enabled(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT maintenance_mode FROM settings WHERE id = 1").fetchone()
        return bool(row["maintenance_mode"]) if row else False

    def get_maintenance_text(self) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT maintenance_text FROM settings WHERE id = 1").fetchone()
        if row and row["maintenance_text"]:
            return str(row["maintenance_text"])
        return DEFAULT_MAINTENANCE_TEXT

    def set_maintenance_mode(self, enabled: bool, text: str | None = None) -> None:
        with self._connect() as conn:
            if text is None:
                conn.execute(
                    "UPDATE settings SET maintenance_mode = ? WHERE id = 1",
                    (1 if enabled else 0,),
                )
            else:
                conn.execute(
                    "UPDATE settings SET maintenance_mode = ?, maintenance_text = ? WHERE id = 1",
                    (1 if enabled else 0, text),
                )

            existing = conn.execute(
                "SELECT id FROM bot_features WHERE feature_name = ?",
                ("maintenance_mode",),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE bot_features SET is_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE feature_name = ?",
                    (1 if enabled else 0, "maintenance_mode"),
                )
            else:
                conn.execute(
                    "INSERT INTO bot_features (feature_name, is_enabled) VALUES (?, ?)",
                    ("maintenance_mode", 1 if enabled else 0),
                )

    def set_required_channel(self, channel_id: str | None, username: str | None, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE settings SET required_channel_id = ?, required_channel_username = ?, required_subscription_enabled = ? WHERE id = 1",
                (channel_id, username, 1 if enabled else 0),
            )
            conn.execute("UPDATE channels SET is_active = 0 WHERE channel_type = 'required_subscription'")
            if enabled:
                conn.execute(
                    "INSERT INTO channels (channel_id, channel_username, channel_type, is_active) VALUES (?, ?, 'required_subscription', 1)",
                    (channel_id, username),
                )

    def get_required_channel(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT required_channel_id, required_channel_username, required_subscription_enabled, required_subscription_text FROM settings WHERE id = 1"
            ).fetchone()
        if not row:
            return {
                "channel_id": None,
                "channel_username": None,
                "enabled": False,
                "text": DEFAULT_REQUIRED_SUBSCRIPTION_TEXT,
            }
        return {
            "channel_id": row["required_channel_id"],
            "channel_username": row["required_channel_username"],
            "enabled": bool(row["required_subscription_enabled"]),
            "text": row["required_subscription_text"] or DEFAULT_REQUIRED_SUBSCRIPTION_TEXT,
        }

    def set_required_subscription_text(self, text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE settings SET required_subscription_text = ? WHERE id = 1",
                (text,),
            )

    def get_ai_settings(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT ai_provider, ai_fallback_1, ai_fallback_2, ai_model, image_provider, system_prompt FROM settings WHERE id = 1"
            ).fetchone()
        if not row:
            return {
                "provider": "gemini",
                "fallback_1": "groq",
                "fallback_2": "openrouter",
                "model": None,
                "image_provider": "deepai",
                "system_prompt": None,
            }
        return {
            "provider": row["ai_provider"] or "gemini",
            "fallback_1": row["ai_fallback_1"] or "groq",
            "fallback_2": row["ai_fallback_2"] or "openrouter",
            "model": row["ai_model"],
            "image_provider": row["image_provider"] or "deepai",
            "system_prompt": row["system_prompt"],
        }

    def set_ai_setting(self, field: str, value: Any) -> None:
        allowed = {
            "ai_provider",
            "ai_fallback_1",
            "ai_fallback_2",
            "ai_model",
            "image_provider",
            "system_prompt",
        }
        if field not in allowed:
            raise ValueError(f"Недопустимое поле настройки AI: {field}")
        with self._connect() as conn:
            conn.execute(f"UPDATE settings SET {field} = ? WHERE id = 1", (value,))

    def list_menu_buttons(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM menu_buttons ORDER BY sort_order ASC, id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_menu_button(self, title: str, button_type: str, action_type: str, action_value: str | None, sort_order: int = 0) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO menu_buttons (title, button_type, action_type, action_value, sort_order) VALUES (?, ?, ?, ?, ?)",
                (title, button_type, action_type, action_value, sort_order),
            )
            return int(cursor.lastrowid)

    def set_menu_button_active(self, button_id: int, is_active: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE menu_buttons SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, button_id),
            )

    def set_menu_button_sort(self, button_id: int, sort_order: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE menu_buttons SET sort_order = ? WHERE id = ?",
                (sort_order, button_id),
            )

    def delete_menu_button(self, button_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM menu_buttons WHERE id = ?", (button_id,))

    def export_users(self, paid_only: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if paid_only:
                rows = conn.execute("SELECT * FROM users WHERE is_premium = 1 ORDER BY id ASC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]
