from __future__ import annotations

import admin


def test_admin_menu_matches_button_labels_exactly():
    assert admin.resolve_admin_menu_key("🔎 Найти пользователя") == "find_user"
    assert admin.resolve_admin_menu_key(" найти   пользователя ") == "find_user"
    assert admin.resolve_admin_menu_key("🛠 Тех.работы") == "maintenance"
    assert admin.resolve_admin_menu_key("⚙️ Функции") == "features"
    assert admin.resolve_admin_menu_key("🧩 Кнопки меню") == "menu"
    assert admin.resolve_admin_menu_key("🔙 В меню") == "to_menu"
    assert admin.resolve_admin_menu_key("Отмена") == "to_menu"


def test_admin_menu_does_not_swallow_user_messages():
    """The admin router runs for every state, so loose matching used to steal
    ordinary homework requests (substring "цены" inside a task text)."""
    for text in [
        "Реши задачу: найди цены на нефть",
        "объясни, что такое лимит всем",
        "напиши эссе про админов",
        "2+2",
        "Помоги с домашним заданием по математике",
    ]:
        assert admin._is_admin_menu_text(text) is False, text


def test_every_admin_button_is_routable():
    keyboard = admin.admin_keyboard()
    for row in keyboard.keyboard:
        for button in row:
            key = admin.resolve_admin_menu_key(button.text)
            assert key in admin.ADMIN_MENU_CODES, f"button {button.text!r} maps to {key!r}"


def test_user_menu_buttons_are_not_admin_sections():
    import bot

    for text in bot.USER_MENU_BUTTONS:
        assert admin.resolve_admin_menu_key(text) is None, text


def test_resolve_user_identifier_by_id_and_username(db):
    db.get_or_create_user(1234, "masha")
    assert admin._resolve_user_identifier(db, "1234")[0] == 1234
    assert admin._resolve_user_identifier(db, "@Masha")[0] == 1234
    user_id, _user, error = admin._resolve_user_identifier(db, "9999")
    assert user_id is None and "не найден" in error
    user_id, _user, error = admin._resolve_user_identifier(db, "")
    assert user_id is None and error


def test_numeric_parsers():
    assert admin._parse_positive_int("7") == 7
    assert admin._parse_positive_int("0") is None
    assert admin._parse_positive_int("-3") is None
    assert admin._parse_positive_int("abc") is None
    assert admin._parse_non_negative_int("0") == 0
    assert admin._parse_non_negative_int("-1") is None
    assert admin._parse_any_int("-5") == -5
    assert admin._parse_any_int(None) is None


def test_parse_promo_create():
    ok, error, payload = admin._parse_promo_create(["create", "SUMMER", "requests", "5", "uses", "100", "days", "3"])
    assert ok and error is None
    assert payload["code"] == "SUMMER"
    assert payload["reward_value"] == 5
    assert payload["max_activations"] == 100
    assert payload["expires_at"]

    ok, error, _payload = admin._parse_promo_create(["create", "X", "money", "5"])
    assert ok is False and "reward_type" in error

    ok, error, _payload = admin._parse_promo_create(["create", "X", "requests", "five"])
    assert ok is False

    ok, error, _payload = admin._parse_promo_create(["create", "X", "requests", "5", "hours"])
    assert ok is False and "hours" in error


def test_parse_menu_button_add():
    assert admin._parse_menu_button_add("Акция | text | Только до пятницы") == ("Акция", "show_text", "Только до пятницы")
    assert admin._parse_menu_button_add("Канал | url | https://t.me/x") == ("Канал", "open_url", "https://t.me/x")
    assert admin._parse_menu_button_add("Канал | https://t.me/x") == ("Канал", "open_url", "https://t.me/x")
    # "|" inside the value must be preserved
    assert admin._parse_menu_button_add("Кнопка | text | a | b")[2] == "a | b"
    assert admin._parse_menu_button_add("Кнопка | неизвестное | x") is None
    assert admin._parse_menu_button_add("| text | x") is None
    assert admin._parse_menu_button_add("Кнопка | text |") is None


def test_promo_render_shows_limits(db):
    db.create_promo_code("PROMO1", "requests", 3, max_activations=2)
    text = admin._render_promo_text(db)
    assert "PROMO1" in text
    assert "0/2" in text


def test_features_render_reflects_database(db):
    text = admin._render_features_text(db)
    assert "🎁 Промокоды" in text and "✅ включено" in text
    db.set_feature_enabled("promocodes", False)
    assert "🚫 выключено" in admin._render_features_text(db)


def test_ban_render_lists_real_bans(db):
    db.get_or_create_user(555, "spammer")
    db.ban_user(555, "спам", 1)
    assert "спам" in "\n".join(
        f"{item['id']} {item['ban_reason']}" for item in db.list_banned_users()
    )
