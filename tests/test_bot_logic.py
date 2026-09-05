from __future__ import annotations

import pytest

import bot


def test_split_long_text_never_returns_empty_or_oversized_chunks():
    text = "x" * 9000
    chunks = list(bot.split_long_text(text))
    assert chunks
    assert all(chunk.strip() for chunk in chunks)
    assert all(len(chunk) <= bot.SAFE_MESSAGE_LIMIT for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == text


def test_split_long_text_keeps_paragraphs_under_the_limit():
    text = "\n".join(f"строка {index} " + "y" * 40 for index in range(300))
    chunks = list(bot.split_long_text(text))
    assert all(len(chunk) <= bot.SAFE_MESSAGE_LIMIT for chunk in chunks)
    assert sum(chunk.count("строка") for chunk in chunks) == text.count("строка")


def test_split_long_text_passes_short_text_through():
    assert list(bot.split_long_text("привет\nмир")) == ["привет\nмир"]
    assert list(bot.split_long_text("")) == []


def test_split_long_text_breaks_words_only_when_needed():
    text = ("слово " * 1500).strip()
    chunks = list(bot.split_long_text(text, limit=500))
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert all(len(chunk) > 400 or index == len(chunks) - 1 for index, chunk in enumerate(chunks))


def test_ai_answer_is_wrapped_in_tags():
    text = "# Заголовок\n\n**Главное** и `код`\n\n```\nprint('a < b')\n```"
    html = bot.format_ai_text_for_telegram_html(text)
    assert "<b>Заголовок</b>" in html
    assert "<b>Главное</b>" in html
    assert "<code>код</code>" in html
    assert "<pre>print('a &lt; b')</pre>" in html


def test_html_special_characters_are_escaped():
    assert bot.format_ai_text_for_telegram_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_strip_html_fallback():
    assert bot.strip_html("<b>текст</b> и <code>x</code>") == "текст и x"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("/start", None),
        ("/start ref_42", 42),
        ("/start@StudyBot ref_42", 42),
        ("/start ref_42_extra", 42),
        ("/start promo_summer", None),
        ("/start ref_", None),
        ("/start ref_abc", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_referral_payload(text, expected):
    assert bot.parse_referral_payload(text) == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        ("buy_stars_3", 3),
        ("buy_robo_30", 30),
        ("buy_stars_5", None),
        ("buy_stars_", None),
        ("buy_stars_x", None),
        (None, None),
    ],
)
def test_parse_subscription_days(data, expected):
    assert bot.parse_subscription_days(data) == expected


def test_menu_button_texts_are_matched_exactly():
    normalized = {bot.normalize_menu_text(item) for item in bot.USER_MENU_BUTTONS}
    assert "📚 решить задачу" in normalized
    assert bot.normalize_menu_text("  📚\u00a0Решить\u00a0задачу  ") in normalized
    # a user message must not look like a menu button
    assert "📚 Решить задачу и объяснить тему" not in normalized


def test_referral_link_uses_configured_username(monkeypatch):
    monkeypatch.setattr(bot, "BOT_USERNAME", "")
    monkeypatch.setattr(bot, "_runtime_bot_username", None)
    assert bot.get_bot_username() == bot.DEFAULT_BOT_USERNAME
    bot.remember_bot_username("@RealStudyBot")
    assert bot.get_bot_username() == "RealStudyBot"
    monkeypatch.setattr(bot, "BOT_USERNAME", "configured_bot")
    assert bot.get_bot_username() == "configured_bot"


def test_simple_request_detection():
    assert bot.is_simple_request("2+2", "solve") is True
    assert bot.is_simple_request("x*3=12", "solve") is True
    assert bot.is_simple_request("Реши, пожалуйста, очень длинную задачу про движение двух поездов", "solve") is False
    assert bot.is_simple_request("придумай название", "text") is True
    assert bot.is_simple_request("напиши реферат по истории про петра первого на 10 страниц", "text") is False


def test_style_rules_keep_answers_short_for_simple_requests():
    simple = bot.build_style_rules("solve", "2+2")
    complex_ = bot.build_style_rules("solve", "докажи теорему пифагора для произвольного треугольника")
    assert "очень простая задача" in simple
    assert "очень простая задача" not in complex_
    assert "markdown" in simple


def test_main_keyboard_honours_feature_flags(db, monkeypatch):
    monkeypatch.setattr(bot, "db", db)
    db.add_menu_button("🎯 Акция", "show_text", "show_text", "Успей!")

    keyboard = bot.main_menu_keyboard()
    titles = [button.text for row in keyboard.keyboard for button in row]
    assert "🎁 Ввести промокод" in titles
    assert "🎯 Акция" in titles

    db.set_feature_enabled("promocodes", False)
    titles = [button.text for row in bot.main_menu_keyboard().keyboard for button in row]
    assert "🎁 Ввести промокод" not in titles
    assert "💬 Поддержка" in titles


def test_dynamic_button_titles_are_recognised(db, monkeypatch):
    monkeypatch.setattr(bot, "db", db)
    assert bot.is_dynamic_menu_button_text("🎯 Акция") is False
    db.add_menu_button("🎯 Акция", "show_text", "show_text", "Текст")
    assert bot.is_dynamic_menu_button_text("🎯 Акция") is True


def test_profile_text_reports_ban_and_subscription(db, monkeypatch):
    monkeypatch.setattr(bot, "db", db)
    db.get_or_create_user(301, "student")
    text = bot.get_profile_text(301)
    assert "301" in text and "@student" in text and "Бан: <b>Нет</b>" in text
    db.ban_user(301, "реклама", 1)
    assert "Бан: <b>Да</b>" in bot.get_profile_text(301)


def test_subscription_date_is_formatted_in_moscow_time():
    value = "2026-01-01T00:00:00"
    assert bot._format_subscription_until(value) == "01.01.2026 03:00"
    assert bot._format_subscription_until(None) == "—"
    assert bot._format_subscription_until("not-a-date") == "not-a-date"
