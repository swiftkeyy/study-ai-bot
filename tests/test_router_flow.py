"""End-to-end router tests: admin router + user router through aiogram's dispatcher.

These lock down routing — in particular that the admin panel must not steal
ordinary user messages (it is registered first and matches every state).

aiogram routers are singletons in this project (module-level ``Router`` objects),
so the dispatcher is built once per module and every test uses its own user ids.
"""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import count
from types import SimpleNamespace

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Update

import admin
import bot as bot_module
from test_handlers import ADMIN_ID, RecordingBot

USER = 1001
ADMIN = ADMIN_ID


@pytest.fixture(scope="module")
def dp_flow():
    dp = Dispatcher()
    dp.include_router(admin.get_admin_router(None))
    dp.include_router(bot_module.router)
    return dp, RecordingBot()


@pytest.fixture()
def flow(db, dp_flow, monkeypatch):
    """Wire the production routers to a throwaway database and stub the AI."""
    dp, bot = dp_flow
    bot.sent.clear()

    monkeypatch.setattr(bot_module, "db", db)
    monkeypatch.setattr(admin, "_shared_db", db)

    calls: list[str] = []

    async def fake_ask_ai(prompt, system_prompt=None, provider_order=None):
        calls.append(prompt)
        return "Ответ от AI", "TestProvider"

    monkeypatch.setattr(bot_module, "ask_ai", fake_ask_ai)

    updates = count(1)

    async def send(text: str, user_id: int | None = None) -> None:
        target = USER if user_id is None else user_id
        update = Update.model_validate(
            {
                "update_id": next(updates),
                "message": {
                    "message_id": next(updates),
                    "date": datetime.now(timezone.utc).timestamp(),
                    "chat": {"id": target, "type": "private"},
                    "from": {"id": target, "is_bot": False, "first_name": "Test"},
                    "text": text,
                },
            },
            context={"bot": bot},
        )
        await dp.feed_update(bot, update)

    async def state_of(user_id: int) -> str | None:
        key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
        return await dp.fsm.storage.get_state(key=key)

    return SimpleNamespace(db=db, bot=bot, dp=dp, send=send, state_of=state_of, calls=calls)


@pytest.mark.asyncio
async def test_user_text_reaches_the_ai_even_with_admin_words_inside(flow):
    await flow.send("/start")
    await flow.send("Реши задачу: найди цены на нефть")

    assert flow.calls, "the AI provider must have been asked"
    assert "цены на нефть" in flow.calls[0]
    assert "Ответ от AI" in flow.bot.texts


@pytest.mark.asyncio
async def test_admin_button_opens_admin_section(flow):
    await flow.send("💰 Цены", user_id=ADMIN)
    state = await flow.state_of(ADMIN)
    assert state and state.endswith("set_price")
    assert "Формат: DAYS stars 100 или DAYS rub 199" in flow.bot.texts


@pytest.mark.asyncio
async def test_admin_task_message_is_not_treated_as_admin_command(flow):
    """An admin solving a task must not be thrown into the price-setting state."""
    await flow.send("/start", user_id=ADMIN)
    await flow.send("📚 Решить задачу", user_id=ADMIN)
    assert (await flow.state_of(ADMIN) or "").endswith("waiting_solve")

    await flow.send("Посчитай, сколько будут стоить цены на билеты", user_id=ADMIN)

    assert flow.calls
    assert (await flow.state_of(ADMIN) or "").endswith("waiting_solve")
    assert "Формат: DAYS" not in flow.bot.texts


@pytest.mark.asyncio
async def test_admin_feature_toggle_changes_user_keyboard(flow):
    await flow.send("/start", user_id=ADMIN)
    await flow.send("⚙️ Функции", user_id=ADMIN)
    assert (await flow.state_of(ADMIN) or "").endswith("feature_manage")

    await flow.send("off promocodes", user_id=ADMIN)
    assert flow.db.is_feature_enabled("promocodes", True) is False
    titles = [button.text for row in bot_module.main_menu_keyboard().keyboard for button in row]
    assert "🎁 Ввести промокод" not in titles


@pytest.mark.asyncio
async def test_free_limit_is_consumed_and_paywall_appears(flow):
    for index in range(3):
        await flow.send(f"вопрос {index}")
    assert flow.db.get_user(USER)["requests_left"] == 0

    await flow.send("вопрос 4")
    assert len(flow.calls) == 3
    assert "Бесплатный лимит закончился" in flow.bot.texts
    assert any("buy_stars_3" in repr(item.reply_markup) for item in flow.bot.sent)


@pytest.mark.asyncio
async def test_promo_code_via_menu(flow):
    flow.db.create_promo_code("STUDY", "requests", 2)
    await flow.send("🎁 Ввести промокод")
    assert (await flow.state_of(USER) or "").endswith("waiting_promo")

    await flow.send("study")
    assert flow.db.get_user(USER)["requests_left"] == 3 + 2
    assert await flow.state_of(USER) is None


@pytest.mark.asyncio
async def test_banned_user_is_blocked_everywhere(flow):
    flow.db.get_or_create_user(USER, "spam")
    flow.db.ban_user(USER, "реклама", ADMIN)

    await flow.send("привет")
    assert not flow.calls
    assert "Доступ к боту ограничен" in flow.bot.texts


@pytest.mark.asyncio
async def test_failed_ai_call_refunds_the_request(flow, monkeypatch):
    async def broken(prompt, system_prompt=None, provider_order=None):
        raise RuntimeError("все провайдеры лежат")

    monkeypatch.setattr(bot_module, "ask_ai", broken)

    await flow.send("вопрос")
    assert flow.db.get_user(USER)["requests_left"] == 3, "a failed request must not cost a quota point"
    assert "Не удалось получить ответ от AI" in flow.bot.texts


@pytest.mark.asyncio
async def test_menu_button_created_by_admin_reaches_users(flow):
    await flow.send("/start", user_id=ADMIN)
    await flow.send("🧩 Кнопки меню", user_id=ADMIN)
    await flow.send("add 🎯 Акция | text | Успей купить подписку", user_id=ADMIN)

    titles = [button.text for row in bot_module.main_menu_keyboard().keyboard for button in row]
    assert "🎯 Акция" in titles

    await flow.send("🎯 Акция")
    assert "Успей купить подписку" in flow.bot.texts
    assert not flow.calls  # a static button must not hit the AI


@pytest.mark.asyncio
async def test_start_shows_onboarding_and_referral_bonus(flow):
    flow.db.get_or_create_user(900, "referrer")
    await flow.send("/start ref_900")

    assert flow.db.get_referral_stats(900)["invited_count"] == 1
    assert "Добро пожаловать" in flow.bot.texts
    assert "Приглашение принято" in flow.bot.texts
