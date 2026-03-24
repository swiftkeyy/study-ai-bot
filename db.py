import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from config import (
    DB_PATH,
    DEFAULT_FREE_LIMIT,
    DEFAULT_HELP_TEXT,
    DEFAULT_PAYWALL_TEXT,
    DEFAULT_RUB_PRICE_3,
    DEFAULT_RUB_PRICE_7,
    DEFAULT_RUB_PRICE_30,
    DEFAULT_STARS_PRICE_3,
    DEFAULT_STARS_PRICE_7,
    DEFAULT_STARS_PRICE_30,
    REFERRAL_BONUS_REQUESTS,
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
                        paywall_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

    def get_or_create_user(self, user_id: int, username: str | None = None) -> dict[str, Any]:
        user = self.get_user(user_id)
        if user:
            if username != user.get("username"):
                self.update_username(user_id, username)
                user["username"] = username
            self.refresh_subscription_status(user_id)
            return self.get_user(user_id)

        settings = self.get_settings()
        free_limit = settings.get("free_limit", DEFAULT_FREE_LIMIT)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, requests_left, is_premium, sub_until, is_vip, created_at, total_requests)
                VALUES (?, ?, ?, 0, NULL, 0, ?, 0)
                """,
                (user_id, username, free_limit, self._now_str()),
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

        sub_until = user.get("sub_until")
        is_vip = bool(user.get("is_vip"))
        if is_vip:
            return

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
                pass

    def has_access(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False

        self.refresh_subscription_status(user_id)
        user = self.get_user(user_id)
        return bool(user["is_vip"] or user["is_premium"] or user["requests_left"] > 0)

    def decrement_request_if_needed(self, user_id: int) -> bool:
        self.refresh_subscription_status(user_id)
        user = self.get_user(user_id)
        if not user:
            return False

        if user["is_vip"] or user["is_premium"]:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET total_requests = total_requests + 1 WHERE id = ?",
                    (user_id,),
                )
            return True

        if user["requests_left"] <= 0:
            return False

        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET requests_left = requests_left - 1, total_requests = total_requests + 1 WHERE id = ?",
                (user_id,),
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
                if current_dt > now:
                    new_until = current_dt + timedelta(days=days)
                else:
                    new_until = now + timedelta(days=days)
            except ValueError:
                new_until = now + timedelta(days=days)
        else:
            new_until = now + timedelta(days=days)

        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 1, sub_until = ? WHERE id = ?",
                (new_until.strftime("%Y-%m-%d %H:%M:%S"), user_id),
            )

    def revoke_subscription(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 0, sub_until = NULL WHERE id = ?",
                (user_id,),
            )

    def add_requests(self, user_id: int, amount: int) -> None:
        with self._connect() as conn:
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
            row = conn.execute(
                "SELECT * FROM payments WHERE external_id = ?",
                (external_id,),
            ).fetchone()
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

    def create_referral(self, referrer_id: int, invited_user_id: int, bonus_requests: int = REFERRAL_BONUS_REQUESTS) -> bool:
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
                """
                INSERT INTO referrals (referrer_id, invited_user_id, bonus_requests, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (referrer_id, invited_user_id, bonus_requests, self._now_str()),
            )
            conn.execute(
                "UPDATE users SET requests_left = requests_left + ? WHERE id = ?",
                (bonus_requests, referrer_id),
            )
        return True

    def get_referral_stats(self, user_id: int) -> dict[str, int]:
        with self._connect() as conn:
            invited_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM referrals WHERE referrer_id = ?",
                (user_id,),
            ).fetchone()["cnt"]
            total_bonus = conn.execute(
                "SELECT COALESCE(SUM(bonus_requests), 0) AS total FROM referrals WHERE referrer_id = ?",
                (user_id,),
            ).fetchone()["total"]
        return {"invited_count": int(invited_count), "total_bonus": int(total_bonus)}

    def get_referrer_id(self, invited_user_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT referrer_id FROM referrals WHERE invited_user_id = ?",
                (invited_user_id,),
            ).fetchone()
            return int(row["referrer_id"]) if row else None

    def export_user_profile_text(self, user_id: int) -> str:
        self.refresh_subscription_status(user_id)
        user = self.get_user(user_id)
        if not user:
            return "Пользователь не найден."

        sub_until = user["sub_until"] or "—"
        premium_text = "Да" if user["is_premium"] else "Нет"
        vip_text = "Да" if user["is_vip"] else "Нет"
        username = f"@{user['username']}" if user["username"] else "—"
        ref_stats = self.get_referral_stats(user_id)

        return (
            f"👤 <b>Профиль пользователя</b>\n\n"
            f"ID: <code>{user['id']}</code>\n"
            f"Username: {username}\n"
            f"Осталось запросов: <b>{user['requests_left']}</b>\n"
            f"Premium: <b>{premium_text}</b>\n"
            f"Подписка до: <b>{sub_until}</b>\n"
            f"VIP: <b>{vip_text}</b>\n"
            f"Всего запросов: <b>{user['total_requests']}</b>\n"
            f"Приглашено друзей: <b>{ref_stats['invited_count']}</b>\n"
            f"Реферальный бонус: <b>{ref_stats['total_bonus']}</b>"
        )
