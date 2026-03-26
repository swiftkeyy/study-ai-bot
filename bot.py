from __future__ import annotations

import asyncio
import html
import logging
from io import BytesIO
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ContentType, ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Document,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)

from admin import get_admin_router
from ai import ask_ai, ask_ai_with_image
from config import (
    BOT_TOKEN,
    DEFAULT_HELP_TEXT,
    DEFAULT_NEWS_CHANNEL_URL,
    DEFAULT_PAYWALL_TEXT,
    DEFAULT_REQUIRED_SUBSCRIPTION_TEXT,
    LOG_FILE,
    LOG_LEVEL,
    validate_config,
)
from db import Database
from image_ai import generate_image
from payments import create_yookassa_payment, start_webhook_server

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


db = Database()
router = Router()


class UserStates(StatesGroup):
    waiting_solve = State()
    waiting_text = State()
    waiting_promo = State()
    waiting_support = State()
    waiting_image = State()


USER_EXIT_TEXTS = {"🔙 В меню", "↩ В меню", "❌ Отмена", "Отмена", "Назад"}
USER_MENU_BUTTONS = {
    "📚 Решить задачу",
    "✍️ Написать текст",
    "🖼 Создать изображение",
    "👤 Личный кабинет",
    "💎 Купить доступ",
    "🎁 Ввести промокод",
    "📣 Новости",
    "💬 Поддержка",
    "👥 Реферальная программа",
    "🎓 Полезные материалы",
    "❓ Помощь",
}


MATERIALS: dict[str, str] = {
    "essay": "🎓 <b>Как писать эссе</b>\n\n1. Определи тему.\n2. Сформулируй тезис.\n3. Дай 2–3 аргумента.\n4. Сделай вывод.\n\nШаблон:\nВступление → Тезис → Аргумент 1 → Аргумент 2 → Вывод.",
    "ref": "📘 <b>Как писать реферат</b>\n\nСтруктура:\n• Титульный лист\n• Содержание\n• Введение\n• Основная часть\n• Заключение\n• Список источников\n\nСовет: сначала сделай план, потом раскрывай каждый пункт отдельно.",
    "conspect": "📝 <b>Как делать конспект</b>\n\n1. Выделяй только главное.\n2. Пиши короткими фразами.\n3. Используй списки и подзаголовки.\n4. Делай определения отдельно.\n5. В конце — мини-вывод.",
    "exam": "📚 <b>Подготовка к экзаменам</b>\n\n• Делай план по дням\n• Повторяй темы блоками\n• Решай типовые задания\n• Проси ИИ объяснять сложные места простыми словами\n• Используй интервальное повторение",
    "prompts": "🤖 <b>Полезные промпты для учёбы</b>\n\n• Объясни простыми словами\n• Реши пошагово\n• Сделай краткий конспект\n• Приведи пример\n• Проверь ошибки\n• Сравни два понятия\n• Составь план ответа",
    "math": "➗ <b>Советы по математике</b>\n\n• Сначала выпиши условие\n• Отдельно запиши, что нужно найти\n• Решай по шагам\n• Проверяй подстановкой\n• Если не понял, проси ИИ объяснить как учитель",
    "russian": "🖊 <b>Советы по русскому языку</b>\n\n• Разбирай предложение по частям\n• Проверяй орфограммы\n• Пиши план сочинения заранее\n• Используй черновой вариант и проси ИИ проверить ошибки",
    "history": "🏛 <b>История и обществознание</b>\n\n• Учи не только даты, но и причины/следствия\n• Делай таблицы: событие → причины → ход → итоги\n• Проси ИИ сравнивать эпохи и реформы",
}


def is_cancel_text(text: str) -> bool:
    return text.strip() in USER_EXIT_TEXTS


def back_to_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 В меню")]],
        resize_keyboard=True,
    )


def get_materials_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Как писать эссе", callback_data="mat_essay")],
            [InlineKeyboardButton(text="Как писать реферат", callback_data="mat_ref")],
            [InlineKeyboardButton(text="Как делать конспект", callback_data="mat_conspect")],
            [InlineKeyboardButton(text="Подготовка к экзаменам", callback_data="mat_exam")],
            [InlineKeyboardButton(text="Полезные промпты", callback_data="mat_prompts")],
            [InlineKeyboardButton(text="Советы по математике", callback_data="mat_math")],
            [InlineKeyboardButton(text="Советы по русскому", callback_data="mat_russian")],
            [InlineKeyboardButton(text="История и обществознание", callback_data="mat_history")],
        ]
    )


def get_material_text(key: str) -> str:
    return MATERIALS.get(key, "Материал не найден.")


def split_long_text(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = []
    current_len = 0
    for part in text.split("\n"):
        add_len = len(part) + 1
        if current_len + add_len > limit and current:
            chunks.append("\n".join(current))
            current = [part]
            current_len = add_len
        else:
            current.append(part)
            current_len += add_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📚 Решить задачу"), KeyboardButton(text="✍️ Написать текст")],
    ]
    if db.is_feature_enabled("image_generation", False):
        rows.append([KeyboardButton(text="🖼 Создать изображение")])
    rows.extend(
        [
            [KeyboardButton(text="👤 Личный кабинет"), KeyboardButton(text="💎 Купить доступ")],
            [KeyboardButton(text="🎁 Ввести промокод"), KeyboardButton(text="📣 Новости")],
            [KeyboardButton(text="💬 Поддержка"), KeyboardButton(text="👥 Реферальная программа")],
            [KeyboardButton(text="🎓 Полезные материалы")],
            [KeyboardButton(text="❓ Помощь")],
        ]
    )

    for button in db.list_menu_buttons():
        if button.get("is_active"):
            rows.append([KeyboardButton(text=button["title"])])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def build_profile_text(user_id: int) -> str:
    user = db.get_or_create_user(user_id, None)
    stats = db.get_referral_stats(user_id)
    premium_text = "Да" if user.get("is_premium") else "Нет"
    vip_text = "Да" if user.get("is_vip") else "Нет"
    sub_until = user.get("sub_until") or "—"
    username = user.get("username") or "—"
    images_left = user.get("images_left", 0)
    return (
        "👤 <b>Личный кабинет</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Username: @{username if username != '—' else '—'}\n"
        f"Запросов осталось: <b>{user.get('requests_left', 0)}</b>\n"
        f"Генераций изображений осталось: <b>{images_left}</b>\n"
        f"Premium: <b>{premium_text}</b>\n"
        f"VIP: <b>{vip_text}</b>\n"
        f"Подписка до: <b>{sub_until}</b>\n"
        f"Приглашено друзей: <b>{stats['invited_count']}</b>\n"
        f"Бонусных запросов получено: <b>{stats['bonus_total']}</b>"
    )


def build_referral_text(user_id: int) -> str:
    stats = db.get_referral_stats(user_id)
    bot_username = "studyai_rubot"
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return (
        "👥 <b>Реферальная программа</b>\n\n"
        "Приглашай друзей и получай <b>5 бонусных запросов</b> за каждого нового пользователя.\n\n"
        f"Твоя ссылка:\n<code>{link}</code>\n\n"
        f"Приглашено: <b>{stats['invited_count']}</b>\n"
        f"Бонусов получено: <b>{stats['bonus_total']}</b>"
    )


def get_onboarding_text(user: dict) -> str:
    free_left = user.get("requests_left", 0)
    return (
        "👋 <b>Добро пожаловать в Study AI Bot</b>\n\n"
        "Я помогу тебе с учёбой:\n"
        "• решу задачу\n"
        "• напишу текст\n"
        "• решу задачу по фото\n"
        "• создам изображение\n\n"
        f"Сейчас у тебя <b>{free_left}</b> бесплатных текстовых запросов."
    )


async def fetch_telegram_file(bot: Bot, file_id: str) -> tuple[bytes, str]:
    file = await bot.get_file(file_id)
    downloaded = await bot.download_file(file.file_path)
    data = downloaded.read()
    lower = (file.file_path or "").lower()
    if lower.endswith(".png"):
        mime = "image/png"
    elif lower.endswith(".webp"):
        mime = "image/webp"
    else:
        mime = "image/jpeg"
    return data, mime


async def has_required_subscription(bot: Bot, user_id: int) -> bool:
    cfg = db.get_required_channel()
    if not cfg["enabled"]:
        return True
    channel_ref = cfg.get("channel_username") or cfg.get("channel_id")
    if not channel_ref:
        return True
    try:
        member = await bot.get_chat_member(channel_ref, user_id)
        return member.status in {"member", "administrator", "creator"}
    except Exception:
        logger.exception("Subscription check failed for user %s", user_id)
        return False


def required_subscription_keyboard() -> InlineKeyboardMarkup:
    cfg = db.get_required_channel()
    channel_username = cfg.get("channel_username")
    url = f"https://t.me/{channel_username.lstrip('@')}" if channel_username else "https://t.me/ai_helper_study"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться", url=url)],
            [InlineKeyboardButton(text="Проверить подписку", callback_data="check_required_subscription")],
        ]
    )


async def deny_if_blocked_message(message: Message) -> bool:
    user_id = message.from_user.id
    if db.is_admin(user_id):
        return False

    if db.is_user_banned(user_id):
        reason = db.get_user_ban_reason(user_id) or "Причина не указана."
        await message.answer(f"⛔ Ты заблокирован.\n\nПричина: {html.escape(reason)}")
        return True

    if db.is_maintenance_enabled():
        await message.answer(db.get_maintenance_text())
        return True

    cfg = db.get_required_channel()
    if cfg["enabled"]:
        subscribed = await has_required_subscription(message.bot, user_id)
        if not subscribed:
            await message.answer(cfg["text"], reply_markup=required_subscription_keyboard())
            return True

    return False


async def check_access_block(message: Message) -> Optional[tuple[str, Optional[InlineKeyboardMarkup]]]:
    user_id = message.from_user.id
    if db.is_admin(user_id):
        return None

    if db.is_user_banned(user_id):
        reason = db.get_user_ban_reason(user_id) or "Причина не указана."
        return (f"⛔ Ты заблокирован.\n\nПричина: {html.escape(reason)}", None)

    if db.is_maintenance_enabled():
        return (db.get_maintenance_text(), None)

    cfg = db.get_required_channel()
    if cfg["enabled"]:
        subscribed = await has_required_subscription(message.bot, user_id)
        if not subscribed:
            return (cfg["text"], required_subscription_keyboard())

    return None


async def ensure_text_access(message: Message) -> bool:
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    if user.get("is_premium") or user.get("is_vip"):
        return True
    if int(user.get("requests_left") or 0) > 0:
        return True
    await message.answer(DEFAULT_PAYWALL_TEXT, reply_markup=main_menu_keyboard())
    return False


async def process_ai_request(message: Message, mode: str):
    block = await check_access_block(message)
    if block:
        await message.answer(block[0], reply_markup=block[1])
        return
    if not await ensure_text_access(message):
        return

    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    text = (message.text or "").strip()

    if mode == "solve":
        prompt = f"Реши учебную задачу пошагово и дай итоговый ответ:\n\n{text}"
        system_prompt = "Ты AI-репетитор. Объясняй решение простыми шагами и не пропускай важные переходы."
        title = "📚 <b>Решение задачи</b>"
    elif mode == "text":
        prompt = f"Напиши учебный текст по запросу:\n\n{text}"
        system_prompt = "Ты учебный AI-помощник. Пиши грамотно, структурированно и понятно."
        title = "✍️ <b>Готовый текст</b>"
    else:
        prompt = text
        system_prompt = db.get_ai_settings().get("system_prompt") or "Ты полезный AI-помощник для учёбы."
        title = "🤖 <b>Ответ</b>"

    ai_settings = db.get_ai_settings()
    provider_order = [
        ai_settings.get("provider") or "gemini",
        ai_settings.get("fallback_1") or "groq",
        ai_settings.get("fallback_2") or "openrouter",
    ]
    # убираем дубли и off
    clean_order = []
    for p in provider_order:
        if not p or p == "off":
            continue
        if p not in clean_order:
            clean_order.append(p)

    thinking = await message.answer("⏳ Думаю...")
    try:
        answer, provider = await ask_ai(prompt, system_prompt=system_prompt, provider_order=clean_order)
        if not user.get("is_premium") and not user.get("is_vip"):
            db.update_user_requests(message.from_user.id, max(0, int(user.get("requests_left") or 0) - 1))
        db.increment_total_requests(message.from_user.id)
        db.log_request(message.from_user.id, provider)
        await thinking.delete()
        for chunk in split_long_text(f"{title} <i>({provider})</i>\n\n{answer}"):
            await message.answer(chunk, reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.exception("AI request failed: %s", e)
        await thinking.edit_text("⚠️ Не удалось получить ответ от AI. Проверь API-ключи и попробуй ещё раз.")


@router.message(StateFilter("*"), F.text.in_(USER_MENU_BUTTONS | USER_EXIT_TEXTS))
async def user_state_switch(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if is_cancel_text(text):
        await state.clear()
        await message.answer("Возвращаю в меню.", reply_markup=main_menu_keyboard())
        return
    if text == "📚 Решить задачу":
        await solve_entry(message, state)
    elif text == "✍️ Написать текст":
        await text_entry(message, state)
    elif text == "🖼 Создать изображение":
        await image_generation_entry(message, state)
    elif text == "👤 Личный кабинет":
        await state.clear()
        await message.answer(build_profile_text(message.from_user.id), reply_markup=main_menu_keyboard())
    elif text == "💎 Купить доступ":
        await state.clear()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⭐ 3 дня", callback_data="buy_stars_3")],
                [InlineKeyboardButton(text="⭐ 7 дней", callback_data="buy_stars_7")],
                [InlineKeyboardButton(text="⭐ 30 дней", callback_data="buy_stars_30")],
            ]
        )
        await message.answer("💎 <b>Купить доступ</b>\n\nВыбери тариф:", reply_markup=kb)
    elif text == "🎁 Ввести промокод":
        await promo_code_entry(message, state)
    elif text == "📣 Новости":
        await news_section(message, state)
    elif text == "💬 Поддержка":
        await support_entry(message, state)
    elif text == "👥 Реферальная программа":
        await referral_section(message, state)
    elif text == "🎓 Полезные материалы":
        await materials_section(message, state)
    elif text == "❓ Помощь":
        await state.clear()
        await message.answer(DEFAULT_HELP_TEXT, reply_markup=main_menu_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    if await deny_if_blocked_message(message):
        return
    await message.answer(get_onboarding_text(user), reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "check_required_subscription")
async def check_required_subscription(callback: CallbackQuery):
    if db.is_admin(callback.from_user.id):
        await callback.answer("Ты админ, ограничения не применяются.", show_alert=True)
        return

    subscribed = await has_required_subscription(callback.bot, callback.from_user.id)
    if subscribed:
        await callback.answer("Подписка подтверждена ✅", show_alert=True)
        await callback.message.answer(
            "✅ <b>Подписка подтверждена</b>\n\nТеперь можешь пользоваться ботом.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await callback.answer("Подписка не найдена ❌", show_alert=True)


@router.callback_query(F.data.startswith("buy_stars_"))
async def buy_stars(callback: CallbackQuery):
    days = int(callback.data.split("_")[-1])
    prices = db.get_prices()
    amount = prices[f"stars_{days}"]
    await callback.message.answer_invoice(
        title=f"Подписка на {days} дней",
        description=f"Доступ к боту на {days} дней",
        payload=f"stars:{days}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{days} дней", amount=amount)],
        provider_token="",
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("stars:"):
        days = int(payload.split(":", 1)[1])
        amount = message.successful_payment.total_amount
        external_id = message.successful_payment.telegram_payment_charge_id
        db.create_payment(message.from_user.id, amount, "stars", "paid", external_id, days)
        db.activate_subscription(message.from_user.id, days)
        await message.answer(
            f"✅ Оплата прошла успешно. Подписка на {days} дней активирована!",
            reply_markup=main_menu_keyboard(),
        )


@router.message(F.text == "🎁 Ввести промокод")
async def promo_code_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserStates.waiting_promo)
    await message.answer(
        "🎁 <b>Промокод</b>\n\nОтправь промокод одним сообщением.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(UserStates.waiting_promo, F.text)
async def promo_code_input(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if is_cancel_text(text):
        await state.clear()
        await message.answer("Возвращаю в меню.", reply_markup=main_menu_keyboard())
        return

    ok, result_text, _promo = db.activate_promo(message.from_user.id, text)
    await state.clear()
    if ok:
        await message.answer(f"✅ {result_text}", reply_markup=main_menu_keyboard())
    else:
        await message.answer(f"⚠️ {result_text}", reply_markup=main_menu_keyboard())


@router.message(F.text == "📣 Новости")
async def news_section(message: Message, state: FSMContext):
    await state.clear()
    news_url = db.get_setting("news_channel_url", DEFAULT_NEWS_CHANNEL_URL)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Перейти в канал", url=news_url)]]
    )
    await message.answer(
        "📣 <b>Новости</b>\n\nПодписывайся на канал, там обновления бота, полезные материалы и анонсы.",
        reply_markup=kb,
    )


@router.message(F.text == "💬 Поддержка")
async def support_entry(message: Message, state: FSMContext):
    await state.clear()
    if not db.is_feature_enabled("support", True):
        await message.answer("⚠️ Поддержка сейчас временно отключена.", reply_markup=main_menu_keyboard())
        return
    await state.set_state(UserStates.waiting_support)
    support_text = db.get_setting("support_text", DEFAULT_NEWS_CHANNEL_URL)
    await message.answer(support_text, reply_markup=back_to_menu_keyboard())


@router.message(UserStates.waiting_support, F.text)
async def support_input(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if is_cancel_text(text):
        await state.clear()
        await message.answer("Возвращаю в меню.", reply_markup=main_menu_keyboard())
        return

    ticket_id = db.create_support_ticket(message.from_user.id, text)
    admins = db.list_admins()
    username = f"@{message.from_user.username}" if message.from_user.username else "без username"
    admin_text = (
        f"📨 <b>Новая заявка в поддержку</b>\n\n"
        f"Ticket ID: <b>{ticket_id}</b>\n"
        f"User ID: <code>{message.from_user.id}</code>\n"
        f"Username: {username}\n\n"
        f"{html.escape(text)}"
    )
    for admin_row in admins:
        try:
            await message.bot.send_message(admin_row["user_id"], admin_text)
        except Exception:
            logger.exception("Failed to send support ticket to admin %s", admin_row["user_id"])

    await state.clear()
    await message.answer(
        "✅ Сообщение отправлено в поддержку. Администратор ответит тебе через бота.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == "👥 Реферальная программа")
async def referral_section(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(build_referral_text(message.from_user.id), reply_markup=main_menu_keyboard())


@router.message(F.text == "🎓 Полезные материалы")
async def materials_section(message: Message, state: FSMContext):
    await state.clear()
    if not db.is_feature_enabled("materials", True):
        await message.answer("⚠️ Раздел материалов сейчас временно отключён.", reply_markup=main_menu_keyboard())
        return
    await message.answer(
        "🎓 <b>Полезные материалы</b>\n\nВыбери раздел:",
        reply_markup=get_materials_keyboard(),
    )


@router.callback_query(F.data.startswith("mat_"))
async def material_callback(callback: CallbackQuery):
    key = callback.data.split("_", 1)[1]
    await callback.answer()
    await callback.message.answer(get_material_text(key), reply_markup=main_menu_keyboard())


@router.message(F.text == "🖼 Создать изображение")
async def image_generation_entry(message: Message, state: FSMContext):
    await state.clear()
    if not db.is_feature_enabled("image_generation", False):
        await message.answer("⚠️ Генерация изображений сейчас выключена.", reply_markup=main_menu_keyboard())
        return

    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    if not user.get("is_premium") and int(user.get("images_left") or 0) <= 0:
        await message.answer(
            "⚠️ Лимит генераций изображений закончился. Купи доступ или дождись пополнения лимита.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(UserStates.waiting_image)
    await message.answer(
        "🖼 <b>Создание изображения</b>\n\nНапиши, что ты хочешь нарисовать.\n\n"
        "Пример: <i>Нарисуй собаку в мультяшном стиле</i>",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(UserStates.waiting_image, F.text)
async def image_generation_input(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if is_cancel_text(text):
        await state.clear()
        await message.answer("Возвращаю в меню.", reply_markup=main_menu_keyboard())
        return

    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    if not user.get("is_premium") and int(user.get("images_left") or 0) <= 0:
        await state.clear()
        await message.answer("⚠️ Лимит генераций изображений закончился.", reply_markup=main_menu_keyboard())
        return

    status_message = await message.answer("⏳ Создаю изображение...")
    try:
        image_url, provider = await generate_image(text)
        if not user.get("is_premium"):
            db.update_user_images(message.from_user.id, max(0, int(user.get("images_left") or 0) - 1))
        db.log_image_generation(message.from_user.id, text, image_url, provider)
        await state.clear()
        await status_message.delete()
        await message.answer_photo(
            photo=image_url,
            caption=f"🖼 <b>Изображение готово</b> <i>({provider})</i>",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        logger.exception("Image generation failed: %s", e)
        await state.clear()
        await status_message.edit_text("⚠️ Не удалось создать изображение.\nПроверь ключ DeepAI и попробуй ещё раз.")


@router.message(F.text == "📚 Решить задачу")
async def solve_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserStates.waiting_solve)
    await message.answer(
        "📚 <b>Решить задачу</b>\n\nОтправь текст задачи или фото задания.\n\nЯ постараюсь решить её пошагово.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(F.text == "✍️ Написать текст")
async def text_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserStates.waiting_text)
    await message.answer(
        "✍️ <b>Написать текст</b>\n\nНапиши тему или задание.\n\nНапример:\n• Напиши эссе на тему экологии\n• Составь план реферата по истории",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(UserStates.waiting_solve, F.photo)
async def solve_photo(message: Message, state: FSMContext):
    block = await check_access_block(message)
    if block:
        await message.answer(block[0], reply_markup=block[1])
        return
    if not await ensure_text_access(message):
        return
    photo = message.photo[-1]
    status_message = await message.answer("⏳ Считываю условие и решаю задачу...")
    try:
        image_bytes, mime = await fetch_telegram_file(message.bot, photo.file_id)
        prompt = (
            "На изображении учебная задача. Сначала кратко перепиши условие, затем реши задачу пошагово и в конце дай итоговый ответ."
        )
        system_prompt = (
            "Ты AI-репетитор. Аккуратно анализируй фото задания, не выдумывай лишнего и объясняй решение пошагово."
        )
        answer, provider = await ask_ai_with_image(
            prompt=prompt,
            image_bytes=image_bytes,
            mime_type=mime,
            system_prompt=system_prompt,
        )
        if not db.is_admin(message.from_user.id):
            user = db.get_or_create_user(message.from_user.id, message.from_user.username)
            if not user.get("is_premium") and not user.get("is_vip"):
                db.update_user_requests(message.from_user.id, max(0, int(user.get("requests_left") or 0) - 1))
        db.log_request(message.from_user.id, provider)
        db.increment_total_requests(message.from_user.id)
        db.add_media_request(message.from_user.id, "photo", photo.file_id, "", answer)
        await state.clear()
        await status_message.delete()
        for chunk in split_long_text(f"📚 <b>Решение по фото</b> <i>({provider})</i>\n\n{answer}"):
            await message.answer(chunk, reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.exception("Solve by photo failed: %s", e)
        await state.clear()
        await status_message.edit_text("⚠️ Не удалось решить задачу по фото. Попробуй ещё раз или отправь условие текстом.")


@router.message(UserStates.waiting_solve, F.document)
async def solve_document_image(message: Message, state: FSMContext):
    doc = message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await message.answer("Отправь изображение документом или обычное фото.")
        return
    block = await check_access_block(message)
    if block:
        await message.answer(block[0], reply_markup=block[1])
        return
    if not await ensure_text_access(message):
        return
    status_message = await message.answer("⏳ Считываю изображение и решаю задачу...")
    try:
        image_bytes, mime = await fetch_telegram_file(message.bot, doc.file_id)
        prompt = (
            "На изображении учебная задача. Сначала кратко перепиши условие, затем реши задачу пошагово и в конце дай итоговый ответ."
        )
        system_prompt = (
            "Ты AI-репетитор. Аккуратно анализируй изображение задания, не выдумывай лишнего и объясняй решение пошагово."
        )
        answer, provider = await ask_ai_with_image(
            prompt=prompt,
            image_bytes=image_bytes,
            mime_type=mime or doc.mime_type,
            system_prompt=system_prompt,
        )
        if not db.is_admin(message.from_user.id):
            user = db.get_or_create_user(message.from_user.id, message.from_user.username)
            if not user.get("is_premium") and not user.get("is_vip"):
                db.update_user_requests(message.from_user.id, max(0, int(user.get("requests_left") or 0) - 1))
        db.log_request(message.from_user.id, provider)
        db.increment_total_requests(message.from_user.id)
        db.add_media_request(message.from_user.id, "document_image", doc.file_id, "", answer)
        await state.clear()
        await status_message.delete()
        for chunk in split_long_text(f"📚 <b>Решение по фото</b> <i>({provider})</i>\n\n{answer}"):
            await message.answer(chunk, reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.exception("Solve document image failed: %s", e)
        await state.clear()
        await status_message.edit_text("⚠️ Не удалось решить задачу по изображению. Попробуй ещё раз или отправь условие текстом.")


@router.message(UserStates.waiting_solve, F.text)
async def solve_text(message: Message, state: FSMContext):
    await process_ai_request(message, "solve")


@router.message(UserStates.waiting_text, F.text)
async def text_mode(message: Message, state: FSMContext):
    await process_ai_request(message, "text")


@router.message(F.photo)
async def generic_photo_hint(message: Message, state: FSMContext):
    await message.answer(
        "📷 Я получил изображение.\n\nЧтобы решить задачу по фото, сначала нажми <b>📚 Решить задачу</b>, а потом отправь фото.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.document)
async def generic_document_hint(message: Message, state: FSMContext):
    doc = message.document
    if doc and doc.mime_type and doc.mime_type.startswith("image/"):
        await message.answer(
            "🖼 Я получил изображение документом.\n\nЧтобы решить задачу по фото, сначала нажми <b>📚 Решить задачу</b>, а потом отправь изображение.",
            reply_markup=main_menu_keyboard(),
        )


@router.message(F.text)
async def generic_text_message(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if is_cancel_text(text):
        await state.clear()
        await message.answer("Возвращаю в меню.", reply_markup=main_menu_keyboard())
        return
    if text == "/start":
        await cmd_start(message, state)
        return
    if text in USER_MENU_BUTTONS:
        return
    for button in db.list_menu_buttons():
        if not button.get("is_active"):
            continue
        if button.get("title") != text:
            continue
        action_type = button.get("action_type")
        action_value = button.get("action_value") or ""
        if action_type == "show_text":
            await message.answer(action_value, reply_markup=main_menu_keyboard())
            return
        if action_type == "open_url":
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Открыть", url=action_value)]]
            )
            await message.answer(f"🔗 <b>{html.escape(button['title'])}</b>", reply_markup=kb)
            return
    await process_ai_request(message, "generic")


async def main() -> None:
    errors = validate_config()
    if errors:
        raise RuntimeError("; ".join(errors))

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    logger.info("Authorized bot: @%s (%s)", me.username, me.id)

    dp = Dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)

    dp.include_router(get_admin_router(db))
    dp.include_router(router)

    webhook_runner = await start_webhook_server(bot)
    try:
        logger.info("Bot polling started")
        await dp.start_polling(bot)
    finally:
        await webhook_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
                      
