import logging
import re
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
    "в меню": "to_menu",
    "назад": "to_menu",
    "отмена": "to_menu",
}

ADMIN_MENU_CODES = {
    "find_user", "stats", "grant_sub", "revoke_sub", "user_limit", "global_limit",
    "prices", "broadcast_all", "broadcast_paid", "promos", "bonus", "export",
    "support", "ban", "maintenance", "admins", "required_sub", "to_menu",
}


def normalize_admin_text(value: str) -> str:
    text = (value or "").replace("\xa0", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[^\wа-яё]+", "", text, flags=re.IGNORECASE)
    text = text.strip()

    for human, code in NORMALIZED_MENU_MAP.items():
        if human in text:
            return code

    return text


def _is_admin_menu_text(value: str) -> bool:
    return normalize_admin_text(value) in ADMIN_MENU_CODES


def user_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Решить задачу"), KeyboardButton(text="✍️ Написать текст")],
            [KeyboardButton(text="👤 Личный кабинет"), KeyboardButton(text="💎 Купить доступ")],
            [KeyboardButton(text="🔥 Разнеси мой ответ"), KeyboardButton(text="📉 Угадай оценку")],
            [KeyboardButton(text="✨ Сделай умнее"), KeyboardButton(text="📷 Шпора по фото")],
            [KeyboardButton(text="🕵️ Палится ли AI?"), KeyboardButton(text="🎁 Ввести промокод")],
            [KeyboardButton(text="📣 Новости"), KeyboardButton(text="💬 Поддержка")],
            [KeyboardButton(text="👥 Реферальная программа"), KeyboardButton(text="🎓 Полезные материалы")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
    )


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
            [KeyboardButton(text="📡 Обязательная подписка"), KeyboardButton(text="🔙 В меню")],
        ],
        resize_keyboard=True,
    )


def is_admin(message: Message, db: Database) -> bool:
    return bool(message.from_user and db.is_admin(message.from_user.id))


async def deny_if_not_admin(message: Message, db: Database) -> bool:
    return not is_admin(message, db)


def _normalize_username(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip().lstrip("@").lower()
    return value or None


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


def _render_promo_text(db: Database) -> str:
    rows = db.list_promo_codes(limit=10)
    lines = [
        "🎟 <b>Промокоды</b>", "", "Команды:", "• list", "• create CODE requests 5",
        "• create CODE premium_days 7", "• create CODE vip 1", "• on CODE", "• off CODE",
        "• info CODE", "", "Последние:"
    ]
    if not rows:
        lines.append("— пусто")
    else:
        for item in rows:
            lines.append(
                f"• {item['code']} | {item['reward_type']}={item['reward_value']} | "
                f"used {item['used_count']} | {'ON' if item['is_active'] else 'OFF'}"
            )
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
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    await state.clear()
    await message.answer(_render_admin_menu(), reply_markup=admin_keyboard())


@router.message(StateFilter("*"), Command("start"))
async def admin_start_exit(message: Message, state: FSMContext):
    db = Database()
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
    db = Database()
    if not is_admin(message, db):
        raise SkipHandler()

    key = normalize_admin_text(message.text or "")
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
    db = Database()
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
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: USER_ID/@username DAYS")
        return
    user_id, _user, error = _resolve_user_identifier(db, parts[0])
    if error or user_id is None:
        await message.answer(error or "Пользователь не найден.")
        return
    db.activate_subscription(user_id, int(parts[1]))
    await message.answer(f"✅ Подписка выдана на {int(parts[1])} дн.")


@router.message(AdminStates.revoke_sub)
async def handle_revoke_sub(message: Message, state: FSMContext):
    db = Database()
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
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: USER_ID/@username LIMIT")
        return
    user_id, _user, error = _resolve_user_identifier(db, parts[0])
    if error or user_id is None:
        await message.answer(error or "Пользователь не найден.")
        return
    db.set_user_requests(user_id, int(parts[1]))
    await message.answer("✅ Лимит пользователя обновлён.")


def get_admin_router(db: Optional[Database] = None) -> Router:
    return router
