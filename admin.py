import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

from db import Database

logger = logging.getLogger(__name__)
router = Router(name="admin")

_shared_db: Optional[Database] = None


def _get_db() -> Database:
    """Reuse one Database instance per process.

    ``Database()`` runs the whole schema migration on construction and opens a new
    SQLite connection, so calling it inside every handler made each admin click do
    ~40 PRAGMA/CREATE statements. ``get_admin_router(db)`` injects the bot instance.
    """
    global _shared_db
    if _shared_db is None:
        _shared_db = Database()
    return _shared_db


class AdminStates(StatesGroup):
    user_search = State()
    grant_sub = State()
    revoke_sub = State()
    user_limit = State()
    global_limit = State()
    set_price = State()
    broadcast_all = State()
    broadcast_paid = State()
    promo_manage = State()
    bonus_manage = State()
    export_manage = State()
    support_manage = State()
    ban_manage = State()
    maintenance_manage = State()
    admin_manage = State()
    required_subscription_manage = State()
    feature_manage = State()
    menu_manage = State()


NORMALIZED_MENU_MAP = {
    "найти пользователя": "find_user",
    "статистика": "stats",
    "выдать подписку": "grant_sub",
    "забрать подписку": "revoke_sub",
    "лимит пользователю": "user_limit",
    "лимит всем": "global_limit",
    "цены": "prices",
    "рассылка всем": "broadcast_all",
    "рассылка платным": "broadcast_paid",
    "промокоды": "promos",
    "начислить бонусы": "bonus",
    "выгрузка пользователей": "export",
    "заявки поддержки": "support",
    "бан / разбан": "ban",
    "тех.работы": "maintenance",
    "админы": "admins",
    "обязательная подписка": "required_sub",
    "функции": "features",
    "кнопки меню": "menu",
    "в меню": "to_menu",
    "назад": "to_menu",
    "отмена": "to_menu",
}

ADMIN_MENU_CODES = {
    "find_user", "stats", "grant_sub", "revoke_sub", "user_limit", "global_limit",
    "prices", "broadcast_all", "broadcast_paid", "promos", "bonus", "export",
    "support", "ban", "maintenance", "admins", "required_sub", "features", "menu",
    "to_menu",
}


# Keys of the bot_features table that can be switched from the admin panel.
# The user keyboard in bot.py is built from exactly these flags.
FEATURE_LABELS = {
    "promocodes": "🎁 Промокоды",
    "support": "💬 Поддержка",
    "news": "📣 Новости",
    "materials": "🎓 Полезные материалы",
    "referrals": "👥 Реферальная программа",
    "solve_by_photo": "📷 Решение задач по фото",
}

MENU_BUTTON_TITLE_LIMIT = 64


def normalize_admin_text(value: str) -> str:
    """Lower-case admin text without emoji/punctuation noise (menu labels are compared on it)."""
    text = (value or "").replace("\xa0", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[^\wа-яё]+", "", text, flags=re.IGNORECASE)
    return text.strip()


# Exact label -> section code map. Substring matching used to swallow ordinary user
# messages: a task like "найди цены на нефть" was routed to the "Цены" admin section
# because the admin router runs before the user ones for every state.
ADMIN_MENU_LABELS = {normalize_admin_text(label): code for label, code in NORMALIZED_MENU_MAP.items()}


def resolve_admin_menu_key(value: str) -> Optional[str]:
    return ADMIN_MENU_LABELS.get(normalize_admin_text(value))


def _is_admin_menu_text(value: str) -> bool:
    return resolve_admin_menu_key(value) is not None


def _normalize_username(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip().lstrip("@").lower()
    return value or None


def _parse_any_int(value: str | None) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_positive_int(value: str | None) -> Optional[int]:
    parsed = _parse_any_int(value)
    return parsed if parsed is not None and parsed > 0 else None


def _parse_non_negative_int(value: str | None) -> Optional[int]:
    parsed = _parse_any_int(value)
    return parsed if parsed is not None and parsed >= 0 else None


def user_menu_keyboard() -> ReplyKeyboardMarkup:
    """Меню, которое админ видит после выхода из админки.

    Специально не своя копия клавиатуры: отдельный список кнопок неизбежно расходится с
    тем, что видят пользователи, — в нём уже не учитывались ни выключенные функции,
    ни кнопки, добавленные через «🧩 Кнопки меню».
    """
    from bot import main_menu_keyboard  # ленивый импорт: bot импортирует admin

    return main_menu_keyboard()


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Найти пользователя"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🎁 Выдать подписку"), KeyboardButton(text="❌ Забрать подписку")],
            [KeyboardButton(text="🎯 Лимит пользователю"), KeyboardButton(text="🌍 Лимит всем")],
            [KeyboardButton(text="💰 Цены"), KeyboardButton(text="📢 Рассылка всем")],
            [KeyboardButton(text="💸 Рассылка платным"), KeyboardButton(text="🎟 Промокоды")],
            [KeyboardButton(text="🎁 Начислить бонусы"), KeyboardButton(text="📤 Выгрузка пользователей")],
            [KeyboardButton(text="🆘 Заявки поддержки"), KeyboardButton(text="🚫 Бан / разбан")],
            [KeyboardButton(text="🛠 Тех.работы"), KeyboardButton(text="🤠 Админы")],
            [KeyboardButton(text="⚙️ Функции"), KeyboardButton(text="🧩 Кнопки меню")],
            [KeyboardButton(text="📡 Обязательная подписка"), KeyboardButton(text="🔙 В меню")],
        ],
        resize_keyboard=True,
    )


def is_admin(message: Message, db: Database) -> bool:
    return bool(message.from_user and db.is_admin(message.from_user.id))


async def deny_if_not_admin(message: Message, db: Database) -> bool:
    return not is_admin(message, db)


def _resolve_user_identifier(db: Database, raw_value: str):
    text = (raw_value or "").strip()
    if not text:
        return None, None, "Укажи USER_ID или @username."

    if text.isdigit():
        user = db.get_user(int(text))
        if not user:
            return None, None, "Пользователь с таким ID не найден."
        return int(text), user, None

    username = _normalize_username(text)
    if not username:
        return None, None, "Некорректный username."

    resolver = getattr(db, "get_user_by_username", None)
    if callable(resolver):
        user = resolver(username)
        if user:
            return int(user["id"]), user, None

    users = db.export_users(paid_only=False)
    for item in users:
        value = _normalize_username(item.get("username"))
        if value == username:
            return int(item["id"]), item, None

    return None, None, "Пользователь с таким username не найден."


async def broadcast(bot, user_ids: list[int], text: str) -> tuple[int, int]:
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


def _render_admin_menu() -> str:
    return "🛠 <b>Админ-панель</b>\n\nВыбери раздел кнопкой ниже."


def _render_admins_text(db: Database) -> str:
    rows = db.list_admins()
    parts = ["🤠 <b>Админы</b>", "", "Команды:", "• list", "• add USER_ID", "• del USER_ID", "", "Список:"]
    if not rows:
        parts.append("— пусто")
    else:
        for item in rows:
            username = f"@{item['username']}" if item.get("username") else "—"
            parts.append(f"• {item['user_id']} | {username} | роль: {item['role']}")
    return "\n".join(parts)


def _render_required_subscription_text(db: Database) -> str:
    channel = db.get_required_channel()
    enabled = "включена" if channel.get("enabled") else "выключена"
    return (
        "📡 <b>Обязательная подписка</b>\n\n"
        f"Статус: {enabled}\n"
        f"Канал ID: {channel.get('channel_id') or '—'}\n"
        f"Username: {channel.get('channel_username') or '—'}\n"
        f"Ссылка: {db.get_required_channel_link() or '—'}\n\n"
        "Как настроить правильно:\n"
        "• для открытого канала: on @channelusername\n"
        "• для надёжной проверки: on -1001234567890 @channelusername\n"
        "• для закрытого канала: on -1001234567890\n\n"
        "Важно:\n"
        "• бот должен быть добавлен в канал как администратор\n"
        "• для закрытых каналов лучше всегда указывать channel_id вида -100...\n\n"
        "Команды:\n"
        "• on @channelusername\n"
        "• on -1001234567890 @channelusername\n"
        "• on -1001234567890\n"
        "• off\n"
        "• status\n"
        "• text Новый текст блока"
    )


def _render_maintenance_text(db: Database) -> str:
    enabled = "включены" if db.is_maintenance_enabled() else "выключены"
    return (
        "🛠 <b>Тех.работы</b>\n\n"
        f"Сейчас техработы: {enabled}\n\n"
        "Команды:\n"
        "• on\n• off\n• status\n• text Новый текст\n\n"
        f"Текущий текст:\n{db.get_maintenance_text()}"
    )


def _format_promo_row(item: dict) -> str:
    expires = item.get("expires_at") or "без срока"
    if expires != "без срока":
        try:
            expires_dt = datetime.fromisoformat(str(expires))
            expires = expires_dt.strftime("%d.%m %H:%M")
        except Exception:
            expires = str(expires)
    max_acts = item.get("max_activations") or 0
    uses = f"{item.get('used_count', 0)}/{max_acts}" if max_acts else f"{item.get('used_count', 0)}/∞"
    return (
        f"• {item['code']} | {item['reward_type']}={item['reward_value']} | "
        f"uses {uses} | till {expires} | {'ON' if item['is_active'] else 'OFF'}"
    )


def _render_promo_text(db: Database) -> str:
    rows = db.list_promo_codes(limit=10)
    lines = [
        "🎟 <b>Промокоды</b>",
        "",
        "Команды:",
        "• list",
        "• create CODE requests 5",
        "• create CODE premium_days 7",
        "• create CODE vip 1",
        "• create CODE requests 5 hours 24",
        "• create CODE requests 5 uses 100",
        "• create CODE requests 5 hours 24 uses 100",
        "• on CODE",
        "• off CODE",
        "• info CODE",
        "",
        "Правила:",
        "• один и тот же пользователь не может активировать один промокод дважды",
        "• uses — лимит общих активаций",
        "• hours / days — срок действия",
        "",
        "Последние:"
    ]
    if not rows:
        lines.append("— пусто")
    else:
        for item in rows:
            lines.append(_format_promo_row(item))
    return "\n".join(lines)


def _render_ban_text() -> str:
    return "🚫 <b>Бан / разбан</b>\n\nКоманды:\n• ban USER_ID/@username причина\n• unban USER_ID/@username\n• status USER_ID/@username"


def _render_bonus_text() -> str:
    return (
        "🎁 <b>Начислить бонусы</b>\n\n"
        "Команды:\n"
        "• user USER_ID/@username REQUESTS\n"
        "• premium USER_ID/@username DAYS\n"
        "• all REQUESTS\n"
        "• paid REQUESTS"
    )


def _render_export_text() -> str:
    return "📤 <b>Выгрузка пользователей</b>\n\nКоманды:\n• all — выгрузить всех\n• paid — выгрузить платных"


def _render_features_text(db: Database) -> str:
    flags = db.get_all_features()
    lines = [
        "⚙️ <b>Функции бота</b>",
        "",
        "Команды:",
        "• on KEY",
        "• off KEY",
        "",
        "Сейчас:",
    ]
    for key, title in FEATURE_LABELS.items():
        state = "✅ включено" if flags.get(key, True) else "🚫 выключено"
        lines.append(f"• {title} — <code>{key}</code> — {state}")
    lines.append("")
    lines.append("Клавиатура пользователя обновится, когда он снова увидит меню (например, после /start).")
    return "\n".join(lines)


def _render_menu_text(db: Database) -> str:
    rows = db.list_menu_buttons()
    lines = [
        "🧩 <b>Кнопки меню</b>",
        "",
        "Команды:",
        "• list",
        "• add ЗАГОЛОВОК | text | текст, который показать",
        "• add ЗАГОЛОВОК | url | https://example.com",
        "• show ID",
        "• on ID   /   off ID",
        "• sort ID N",
        "• del ID",
        "",
        "Кнопки:",
    ]
    if not rows:
        lines.append("— пусто")
    else:
        for item in rows:
            flag = "✅" if item.get("is_active") else "🚫"
            lines.append(
                f"{flag} <code>{item['id']}</code> | {item['title']} | {item.get('action_type')} | sort {item.get('sort_order', 0)}"
            )
    lines.append("")
    lines.append(f"Максимальная длина заголовка — {MENU_BUTTON_TITLE_LIMIT} символов.")
    return "\n".join(lines)


def _render_support_text(db: Database) -> str:
    tickets = db.get_open_support_tickets(limit=10)
    lines = ["🆘 <b>Заявки поддержки</b>", "", "Команды:", "• list", "• show ID", "• reply ID текст", "• close ID", "", "Открытые заявки:"]
    if not tickets:
        lines.append("— нет открытых")
    else:
        for item in tickets:
            preview = (item["message"] or "")[:50].replace("\n", " ")
            lines.append(f"• {item['id']} | user {item['user_id']} | {preview}")
    return "\n".join(lines)


def _parse_promo_create(parts: list[str]) -> tuple[bool, str | None, dict | None]:
    if len(parts) < 4 or parts[0] != "create":
        return False, "Формат: create CODE requests 5 [hours 24] [days 7] [uses 100]", None

    code = parts[1].upper()
    reward_type = parts[2]
    value_raw = parts[3]

    if reward_type not in {"requests", "premium_days", "vip"}:
        return False, "reward_type должен быть requests, premium_days или vip", None

    if not value_raw.isdigit():
        return False, "Значение награды должно быть числом.", None

    reward_value = int(value_raw)
    max_activations = 0
    expires_at = None

    idx = 4
    while idx < len(parts):
        token = parts[idx].lower()

        if token == "uses":
            if idx + 1 >= len(parts) or not parts[idx + 1].isdigit():
                return False, "После uses нужно указать число.", None
            max_activations = int(parts[idx + 1])
            idx += 2
            continue

        if token == "hours":
            if idx + 1 >= len(parts) or not parts[idx + 1].isdigit():
                return False, "После hours нужно указать число.", None
            hours = int(parts[idx + 1])
            expires_at = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
            idx += 2
            continue

        if token == "days":
            if idx + 1 >= len(parts) or not parts[idx + 1].isdigit():
                return False, "После days нужно указать число.", None
            days = int(parts[idx + 1])
            expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
            idx += 2
            continue

        return False, f"Неизвестный параметр: {parts[idx]}", None

    return True, None, {
        "code": code,
        "reward_type": reward_type,
        "reward_value": reward_value,
        "max_activations": max_activations,
        "expires_at": expires_at,
    }


def _parse_menu_button_add(raw: str) -> Optional[tuple[str, str, str]]:
    """Parse ``ЗАГОЛОВОК | text | текст`` / ``ЗАГОЛОВОК | url | https://…``.

    ``ЗАГОЛОВОК | https://…`` works as a shortcut for url buttons. The value is
    everything after the second separator, so "|" inside long texts survives.
    """
    text = (raw or "").strip()

    if text.count("|") < 2:
        if text.count("|") == 1:
            title, _, value = (part.strip() for part in text.partition("|"))
            if title and value.startswith(("http://", "https://", "tg://")):
                return title, "open_url", value
        return None

    title, kind, value = (part.strip() for part in text.split("|", 2))
    if not title or not value:
        return None

    kind = kind.lower()
    if kind in {"url", "link", "open_url"}:
        return title, "open_url", value
    if kind in {"text", "show_text"}:
        return title, "show_text", value
    return None


async def _open_admin_section_normalized(message: Message, state: FSMContext, key: str, db: Database):
    mapping = {
        "find_user": (AdminStates.user_search, "🔎 <b>Поиск пользователя</b>\n\nОтправь USER_ID или @username"),
        "grant_sub": (AdminStates.grant_sub, "🎁 <b>Выдать подписку</b>\n\nФормат: USER_ID/@username DAYS"),
        "revoke_sub": (AdminStates.revoke_sub, "❌ <b>Забрать подписку</b>\n\nОтправь USER_ID или @username"),
        "user_limit": (AdminStates.user_limit, "🎯 <b>Лимит пользователю</b>\n\nФормат: USER_ID/@username LIMIT"),
        "global_limit": (AdminStates.global_limit, "🌍 <b>Лимит всем</b>\n\nОтправь новое значение лимита, например 10"),
        "prices": (AdminStates.set_price, "💰 <b>Цены</b>\n\nФормат: DAYS stars 100 или DAYS rub 199"),
        "broadcast_all": (AdminStates.broadcast_all, "📢 <b>Рассылка всем</b>\n\nОтправь текст сообщения."),
        "broadcast_paid": (AdminStates.broadcast_paid, "💸 <b>Рассылка платным</b>\n\nОтправь текст сообщения."),
        "promos": (AdminStates.promo_manage, _render_promo_text(db)),
        "bonus": (AdminStates.bonus_manage, _render_bonus_text()),
        "export": (AdminStates.export_manage, _render_export_text()),
        "support": (AdminStates.support_manage, _render_support_text(db)),
        "ban": (AdminStates.ban_manage, _render_ban_text()),
        "maintenance": (AdminStates.maintenance_manage, _render_maintenance_text(db)),
        "admins": (AdminStates.admin_manage, _render_admins_text(db)),
        "required_sub": (AdminStates.required_subscription_manage, _render_required_subscription_text(db)),
        "features": (AdminStates.feature_manage, _render_features_text(db)),
        "menu": (AdminStates.menu_manage, _render_menu_text(db)),
    }

    if key == "stats":
        stats = db.get_stats()
        await state.clear()
        await message.answer(
            "📊 <b>Статистика</b>\n\n"
            f"Всего пользователей: {stats['users']}\n"
            f"Платных пользователей: {stats['paid']}\n"
            f"Запросов сегодня: {stats['requests_today']}\n"
            f"Доход Stars: {stats['stars']}\n"
            f"Доход RUB: {stats['rub']}",
            reply_markup=admin_keyboard(),
        )
        return

    target = mapping.get(key)
    if not target:
        return

    await state.set_state(target[0])
    await message.answer(target[1], reply_markup=admin_keyboard())


@router.message(Command("admin"))
async def admin_entry(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    await state.clear()
    await message.answer(_render_admin_menu(), reply_markup=admin_keyboard())


@router.message(StateFilter("*"), Command("start"))
async def admin_start_exit(message: Message, state: FSMContext):
    db = _get_db()
    if not is_admin(message, db):
        raise SkipHandler()
    await state.clear()
    await message.answer(
        "👋 <b>Привет, админ.</b>\n\n"
        "Ты вышел из текущего режима и вернулся в обычное меню.",
        reply_markup=user_menu_keyboard(),
    )


@router.message(StateFilter("*"), F.text.func(_is_admin_menu_text))
async def admin_menu_router(message: Message, state: FSMContext):
    db = _get_db()
    if not is_admin(message, db):
        raise SkipHandler()

    key = resolve_admin_menu_key(message.text or "")
    if not key:
        raise SkipHandler()
    if key == "to_menu":
        await state.clear()
        await message.answer(
            "✅ Выход из админки.\nВозвращаю в обычное меню.",
            reply_markup=user_menu_keyboard(),
        )
        return

    await _open_admin_section_normalized(message, state, key, db)


@router.message(AdminStates.user_search)
async def handle_user_search(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    user_id, user, error = _resolve_user_identifier(db, message.text or "")
    if error or not user:
        await message.answer(error or "Пользователь не найден.")
        return
    username = f"@{user['username']}" if user.get("username") else "—"
    await message.answer(
        f"👤 <b>Пользователь</b>\n\n"
        f"ID: <code>{user['id']}</code>\n"
        f"Username: {username}\n"
        f"Запросов: {user['requests_left']}\n"
        f"Premium: {'Да' if user['is_premium'] else 'Нет'}\n"
        f"VIP: {'Да' if user['is_vip'] else 'Нет'}\n"
        f"Sub until: {user['sub_until'] or '—'}"
    )


@router.message(AdminStates.grant_sub)
async def handle_grant_sub(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Формат: USER_ID/@username DAYS")
        return
    days = _parse_positive_int(parts[1])
    if days is None:
        await message.answer("Количество дней должно быть положительным числом.")
        return
    user_id, _user, error = _resolve_user_identifier(db, parts[0])
    if error or user_id is None:
        await message.answer(error or "Пользователь не найден.")
        return
    db.activate_subscription(user_id, days)
    await message.answer(f"✅ Подписка выдана на {days} дн.")


@router.message(AdminStates.revoke_sub)
async def handle_revoke_sub(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    user_id, _user, error = _resolve_user_identifier(db, message.text or "")
    if error or user_id is None:
        await message.answer(error or "Пользователь не найден.")
        return
    db.revoke_subscription(user_id)
    await message.answer("✅ Подписка забрана.")


@router.message(AdminStates.user_limit)
async def handle_user_limit(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Формат: USER_ID/@username LIMIT")
        return
    limit = _parse_non_negative_int(parts[1])
    if limit is None:
        await message.answer("Лимит должен быть числом 0 или больше.")
        return
    user_id, _user, error = _resolve_user_identifier(db, parts[0])
    if error or user_id is None:
        await message.answer(error or "Пользователь не найден.")
        return
    db.set_user_requests(user_id, limit)
    await message.answer("✅ Лимит пользователя обновлён.")


@router.message(AdminStates.global_limit)
async def handle_global_limit(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    limit = _parse_non_negative_int(text)
    if limit is None:
        await message.answer("Нужно целое число 0 или больше")
        return
    db.set_all_users_requests(limit)
    await message.answer("✅ Лимит для всех обновлён.")


@router.message(AdminStates.set_price)
async def handle_set_price(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[0] not in {"3", "7", "30"} or parts[1] not in {"stars", "rub"}:
        await message.answer("Формат: DAYS stars|rub VALUE")
        return
    value = _parse_positive_int(parts[2])
    if value is None:
        await message.answer("Цена должна быть положительным числом.")
        return
    days = int(parts[0])
    if parts[1] == "stars":
        db.set_price(days, stars=value)
    else:
        db.set_price(days, rub=value)
    await message.answer("✅ Цена обновлена.")


@router.message(AdminStates.broadcast_all)
async def handle_broadcast_all(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ Пустое сообщение. Отправь текст рассылки одним сообщением.")
        return
    sent, failed = await broadcast(message.bot, db.get_all_user_ids(), text)
    await message.answer(f"✅ Рассылка завершена.\nОтправлено: {sent}, ошибок: {failed}")


@router.message(AdminStates.broadcast_paid)
async def handle_broadcast_paid(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ Пустое сообщение. Отправь текст рассылки одним сообщением.")
        return
    sent, failed = await broadcast(message.bot, db.get_paid_user_ids(), text)
    await message.answer(f"✅ Рассылка платным завершена.\nОтправлено: {sent}, ошибок: {failed}")


@router.message(AdminStates.promo_manage)
async def handle_promo(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return

    parts = (message.text or "").split()
    if not parts:
        await message.answer(_render_promo_text(db))
        return

    cmd = parts[0].lower()

    if cmd == "list":
        await message.answer(_render_promo_text(db))
        return

    if cmd == "create":
        ok, error, payload = _parse_promo_create(parts)
        if not ok or not payload:
            await message.answer(error or "Некорректная команда.")
            return

        try:
            db.create_promo_code(
                payload["code"],
                payload["reward_type"],
                payload["reward_value"],
                max_activations=payload["max_activations"],
                expires_at=payload["expires_at"],
                is_active=True,
            )
        except Exception as e:
            await message.answer(f"Не удалось создать промокод: {e}")
            return

        expires_text = "без срока"
        if payload["expires_at"]:
            try:
                expires_text = datetime.fromisoformat(payload["expires_at"]).strftime("%d.%m.%Y %H:%M")
            except Exception:
                expires_text = str(payload["expires_at"])

        uses_text = payload["max_activations"] if payload["max_activations"] else "∞"

        await message.answer(
            "✅ Промокод создан.\n\n"
            f"Код: {payload['code']}\n"
            f"Награда: {payload['reward_type']}={payload['reward_value']}\n"
            f"Лимит использований: {uses_text}\n"
            f"Срок действия: {expires_text}\n\n"
            "Один пользователь не сможет активировать этот промокод больше одного раза."
        )
        return

    if cmd in {"on", "off"} and len(parts) == 2:
        db.set_promo_active(parts[1], cmd == "on")
        await message.answer("✅ Статус промокода обновлён.")
        return

    if cmd == "info" and len(parts) == 2:
        promo = db.get_promo_code(parts[1])
        if not promo:
            await message.answer("Промокод не найден.")
            return

        expires = promo.get("expires_at") or "без срока"
        if expires != "без срока":
            try:
                expires = datetime.fromisoformat(str(expires)).strftime("%d.%m.%Y %H:%M")
            except Exception:
                expires = str(expires)

        max_acts = promo.get("max_activations") or 0
        uses = f"{promo.get('used_count', 0)}/{max_acts}" if max_acts else f"{promo.get('used_count', 0)}/∞"

        await message.answer(
            f"🎟 <b>{promo['code']}</b>\n\n"
            f"Тип: {promo['reward_type']}\n"
            f"Значение: {promo['reward_value']}\n"
            f"Использований: {uses}\n"
            f"Срок действия: {expires}\n"
            f"Статус: {'ON' if promo['is_active'] else 'OFF'}\n\n"
            "Повторная активация одним и тем же пользователем запрещена."
        )
        return

    await message.answer(_render_promo_text(db))


@router.message(AdminStates.bonus_manage)
async def handle_bonus(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if not parts:
        await message.answer(_render_bonus_text())
        return

    if parts[0] == "user" and len(parts) == 3 and _parse_any_int(parts[2]) is not None:
        user_id, _user, error = _resolve_user_identifier(db, parts[1])
        if error or user_id is None:
            await message.answer(error or "Пользователь не найден.")
            return
        db.add_user_requests(user_id, _parse_any_int(parts[2]) or 0)
        await message.answer("✅ Запросы начислены.")
        return

    if parts[0] == "premium" and len(parts) == 3 and _parse_positive_int(parts[2]) is not None:
        user_id, _user, error = _resolve_user_identifier(db, parts[1])
        if error or user_id is None:
            await message.answer(error or "Пользователь не найден.")
            return
        db.activate_subscription(user_id, _parse_positive_int(parts[2]) or 0)
        await message.answer("✅ Подписка выдана.")
        return

    if parts[0] == "all" and len(parts) == 2 and _parse_any_int(parts[1]) is not None:
        count = db.add_requests_to_all(_parse_any_int(parts[1]) or 0, paid_only=False)
        await message.answer(f"✅ Начислено всем.\nОбновлено пользователей: {count}")
        return

    if parts[0] == "paid" and len(parts) == 2 and _parse_any_int(parts[1]) is not None:
        count = db.add_requests_to_all(_parse_any_int(parts[1]) or 0, paid_only=True)
        await message.answer(f"✅ Начислено платным.\nОбновлено пользователей: {count}")
        return

    await message.answer(_render_bonus_text())


@router.message(AdminStates.export_manage)
async def handle_export(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if text not in {"all", "paid"}:
        await message.answer(_render_export_text())
        return
    data = db.export_users_csv(paid_only=(text == "paid"))
    await message.answer_document(BufferedInputFile(data, filename=f"users_{text}.csv"))


@router.message(AdminStates.support_manage)
async def handle_support_manage(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split(maxsplit=2)
    if not parts:
        await message.answer(_render_support_text(db))
        return
    if parts[0] == "list":
        await message.answer(_render_support_text(db))
        return
    if parts[0] == "show" and len(parts) == 2 and parts[1].isdigit():
        ticket = db.get_support_ticket(int(parts[1]))
        if not ticket:
            await message.answer("Заявка не найдена.")
        else:
            await message.answer(
                f"🆘 <b>Заявка #{ticket['id']}</b>\n"
                f"User: <code>{ticket['user_id']}</code>\n"
                f"Status: {ticket['status']}\n\n"
                f"Сообщение:\n{ticket['message']}\n\n"
                f"Ответ:\n{ticket['admin_reply'] or '—'}"
            )
        return
    if parts[0] == "reply" and len(parts) == 3 and parts[1].isdigit():
        ticket_id = int(parts[1])
        db.reply_support_ticket(ticket_id, parts[2])
        ticket = db.get_support_ticket(ticket_id)
        if ticket:
            try:
                await message.bot.send_message(ticket["user_id"], f"💬 <b>Ответ поддержки</b>\n\n{parts[2]}")
            except Exception:
                logger.exception("Failed to deliver support reply")
        await message.answer("✅ Ответ отправлен.")
        return
    if parts[0] == "close" and len(parts) == 2 and parts[1].isdigit():
        db.close_support_ticket(int(parts[1]))
        await message.answer("✅ Заявка закрыта.")
        return
    await message.answer(_render_support_text(db))


@router.message(AdminStates.ban_manage)
async def handle_ban(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if text == "list":
        rows = db.list_banned_users()
        if not rows:
            await message.answer("🚫 <b>Заблокированные</b>\n\n— пусто")
            return
        lines = ["🚫 <b>Заблокированные</b>", ""]
        for item in rows:
            username = f"@{item['username']}" if item.get("username") else "—"
            reason = (item.get("ban_reason") or "без причины").replace("\n", " ")
            lines.append(f"• <code>{item['id']}</code> | {username} | {reason}")
        await message.answer("\n".join(lines))
        return
    if len(parts) >= 2 and parts[0] == "ban":
        user_id, _user, error = _resolve_user_identifier(db, parts[1])
        if error or user_id is None:
            await message.answer(error or "Пользователь не найден.")
            return
        reason = parts[2] if len(parts) > 2 else "Без причины"
        db.ban_user(user_id, reason, message.from_user.id)
        await message.answer("✅ Пользователь забанен.")
        return
    if len(parts) == 2 and parts[0] == "unban":
        user_id, _user, error = _resolve_user_identifier(db, parts[1])
        if error or user_id is None:
            await message.answer(error or "Пользователь не найден.")
            return
        db.unban_user(user_id)
        await message.answer("✅ Пользователь разбанен.")
        return
    if len(parts) == 2 and parts[0] == "status":
        user_id, _user, error = _resolve_user_identifier(db, parts[1])
        if error or user_id is None:
            await message.answer(error or "Пользователь не найден.")
            return
        st = db.get_ban_status(user_id)
        await message.answer(f"Статус: {'BAN' if st['is_banned'] else 'OK'}\nПричина: {st['reason'] or '—'}")
        return
    await message.answer(_render_ban_text())


@router.message(AdminStates.maintenance_manage)
async def handle_maintenance(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if text == "on":
        db.set_maintenance_mode(True)
        await message.answer("✅ Техработы включены.")
        return
    if text == "off":
        db.set_maintenance_mode(False)
        await message.answer("✅ Техработы выключены.")
        return
    if text == "status":
        await message.answer(_render_maintenance_text(db))
        return
    if text.startswith("text "):
        db.set_maintenance_mode(db.is_maintenance_enabled(), text[5:].strip())
        await message.answer("✅ Текст техработ обновлён.")
        return
    await message.answer(_render_maintenance_text(db))


@router.message(AdminStates.admin_manage)
async def handle_admin_manage(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split(maxsplit=2)
    if (message.text or "").strip() == "list":
        await message.answer(_render_admins_text(db))
        return
    if len(parts) >= 2 and parts[0] == "add" and parts[1].isdigit():
        role = parts[2] if len(parts) > 2 else "admin"
        db.add_admin(int(parts[1]), role)
        await message.answer("✅ Админ добавлен.")
        return
    if len(parts) == 2 and parts[0] == "del" and parts[1].isdigit():
        db.remove_admin(int(parts[1]))
        await message.answer("✅ Админ удалён.")
        return
    await message.answer(_render_admins_text(db))


@router.message(AdminStates.required_subscription_manage)
async def handle_required_sub(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    parts = text.split()

    if text == "off":
        db.set_required_channel(None, None, False)
        await message.answer("✅ Обязательная подписка выключена.")
        return

    if text == "status":
        await message.answer(_render_required_subscription_text(db))
        return

    if text.startswith("text "):
        db.set_required_subscription_text(text[5:].strip())
        await message.answer("✅ Текст обязательной подписки обновлён.")
        return

    if parts and parts[0] == "on":
        if len(parts) == 2:
            value = parts[1]
            if value.startswith("-100"):
                db.set_required_channel(value, None, True)
                await message.answer(
                    "✅ Обязательная подписка включена.\n\n"
                    "Сохранён channel_id без username. Это подходит для закрытых каналов."
                )
                return
            db.set_required_channel(None, value, True)
            await message.answer(
                "✅ Обязательная подписка включена.\n\n"
                "Для закрытых каналов лучше указывать channel_id вида -100..."
            )
            return

        if len(parts) == 3:
            db.set_required_channel(parts[1], parts[2], True)
            await message.answer(
                "✅ Обязательная подписка включена.\n\n"
                "Сохранены channel_id и username. Это лучший вариант для стабильной проверки."
            )
            return

    await message.answer(_render_required_subscription_text(db))


@router.message(AdminStates.feature_manage)
async def handle_features_manage(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2:
        action = parts[0].strip().lower()
        if action in {"on", "off"}:
            feature = normalize_admin_text(parts[1])
            if feature not in FEATURE_LABELS:
                await message.answer(
                    "Неизвестный ключ функции.\n\nДоступны: " + ", ".join(f"<code>{k}</code>" for k in FEATURE_LABELS)
                )
                return
            db.set_feature_enabled(feature, action == "on")
            await message.answer(_render_features_text(db))
            return
    await message.answer(_render_features_text(db))


@router.message(AdminStates.menu_manage)
async def handle_menu_manage(message: Message, state: FSMContext):
    db = _get_db()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if not text or text.lower() == "list":
        await message.answer(_render_menu_text(db))
        return

    if text.lower().startswith("add "):
        parsed = _parse_menu_button_add(text[4:])
        if not parsed:
            await message.answer(
                "Формат:\n• add ЗАГОЛОВОК | text | текст кнопки\n• add ЗАГОЛОВОК | url | https://example.com"
            )
            return
        title, action_type, action_value = parsed
        if len(title) > MENU_BUTTON_TITLE_LIMIT:
            await message.answer(f"Заголовок длиннее {MENU_BUTTON_TITLE_LIMIT} символов, сократи его.")
            return
        if action_type == "open_url" and not action_value.startswith(("http://", "https://", "tg://")):
            await message.answer("Для url-кнопки нужна ссылка, начинающаяся с http://, https:// или tg://.")
            return
        if not action_value:
            await message.answer("Действие кнопки не может быть пустым.")
            return
        button_id = db.add_menu_button(title, action_type, action_type, action_value)
        await message.answer(f"✅ Кнопка добавлена. ID: <code>{button_id}</code>\n\n{_render_menu_text(db)}")
        return

    parts = text.split(maxsplit=2)
    action = parts[0].strip().lower()
    if action in {"on", "off"} and len(parts) == 2:
        button_id = _parse_positive_int(parts[1])
        if button_id is None or not db.get_menu_button(button_id):
            await message.answer("Кнопка с таким ID не найдена.")
            return
        db.set_menu_button_active(button_id, action == "on")
        await message.answer(_render_menu_text(db))
        return
    if action == "del" and len(parts) == 2:
        button_id = _parse_positive_int(parts[1])
        if button_id is None or not db.get_menu_button(button_id):
            await message.answer("Кнопка с таким ID не найдена.")
            return
        db.delete_menu_button(button_id)
        await message.answer(_render_menu_text(db))
        return
    if action == "sort" and len(parts) == 3:
        button_id = _parse_positive_int(parts[1])
        order = _parse_non_negative_int(parts[2])
        if button_id is None or order is None or not db.get_menu_button(button_id):
            await message.answer("Формат: sort ID N, где ID и N — числа.")
            return
        db.set_menu_button_sort(button_id, order)
        await message.answer(_render_menu_text(db))
        return
    if action == "show" and len(parts) == 2:
        button_id = _parse_positive_int(parts[1])
        item = db.get_menu_button(button_id) if button_id is not None else None
        if not item:
            await message.answer("Кнопка с таким ID не найдена.")
            return
        await message.answer(
            f"🧩 <b>{item['title']}</b>\n\n"
            f"ID: <code>{item['id']}</code>\n"
            f"Тип: {item.get('button_type')}\n"
            f"Действие: {item.get('action_type')}\n"
            f"Активна: {'да' if item.get('is_active') else 'нет'}\n"
            f"Порядок: {item.get('sort_order', 0)}\n\n"
            f"Значение:\n{item.get('action_value') or '—'}"
        )
        return

    await message.answer(_render_menu_text(db))


def get_admin_router(db: Optional[Database] = None) -> Router:
    """Admin router. The bot passes its own Database instance so that a single
    connection configuration and schema migration is used for the whole process."""
    global _shared_db
    if db is not None:
        _shared_db = db
    return router
