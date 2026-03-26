import csv
import io
import sqlite3
from contextlib import contextmanager
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
        self.init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row[1]) for row in rows}

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        if column_name not in self._table_columns(conn, table_name):
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def init_db(self) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    requests_left INTEGER NOT NULL DEFAULT 3,
                    is_premium INTEGER NOT NULL DEFAULT 0,
                    sub_until TEXT,
                    is_vip INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    total_requests INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            # Stage 1 foundation columns for v2.0
            self._ensure_column(cursor.connection, "users", "is_banned", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(cursor.connection, "users", "ban_reason", "TEXT")
            self._ensure_column(cursor.connection, "users", "referred_by", "INTEGER")
            self._ensure_column(cursor.connection, "users", "bonus_requests_total", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(cursor.connection, "users", "images_left", f"INTEGER NOT NULL DEFAULT {DEFAULT_FREE_IMAGE_LIMIT}")
            self._ensure_column(cursor.connection, "users", "support_blocked", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(cursor.connection, "users", "last_activity_at", "TEXT")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    external_id TEXT UNIQUE,
                    days INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    free_limit INTEGER NOT NULL DEFAULT 3,
                    price_3_days_stars INTEGER NOT NULL DEFAULT 59,
                    price_7_days_stars INTEGER NOT NULL DEFAULT 99,
                    price_30_days_stars INTEGER NOT NULL DEFAULT 199,
                    price_3_days_rub INTEGER NOT NULL DEFAULT 99,
                    price_7_days_rub INTEGER NOT NULL DEFAULT 199,
                    price_30_days_rub INTEGER NOT NULL DEFAULT 499,
                    help_text TEXT NOT NULL,
                    paywall_text TEXT NOT NULL
                )
                """
            )

            # New settings fields for v2.0 foundation
            self._ensure_column(cursor.connection, "settings", "free_image_limit", f"INTEGER NOT NULL DEFAULT {DEFAULT_FREE_IMAGE_LIMIT}")
            self._ensure_column(cursor.connection, "settings", "news_channel_url", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(cursor.connection, "settings", "support_text", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(cursor.connection, "settings", "maintenance_mode", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(cursor.connection, "settings", "maintenance_text", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(cursor.connection, "settings", "required_channel_id", "TEXT")
            self._ensure_column(cursor.connection, "settings", "required_channel_username", "TEXT")
            self._ensure_column(cursor.connection, "settings", "required_subscription_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(cursor.connection, "settings", "required_subscription_text", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(cursor.connection, "settings", "ai_provider", "TEXT NOT NULL DEFAULT 'gemini'")
            self._ensure_column(cursor.connection, "settings", "ai_fallback_1", "TEXT NOT NULL DEFAULT 'groq'")
            self._ensure_column(cursor.connection, "settings", "ai_fallback_2", "TEXT NOT NULL DEFAULT 'openrouter'")
            self._ensure_column(cursor.connection, "settings", "ai_model", "TEXT")
            self._ensure_column(cursor.connection, "settings", "image_provider", "TEXT NOT NULL DEFAULT 'deepai'")
            self._ensure_column(cursor.connection, "settings", "system_prompt", "TEXT")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    provider TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    invited_user_id INTEGER NOT NULL UNIQUE,
                    bonus_requests INTEGER NOT NULL DEFAULT 5,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(referrer_id) REFERENCES users(id),
                    FOREIGN KEY(invited_user_id) REFERENCES users(id)
                )
                """
            )

            # v2.0 foundation tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'owner',
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    reward_type TEXT NOT NULL,
                    reward_value INTEGER NOT NULL,
                    max_activations INTEGER,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    promo_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    activated_at TEXT NOT NULL,
                    UNIQUE(promo_id, user_id),
                    FOREIGN KEY(promo_id) REFERENCES promo_codes(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    message TEXT NOT NULL,
                    admin_reply TEXT,
                    created_at TEXT NOT NULL,
                    replied_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    reason TEXT,
                    banned_by INTEGER,
                    created_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS menu_buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    button_type TEXT NOT NULL DEFAULT 'reply',
                    action_type TEXT NOT NULL,
                    action_value TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_value TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feature_name TEXT NOT NULL UNIQUE,
                    is_enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT,
                    channel_username TEXT,
                    channel_type TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(channel_type)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS image_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    image_url TEXT,
                    provider TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS media_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    extracted_text TEXT,
                    result_text TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )

            cursor.execute("SELECT id FROM settings WHERE id = 1")
            settings_exists = cursor.fetchone()
            if not settings_exists:
                cursor.execute(
                    """
                    INSERT INTO settings (
                        id,
                        free_limit,
                        price_3_days_stars,
                        price_7_days_stars,
                        price_30_days_stars,
                        price_3_days_rub,
                        price_7_days_rub,
                        price_30_days_rub,
                        help_text,
                        paywall_text,
                        free_image_limit,
                        news_channel_url,
                        support_text,
                        maintenance_mode,
                        maintenance_text,
                        required_subscription_enabled,
                        required_subscription_text,
                        ai_provider,
                        ai_fallback_1,
                        ai_fallback_2,
                        image_provider
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        0,
                        DEFAULT_REQUIRED_SUBSCRIPTION_TEXT,
                        'gemini',
                        'groq',
                        'openrouter',
                        'deepai',
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE settings
                    SET
                        free_image_limit = COALESCE(free_image_limit, ?),
                        news_channel_url = COALESCE(NULLIF(news_channel_url, ''), ?),
                        support_text = COALESCE(NULLIF(support_text, ''), ?),
                        maintenance_text = COALESCE(NULLIF(maintenance_text, ''), ?),
                        required_subscription_text = COALESCE(NULLIF(required_subscription_text, ''), ?),
                        ai_provider = COALESCE(NULLIF(ai_provider, ''), 'gemini'),
                        ai_fallback_1 = COALESCE(NULLIF(ai_fallback_1, ''), 'groq'),
                        ai_fallback_2 = COALESCE(NULLIF(ai_fallback_2, ''), 'openrouter'),
                        image_provider = COALESCE(NULLIF(image_provider, ''), 'deepai')
                    WHERE id = 1
                    """,
                    (
                        DEFAULT_FREE_IMAGE_LIMIT,
                        DEFAULT_NEWS_CHANNEL_URL,
                        DEFAULT_SUPPORT_TEXT,
                        DEFAULT_MAINTENANCE_TEXT,
                        DEFAULT_REQUIRED_SUBSCRIPTION_TEXT,
                    ),
                )

            # Backfill nullable values for existing installations
            cursor.execute(
                "UPDATE users SET images_left = ? WHERE images_left IS NULL",
                (DEFAULT_FREE_IMAGE_LIMIT,),
            )
            now = self._now_str()
            cursor.execute(
                "UPDATE users SET last_activity_at = ? WHERE last_activity_at IS NULL",
                (now,),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO admins (user_id, role, created_at) VALUES (?, 'owner', ?)",
                (ADMIN_ID, now),
            )

            self._seed_feature_flags(cursor)

    def _seed_feature_flags(self, cursor: sqlite3.Cursor) -> None:
        now = self._now_str()
        feature_defaults = {
            "referrals": 1,
            "promocodes": 0,
            "support": 0,
            "news": 0,
            "materials": 0,
            "image_generation": 0,
            "solve_by_photo": 0,
            "required_subscription": 0,
            "maintenance_mode": 0,
        }
        for feature_name, is_enabled in feature_defaults.items():
            cursor.execute(
                "INSERT OR IGNORE INTO bot_features (feature_name, is_enabled, updated_at) VALUES (?, ?, ?)",
                (feature_name, is_enabled, now),
            )

    # -------- Base settings and user methods --------
    def get_settings(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
            return dict(row) if row else {}

    def set_free_limit(self, value: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE settings SET free_limit = ? WHERE id = 1", (value,))

    def apply_free_limit_to_all(self, value: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE settings SET free_limit = ? WHERE id = 1", (value,))
            conn.execute(
                "UPDATE users SET requests_left = ? WHERE is_premium = 0 AND is_vip = 0",
                (value,),
            )

    def set_prices(self, days: int, stars_price: int, rub_price: int) -> None:
        if days not in (3, 7, 30):
            raise ValueError("Поддерживаются только тарифы на 3, 7 и 30 дней")
        with self._connect() as conn:
            conn.execute(
                f"UPDATE settings SET price_{days}_days_stars = ?, price_{days}_days_rub = ? WHERE id = 1",
                (stars_price, rub_price),
            )

    def set_help_text(self, text: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE settings SET help_text = ? WHERE id = 1", (text,))

    def set_paywall_text(self, text: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE settings SET paywall_text = ? WHERE id = 1", (text,))

    def touch_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET last_activity_at = ? WHERE id = ?", (self._now_str(), user_id))

    def get_or_create_user(self, user_id: int, username: str | None = None) -> dict[str, Any]:
        user = self.get_user(user_id)
        if user:
            if username != user.get("username"):
                self.update_username(user_id, username)
            self.refresh_subscription_status(user_id)
            self.touch_user(user_id)
            return self.get_user(user_id)

        settings = self.get_settings()
        free_limit = int(settings.get("free_limit", DEFAULT_FREE_LIMIT))
        free_image_limit = int(settings.get("free_image_limit", DEFAULT_FREE_IMAGE_LIMIT))
        now = self._now_str()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, username, requests_left, is_premium, sub_until, is_vip, created_at,
                    total_requests, is_banned, ban_reason, referred_by, bonus_requests_total,
                    images_left, support_blocked, last_activity_at
                ) VALUES (?, ?, ?, 0, NULL, 0, ?, 0, 0, NULL, NULL, 0, ?, 0, ?)
                """,
                (user_id, username, free_limit, now, free_image_limit, now),
            )
        return self.get_user(user_id)

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def update_username(self, user_id: int, username: str | None) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))

    def refresh_subscription_status(self, user_id: int) -> None:
        user = self.get_user(user_id)
        if not user:
            return
        if bool(user.get("is_vip")):
            return

        sub_until = user.get("sub_until")
        if sub_until:
            try:
                sub_dt = datetime.strptime(sub_until, "%Y-%m-%d %H:%M:%S")
                if sub_dt < datetime.now() and user.get("is_premium"):
                    with self._connect() as conn:
                        conn.execute(
                            "UPDATE users SET is_premium = 0, sub_until = NULL WHERE id = ?",
                            (user_id,),
                        )
            except ValueError:
                return

    def has_access(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user or bool(user.get("is_banned")):
            return False
        self.refresh_subscription_status(user_id)
        user = self.get_user(user_id)
        return bool(user["is_vip"] or user["is_premium"] or user["requests_left"] > 0)

    def decrement_request_if_needed(self, user_id: int) -> bool:
        self.refresh_subscription_status(user_id)
        user = self.get_user(user_id)
        if not user or bool(user.get("is_banned")):
            return False

        if user["is_vip"] or user["is_premium"]:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET total_requests = total_requests + 1, last_activity_at = ? WHERE id = ?",
                    (self._now_str(), user_id),
                )
            return True

        if user["requests_left"] <= 0:
            return False

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET requests_left = requests_left - 1,
                    total_requests = total_requests + 1,
                    last_activity_at = ?
                WHERE id = ?
                """,
                (self._now_str(), user_id),
            )
        return True

    def add_request_log(self, user_id: int, mode: str, provider: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO request_logs (user_id, mode, provider, created_at) VALUES (?, ?, ?, ?)",
                (user_id, mode, provider, self._now_str()),
            )

    def activate_subscription(self, user_id: int, days: int) -> None:
        user = self.get_or_create_user(user_id)
        now = datetime.now()
        current_sub_until = user.get("sub_until")
        if user.get("is_premium") and current_sub_until:
            try:
                current_dt = datetime.strptime(current_sub_until, "%Y-%m-%d %H:%M:%S")
                new_until = current_dt + timedelta(days=days) if current_dt > now else now + timedelta(days=days)
            except ValueError:
                new_until = now + timedelta(days=days)
        else:
            new_until = now + timedelta(days=days)

        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 1, sub_until = ?, last_activity_at = ? WHERE id = ?",
                (new_until.strftime("%Y-%m-%d %H:%M:%S"), self._now_str(), user_id),
            )

    def revoke_subscription(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 0, sub_until = NULL WHERE id = ?",
                (user_id,),
            )

    def add_requests(self, user_id: int, amount: int, bonus: bool = False) -> None:
        with self._connect() as conn:
            if bonus:
                conn.execute(
                    "UPDATE users SET requests_left = requests_left + ?, bonus_requests_total = bonus_requests_total + ? WHERE id = ?",
                    (amount, amount, user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET requests_left = requests_left + ? WHERE id = ?",
                    (amount, user_id),
                )

    def set_user_limit(self, user_id: int, value: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET requests_left = ? WHERE id = ?", (value, user_id))

    def set_vip(self, user_id: int, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET is_vip = ? WHERE id = ?", (1 if enabled else 0, user_id))

    # -------- Payments and stats --------
    def create_payment(self, user_id: int, amount: float, payment_type: str, status: str,
                       external_id: str | None = None, days: int | None = None) -> None:
        now = self._now_str()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO payments (user_id, amount, type, status, external_id, days, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, amount, payment_type, status, external_id, days, now, now),
            )

    def update_payment_status(self, external_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE payments SET status = ?, updated_at = ? WHERE external_id = ?",
                (status, self._now_str(), external_id),
            )

    def upsert_payment(self, user_id: int, amount: float, payment_type: str, status: str,
                       external_id: str, days: int | None = None) -> None:
        existing = self.get_payment_by_external_id(external_id)
        if existing:
            self.update_payment_status(external_id, status)
            return
        self.create_payment(user_id, amount, payment_type, status, external_id, days)

    def get_payment_by_external_id(self, external_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM payments WHERE external_id = ?", (external_id,)).fetchone()
            return dict(row) if row else None

    def user_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
            return int(row["cnt"])

    def paid_user_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM users WHERE is_premium = 1 OR is_vip = 1"
            ).fetchone()
            return int(row["cnt"])

    def requests_today_count(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM request_logs WHERE date(created_at) = ?",
                (today,),
            ).fetchone()
            return int(row["cnt"])

    def income_stats(self) -> dict[str, float]:
        with self._connect() as conn:
            stars = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE type = 'stars' AND status = 'succeeded'"
            ).fetchone()["total"]
            rub = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE type = 'yookassa' AND status = 'succeeded'"
            ).fetchone()["total"]
        return {"stars": float(stars), "rub": float(rub)}

    def all_user_ids(self, only_paid: bool = False) -> list[int]:
        query = "SELECT id FROM users"
        if only_paid:
            query += " WHERE is_premium = 1 OR is_vip = 1"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
            return [int(row["id"]) for row in rows]

    def get_prices(self) -> dict[int, dict[str, int]]:
        settings = self.get_settings()
        return {
            3: {"stars": settings["price_3_days_stars"], "rub": settings["price_3_days_rub"]},
            7: {"stars": settings["price_7_days_stars"], "rub": settings["price_7_days_rub"]},
            30: {"stars": settings["price_30_days_stars"], "rub": settings["price_30_days_rub"]},
        }

    def export_user_profile_text(self, user_id: int) -> str:
        self.refresh_subscription_status(user_id)
        user = self.get_user(user_id)
        if not user:
            return "Пользователь не найден."

        sub_until = user["sub_until"] or "—"
        premium_text = "Да" if user["is_premium"] else "Нет"
        vip_text = "Да" if user["is_vip"] else "Нет"
        username = f"@{user['username']}" if user["username"] else "—"
        banned = "Да" if user.get("is_banned") else "Нет"

        return (
            f"👤 <b>Профиль пользователя</b>\n\n"
            f"ID: <code>{user['id']}</code>\n"
            f"Username: {username}\n"
            f"Осталось запросов: <b>{user['requests_left']}</b>\n"
            f"Premium: <b>{premium_text}</b>\n"
            f"Подписка до: <b>{sub_until}</b>\n"
            f"VIP: <b>{vip_text}</b>\n"
            f"Бан: <b>{banned}</b>\n"
            f"Бонусных запросов всего: <b>{user.get('bonus_requests_total', 0)}</b>\n"
            f"Всего запросов: <b>{user['total_requests']}</b>"
        )

    # -------- Referrals --------
    def add_referral(self, referrer_id: int, invited_user_id: int, bonus_requests: int = 5) -> bool:
        if referrer_id == invited_user_id:
            return False
        self.get_or_create_user(referrer_id)
        self.get_or_create_user(invited_user_id)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM referrals WHERE invited_user_id = ?",
                (invited_user_id,),
            ).fetchone()
            if existing:
                return False
            conn.execute(
                "INSERT INTO referrals (referrer_id, invited_user_id, bonus_requests, created_at) VALUES (?, ?, ?, ?)",
                (referrer_id, invited_user_id, bonus_requests, self._now_str()),
            )
            conn.execute(
                "UPDATE users SET referred_by = ? WHERE id = ? AND referred_by IS NULL",
                (referrer_id, invited_user_id),
            )
        self.add_requests(referrer_id, bonus_requests, bonus=True)
        return True

    def get_referral_stats(self, user_id: int) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS invited_count, COALESCE(SUM(bonus_requests), 0) AS bonus_total FROM referrals WHERE referrer_id = ?",
                (user_id,),
            ).fetchone()
            return {
                "invited_count": int(row["invited_count"]),
                "bonus_total": int(row["bonus_total"]),
            }

    # -------- Admins --------
    def is_admin(self, user_id: int) -> bool:
        if user_id == ADMIN_ID:
            return True
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
            return bool(row)

    def add_admin(self, user_id: int, role: str = "admin") -> None:
        self.get_or_create_user(user_id)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO admins (user_id, role, created_at) VALUES (?, ?, COALESCE((SELECT created_at FROM admins WHERE user_id = ?), ?))",
                (user_id, role, user_id, self._now_str()),
            )

    def remove_admin(self, user_id: int) -> None:
        if user_id == ADMIN_ID:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))

    def list_admins(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT a.user_id, a.role, a.created_at, u.username FROM admins a LEFT JOIN users u ON u.id = a.user_id ORDER BY a.created_at ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    # -------- Feature flags --------
    def is_feature_enabled(self, feature_name: str, default: bool = False) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM bot_features WHERE feature_name = ?",
                (feature_name,),
            ).fetchone()
            if not row:
                return default
            return bool(row["is_enabled"])

    def set_feature_enabled(self, feature_name: str, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_features (feature_name, is_enabled, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(feature_name) DO UPDATE SET is_enabled = excluded.is_enabled, updated_at = excluded.updated_at
                """,
                (feature_name, 1 if enabled else 0, self._now_str()),
            )

    def get_all_features(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM bot_features ORDER BY feature_name ASC").fetchall()
            return [dict(row) for row in rows]

    # -------- Maintenance / required channel --------
    def set_maintenance_mode(self, enabled: bool, text: str | None = None) -> None:
        with self._connect() as conn:
            if text is None:
                conn.execute("UPDATE settings SET maintenance_mode = ? WHERE id = 1", (1 if enabled else 0,))
            else:
                conn.execute(
                    "UPDATE settings SET maintenance_mode = ?, maintenance_text = ? WHERE id = 1",
                    (1 if enabled else 0, text),
                )
            self.set_feature_enabled("maintenance_mode", enabled)

    def set_required_channel(self, channel_id: str | None, channel_username: str | None, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE settings SET required_channel_id = ?, required_channel_username = ?, required_subscription_enabled = ? WHERE id = 1",
                (channel_id, channel_username, 1 if enabled else 0),
            )
            if channel_id or channel_username:
                conn.execute(
                    """
                    INSERT INTO channels (channel_id, channel_username, channel_type, is_active, created_at, updated_at)
                    VALUES (?, ?, 'required_subscription', ?, ?, ?)
                    ON CONFLICT(channel_type) DO UPDATE SET
                        channel_id = excluded.channel_id,
                        channel_username = excluded.channel_username,
                        is_active = excluded.is_active,
                        updated_at = excluded.updated_at
                    """,
                    (channel_id, channel_username, 1 if enabled else 0, self._now_str(), self._now_str()),
                )
        self.set_feature_enabled("required_subscription", enabled)

    def get_required_channel(self) -> dict[str, Any]:
        settings = self.get_settings()
        return {
            "channel_id": settings.get("required_channel_id"),
            "channel_username": settings.get("required_channel_username"),
            "enabled": bool(settings.get("required_subscription_enabled")),
            "text": settings.get("required_subscription_text") or DEFAULT_REQUIRED_SUBSCRIPTION_TEXT,
        }

    def get_required_channel_link(self) -> str | None:
        channel = self.get_required_channel()
        username = channel.get("channel_username")
        if username:
            username = str(username).strip()
            if username.startswith("http://") or username.startswith("https://"):
                return username
            if username.startswith("@"):
                return f"https://t.me/{username[1:]}"
            return f"https://t.me/{username}"
        return None

    def set_required_subscription_text(self, text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE settings SET required_subscription_text = ? WHERE id = 1",
                (text,),
            )

    def is_maintenance_enabled(self) -> bool:
        settings = self.get_settings()
        return bool(settings.get("maintenance_mode"))

    def get_maintenance_text(self) -> str:
        settings = self.get_settings()
        return settings.get("maintenance_text") or DEFAULT_MAINTENANCE_TEXT

    # -------- Bans --------
    def ban_user(self, user_id: int, reason: str | None = None, banned_by: int | None = None) -> None:
        self.get_or_create_user(user_id)
        with self._connect() as conn:
            conn.execute("UPDATE bans SET is_active = 0 WHERE user_id = ?", (user_id,))
            conn.execute(
                "INSERT INTO bans (user_id, reason, banned_by, created_at, is_active) VALUES (?, ?, ?, ?, 1)",
                (user_id, reason, banned_by, self._now_str()),
            )
            conn.execute(
                "UPDATE users SET is_banned = 1, ban_reason = ? WHERE id = ?",
                (reason, user_id),
            )

    def unban_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE bans SET is_active = 0 WHERE user_id = ?", (user_id,))
            conn.execute(
                "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE id = ?",
                (user_id,),
            )

    def is_user_banned(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return bool(user and user.get("is_banned"))

    # -------- Promo codes foundation --------
    def create_promo_code(
        self,
        code: str,
        reward_type: str,
        reward_value: int,
        max_activations: int | None = None,
        expires_at: str | None = None,
        is_active: bool = True,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO promo_codes (code, reward_type, reward_value, max_activations, used_count, expires_at, is_active, created_at)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (code.upper().strip(), reward_type, reward_value, max_activations, expires_at, 1 if is_active else 0, self._now_str()),
            )

    def get_promo_code(self, code: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM promo_codes WHERE code = ?",
                (code.upper().strip(),),
            ).fetchone()
            return dict(row) if row else None

    def has_user_activated_promo(self, promo_id: int, user_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM promo_activations WHERE promo_id = ? AND user_id = ?",
                (promo_id, user_id),
            ).fetchone()
            return bool(row)

    def activate_promo_code(self, code: str, user_id: int) -> tuple[bool, str]:
        promo = self.get_promo_code(code)
        if not promo:
            return False, "Промокод не найден."
        if not promo["is_active"]:
            return False, "Промокод отключён."
        if promo["expires_at"]:
            try:
                if datetime.strptime(promo["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
                    return False, "Срок действия промокода истёк."
            except ValueError:
                return False, "У промокода некорректная дата окончания."
        if promo["max_activations"] is not None and promo["used_count"] >= promo["max_activations"]:
            return False, "Лимит активаций промокода закончился."
        if self.has_user_activated_promo(int(promo["id"]), user_id):
            return False, "Ты уже использовал этот промокод."

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO promo_activations (promo_id, user_id, activated_at) VALUES (?, ?, ?)",
                (promo["id"], user_id, self._now_str()),
            )
            conn.execute(
                "UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?",
                (promo["id"],),
            )
        if promo["reward_type"] == "requests":
            self.add_requests(user_id, int(promo["reward_value"]), bonus=True)
            return True, f"Промокод активирован. Начислено {promo['reward_value']} запросов."
        if promo["reward_type"] == "premium_days":
            self.activate_subscription(user_id, int(promo["reward_value"]))
            return True, f"Промокод активирован. Подписка выдана на {promo['reward_value']} дней."
        if promo["reward_type"] == "vip":
            self.set_vip(user_id, True)
            return True, "Промокод активирован. Выдан VIP-статус."
        return False, "Неизвестный тип награды промокода."

    # -------- Support foundation --------
    def create_support_ticket(self, user_id: int, message_text: str) -> int:
        self.get_or_create_user(user_id)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO support_tickets (user_id, status, message, created_at) VALUES (?, 'open', ?, ?)",
                (user_id, message_text, self._now_str()),
            )
            return int(cursor.lastrowid)

    def reply_support_ticket(self, ticket_id: int, reply_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE support_tickets SET status = 'answered', admin_reply = ?, replied_at = ? WHERE id = ?",
                (reply_text, self._now_str(), ticket_id),
            )

    def get_support_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM support_tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_open_support_tickets(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM support_tickets WHERE status = 'open' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    # -------- Dynamic buttons foundation --------
    def add_menu_button(self, title: str, action_type: str, action_value: str | None = None,
                        button_type: str = "reply", sort_order: int = 0, is_active: bool = True) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO menu_buttons (title, button_type, action_type, action_value, is_active, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, button_type, action_type, action_value, 1 if is_active else 0, sort_order, self._now_str()),
            )

    def get_active_menu_buttons(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM menu_buttons WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    # -------- Export foundation --------
    def export_users_csv(self, only_paid: bool = False) -> str:
        query = "SELECT id, username, requests_left, is_premium, sub_until, is_vip, is_banned, bonus_requests_total, created_at, last_activity_at FROM users"
        if only_paid:
            query += " WHERE is_premium = 1 OR is_vip = 1"
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id",
            "username",
            "requests_left",
            "is_premium",
            "sub_until",
            "is_vip",
            "is_banned",
            "bonus_requests_total",
            "created_at",
            "last_activity_at",
        ])
        for row in rows:
            writer.writerow([row[col] for col in row.keys()])
        return output.getvalue()

    # -------- Image/photo foundation --------
    def add_image_log(self, user_id: int, prompt: str, image_url: str | None, provider: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO image_logs (user_id, prompt, image_url, provider, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, prompt, image_url, provider, self._now_str()),
            )

    def add_media_request(self, user_id: int, request_type: str, file_id: str,
                          extracted_text: str | None = None, result_text: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO media_requests (user_id, type, file_id, extracted_text, result_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, request_type, file_id, extracted_text, result_text, self._now_str()),
            )
