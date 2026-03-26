import asyncio
import logging
from io import BytesIO
from typing import Iterable, Optional

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from admin import get_admin_router
from ai import ask_ai, ask_ai_with_image
from config import (
    BOT_TOKEN,
    LOG_FILE,
    LOG_LEVEL,
    YOOKASSA_WEBHOOK_HOST,
    YOOKASSA_WEBHOOK_PORT,
    validate_config,
)
from db import Database
from image_ai import generate_image
from payments import create_yookassa_payment, format_prices_text, get_buy_keyboard, send_stars_invoice
from yookassa_webhook import create_yookassa_app

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

router = Router(name="main")
db = Database()


class UserStates(StatesGroup):
    waiting_solve = State()
    waiting_text = State()
    waiting_image = State()
    waiting_promo = State()
    waiting_support = State()


EXIT_LABELS = {"🔙 В меню", "↩ В меню", "❌ Отмена", "Отмена", "Назад"}


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📚 Решить задачу"), KeyboardButton(text="✍️ Написать текст"))
    kb.row(KeyboardButton(text="🖼 Создать изображение"), KeyboardButton(text="👤 Личный кабинет"))
    kb.row(KeyboardButton(text="💎 Купить доступ"), KeyboardButton(text="🎁 Ввести промокод"))
    kb.row(KeyboardButton(text="📣 Новости"), KeyboardButton(text="💬 Поддержка"))
    kb.row(KeyboardButton(text="👥 Реферальная программа"), KeyboardButton(text="🎓 Полезные материалы"))
    for item in db.get_active_menu_buttons():
        kb.row(KeyboardButton(text=item["title"]))
    kb.row(KeyboardButton(text="❓ Помощь"))
    return kb.as_markup(resize_keyboard=True)


def channel_check_keyboard() -> InlineKeyboardMarkup:
    link = db.get_required_channel_link()
    kb = InlineKeyboardBuilder()
    if link:
        kb.row(InlineKeyboardButton(text="📡 Подписаться", url=link))
    kb.row(InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_required_subscription"))
    return kb.as_markup()


def split_long_text(text: str, limit: int = 3900) -> Iterable[str]:
    if len(text) <= limit:
        yield text
        return
    current = []
    length = 0
    for paragraph in text.split("\n"):
        add = len(paragraph) + 1
        if current and length + add > limit:
            yield "\n".join(current)
            current = [paragraph]
            length = len(paragraph)
        else:
            current.append(paragraph)
            length += add
    if current:
        yield "\n".join(current)


def get_onboarding_text(user: dict) -> str:
    settings = db.get_settings()
    return (
        "👋 <b>Добро пожаловать в Study AI Bot</b>\n\n"
        "Я твой AI-помощник для учебы прямо в Telegram.\n\n"
        f"🎁 Текстовых запросов: <b>{user['requests_left']}</b>\n"
        f"🖼 Генераций изображений: <b>{user['images_left']}</b>\n"
        f"Бесплатный лимит по тексту: <b>{settings['free_limit']}</b>\n"
        f"Бесплатный лимит по картинкам: <b>{settings['free_image_limit']}</b>\n\n"
        "Выбери действие в меню ниже."
    )


def build_referral_text(user_id: int) -> str:
    bot_username = BOT_TOKEN.split(":")[0]
    stats = db.get_referral_stats(user_id)
    return (
        "👥 <b>Реферальная программа</b>\n\n"
        f"Приглашено друзей: <b>{stats['invited_count']}</b>\n"
        f"Бонусных запросов получено: <b>{stats['bonus_total']}</b>\n\n"
        f"Твоя ссылка:\n<code>https://t.me/studyai_rubot?start=ref_{user_id}</code>\n\n"
        "За каждого нового пользователя по твоей ссылке ты получаешь <b>5 запросов</b>."
    )


def get_profile_text(user_id: int) -> str:
    db.refresh_subscription_status(user_id)
    user = db.get_user(user_id)
    if not user:
        return "Профиль не найден."
    username = f"@{user['username']}" if user['username'] else "—"
    premium = "Да" if user['is_premium'] else "Нет"
    vip = "Да" if user['is_vip'] else "Нет"
    sub_until = user['sub_until'] or "—"
    stats = db.get_referral_stats(user_id)
    return (
        "👤 <b>Личный кабинет</b>\n\n"
        f"ID: <code>{user['id']}</code>\n"
        f"Username: {username}\n"
        f"Осталось запросов: <b>{user['requests_left']}</b>\n"
        f"Осталось генераций: <b>{user['images_left']}</b>\n"
        f"Premium: <b>{premium}</b>\n"
        f"Подписка до: <b>{sub_until}</b>\n"
        f"VIP: <b>{vip}</b>\n"
        f"Всего запросов: <b>{user['total_requests']}</b>\n"
        f"Приглашено друзей: <b>{stats['invited_count']}</b>"
    )


def get_materials_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✍️ Как писать эссе", callback_data="mat_essay"))
    kb.row(InlineKeyboardButton(text="📄 Как писать реферат", callback_data="mat_report"))
    kb.row(InlineKeyboardButton(text="📝 Как делать конспект", callback_data="mat_notes"))
    kb.row(InlineKeyboardButton(text="🎓 Подготовка к экзаменам", callback_data="mat_exam"))
    kb.row(InlineKeyboardButton(text="🤖 Полезные промпты", callback_data="mat_prompts"))
    return kb.as_markup()


def get_material_text(key: str) -> str:
    materials = {
        "essay": "✍️ <b>Как писать эссе</b>\n\n1. Определи тему.\n2. Сформулируй тезис.\n3. Дай 2–3 аргумента.\n4. Сделай вывод.\n\nШаблон: вступление → позиция → аргументы → вывод.",
        "report": "📄 <b>Как писать реферат</b>\n\nСтруктура: титул → содержание → введение → основная часть → заключение → список источников.",
        "notes": "📝 <b>Как делать конспект</b>\n\nПиши кратко, выделяй определения, делай подзаголовки и примеры.",
        "exam": "🎓 <b>Подготовка к экзаменам</b>\n\nРазбей темы на блоки, повторяй регулярно, тренируйся на типовых заданиях.",
        "prompts": "🤖 <b>Полезные промпты</b>\n\n• Объясни простыми словами\n• Реши пошагово\n• Сделай краткий конспект\n• Проверь ошибки\n• Приведи пример",
    }
    return materials.get(key, "Материал не найден.")


def get_news_text() -> tuple[str, InlineKeyboardMarkup]:
    url = db.get_settings()["news_channel_url"]
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📣 Перейти в канал", url=url))
    return "📣 <b>Новости</b>\n\nПодписывайся на канал, там выходят обновления бота, полезные материалы и акции.", kb.as_markup()


async def send_paywall(message: Message) -> None:
    settings = db.get_settings()
    await message.answer(settings["paywall_text"], reply_markup=get_buy_keyboard(db))


async def check_access_block(message: Message) -> Optional[tuple[str, Optional[InlineKeyboardMarkup]]]:
    user_id = message.from_user.id
    db.get_or_create_user(user_id, message.from_user.username)

    if db.is_admin(user_id):
        return None
    if db.is_banned(user_id):
        ban = db.get_ban_status(user_id)
        return (f"🚫 Ты заблокирован.\nПричина: {ban['reason'] or '—'}", None)
    if db.is_maintenance_enabled():
        return (db.get_maintenance_text(), None)
    req = db.get_required_channel()
    if req.get("enabled"):
        try:
            chat_id = req.get("channel_id") or req.get("channel_username")
            member = await message.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in {"left", "kicked"}:
                return (db.get_required_subscription_text(), channel_check_keyboard())
        except Exception:
            return (db.get_required_subscription_text(), channel_check_keyboard())
    return None


async def ensure_text_access(message: Message) -> bool:
    if not db.has_access(message.from_user.id):
        await send_paywall(message)
        return False
    if not db.decrement_request_if_needed(message.from_user.id):
        await send_paywall(message)
        return False
    return True


async def ensure_image_access(message: Message) -> bool:
    if not db.has_image_access(message.from_user.id):
        await message.answer("⚠️ Лимит генераций изображений закончился. Купи доступ, чтобы продолжить.")
        return False
    if not db.decrement_image_if_needed(message.from_user.id):
        await message.answer("⚠️ Лимит генераций изображений закончился. Купи доступ, чтобы продолжить.")
        return False
    return True


def build_mode_prompt(mode: str, user_text: str) -> tuple[str, str]:
    ai_settings = db.get_ai_settings()
    custom = ai_settings.get("system_prompt", "").strip()
    if mode == "solve":
        system_prompt = custom or (
            "Ты AI-репетитор. Решай задачи понятно для ученика. Показывай ход решения по шагам. "
            "Если данных мало — скажи, чего не хватает. Пиши простым русским языком."
        )
        prompt = f"Реши задачу и объясни решение:\n\n{user_text}"
        return prompt, system_prompt
    if mode == "text":
        system_prompt = custom or (
            "Ты AI-редактор и автор текстов. Пиши грамотно, понятно и современно. "
            "Если уместно, структурируй текст."
        )
        prompt = f"Напиши текст по запросу пользователя:\n\n{user_text}"
        return prompt, system_prompt
    system_prompt = custom or "Ты дружелюбный AI-помощник для учебы в Telegram. Отвечай полезно, структурированно и без воды."
    return user_text, system_prompt


def current_provider_order() -> list[str]:
    ai_settings = db.get_ai_settings()
    order = [ai_settings.get("provider") or "gemini"]
    if ai_settings.get("fallback_1"):
        order.append(ai_settings["fallback_1"])
    if ai_settings.get("fallback_2"):
        order.append(ai_settings["fallback_2"])
    return order


async def process_ai_request(message: Message, mode: str) -> None:
    block = await check_access_block(message)
    if block:
        await message.answer(block[0], reply_markup=block[1])
        return
    if not await ensure_text_access(message):
        return
    prompt, system_prompt = build_mode_prompt(mode, message.text or "")
    status_message = await message.answer("⏳ Думаю над ответом...")
    try:
        answer, provider = await ask_ai(prompt, system_prompt=system_prompt, provider_order=current_provider_order())
        db.add_request_log(message.from_user.id, mode, provider)
        await status_message.delete()
        for chunk in split_long_text(f"🤖 <b>Ответ</b> <i>({provider})</i>\n\n{answer}"):
            await message.answer(chunk)
    except Exception as e:
        logger.exception("AI request failed: %s", e)
        await status_message.edit_text("⚠️ Не удалось получить ответ от AI.\nПроверь API-ключи и попробуй ещё раз.")


async def fetch_telegram_file(bot: Bot, file_id: str) -> tuple[bytes, str]:
    file = await bot.get_file(file_id)
    data = await bot.download_file(file.file_path)
    content = data.read() if hasattr(data, "read") else data.getvalue()
    mime = "image/jpeg"
    lower = (file.file_path or "").lower()
    if lower.endswith(".png"):
        mime = "image/png"
    elif lower.endswith(".webp"):
        mime = "image/webp"
    return content, mime


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    referred_by = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            referred_by = int(parts[1].split("_", 1)[1])
        except Exception:
            referred_by = None
    user = db.get_or_create_user(message.from_user.id, message.from_user.username, referred_by=referred_by)
    if referred_by:
        db.register_referral(referred_by, message.from_user.id, bonus_requests=5)
    block = await check_access_block(message)
    if block:
        await message.answer(block[0], reply_markup=block[1])
        return
    await message.answer(get_onboarding_text(user), reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "check_required_subscription")
async def check_required_subscription(callback: CallbackQuery):
    fake_message = callback.message
    block = await check_access_block(callback.message)
    if block:
        await callback.answer("Подписка ещё не подтверждена", show_alert=True)
        await callback.message.answer(block[0], reply_markup=block[1])
    else:
        await callback.answer("Подписка подтверждена ✅", show_alert=True)
        await callback.message.answer("✅ Доступ открыт.", reply_markup=main_menu_keyboard())


@router.message(F.text.in_(EXIT_LABELS))
async def user_exit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Выход из текущего режима. Возвращаю в обычное меню.", reply_markup=main_menu_keyboard())


async def _start_mode(message: Message, state: FSMContext, mode: str, text: str):
    block = await check_access_block(message)
    if block:
        await message.answer(block[0], reply_markup=block[1])
        return
    await state.set_state(getattr(UserStates, mode))
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(F.text == "📚 Решить задачу")
async def solve_entry(message: Message, state: FSMContext):
    await _start_mode(message, state, "waiting_solve", "📚 <b>Режим решения задач</b>\n\nОтправь задачу текстом или фото задания.\nМожно писать как есть, например:\n<i>Реши уравнение 2x + 5 = 17</i>")


@router.message(F.text == "✍️ Написать текст")
async def text_entry(message: Message, state: FSMContext):
    await _start_mode(message, state, "waiting_text", "✍️ <b>Режим написания текста</b>\n\nНапиши, какой текст нужен.\nНапример:\n<i>Напиши эссе на тему экологии на 300 слов</i>")


@router.message(F.text == "🖼 Создать изображение")
async def image_entry(message: Message, state: FSMContext):
    await _start_mode(message, state, "waiting_image", "🖼 <b>Режим генерации изображения</b>\n\nНапиши, что хочешь нарисовать.\nНапример:\n<i>Нарисуй собаку в мультяшном стиле</i>")


@router.message(F.text == "🎁 Ввести промокод")
async def promo_entry(message: Message, state: FSMContext):
    await _start_mode(message, state, "waiting_promo", "🎁 <b>Промокод</b>\n\nОтправь промокод одним сообщением.")


@router.message(F.text == "💬 Поддержка")
async def support_entry(message: Message, state: FSMContext):
    await _start_mode(message, state, "waiting_support", db.get_settings()["support_text"])


@router.message(F.text == "👤 Личный кабинет")
async def profile(message: Message, state: FSMContext):
    block = await check_access_block(message)
    if block:
        await message.answer(block[0], reply_markup=block[1])
        return
    await state.clear()
    db.get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(get_profile_text(message.from_user.id), reply_markup=main_menu_keyboard())


@router.message(F.text == "❓ Помощь")
async def help_section(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(db.get_settings()["help_text"], reply_markup=main_menu_keyboard())


@router.message(F.text == "📣 Новости")
async def news_section(message: Message, state: FSMContext):
    await state.clear()
    text, kb = get_news_text()
    await message.answer(text, reply_markup=main_menu_keyboard())
    await message.answer("Открыть канал:", reply_markup=kb)


@router.message(F.text == "👥 Реферальная программа")
async def referrals_section(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(build_referral_text(message.from_user.id), reply_markup=main_menu_keyboard())


@router.message(F.text == "🎓 Полезные материалы")
async def materials_section(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🎓 <b>Полезные материалы</b>\n\nВыбери раздел:", reply_markup=main_menu_keyboard())
    await message.answer("Разделы материалов:", reply_markup=get_materials_keyboard())


@router.callback_query(F.data.startswith("mat_"))
async def material_callback(callback: CallbackQuery):
    key = callback.data.split("_", 1)[1]
    await callback.answer()
    await callback.message.answer(get_material_text(key))


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
            "На изображении задача для учебы. Сначала кратко перепиши условие, затем реши задачу пошагово и в конце дай ответ."
        )
        system_prompt = "Ты AI-репетитор. Аккуратно анализируй фото задания, не выдумывай лишнего, объясняй пошагово."
        answer, provider = await ask_ai_with_image(prompt, image_bytes, mime, system_prompt=system_prompt)
        db.add_request_log(message.from_user.id, "solve_photo", provider)
        db.add_media_request(message.from_user.id, "photo", photo.file_id, "", answer)
        await state.clear()
        await status_message.delete()
        for chunk in split_long_text(f"📚 <b>Решение по фото</b> <i>({provider})</i>\n\n{answer}"):
            await message.answer(chunk, reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.exception("Solve by photo failed: %s", e)
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
        prompt = "На изображении задача для учебы. Перепиши условие, реши пошагово и дай итоговый ответ."
        system_prompt = "Ты AI-репетитор. Аккуратно анализируй изображение задания и объясняй по шагам."
        answer, provider = await ask_ai_with_image(prompt, image_bytes, mime or doc.mime_type, system_prompt=system_prompt)
        db.add_request_log(message.from_user.id, "solve_photo", provider)
        db.add_media_request(message.from_user.id, "document_image", doc.file_id, "", answer)
        await state.clear()
        await status_message.delete()
        for chunk in split_long_text(f"📚 <b>Решение по фото</b> <i>({provider})</i>\n\n{answer}"):
            await message.answer(chunk, reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.exception("Solve document image failed: %s", e)
        await status_message.edit_text("⚠️ Не удалось решить задачу по изображению. Попробуй ещё раз или отправь условие текстом.")


@router.message(UserStates.waiting_solve, F.text)
async def solve_text(message: Message,
