from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from db import Database


def test_get_or_create_user_applies_free_limit(db):
    user = db.get_or_create_user(10, "@Vasya")
    assert user["requests_left"] == 3
    assert user["username"] == "vasya"


def test_internal_calls_never_wipe_username(db):
    """Admin bonuses and payment activation pass username=None — it must not clear
    the stored username (regression test)."""
    db.get_or_create_user(11, "petia")
    db.activate_subscription(11, 3)
    db.add_user_requests(11, 2)
    db.set_user_requests(11, 7)
    db.get_or_create_user(11, None)
    assert db.get_user(11)["username"] == "petia"


def test_get_user_by_username_is_case_and_at_insensitive(db):
    db.get_or_create_user(12, "SuperUser")
    assert db.get_user_by_username("@superuser")["id"] == 12
    assert db.get_user_by_username("SUPERUSER")["id"] == 12
    assert db.get_user_by_username("") is None
    assert db.get_user_by_username("ghost") is None


def test_request_log_keeps_mode(db):
    db.get_or_create_user(13, None)
    db.add_request_log(13, "grade_guess", "Groq")
    with db._tx() as conn:
        row = conn.execute("SELECT * FROM request_logs").fetchone()
    assert dict(row)["mode"] == "grade_guess"
    assert dict(row)["provider"] == "Groq"
    assert db.requests_today() == 1


def test_legacy_database_gains_missing_columns(tmp_path):
    """A DB created by an older version is migrated instead of crashing on insert."""
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
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
            CREATE TABLE settings (
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
        conn.execute("INSERT INTO settings (id, free_limit, stars_price_3, stars_price_7, stars_price_30,"
                     " rub_price_3, rub_price_7, rub_price_30, help_text, paywall_text)"
                     " VALUES (1, 5, 1, 2, 3, 4, 5, 6, 'h', 'p')")
        conn.execute("CREATE TABLE request_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, provider TEXT)")

    legacy = Database(path)
    assert legacy.get_setting("free_limit") == 5
    legacy.log_request(77, "Mistral", "solve")
    assert legacy.get_user(77) is None  # log_request must not create users


@pytest.mark.parametrize(
    "external_id",
    ["INV-1", None],
)
def test_upsert_payment_stores_values_without_shifting(db, external_id):
    """The insert used to drop None values and misalign every placeholder."""
    payment_id = db.upsert_payment(
        user_id=21,
        amount=199.5,
        payment_type="robokassa",
        status="pending",
        external_id=external_id,
        days=7,
    )
    with db._tx() as conn:
        row = dict(conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone())

    assert row["user_id"] == 21
    assert row["amount"] == 199.5
    assert row["type"] == "robokassa"
    assert row["status"] == "pending"
    assert row["external_id"] == external_id
    assert row["days"] == 7
    assert row["created_at"]

    if external_id:
        again = db.upsert_payment(
            user_id=21,
            amount=199.5,
            payment_type="robokassa",
            status="succeeded",
            external_id=external_id,
            days=7,
        )
        assert again == payment_id
        assert db.get_payment_by_external_id(external_id)["status"] == "succeeded"
        with db._tx() as conn:
            assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1


def test_revenue_groups_stars_and_rubles(db):
    db.upsert_payment(31, 100.0, "stars", "succeeded", "tg-1", 3)
    db.upsert_payment(31, 199.0, "robokassa", "paid", "robo-1", 7)
    db.upsert_payment(31, 50.0, "robokassa", "pending", "robo-2", 7)
    revenue = db.total_revenue()
    assert revenue["stars"] == 100.0
    # a pending payment is not revenue yet
    assert revenue["rub"] == 199.0
    assert db.get_stats()["rub"] == 199.0


def test_subscription_lifecycle(db):
    db.get_or_create_user(41, None)
    assert db.has_access(41) is True  # free requests left

    db.set_user_requests(41, 0)
    assert db.has_access(41) is False
    assert db.decrement_request_if_needed(41) is False

    db.activate_subscription(41, 3)
    assert db.has_access(41) is True
    assert db.decrement_request_if_needed(41) is True
    # premium users are not charged
    assert db.get_user(41)["requests_left"] == 0
    # Premium users are not charged, so a refund must not add requests.
    before = db.get_user(41)["requests_left"]
    db.refund_request(41)
    assert db.get_user(41)["requests_left"] == before

    # expire the subscription manually and let the lazy refresh revoke it
    with db._tx() as conn:
        conn.execute(
            "UPDATE users SET sub_until = ? WHERE id = 41",
            ((datetime.utcnow() - timedelta(days=1)).isoformat(),),
        )
    db.refresh_subscription_status(41)
    assert db.get_user(41)["is_premium"] == 0
    assert db.get_user(41)["sub_until"] is None
    # back to the free quota: requests are consumed again
    db.set_user_requests(41, 2)
    assert db.decrement_request_if_needed(41) is True
    assert db.get_user(41)["requests_left"] == 1


def test_refund_returns_request_to_free_users(db):
    db.get_or_create_user(42, None)
    assert db.decrement_request_if_needed(42) is True
    assert db.get_user(42)["requests_left"] == 2
    db.refund_request(42)
    user = db.get_user(42)
    assert user["requests_left"] == 3
    assert user["total_requests"] == 0


def test_referral_bonus_is_granted_once(db):
    db.get_or_create_user(51, "referrer")
    db.get_or_create_user(52, "invited")
    assert db.register_referral(51, 52) is True
    assert db.get_user(51)["requests_left"] == 3 + 5
    assert db.get_referral_stats(51) == {"invited_count": 1, "bonus_total": 5}
    assert db.register_referral(51, 52) is False
    assert db.get_user(51)["requests_left"] == 8


def test_referral_rejects_self_and_unknown_referrer(db):
    db.get_or_create_user(53, None)
    assert db.register_referral(53, 53) is False
    assert db.register_referral(0, 53) is False
    assert db.register_referral(-1, 53) is False
    # a referrer without a profile is created on demand before the bonus lands
    assert db.register_referral(54, 53) is True
    assert db.get_user(54)["requests_left"] == 3 + 5


def test_promo_codes(db):
    db.get_or_create_user(61, None)
    db.get_or_create_user(62, None)
    db.create_promo_code("GIFT", "requests", 4, max_activations=1)

    assert db.activate_promo_code("gift", 61) == (True, "Промокод активирован. Тебе начислено 4 запросов.")
    assert db.get_user(61)["requests_left"] == 7
    ok, message = db.activate_promo_code("GIFT", 62)
    assert ok is False
    assert "Лимит активаций" in message

    db.create_promo_code("OLD", "requests", 9, expires_at=(datetime.utcnow() - timedelta(hours=1)).isoformat())
    ok, message = db.activate_promo_code("OLD", 62)
    assert ok is False and "истёк" in message

    db.create_promo_code("OFF", "requests", 9, is_active=False)
    assert db.activate_promo_code("OFF", 62)[0] is False

    db.create_promo_code("VIP", "vip", 1)
    assert db.activate_promo_code("VIP", 62)[0] is True
    assert db.get_user(62)["is_vip"] == 1
    assert db.has_access(62) is True


def test_ban_and_banned_list(db):
    db.get_or_create_user(71, "hacker")
    db.ban_user(71, "спам", 1)
    assert db.is_user_banned(71) is True
    assert db.get_user_ban_reason(71) == "спам"
    rows = db.list_banned_users()
    assert [row["id"] for row in rows] == [71]
    assert rows[0]["ban_reason"] == "спам"
    db.unban_user(71)
    assert db.list_banned_users() == []


def test_settings_validation_and_prices(db):
    with pytest.raises(ValueError):
        db.set_setting("help_text); DROP TABLE users --", "x")
    assert db.get_settings()["help_text"]

    db.set_price(3, stars=42)
    db.set_price(3, rub=111)
    prices = db.get_prices()
    assert prices["stars_3"] == 42
    assert prices["rub_3"] == 111
    db.set_price("stars_price_30", 300)
    assert db.get_prices()["stars_30"] == 300


def test_feature_flags(db):
    assert db.is_feature_enabled("referrals", True) is True
    db.set_feature_enabled("referrals", False)
    assert db.is_feature_enabled("referrals", True) is False
    assert db.get_all_features()["referrals"] is False


def test_maintenance_mode(db):
    assert db.is_maintenance_enabled() is False
    db.set_maintenance_mode(True, "Технические работы до 18:00")
    assert db.is_maintenance_enabled() is True
    assert db.get_maintenance_text() == "Технические работы до 18:00"
    db.set_maintenance_mode(False)
    assert db.is_maintenance_enabled() is False


def test_menu_buttons_crud(db):
    button_id = db.add_menu_button("Акция", "show_text", "show_text", "Только до пятницы")
    assert db.get_menu_button(button_id)["action_value"] == "Только до пятницы"
    assert [item["title"] for item in db.get_active_menu_buttons()] == ["Акция"]

    db.set_menu_button_active(button_id, False)
    assert db.get_active_menu_buttons() == []

    db.set_menu_button_sort(button_id, 5)
    assert db.get_menu_button(button_id)["sort_order"] == 5

    db.delete_menu_button(button_id)
    assert db.get_menu_button(button_id) is None


def test_menu_button_legacy_actions_are_normalized(db):
    db.add_menu_button("Старая", "show_text", "text", "текст")
    db.add_menu_button("Старая ссылка", "open_url", "url", "https://example.com")
    db.normalize_menu_button_actions()
    by_title = {item["title"]: item for item in db.list_menu_buttons()}
    assert by_title["Старая"]["action_type"] == "show_text"
    assert by_title["Старая ссылка"]["action_type"] == "open_url"


def test_support_tickets(db):
    db.get_or_create_user(81, "student")
    ticket_id = db.create_support_ticket(81, "Не открылась оплата")
    assert db.get_open_support_tickets(5)[0]["message"] == "Не открылась оплата"
    db.reply_support_ticket(ticket_id, "Проверь карту")
    ticket = db.get_support_ticket(ticket_id)
    assert ticket["status"] == "answered"
    assert ticket["admin_reply"] == "Проверь карту"
    db.close_support_ticket(ticket_id)
    assert db.get_open_support_tickets() == []


def test_admins(db):
    assert db.is_admin(1) is True  # ADMIN_ID from env
    db.add_admin(91, "moderator")
    assert db.is_admin(91) is True
    assert [item["user_id"] for item in db.list_admins()] == [1, 91]
    db.remove_admin(91)
    assert db.is_admin(91) is False


def test_export_csv(db):
    db.get_or_create_user(101, "alpha")
    db.get_or_create_user(102, "beta")
    db.activate_subscription(102, 3)
    csv_text = db.export_users_csv().decode("utf-8-sig")
    assert "alpha" in csv_text and "beta" in csv_text
    paid_only = db.export_users_csv(paid_only=True).decode("utf-8-sig")
    assert "beta" in paid_only and "alpha" not in paid_only
    assert db.get_paid_user_ids() == [102]
