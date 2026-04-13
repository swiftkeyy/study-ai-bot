import asyncio
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, KeyboardButton, Message, PreCheckoutQuery, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from admin import get_admin_router
from ai import ask_ai, ask_ai_with_image
from config import BOT_TOKEN, LOG_FILE, LOG_LEVEL, validate_config
from db import Database
from payments import (
    build_robokassa_payment_keyboard,
    create_robokassa_payment,
    format_prices_text,
    get_buy_keyboard,
    send_stars_invoice,
)
from robokassa import start_robokassa_server


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
    waiting_roast_answer = State()
    waiting_grade_guess = State()
    waiting_make_smarter = State()
    waiting_photo_cheat = State()
    waiting_ai_detect = State()


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


USER_MENU_BUTTONS = {
    "📚 Решить задачу",
    "✍️ Написать текст",
    "👤 Личный кабинет",
    "💎 Купить доступ",
    "🔥 Разнеси мой ответ",
    "📉 Угадай оценку",
    "✨ Сделай умнее",
    "📷 Шпора по фото",
    "🕵️ Палится ли AI?",
    "🎁 Ввести промокод",
    "📣 Новости",
    "💬 Поддержка",
    "👥 Реферальная программа",
    "🎓 Полезные материалы",
    "❓ Помощь",
}
USER_EXIT_TEXTS = {"🔙 В меню", "↩ В меню", "❌ Отмена", "Отмена", "Назад"}



def normalize_menu_text(value: str) -> str:
    text = (value or "").replace("\xa0", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text



def main_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📚 Решить задачу"), KeyboardButton(text="✍️ Написать текст"))
    kb.row(KeyboardButton(text="👤 Личный кабинет"), KeyboardButton(text="💎 Купить доступ"))
    kb.row(KeyboardButton(text="🔥 Разнеси мой ответ"), KeyboardButton(text="📉 Угадай оценку"))
    kb.row(KeyboardButton(text="✨ Сделай умнее"), KeyboardButton(text="📷 Шпора по фото"))
    kb.row(KeyboardButton(text="🕵️ Палится ли AI?"))

    optional_buttons: list[str] = []
    if db.is_feature_enabled("promocodes", True):
        optional_buttons.append("🎁 Ввести промокод")
    if db.is_feature_enabled("news", True):
        optional_buttons.append("📣 Новости")
    if db.is_feature_enabled("support", True):
        optional_buttons.append("💬 Поддержка")
    if db.is_feature_enabled("referrals", True):
        optional_buttons.append("👥 Реферальная программа")
    if db.is_feature_enabled("materials", True):
        optional_buttons.append("🎓 Полезные материалы")

    for i in range(0, len(optional_buttons), 2):
        row = [KeyboardButton(text=item) for item in optional_buttons[i:i + 2]]
        kb.row(*row)

    for item in db.get_active_menu_buttons():
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        if len(title) > 64:
            title = title[:64]
        kb.row(KeyboardButton(text=title))

    kb.row(KeyboardButton(text="❓ Помощь"))
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


def is_dynamic_menu_button_text(value: str) -> bool:
    text_value = (value or "").strip()
    if not text_value:
        return False
    dynamic_titles = {
        str(item.get("title") or "").strip()
        for item in db.get_active_menu_buttons()
        if str(item.get("title") or "").strip()
    }
    return text_value in dynamic_titles


def build_referral_text(user_id: int) -> str:
    stats = db.get_referral_stats(user_id)
    bot_username = "studyai_rubot"
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return (
        "👥 <b>Реферальная программа</b>\n\n"
        f"Твоя ссылка: {link}\n\n"
        f"Приглашено друзей: <b>{stats['invited_count']}</b>\n"
        f"Бонусных запросов получено: <b>{stats['bonus_total']}</b>\n\n"
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
        "• проверять ответы\n"
        "• делать шпоры по фото\n"
        "• помогать с ЕГЭ, ОГЭ и ВПР\n\n"
        f"🎁 Сейчас у тебя <b>{user['requests_left']}</b> бесплатных запросов.\n"
        f"Базовый бесплатный лимит: <b>{settings['free_limit']}</b>.\n\n"
        "Выбери действие в меню ниже."
    )


def _format_subscription_until(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if ZoneInfo is not None:
            local_dt = dt.astimezone(ZoneInfo("Europe/Moscow"))
        else:
            local_dt = dt.astimezone(timezone(timedelta(hours=3)))
        return local_dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(value)


def get_profile_text(user_id: int) -> str:
    db.refresh_subscription_status(user_id)
    user = db.get_user(user_id)
    settings = db.get_settings()
    if not user:
        return "Профиль не найден."
    premium = "Да" if user["is_premium"] else "Нет"
    vip = "Да" if user["is_vip"] else "Нет"
    sub_until = _format_subscription_until(user.get("sub_until"))
    username = f"@{user['username']}" if user["username"] else "—"
    banned = "Да" if user.get("is_banned") else "Нет"
    return (
        "👤 <b>Личный кабинет</b>\n\n"
        f"ID: <code>{user['id']}</code>\n"
        f"Username: {username}\n"
        f"Осталось запросов: <b>{user['requests_left']}</b>\n"
        f"Premium: <b>{premium}</b>\n"
        f"Подписка до: <b>{sub_until}</b>\n"
        f"VIP: <b>{vip}</b>\n"
        f"Бан: <b>{banned}</b>\n"
        f"Всего запросов: <b>{user['total_requests']}</b>\n"
        f"Бонусных запросов: <b>{user.get('bonus_requests_total', 0)}</b>\n"
        f"Бесплатный лимит по умолчанию: <b>{settings['free_limit']}</b>"
    )


FEATURE_TITLES = {
    "promocodes": "Промокоды",
    "support": "Поддержка",
    "news": "Новости",
    "materials": "Полезные материалы",
    "referrals": "Реферальная программа",
    "solve_by_photo": "Решение задач по фото",
}


def feature_disabled_text(feature_name: str) -> str:
    title = FEATURE_TITLES.get(feature_name, feature_name)
    return f"⚠️ <b>{title} временно отключены</b>\n\nЭту функцию админ временно выключил. Попробуй позже."


async def deny_if_feature_disabled(message: Message, feature_name: str) -> bool:
    if not db.is_feature_enabled(feature_name, True):
        await message.answer(feature_disabled_text(feature_name))
        return True
    return False


async def deny_if_feature_disabled_callback(callback: CallbackQuery, feature_name: str) -> bool:
    if not db.is_feature_enabled(feature_name, True):
        await callback.answer("Функция временно отключена", show_alert=True)
        await callback.message.answer(feature_disabled_text(feature_name))
        return True
    return False


async def send_paywall(message: Message) -> None:
    settings = db.get_settings()
    await message.answer(settings["paywall_text"], reply_markup=get_buy_keyboard(db, message.from_user.id))


def _required_channel_chat_ref() -> str | None:
    channel = db.get_required_channel()
    if channel.get("channel_id"):
        return str(channel["channel_id"])
    username = channel.get("channel_username")
    if username:
        username = str(username).strip()
        if username.startswith("https://t.me/") or username.startswith("http://t.me/"):
            username = username.rsplit("/", 1)[-1]
        if not username.startswith("@"):
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


def is_simple_request(user_text: str, mode: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", " ", text)
    words = re.findall(r"[\wа-яё]+", normalized.lower(), flags=re.IGNORECASE)
    if mode == "solve":
        if re.fullmatch(r"[0-9\s\+\-\*xх×/÷=().,]+", normalized):
            return True
        return len(words) <= 6 and len(normalized) <= 40
    if mode == "text":
        short_text_keywords = {"заголовок", "название", "тема", "идея", "план", "слоган", "подпись", "описание"}
        return len(words) <= 7 and any(keyword in normalized.lower() for keyword in short_text_keywords)
    return len(words) <= 10 and len(normalized) <= 60


def build_style_rules(mode: str, user_text: str) -> str:
    simple = is_simple_request(user_text, mode)
    common = (
        "Отвечай понятно и аккуратно для Telegram. "
        "Не используй Markdown: **, __, #, `, ``` и другие markdown-маркеры. "
        "Не пиши воду, повторы и лишние вступления. "
        "Если нужно оформить структуру, используй обычный текст, короткие абзацы и нумерацию 1., 2., 3."
    )
    if mode == "solve":
        if simple:
            return common + " Это очень простая задача, поэтому ответ должен быть коротким: сначала итог, потом максимум 1–2 коротких шага объяснения."
        return common + " Решай по шагам, но только по делу. Не растягивай решение. Для простой школьной задачи обычно достаточно 3–5 шагов."
    if mode == "text":
        if simple:
            return common + " Запрос короткий, поэтому дай короткий результат без лишних пояснений."
        return common + " Пиши содержательно, но компактно. Если можно ответить короче без потери смысла — отвечай короче."
    if simple:
        return common + " Вопрос простой, поэтому ответ должен быть очень коротким: 1–3 предложения."
    return common + " Если вопрос несложный, не расписывай слишком длинно."


def format_ai_text_for_telegram_html(text: str) -> str:
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return ""
    safe = html.escape(raw, quote=False)
    placeholders: list[tuple[str, str]] = []

    def _store(tag: str, content: str) -> str:
        index = len(placeholders)
        placeholders.append((tag, content))
        return f"@@BLOCK_{index}@@"

    safe = re.sub(r"```(?:[a-zA-Z0-9_+-]+)?\n?(.*?)```", lambda m: _store("pre", m.group(1).strip()), safe, flags=re.S)
    safe = re.sub(r"`([^`\n]+)`", lambda m: _store("code", m.group(1).strip()), safe)
    safe = re.sub(r"(?m)^\s*#{1,6}\s*(.+)$", r"<b>\1</b>", safe)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(r"__(.+?)__", r"<b>\1</b>", safe)
    safe = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", safe)
    safe = re.sub(r"\n{3,}", "\n\n", safe)
    for index, (tag, content) in enumerate(placeholders):
        safe = safe.replace(f"@@BLOCK_{index}@@", f"<{tag}>{content}</{tag}>")
    return safe


def build_mode_prompt(mode: str, user_text: str) -> tuple[str, str]:
    style_rules = build_style_rules(mode, user_text)
    if mode == "solve":
        system_prompt = "Ты AI-репетитор. Решай задачи понятно для ученика. Показывай только нужные шаги решения. Если данных мало — скажи, чего не хватает. Не выдумывай факты. " + style_rules
        prompt = f"Реши задачу и объясни решение:\n\n{user_text}"
        return prompt, system_prompt
    if mode == "text":
        system_prompt = "Ты AI-редактор и автор текстов. Пиши грамотно, понятно и современно. Учитывай цель, аудиторию и стиль. " + style_rules
        prompt = f"Напиши текст по запросу пользователя:\n\n{user_text}"
        return prompt, system_prompt
    if mode == "roast_answer":
        system_prompt = "Ты строгий, но полезный преподаватель. Разбери ответ ученика: что слабо, где ошибки, какая вероятная оценка и как переписать до сильной версии. Пиши жёстко, но без оскорблений. " + style_rules
        prompt = f"Разнеси ответ ученика и покажи улучшенную версию:\n\n{user_text}"
        return prompt, system_prompt
    if mode == "grade_guess":
        system_prompt = "Ты эксперт-проверяющий. Оцени, на какую отметку тянет ответ, объясни почему и как улучшить до более высокой оценки. " + style_rules
        prompt = f"Оцени ответ ученика:\n\n{user_text}"
        return prompt, system_prompt
    if mode == "make_smarter":
        system_prompt = "Ты редактор школьных ответов. Превращай сырой ответ в сильный, но естественный текст без пафоса и лишней воды. Покажи итоговую версию и кратко, что улучшил. " + style_rules
        prompt = f"Сделай этот ответ умнее и сильнее:\n\n{user_text}"
        return prompt, system_prompt
    if mode == "photo_cheat":
        system_prompt = "Ты помощник по учебе. Сожми материал в удобную шпаргалку: 5–8 ключевых мыслей, мини-формулы, определения, антиошибки. " + style_rules
        prompt = f"Сделай шпаргалку по этому материалу:\n\n{user_text}"
        return prompt, system_prompt
    if mode == "ai_detect":
        system_prompt = "Ты редактор естественной речи. Оцени, палится ли текст как написанный AI, укажи, какие фразы звучат неестественно, и покажи более живую версию. " + style_rules
        prompt = f"Проверь, палится ли этот текст как AI:\n\n{user_text}"
        return prompt, system_prompt
    system_prompt = "Ты дружелюбный AI-помощник для учебы в Telegram. Отвечай полезно и по делу. " + style_rules
    return user_text, system_prompt


async def safe_delete_status(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def safe_edit_status(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except Exception:
        await message.answer(text)


async def process_ai_request(message: Message, mode: str) -> None:
    if not await ensure_access_and_consume(message):
        return
    prompt, system_prompt = build_mode_prompt(mode, message.text)
    status_message = await message.answer("⏳ Думаю над ответом...")
    try:
        ai_settings = db.get_ai_settings()
        provider_order = [ai_settings.get("provider"), ai_settings.get("fallback_1"), ai_settings.get("fallback_2")]
        answer, provider = await ask_ai(prompt, system_prompt=system_prompt, provider_order=provider_order)
        db.add_request_log(message.from_user.id, mode, provider)
        user = db.get_user(message.from_user.id)
        formatted_answer = format_ai_text_for_telegram_html(answer)
        prefix_map = {
            "roast_answer": f"🔥 <b>Разбор ответа</b> <i>({provider})</i>\n\n",
            "grade_guess": f"📉 <b>Оценка ответа</b> <i>({provider})</i>\n\n",
            "make_smarter": f"✨ <b>Улучшенная версия</b> <i>({provider})</i>\n\n",
            "photo_cheat": f"📷 <b>Шпора</b> <i>({provider})</i>\n\n",
            "ai_detect": f"🕵️ <b>Проверка текста</b> <i>({provider})</i>\n\n",
        }
        prefix = prefix_map.get(mode, f"🤖 <b>Ответ</b> <i>({provider})</i>\n\n")
        chunks = list(split_long_text(prefix + formatted_answer))
        await safe_delete_status(status_message)
        for index, chunk in enumerate(chunks):
            if index == len(chunks) - 1 and user and not (user["is_premium"] or user["is_vip"]):
                chunk += f"\n\n💡 Осталось бесплатных запросов: <b>{user['requests_left']}</b>"
            await message.answer(chunk)
    except Exception:
        logger.exception("AI request failed")
        await safe_edit_status(status_message, "⚠️ Не удалось получить ответ от AI.\nПроверь API-ключи и попробуй ещё раз.")


async def process_ai_photo_request(message: Message, mode: str = "solve") -> None:
    if await deny_if_feature_disabled(message, "solve_by_photo"):
        return
    if not message.photo:
        await message.answer("Пришли фото задания ещё раз.")
        return
    if not await ensure_access_and_consume(message):
        return

    status_message = await message.answer("⏳ Считываю фото и обрабатываю...")
    try:
        largest = message.photo[-1]
        file = await message.bot.get_file(largest.file_id)
        image_bytes = await message.bot.download_file(file.file_path)
        caption = (message.caption or "").strip()
        if mode == "photo_cheat":
            prompt = caption or "Сделай очень короткую и понятную шпаргалку по материалу на фото: ключевые мысли, формулы, термины, антиошибки."
            system_prompt = build_style_rules("text", prompt)
            prefix = "📷 <b>Шпора по фото</b>"
        else:
            prompt = caption or "Реши задачу по фото. Сначала кратко распознай условие, затем дай понятное пошаговое решение на русском языке."
            system_prompt = build_style_rules("solve", prompt)
            prefix = "📷 <b>Решение по фото</b>"
        answer, provider = await ask_ai_with_image(
            prompt=prompt,
            image_bytes=image_bytes.read(),
            system_prompt=system_prompt,
        )
        db.add_request_log(message.from_user.id, mode, provider)
        user = db.get_user(message.from_user.id)
        formatted_answer = format_ai_text_for_telegram_html(answer)
        chunks = list(split_long_text(f"{prefix} <i>({provider})</i>\n\n" + formatted_answer))
        await safe_delete_status(status_message)
        for index, chunk in enumerate(chunks):
            if index == len(chunks) - 1 and user and not (user["is_premium"] or user["is_vip"]):
                chunk += f"\n\n💡 Осталось бесплатных запросов: <b>{user['requests_left']}</b>"
            await message.answer(chunk)
    except Exception:
        logger.exception("AI photo request failed")
        await safe_edit_status(status_message, "⚠️ Не удалось обработать фото.\nУбедись, что текст на снимке читаемый, и попробуй ещё раз.")




async def _open_user_section(message: Message, state: FSMContext, button_text: str) -> None:
    await state.clear()
    db.get_or_create_user(message.from_user.id, message.from_user.username)
    normalized_button = normalize_menu_text(button_text)

    if normalized_button in {normalize_menu_text(x) for x in USER_EXIT_TEXTS}:
        await message.answer("✅ Текущий режим закрыт. Возвращаю тебя в меню.", reply_markup=main_menu_keyboard())
        return
    if button_text == "📚 Решить задачу":
        if await deny_if_blocked_message(message):
            return
        await state.set_state(UserStates.waiting_solve)
        await message.answer("📚 <b>Режим решения задач</b>\n\nОтправь задачу текстом или фото.")
        return
    if button_text == "✍️ Написать текст":
        if await deny_if_blocked_message(message):
            return
        await state.set_state(UserStates.waiting_text)
        await message.answer("✍️ <b>Режим написания текста</b>\n\nНапиши, какой текст нужен.")
        return
    if button_text == "👤 Личный кабинет":
        if await deny_if_blocked_message(message):
            return
        await message.answer(get_profile_text(message.from_user.id))
        return
    if button_text == "💎 Купить доступ":
        if await deny_if_blocked_message(message):
            return
        await message.answer(format_prices_text(db), reply_markup=get_buy_keyboard(db, message.from_user.id))
        return
    if button_text == "🔥 Разнеси мой ответ":
        if await deny_if_blocked_message(message):
            return
        await state.set_state(UserStates.waiting_roast_answer)
        await message.answer("🔥 <b>Разнеси мой ответ</b>\n\nПришли текст ответа или решение. Я покажу слабые места, вероятную оценку и как улучшить до сильной версии.")
        return
    if button_text == "📉 Угадай оценку":
        if await deny_if_blocked_message(message):
            return
        await state.set_state(UserStates.waiting_grade_guess)
        await message.answer("📉 <b>Угадай оценку</b>\n\nПришли ответ, а я скажу, на какую оценку он тянет и что нужно исправить.")
        return
    if button_text == "✨ Сделай умнее":
        if await deny_if_blocked_message(message):
            return
        await state.set_state(UserStates.waiting_make_smarter)
        await message.answer("✨ <b>Сделай умнее</b>\n\nПришли сырой ответ, а я перепишу его в более сильную и аккуратную версию.")
        return
    if button_text == "📷 Шпора по фото":
        if await deny_if_blocked_message(message):
            return
        await state.set_state(UserStates.waiting_photo_cheat)
        await message.answer("📷 <b>Шпора по фото</b>\n\nПришли фото конспекта, задания или параграфа — сделаю краткую шпаргалку.")
        return
    if button_text == "🕵️ Палится ли AI?":
        if await deny_if_blocked_message(message):
            return
        await state.set_state(UserStates.waiting_ai_detect)
        await message.answer("🕵️ <b>Палится ли AI?</b>\n\nПришли текст, и я скажу, звучит ли он как нейросеть, и как сделать его естественнее.")
        return
    if button_text == "🎁 Ввести промокод":
        if await deny_if_blocked_message(message):
            return
        if await deny_if_feature_disabled(message, "promocodes"):
            return
        await state.set_state(UserStates.waiting_promo)
        await message.answer("🎁 <b>Ввод промокода</b>\n\nОтправь промокод одним сообщением.")
        return
    if button_text == "📣 Новости":
        if await deny_if_blocked_message(message):
            return
        if await deny_if_feature_disabled(message, "news"):
            return
        await message.answer("📣 <b>Новости и обновления</b>\n\nПодписывайся на канал: там публикуются обновления бота, акции и полезные материалы.", reply_markup=build_news_keyboard())
        return
    if button_text == "💬 Поддержка":
        if await deny_if_blocked_message(message):
            return
        if await deny_if_feature_disabled(message, "support"):
            return
        await state.set_state(UserStates.waiting_support)
        await message.answer("💬 <b>Поддержка</b>\n\nНапиши одним сообщением, в чём нужна помощь.")
        return
    if button_text == "👥 Реферальная программа":
        if await deny_if_blocked_message(message):
            return
        if await deny_if_feature_disabled(message, "referrals"):
            return
        await message.answer(build_referral_text(message.from_user.id))
        return
    if button_text == "🎓 Полезные материалы":
        if await deny_if_blocked_message(message):
            return
        if await deny_if_feature_disabled(message, "materials"):
            return
        await message.answer("🎓 <b>Полезные материалы</b>\n\nВыбери раздел ниже.", reply_markup=build_materials_keyboard())
        return
    if button_text == "❓ Помощь":
        if await deny_if_blocked_message(message):
            return
        settings = db.get_settings()
        await message.answer(settings["help_text"])
        return
    await message.answer("Выбери действие из меню ниже.", reply_markup=main_menu_keyboard())


@router.message(StateFilter(None), F.text)
async def user_state_switch(message: Message, state: FSMContext):
    text_value = (message.text or "").strip()
    normalized = normalize_menu_text(text_value)
    normalized_user_buttons = {normalize_menu_text(x) for x in (USER_MENU_BUTTONS | USER_EXIT_TEXTS)}

    if normalized not in normalized_user_buttons:
        return

    await _open_user_section(message, state, text_value)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    if await deny_if_blocked_message(message):
        return
    try:
        await message.answer(get_onboarding_text(user), reply_markup=main_menu_keyboard())
    except Exception:
        logger.exception("Failed to send /start with keyboard")
        await message.answer(get_onboarding_text(user))


@router.callback_query(F.data == "check_required_subscription")
async def check_required_subscription(callback: CallbackQuery):
    if db.is_admin(callback.from_user.id):
        await callback.answer("Ты админ, ограничения не применяются.", show_alert=True)
        return
    subscribed = await has_required_subscription(callback.bot, callback.from_user.id)
    if subscribed:
        await callback.answer("Подписка подтверждена ✅", show_alert=True)
        await callback.message.answer("✅ <b>Подписка подтверждена</b>\n\nТеперь можешь пользоваться ботом.", reply_markup=main_menu_keyboard())
    else:
        await callback.answer("Подписка пока не найдена", show_alert=True)
        await callback.message.answer(db.get_required_channel().get("text") or "Сначала подпишись на канал.", reply_markup=build_required_subscription_keyboard())


@router.message(UserStates.waiting_promo, F.text)
async def promo_input(message: Message, state: FSMContext):
    if await deny_if_blocked_message(message):
        return
    if await deny_if_feature_disabled(message, "promocodes"):
        return
    code = (message.text or "").strip()
    ok, result = db.activate_promo_code(code, message.from_user.id)
    await message.answer(("✅ " if ok else "⚠️ ") + result)
    await state.clear()


@router.message(UserStates.waiting_support, F.text)
async def support_input(message: Message, state: FSMContext):
    if await deny_if_blocked_message(message):
        return
    if await deny_if_feature_disabled(message, "support"):
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
        f"Сообщение:\n{text_value}"
    )
    for admin_id in db.admin_user_ids():
        try:
            await message.bot.send_message(admin_id, admin_text)
        except Exception:
            logger.exception("Failed to deliver support ticket %s to admin %s", ticket_id, admin_id)
    await message.answer(f"✅ <b>Сообщение отправлено</b>\n\nНомер обращения: <code>{ticket_id}</code>")
    await state.clear()


@router.callback_query(F.data.startswith("material:"))
async def material_callback(callback: CallbackQuery):
    if await deny_if_blocked_callback(callback):
        return
    if await deny_if_feature_disabled_callback(callback, "materials"):
        return
    key = callback.data.split(":", 1)[1]
    material = MATERIALS.get(key)
    if not material:
        await callback.answer("Материал не найден", show_alert=True)
        return
    title, body = material
    await callback.message.answer(f"{title}\n\n{body}")
    await callback.answer()


@router.message(F.text.func(is_dynamic_menu_button_text))
async def dynamic_menu_button_handler(message: Message, state: FSMContext):
    text_value = (message.text or "").strip()
    if not text_value:
        return
    dynamic_buttons = {item["title"]: item for item in db.get_active_menu_buttons()}
    item = dynamic_buttons.get(text_value)
    if not item:
        return
    await state.clear()
    if await deny_if_blocked_message(message):
        return
    action_type = str(item.get("action_type") or "show_text").strip().lower()
    action_value = str(item.get("action_value") or "").strip()
    if action_type == "show_text":
        await message.answer(action_value or "Кнопка сработала, но текст не задан.")
        return
    if action_type == "open_url":
        if not action_value:
            await message.answer("Для этой кнопки не настроена ссылка.")
            return
        kb = InlineKeyboardBuilder()
        kb.button(text="🔗 Открыть", url=action_value)
        await message.answer("Нажми кнопку ниже, чтобы открыть ссылку.", reply_markup=kb.as_markup())
        return
    await message.answer(action_value or "Действие кнопки пока не настроено.")


@router.callback_query(F.data == "refresh_prices")
async def refresh_prices(callback: CallbackQuery):
    if await deny_if_blocked_callback(callback):
        return
    try:
        await callback.message.edit_text(format_prices_text(db), reply_markup=get_buy_keyboard(db, callback.from_user.id))
        await callback.answer("Цены обновлены")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("Цены уже актуальны")
        else:
            raise


@router.callback_query(F.data.startswith("buy_stars_"))
async def buy_stars_callback(callback: CallbackQuery):
    if await deny_if_blocked_callback(callback):
        return
    days = int(callback.data.split("_")[-1])
    await send_stars_invoice(callback.bot, callback.message.chat.id, callback.from_user.id, days, db)
    await callback.answer("Инвойс отправлен")


@router.callback_query(F.data.in_({"buy_robo_3", "buy_robo_7", "buy_robo_30"}))
async def buy_robo_callback(callback: CallbackQuery):
    if await deny_if_blocked_callback(callback):
        return
    days = int(callback.data.split("_")[-1])
    try:
        inv_id, payment_url = await create_robokassa_payment(user_id=callback.from_user.id, days=days, db=db)
        await callback.message.answer(
            f"💳 <b>Оплата через Robokassa</b>\n\nТариф: <b>{days}</b> дней\nЗаказ: <code>{inv_id}</code>\n\nНажми кнопку ниже, чтобы перейти к оплате.",
            reply_markup=build_robokassa_payment_keyboard(payment_url),
        )
        await callback.answer("Ссылка на оплату создана")
    except Exception:
        logger.exception("Failed to create Robokassa payment")
        await callback.answer("Не удалось создать ссылку на оплату", show_alert=True)


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
    await bot.answer_pre_checkout_query(pre_checkout_query_id=pre_checkout_query.id, ok=ok, error_message=None if ok else error_message)


@router.message(UserStates.waiting_solve, F.photo)
async def solve_mode_photo(message: Message):
    await process_ai_photo_request(message, mode="solve")


@router.message(UserStates.waiting_photo_cheat, F.photo)
async def photo_cheat_mode_photo(message: Message):
    await process_ai_photo_request(message, mode="photo_cheat")



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
        db.upsert_payment(user_id=user_id, amount=float(payment.total_amount), payment_type="stars", status="succeeded", external_id=payment.telegram_payment_charge_id, days=days)
        db.activate_subscription(user_id, days)
        await message.answer(
            f"✅ <b>Оплата прошла успешно</b>\n\nПодписка активирована на <b>{days}</b> дней.\nСпособ оплаты: <b>Telegram Stars</b>\n\nТеперь можно пользоваться ботом без ограничений по подписке."
        )
    except Exception:
        logger.exception("Failed to process successful payment")
        await message.answer("Платёж получен, но при активации подписки произошла ошибка. Напиши администратору.")


@router.message(UserStates.waiting_solve, F.text)
async def solve_mode_message(message: Message):
    await process_ai_request(message, mode="solve")


@router.message(UserStates.waiting_text, F.text)
async def text_mode_message(message: Message):
    await process_ai_request(message, mode="text")


@router.message(UserStates.waiting_roast_answer, F.text)
async def roast_answer_message(message: Message):
    await process_ai_request(message, mode="roast_answer")


@router.message(UserStates.waiting_grade_guess, F.text)
async def grade_guess_message(message: Message):
    await process_ai_request(message, mode="grade_guess")


@router.message(UserStates.waiting_make_smarter, F.text)
async def make_smarter_message(message: Message):
    await process_ai_request(message, mode="make_smarter")


@router.message(UserStates.waiting_photo_cheat, F.text)
async def photo_cheat_text(message: Message):
    await process_ai_request(message, mode="photo_cheat")


@router.message(UserStates.waiting_ai_detect, F.text)
async def ai_detect_message(message: Message):
    await process_ai_request(message, mode="ai_detect")



@router.message(F.text)
async def generic_text_message(message: Message):
    if message.text and message.text.startswith("/"):
        return
    db.get_or_create_user(message.from_user.id, message.from_user.username)
    if await deny_if_blocked_message(message):
        return
    await process_ai_request(message, mode="general")


async def main() -> None:
    errors = validate_config()
    if errors:
        raise RuntimeError("; ".join(errors))
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    await bot.delete_webhook(drop_pending_updates=False)
    dp.include_router(get_admin_router(db))
    dp.include_router(router)
    robokassa_runner = None
    try:
        robokassa_runner = await start_robokassa_server(bot, db)
        logger.info("Bot polling started")
        await dp.start_polling(bot)
    finally:
        if robokassa_runner:
            await robokassa_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
