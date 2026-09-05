"""Handler-level integration tests.

Real aiogram message objects and a real FSM context are used, while the Telegram
HTTP session is replaced with a recorder, so no network access is required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import Message

import admin
import bot as bot_module

ADMIN_ID = 1


class RecordingBot(Bot):
    """Bot stub: every Telegram method is recorded instead of being sent."""

    def __init__(self) -> None:
        super().__init__(token="123456:TEST-TOKEN")
        self.sent: list[SimpleNamespace] = []

    async def __call__(self, method, timeout=None):  # type: ignore[override]
        chat_id = getattr(method, "chat_id", None)
        text = getattr(method, "text", None)
        self.sent.append(
            SimpleNamespace(
                chat_id=chat_id,
                text=text,
                method=type(method).__name__,
                reply_markup=getattr(method, "reply_markup", None),
            )
        )
        if isinstance(method, SendMessage):
            # the reply must be mounted to this bot so follow-up calls
            # (edit/delete of the status message) work like in production
            return make_message(chat_id=int(chat_id), text=text or "", message_id=len(self.sent), bot=self)
        return True

    @property
    def texts(self) -> str:
        return "\n".join(item.text or "" for item in self.sent)


def make_message(chat_id: int, text: str | None, user_id: int = 1001, bot: Bot | None = None, message_id: int = 1) -> Message:
    message = Message.model_validate(
        {
            "message_id": message_id,
            "date": datetime.now(timezone.utc).timestamp(),
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "text": text,
        }
    )
    if bot is not None:
        message = message.as_(bot)
    return message


def make_state(bot: Bot, chat_id: int, user_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


@pytest.fixture()
def wired_dbs(db, monkeypatch):
    """Point both modules at the throwaway database."""
    monkeypatch.setattr(bot_module, "db", db)
    monkeypatch.setattr(admin, "_shared_db", db)
    return db


@pytest.fixture()
def fake_bot():
    # no session is ever opened: __call__ is short-circuited
    return RecordingBot()


@pytest.mark.asyncio
async def test_admin_can_add_custom_menu_button(wired_dbs, fake_bot):
    message = make_message(ADMIN_ID, "add 🎯 Акция | text | Только до пятницы", user_id=ADMIN_ID, bot=fake_bot)
    state = make_state(fake_bot, ADMIN_ID, ADMIN_ID)

    await admin.handle_menu_manage(message, state)

    buttons = wired_dbs.list_menu_buttons()
    assert len(buttons) == 1
    assert buttons[0]["title"] == "🎯 Акция"
    assert buttons[0]["action_type"] == "show_text"
    assert buttons[0]["action_value"] == "Только до пятницы"
    assert "Кнопка добавлена" in fake_bot.texts


@pytest.mark.asyncio
async def test_admin_menu_button_validation(wired_dbs, fake_bot):
    state = make_state(fake_bot, ADMIN_ID, ADMIN_ID)
    await admin.handle_menu_manage(make_message(ADMIN_ID, "add | text | без заголовка", user_id=ADMIN_ID, bot=fake_bot), state)
    await admin.handle_menu_manage(make_message(ADMIN_ID, "add Кнопка | url | t.me/x", user_id=ADMIN_ID, bot=fake_bot), state)
    assert wired_dbs.list_menu_buttons() == []
    assert "Формат" in fake_bot.texts or "http://" in fake_bot.texts


@pytest.mark.asyncio
async def test_admin_can_toggle_features(wired_dbs, fake_bot):
    state = make_state(fake_bot, ADMIN_ID, ADMIN_ID)
    await admin.handle_features_manage(make_message(ADMIN_ID, "off news", user_id=ADMIN_ID, bot=fake_bot), state)
    assert wired_dbs.is_feature_enabled("news", True) is False

    await admin.handle_features_manage(make_message(ADMIN_ID, "on news", user_id=ADMIN_ID, bot=fake_bot), state)
    assert wired_dbs.is_feature_enabled("news", True) is True

    await admin.handle_features_manage(make_message(ADMIN_ID, "off whatever", user_id=ADMIN_ID, bot=fake_bot), state)
    assert "Неизвестный ключ" in fake_bot.texts


@pytest.mark.asyncio
async def test_disabled_feature_disappears_from_user_menu(wired_dbs, fake_bot):
    wired_dbs.set_feature_enabled("support", False)
    titles = [button.text for row in bot_module.main_menu_keyboard().keyboard for button in row]
    assert "💬 Поддержка" not in titles
    wired_dbs.set_feature_enabled("support", True)
    titles = [button.text for row in bot_module.main_menu_keyboard().keyboard for button in row]
    assert "💬 Поддержка" in titles


@pytest.mark.asyncio
async def test_admin_section_opens_state_and_menu(wired_dbs, fake_bot):
    state = make_state(fake_bot, ADMIN_ID, ADMIN_ID)
    await admin._open_admin_section_normalized(make_message(ADMIN_ID, "🧩 Кнопки меню", user_id=ADMIN_ID, bot=fake_bot), state, "menu", wired_dbs)
    assert (await state.get_state() or "").endswith("menu_manage")
    assert "Кнопки меню" in fake_bot.texts


@pytest.mark.asyncio
async def test_broadcast_requires_text(wired_dbs, fake_bot):
    state = make_state(fake_bot, ADMIN_ID, ADMIN_ID)
    await state.set_state(admin.AdminStates.broadcast_all)
    await admin.handle_broadcast_all(make_message(ADMIN_ID, None, user_id=ADMIN_ID, bot=fake_bot), state)
    assert "Пустое сообщение" in fake_bot.texts


@pytest.mark.asyncio
async def test_bonus_validation(wired_dbs, fake_bot):
    wired_dbs.get_or_create_user(2002, "user2002")
    state = make_state(fake_bot, ADMIN_ID, ADMIN_ID)

    await admin.handle_grant_sub(make_message(ADMIN_ID, "2002 abc", user_id=ADMIN_ID, bot=fake_bot), state)
    assert "положительным числом" in fake_bot.texts

    await admin.handle_grant_sub(make_message(ADMIN_ID, "2002 -5", user_id=ADMIN_ID, bot=fake_bot), state)
    assert wired_dbs.get_user(2002)["is_premium"] == 0

    await admin.handle_grant_sub(make_message(ADMIN_ID, "2002 4", user_id=ADMIN_ID, bot=fake_bot), state)
    assert wired_dbs.get_user(2002)["is_premium"] == 1


@pytest.mark.asyncio
async def test_user_menu_button_opens_mode_state(wired_dbs, fake_bot):
    state = make_state(fake_bot, 1001, 1001)
    wired_dbs.get_or_create_user(1001, "student")

    await bot_module.user_state_switch(make_message(1001, "📚 Решить задачу", user_id=1001, bot=fake_bot), state)
    assert (await state.get_state() or "").endswith("waiting_solve")
    assert "Режим решения задач" in fake_bot.texts
    # profile was created with the free limit
    assert wired_dbs.get_user(1001)["requests_left"] == 3


@pytest.mark.asyncio
async def test_start_with_referral_registers_bonus(wired_dbs, fake_bot):
    wired_dbs.get_or_create_user(500, "referrer")
    state = make_state(fake_bot, 600, 600)

    await bot_module.cmd_start(make_message(600, "/start ref_500", user_id=600, bot=fake_bot), state)

    assert wired_dbs.get_referral_stats(500)["invited_count"] == 1
    assert wired_dbs.get_user(500)["requests_left"] == 3 + 5
    assert wired_dbs.get_user(600)["referred_by"] == 500
    assert "Приглашение принято" in fake_bot.texts
    assert "Добро пожаловать" in fake_bot.texts


@pytest.mark.asyncio
async def test_start_referral_is_not_awarded_twice(wired_dbs, fake_bot):
    wired_dbs.get_or_create_user(501, "referrer")
    wired_dbs.get_or_create_user(601, "early")
    wired_dbs.register_referral(501, 601)
    before = wired_dbs.get_user(501)["requests_left"]

    # an existing user opening the same link must not pay the referrer again
    await bot_module.cmd_start(make_message(601, "/start ref_501", user_id=601, bot=fake_bot), make_state(fake_bot, 601, 601))
    assert wired_dbs.get_user(501)["requests_left"] == before


@pytest.mark.asyncio
async def test_unknown_command_gets_a_hint(wired_dbs, fake_bot):
    await bot_module.generic_text_message(make_message(1001, "/frob", user_id=1001, bot=fake_bot))
    assert "Такой команды нет" in fake_bot.texts


@pytest.mark.asyncio
async def test_non_text_message_gets_explanation(wired_dbs, fake_bot):
    wired_dbs.get_or_create_user(1001, "student")
    message = make_message(1001, None, user_id=1001, bot=fake_bot)
    message = message.model_copy(update={"document": SimpleNamespace(file_id="x", file_unique_id="x", file_size=1)})

    await bot_module.unsupported_content_message(message)
    assert "Я понимаю текст и фото" in fake_bot.texts


@pytest.mark.asyncio
async def test_referral_text_uses_username_from_get_me(wired_dbs, fake_bot, monkeypatch):
    monkeypatch.setattr(bot_module, "BOT_USERNAME", "")
    monkeypatch.setattr(bot_module, "_runtime_bot_username", None)
    wired_dbs.get_or_create_user(700, "lucky")

    monkeypatch.setattr(bot_module, "DEFAULT_BOT_USERNAME", "fallback_bot")
    assert "t.me/fallback_bot?start=ref_700" in bot_module.build_referral_text(700)

    monkeypatch.setattr(bot_module, "_runtime_bot_username", "real_study_bot")
    assert "t.me/real_study_bot?start=ref_700" in bot_module.build_referral_text(700)
