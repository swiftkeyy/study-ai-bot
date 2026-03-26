import asyncio
import logging
from typing import Iterable

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, KeyboardButton, Message, PreCheckoutQuery, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from admin import get_admin_router
from ai import ask_ai
from config import (
    BOT_TOKEN,
    LOG_FILE,
    LOG_LEVEL,
    YOOKASSA_WEBHOOK_HOST,
    YOOKASSA_WEBHOOK_PORT,
    validate_config,
)
from db import Database
from payments import create_yookassa_payment, format_prices_text, get_buy_keyboard, send_stars_invoice
from yookassa_webhook import create_yookassa_app


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


db = Database()
router = Router(name="main")


class UserStates(StatesGroup):
    waiting_solve = State()
    waiting_text = State()
    waiting_promo = State()
    waiting_support = State()


MATERIALS = {
    "essays": (
        "📝 Как писать эссе",
        "<b>Как писать эссе</b>\n\n"
        "1. Сформулируй тезис.\n"
        "2. Подбери 2–3 аргумента.\n"
        "3. Пиши короткими абзацами: вступление → основная часть → вывод.\n"
        "4. Не уходи от темы.\n\n"
        "Шаблон:\n"
        "• Вступление: почему тема важна\n"
        "• Основная часть: позиция + примеры\n"
        "• Вывод: краткий итог"
    ),
    "referat": (
        "📚 Как писать реферат",
        "<b>Как писать реферат</b>\n\n"
        "Структура:\n"
        "• Титульный лист\n"
        "• Содержание\n"
        "• Введение\n"
        "• Основная часть\n"
        "• Заключение\n"
        "• Список источников\n\n"
        "Совет: сначала сделай план разделов, а потом заполняй его по очереди."
    ),
    "conspect": (
        "🗒 Как делать конспект",
        "<b>Как делать конспект</b>\n\n"
        "1. Выпиши тему и дату.\n"
        "2. Делай короткие тезисы, а не сплошной текст.\n"
        "3. Выделяй определения и формулы.\n"
        "4. В конце добавь 3–5 ключевых выводов."
    ),
    "exams": (
        "🎯 Подготовка к экзаменам",
        "<b>Как готовиться к экзаменам</b>\n\n"
        "• Разбей подготовку на маленькие блоки\n"
        "• Повторяй по таймеру 25/5\n"
        "• Решай типовые задания\n"
        "• Раз в неделю делай пробник\n"
        "• Слабые темы выноси в отдельный список"
    ),
    "prompts": (
        "🤖 Полезные промпты",
        "<b>Полезные промпты для учебы</b>\n\n"
        "• Объясни тему простыми словами\n"
        "• Реши задачу пошагово\n"
        "• Сделай краткий конспект текста\n"
        "• Проверь ошибки и исправь\n"
        "• Приведи 3 примера по теме"
    ),
    "math": (
        "📐 Советы по математике",
        "<b>Советы по математике</b>\n\n"
        "• Сначала выпиши, что дано\n"
        "• Определи, что нужно найти\n"
        "• Решай по шагам, не перепрыгивай\n"
        "• Проверяй ответ подстановкой\n"
        "• Если задача большая — раздели на части"
    ),
}


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📚 Решить задачу"), KeyboardButton(text="✍️ Написать текст"))
    kb.row(KeyboardButton(text="👤 Личный кабинет"), KeyboardButton(text="💎 Купить доступ"))
    kb.row(KeyboardButton(text="🎁 Ввести промокод"), KeyboardButton(text="📣 Новости"))
    kb.row(KeyboardButton(text="💬 Поддержка"), KeyboardButton(text="👥 Реферальная программа"))
    kb.row(KeyboardButton(text="🎓 Полезные материалы"), KeyboardButton(text="❓ Помощь"))
    return kb.as_markup(resize_keyboard=True)


def build_required_subscription_keyboard():
    channel_link = db.get_required_channel_link()
    kb = InlineKeyboardBuilder()
    if channel_link:
        kb.button(text="📢 Подписаться", url=channel_link)
    kb.button(text="✅ Проверить подписку", callback_data="check_required_subscription")
    kb.adjust(1)
    return kb.as_markup()


def build_materials_keyboard():
    kb = InlineKeyboardBuilder()
    for key, (title, _) in MATERIALS.items():
        kb.button(text=title, callback_data=f"material:{key}")
    kb.adjust(1)
    return kb.as_markup()


def build_news_keyboard():
    url = db.get_news_channel_url() or db.get_required_channel_link()
    if not url:
        return None
    kb = InlineKeyboardBuilder()
    kb.button(text="📣 Перейти в канал", url=url)
    return kb.as_markup()


def build_referral_text(user_id: int) -> str:
    stats = db.get_referral_stats(user_id)
    bot_username = "studyai_rubot"
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return (
        "👥 <b>Реферальная программа</b>\n\n"
        f"Твоя ссылка: {link}\n\n"
        f"Приглашено друзей: <b>{stats['invited_count']}</b>\n"
        f"Бонусных запросов получено: <b>{stats['total_bonus']}</b>\n\n"
        "За каждого нового пользователя по твоей ссылке ты получаешь <b>5 запросов</b>."
    )


def split_long_text(text: str, limit: int = 3900) -> Iterable[str]:
    if len(text) <= limit:
        yield text
        return

    current = []
    current_len = 0
    for paragraph in text.split("\n"):
        if current_len + len(paragraph) + 1 > limit:
            yield "\n".join(current)
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len += len(paragraph) + 1

    if current:
        yield "\n".join(current)


def get_onboarding_text(user: dict) -> str:
    settings = db.get_settings()
    return (
        "👋 <b>Добро пожаловать в Study AI Bot</b>\n\n"
        "Я твой AI-помощник для учебы прямо в Telegram.\n\n"
        "Что умею:\n"
        "• решать задачи\n"
        "• писать тексты\n"
        "• объяснять темы простым языком\n"
        "• отвечать как ChatGPT\n\n"
        f"🎁 Сейчас у тебя <b>{user['requests_left']}</b> бесплатных запросов.\n"
        f"Базовый бесплатный лимит: <b>{settings['free_limit']}</b>.\n\n"
        "Выбери действие в меню ниже."
    )


def get_profile_text(user_id: int) -> str:
    db.refresh_subscription_status(user_id)
    user = db.get_user(user_id)
    settings = db.get_settings()
    if not user:
        return "Профиль не найден."

    premium = "Да" if user["is_premium"] else "Нет"
    vip = "Да" if user["is_vip"] else "Нет"
    sub_until = user["sub_until"] or "—"
    username = f"@{user['username']}" if user["username"] else "—"
    banned = "Да" if user.get("is_banned") else "Нет"

    return (
        "👤 <b>Личный кабинет</b>\n\n"
        f"ID: <code>{user['id']}</code>\n"
        f"Username: {username}\n"
        f"Осталось запросов: <b>{user['requests_left']}</b>\n"
        f"Осталось генераций: <b>{user.get('images_left', 0)}</b>\n"
        f"Premium: <b>{premium}</b>\n"
        f"Подписка до: <b>{sub_until}</b>\n"
        f"VIP: <b>{vip}</b>\n"
        f"Бан: <b>{banned}</b>\n"
        f"Всего запросов: <b>{user['total_requests']}</b>\n"
        f"Бонусных запросов: <b>{user.get('bonus_requests_total', 0)}</b>\n"
        f"Бесплатный лимит по умолчанию: <b>{settings['free_limit']}</b>"
    )


async def send_paywall(message: Message) -> None:
    settings = db.get_settings()
    await message.answer(settings["paywall_text"], reply_markup=get_buy_keyboard(db))


def _required_channel_chat_ref() -> str | None:
    channel = db.get_required_channel()
    if channel.get("channel_id"):
        return str(channel["channel_id"])
    username = channel.get("channel_username")
    if username:
        username = str(username).strip()
        if username.startswith("https://t.me/") or username.startswith("http://t.me/"):
            username = username.rsplit("/", 1)[-1]
        if not username.startswith("@"):  # pragma: no branch
            username = f"@{username}"
        return username
    return None


async def has_required_subscription(bot: Bot, user_id: int) -> bool:
    channel = db.get_required_channel()
    if not channel.get("enabled"):
        return True

    chat_ref = _required_channel_chat_ref()
    if not chat_ref:
        logger.warning("Required subscription enabled, but channel is not configured")
        return False

    try:
        member = await bot.get_chat_member(chat_id=chat_ref, user_id=user_id)
        return member.status not in {"left", "kicked"}
    except Exception as e:
        logger.warning("Failed to verify required subscription for user %s: %s", user_id, e)
        return False


async def get_access_block(bot: Bot, user_id: int, username: str | None = None):
    user = db.get_or_create_user(user_id, username)

    if db.is_admin(user_id):
        return None

    if user.get("is_banned"):
        reason = user.get("ban_reason") or "Причина не указана"
        return (
            "⛔ <b>Доступ к боту ограничен</b>\n\n"
            f"Ты был заблокирован администратором.\nПричина: <b>{reason}</b>",
            None,
        )

    if db.is_maintenance_enabled():
        return db.get_maintenance_text(), None

    channel = db.get_required_channel()
    if channel.get("enabled"):
        subscribed = await has_required_subscription(bot, user_id)
        if not subscribed:
            return channel.get("text") or "Сначала подпишись на обязательный канал.", build_required_subscription_keyboard()

    return None


async def deny_if_blocked_message(message: Message) -> bool:
    block = await get_access_block(message.bot, message.from_user.id, message.from_user.username)
    if not block:
        return False
    text, markup = block
    await message.answer(text, reply_markup=markup)
    return True


async def deny_if_blocked_callback(callback: CallbackQuery) -> bool:
    block = await get_access_block(callback.bot, callback.from_user.id, callback.from_user.username)
    if not block:
        return False
    text, markup = block
    await callback.answer("Сначала выполни обязательные условия", show_alert=True)
    await callback.message.answer(text, reply_markup=markup)
    return True


async def ensure_access_and_consume(message: Message) -> bool:
    user_id = message.from_user.id
    db.get_or_create_user(user_id, message.from_user.username)

    if await deny_if_blocked_message(message):
        return False

    if not db.has_access(user_id):
        await send_paywall(message)
        return False

    allowed = db.decrement_request_if_needed(user_id)
    if not allowed:
        await send_paywall(message)
        return False

    return True


def build_mode_prompt(mode: str, user_text: str) -> tuple[str, str]:
    if mode == "solve":
        system_prompt = (
            "Ты AI-репетитор. Решай задачи понятно для ученика. "
            "Показывай ход решения по шагам. Если данных мало — скажи, чего не хватает. "
            "Не выдумывай факты. Пиши простым русским языком."
        )
        prompt = f"Реши задачу и объясни решение:\n\n{user_text}"
        return prompt, system_prompt

    if mode == "text":
        system_prompt = (
            "Ты AI-редактор и автор текстов. Пиши грамотно, понятно и современно. "
            "Если уместно, структурируй текст. Учитывай цель, аудиторию и стиль."
        )
        prompt = f"Напиши текст по запросу пользователя:\n\n{user_text}"
        return prompt, system_prompt

    system_prompt = (
        "Ты дружелюбный AI-помощник для учебы в Telegram. "
        "Отвечай полезно, структурированно и без воды."
    )
    return user_text, system_prompt


async def process_ai_request(message: Message, mode: str) -> None:
    if not await ensure_access_and_consume(message):
        return

    prompt, system_prompt = build_mode_prompt(mode, message.text)
    status_message = await message.answer("⏳ Думаю над ответом...")

    try:
        answer, provider = await ask_ai(prompt, system_prompt=system_prompt)
        db.add_request_log(message.from_user.id, mode, provider)
        user = db.get_user(message.from_user.id)

        prefix = f"🤖 <b>Ответ</b> <i>({provider})</i>\n\n"
        chunks = list(split_long_text(prefix + answer))

        await status_message.delete()
        for index, chunk in enumerate(chunks):
            if index == len(chunks) - 1 and user and not (user["is_premium"] or user["is_vip"]):
                chunk += f"\n\n💡 Осталось бесплатных запросов: <b>{user['requests_left']}</b>"
            await message.answer(chunk)
    except Exception as e:
        logger.exception("AI request failed: %s", e)
        await status_message.edit_text(
            "⚠️ Не удалось получить ответ от AI.\n"
            "Проверь API-ключи и попробуй ещё раз."
        )


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
        await callback.answer("Подписка пока не найдена", show_alert=True)
        await callback.message.answer(
            db.get_required_channel().get("text") or "Сначала подпишись на канал.",
            reply_markup=build_required_subscription_keyboard(),
        )


@router.message(F.text == "📚 Решить задачу")
async def solve_entry(message: Message, state: FSMContext):
    if await deny_if_blocked_message(message):
        return
    await state.set_state(UserStates.waiting_solve)
    await message.answer(
        "📚 <b>Режим решения задач</b>\n\n"
        "Отправь задачу текстом.\n"
        "Можно писать как есть, например:\n"
        "<i>Реши уравнение 2x + 5 = 17</i>"
    )


@router.message(F.text == "✍️ Написать текст")
async def text_entry(message: Message, state: FSMContext):
    if await deny_if_blocked_message(message):
        return
    await state.set_state(UserStates.waiting_text)
    await message.answer(
        "✍️ <b>Режим написания текста</b>\n\n"
        "Напиши, какой текст нужен.\n"
        "Например:\n"
        "<i>Напиши эссе на тему экологии на 300 слов</i>"
    )


@router.message(F.text == "👤 Личный кабинет")
async def profile_handler(message: Message, state: FSMContext):
    await state.clear()
    db.get_or_create_user(message.from_user.id, message.from_user.username)
    if await deny_if_blocked_message(message):
        return
    await message.answer(get_profile_text(message.from_user.id))


@router.message(F.text == "💎 Купить доступ")
async def buy_handler(message: Message, state: FSMContext):
    await state.clear()
    db.get_or_create_user(message.from_user.id, message.from_user.username)
    if await deny_if_blocked_message(message):
        return
    await message.answer(format_prices_text(db), reply_markup=get_buy_keyboard(db))


@router.message(F.text == "🎁 Ввести промокод")
async def promo_entry(message: Message, state: FSMContext):
    if await deny_if_blocked_message(message):
        return
    await state.set_state(UserStates.waiting_promo)
    await message.answer(
        "🎁 <b>Ввод промокода</b>\n\n"
        "Отправь промокод одним сообщением.\n"
        "Например: <code>START5</code>"
    )


@router.message(UserStates.waiting_promo, F.text)
async def promo_input(message: Message, state: FSMContext):
    if await deny_if_blocked_message(message):
        return
    code = (message.text or "").strip()
    ok, result = db.activate_promo_code(code, message.from_user.id)
    await message.answer(("✅ " if ok else "⚠️ ") + result)
    await state.clear()


@router.message(F.text == "📣 Новости")
async def news_handler(message: Message, state: FSMContext):
    await state.clear()
    if await deny_if_blocked_message(message):
        return
    await message.answer(
        "📣 <b>Новости и обновления</b>\n\n"
        "Подписывайся на канал: там публикуются обновления бота, акции и полезные материалы.",
        reply_markup=build_news_keyboard(),
    )


@router.message(F.text == "💬 Поддержка")
async def support_entry(message: Message, state: FSMContext):
    if await deny_if_blocked_message(message):
        return
    await state.set_state(UserStates.waiting_support)
    await message.answer(
        "💬 <b>Поддержка</b>\n\n"
        "Напиши одним сообщением, в чём нужна помощь.\n"
        "Админ получит твой запрос и ответит через бота."
    )


@router.message(UserStates.waiting_support, F.text)
async def support_input(message: Message, state: FSMContext):
    if await deny_if_blocked_message(message):
        return
    text_value = (message.text or "").strip()
    if not text_value:
        await message.answer("Сообщение пустое. Попробуй ещё раз.")
        return
    ticket_id = db.create_support_ticket(message.from_user.id, text_value)
    username = f"@{message.from_user.username}" if message.from_user.username else "—"
    admin_text = (
        "💬 <b>Новое обращение в поддержку</b>\n\n"
        f"Ticket ID: <code>{ticket_id}</code>\n"
        f"User ID: <code>{message.from_user.id}</code>\n"
        f"Username: {username}\n\n"
        f"Сообщение:\n{text_value}\n\n"
        "Чтобы ответить, открой в админке раздел 💬 Поддержка и используй команду:\n"
        f"<code>reply {ticket_id} твой ответ</code>"
    )
    for admin_id in db.admin_user_ids():
        try:
            await message.bot.send_message(admin_id, admin_text)
        except Exception:
            logger.exception("Failed to deliver support ticket %s to admin %s", ticket_id, admin_id)
    await message.answer(
        "✅ <b>Сообщение отправлено</b>\n\n"
        f"Номер обращения: <code>{ticket_id}</code>\n"
        "Когда админ ответит, сообщение придёт сюда в бот."
    )
    await state.clear()


@router.message(F.text == "👥 Реферальная программа")
async def referral_handler(message: Message, state: FSMContext):
    await state.clear()
    db.get_or_create_user(message.from_user.id, message.from_user.username)
    if await deny_if_blocked_message(message):
        return
    await message.answer(build_referral_text(message.from_user.id))


@router.message(F.text == "🎓 Полезные материалы")
async def materials_handler(message: Message, state: FSMContext):
    await state.clear()
    if await deny_if_blocked_message(message):
        return
    await message.answer(
        "🎓 <b>Полезные материалы</b>\n\nВыбери раздел ниже.",
        reply_markup=build_materials_keyboard(),
    )


@router.callback_query(F.data.startswith("material:"))
async def material_callback(callback: CallbackQuery):
    if await deny_if_blocked_callback(callback):
        return
    key = callback.data.split(":", 1)[1]
    material = MATERIALS.get(key)
    if not material:
        await callback.answer("Материал не найден", show_alert=True)
        return
    title, body = material
    await callback.message.answer(f"{title}\n\n{body}")
    await callback.answer()


@router.message(F.text == "❓ Помощь")
async def help_handler(message: Message, state: FSMContext):
    await state.clear()
    if await deny_if_blocked_message(message):
        return
    settings = db.get_settings()
    await message.answer(settings["help_text"])


@router.callback_query(F.data == "refresh_prices")
async def refresh_prices(callback: CallbackQuery):
    if await deny_if_blocked_callback(callback):
        return
    await callback.message.edit_text(format_prices_text(db), reply_markup=get_buy_keyboard(db))
    await callback.answer("Цены обновлены")


@router.callback_query(F.data.startswith("buy_stars_"))
async def buy_stars_callback(callback: CallbackQuery):
    if await deny_if_blocked_callback(callback):
        return
    days = int(callback.data.split("_")[-1])
    await send_stars_invoice(callback.bot, callback.message.chat.id, callback.from_user.id, days, db)
    await callback.answer("Инвойс отправлен")


@router.callback_query(F.data.startswith("buy_yk_"))
async def buy_yk_callback(callback: CallbackQuery):
    if await deny_if_blocked_callback(callback):
        return
    days = int(callback.data.split("_")[-1])
    try:
        _, confirmation_url = await create_yookassa_payment(callback.from_user.id, days, db)
        await callback.message.answer(
            (
                f"💳 <b>Оплата через ЮKassa</b>\n\n"
                f"Тариф: <b>{days} дней</b>\n"
                f"Перейди по ссылке для оплаты:\n{confirmation_url}\n\n"
                "После успешной оплаты подписка активируется автоматически."
            )
        )
        await callback.answer("Ссылка на оплату создана")
    except Exception as e:
        logger.exception("YooKassa create payment failed: %s", e)
        await callback.answer("Не удалось создать оплату", show_alert=True)
        await callback.message.answer(
            "⚠️ Не удалось создать ссылку ЮKassa.\n"
            "Проверь настройки магазина и попробуй снова."
        )


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    payload = pre_checkout_query.invoice_payload or ""
    ok = False
    error_message = "Некорректный платёж. Попробуй ещё раз."

    try:
        parts = payload.split(":")
        if len(parts) >= 4 and parts[0] == "stars":
            days = int(parts[1])
            user_id = int(parts[2])
            if days in (3, 7, 30) and user_id == pre_checkout_query.from_user.id:
                ok = True
    except Exception:
        ok = False

    await bot.answer_pre_checkout_query(
        pre_checkout_query_id=pre_checkout_query.id,
        ok=ok,
        error_message=None if ok else error_message,
    )


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload or ""

    try:
        parts = payload.split(":")
        if len(parts) < 4 or parts[0] != "stars":
            await message.answer("Платёж получен, но не удалось распознать тариф. Напиши администратору.")
            return

        days = int(parts[1])
        user_id = int(parts[2])
        if user_id != message.from_user.id:
            await message.answer("Платёж получен, но user_id не совпал. Напиши администратору.")
            return

        db.upsert_payment(
            user_id=user_id,
            amount=float(payment.total_amount),
            payment_type="stars",
            status="succeeded",
            external_id=payment.telegram_payment_charge_id,
            days=days,
        )
        db.activate_subscription(user_id, days)

        await message.answer(
            (
                "✅ <b>Оплата прошла успешно</b>\n\n"
                f"Подписка активирована на <b>{days}</b> дней.\n"
                f"Способ оплаты: <b>Telegram Stars</b>\n\n"
                "Теперь можно пользоваться ботом без ограничений по подписке."
            )
        )
    except Exception as e:
        logger.exception("Failed to process successful payment: %s", e)
        await message.answer("Платёж получен, но при активации подписки произошла ошибка. Напиши администратору.")


@router.message(UserStates.waiting_solve, F.text)
async def solve_mode_message(message: Message):
    await process_ai_request(message, mode="solve")


@router.message(UserStates.waiting_text, F.text)
async def text_mode_message(message: Message):
    await process_ai_request(message, mode="text")


@router.message(F.text)
async def generic_text_message(message: Message):
    if message.text and message.text.startswith("/"):
        return
    db.get_or_create_user(message.from_user.id, message.from_user.username)
    if await deny_if_blocked_message(message):
        return
    await process_ai_request(message, mode="general")


async def start_webhook_server(bot: Bot) -> web.AppRunner:
    app = create_yookassa_app(bot, db)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, YOOKASSA_WEBHOOK_HOST, YOOKASSA_WEBHOOK_PORT)
    await site.start()
    logger.info("YooKassa webhook server started on %s:%s", YOOKASSA_WEBHOOK_HOST, YOOKASSA_WEBHOOK_PORT)
    return runner


async def main() -> None:
    errors = validate_config()
    if errors:
        raise RuntimeError("; ".join(errors))

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    await bot.delete_webhook(drop_pending_updates=False)

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
