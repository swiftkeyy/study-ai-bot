import logging
import re
from typing import Any, Optional

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
    menu = State()

    search_wait_identifier = State()

    grant_choose_days = State()
    grant_wait_identifier = State()

    revoke_wait_identifier = State()

    user_limit_wait_identifier = State()
    user_limit_wait_value = State()

    prices_choose_days = State()
    prices_choose_currency = State()
    prices_wait_value = State()

    support_wait_ticket_id = State()
    support_wait_reply_ticket_id = State()
    support_wait_reply_text = State()
    support_wait_close_ticket_id = State()

    ban_choose_action = State()
    ban_wait_identifier = State()
    ban_wait_reason = State()

    maintenance_wait_text = State()

    global_limit_wait_value = State()

    broadcast_all_wait_text = State()
    broadcast_paid_wait_text = State()

    promo_choose_action = State()
    promo_wait_code = State()
    promo_wait_create_reward_type = State()
    promo_wait_create_reward_value = State()
    promo_wait_toggle_code = State()
    promo_wait_info_code = State()

    bonus_choose_action = State()
    bonus_wait_identifier = State()
    bonus_wait_value = State()
    bonus_wait_scope_value = State()

    export_choose_scope = State()

    admins_choose_action = State()
    admins_wait_user_id = State()
    admins_wait_role = State()

    required_sub_choose_action = State()
    required_sub_wait_username = State()
    required_sub_wait_channel_id = State()
    required_sub_wait_text = State()


SECTION_LABELS = {
    "search": "🔎 Найти пользователя",
    "stats": "📊 Статистика",
    "grant": "🎁 Выдать подписку",
    "revoke": "❌ Забрать подписку",
    "user_limit": "🎯 Лимит пользователю",
    "prices": "💰 Цены",
    "support": "🆘 Заявки поддержки",
    "ban": "🚫 Бан / разбан",
    "maintenance": "🛠 Тех.работы",
    "global_limit": "🌍 Лимит всем",
    "broadcast_all": "📢 Рассылка всем",
    "broadcast_paid": "💸 Рассылка платным",
    "promos": "🎟 Промокоды",
    "bonus": "🎁 Начислить бонусы",
    "export": "📤 Выгрузка пользователей",
    "admins": "🤠 Админы",
    "required_sub": "📡 Обязательная подписка",
    "to_menu": "🔙 В меню",
}

TOP_LEVEL_CODES = set(SECTION_LABELS)
EXIT_ALIASES = {"🔙 В меню", "↩ В меню", "❌ Отмена", "Отмена", "Назад", "В меню"}
BACK_TO_ADMIN = "⬅️ Назад в админку"
BACK_TO_SECTION = "⬅️ Назад"
CANCEL_ACTION = "❌ Отмена"

PROMO_REWARD_LABELS = {
    "➕ Запросы": "requests",
    "📅 Premium дни": "premium_days",
    "⭐ VIP": "vip",
}

BONUS_ACTION_LABELS = {
    "👤 Пользователю запросы": "user_requests",
    "👤 Пользователю premium": "user_premium",
    "🌍 Всем запросы": "all_requests",
    "💸 Платным запросы": "paid_requests",
}


def normalize_admin_text(value: str) -> str:
    text = (value or "").replace("\xa0", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def is_admin(message: Message, db: Database) -> bool:
    return bool(message.from_user and db.is_admin(message.from_user.id))


async def deny_if_not_admin(message: Message, db: Database) -> bool:
    return not is_admin(message, db)


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
            [KeyboardButton(text=SECTION_LABELS["search"]), KeyboardButton(text=SECTION_LABELS["stats"])],
            [KeyboardButton(text=SECTION_LABELS["grant"]), KeyboardButton(text=SECTION_LABELS["revoke"])],
            [KeyboardButton(text=SECTION_LABELS["user_limit"]), KeyboardButton(text=SECTION_LABELS["prices"])],
            [KeyboardButton(text=SECTION_LABELS["support"]), KeyboardButton(text=SECTION_LABELS["ban"])],
            [KeyboardButton(text=SECTION_LABELS["maintenance"]), KeyboardButton(text=SECTION_LABELS["global_limit"])],
            [KeyboardButton(text=SECTION_LABELS["broadcast_all"]), KeyboardButton(text=SECTION_LABELS["broadcast_paid"])],
            [KeyboardButton(text=SECTION_LABELS["promos"]), KeyboardButton(text=SECTION_LABELS["bonus"])],
            [KeyboardButton(text=SECTION_LABELS["export"]), KeyboardButton(text=SECTION_LABELS["admins"])],
            [KeyboardButton(text=SECTION_LABELS["required_sub"]), KeyboardButton(text=SECTION_LABELS["to_menu"])],
        ],
        resize_keyboard=True,
    )


def simple_keyboard(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=item) for item in row] for row in rows],
        resize_keyboard=True,
    )


def section_keyboard(section: str, rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return simple_keyboard(rows + [[BACK_TO_ADMIN, CANCEL_ACTION]])


def _render_admin_menu() -> str:
    return "🛠 Админ-панель\n\nВыбери раздел кнопкой ниже."


def _render_admins_text(db: Database) -> str:
    rows = db.list_admins()
    parts = ["🤠 Админы", "", "Список:"]
    if not rows:
        parts.append("— пусто")
    else:
        for item in rows:
            username = f"@{item['username']}" if item.get("username") else "—"
            parts.append(f"• `{item['user_id']}` | {username} | роль: {item['role']}")
    return "\n".join(parts)


def _render_required_subscription_text(db: Database) -> str:
    channel = db.get_required_channel()
    enabled = "включена" if channel.get("enabled") else "выключена"
    return (
        "📡 Обязательная подписка\n\n"
        f"Статус: {enabled}\n"
        f"Канал ID: `{channel.get('channel_id') or '—'}`\n"
        f"Username: `{channel.get('channel_username') or '—'}`\n"
        f"Ссылка: {db.get_required_channel_link() or '—'}\n\n"
        f"Текст блока:\n{channel.get('text') or '—'}"
    )


def _render_maintenance_text(db: Database) -> str:
    enabled = "включены" if db.is_maintenance_enabled() else "выключены"
    return (
        "🛠 Тех.работы\n\n"
        f"Сейчас техработы: {enabled}\n\n"
        f"Текущий текст:\n{db.get_maintenance_text()}"
    )


def _render_promo_text(db: Database) -> str:
    rows = db.list_promo_codes(limit=10)
    lines = ["🎟 Промокоды", "", "Последние:"]
    if not rows:
        lines.append("— пусто")
    else:
        for item in rows:
            lines.append(
                f"• `{item['code']}` | {item['reward_type']}={item['reward_value']} | used {item['used_count']} | {'ON' if item['is_active'] else 'OFF'}"
            )
    return "\n".join(lines)


def _render_ban_text(db: Database, identifier: Optional[str] = None) -> str:
    if not identifier:
        return "🚫 Бан / разбан\n\nВыбери действие кнопкой ниже."
    user_id, user, error = resolve_user_identifier(db, identifier)
    if error or not user:
        return error or "Пользователь не найден."
    return (
        "👤 Статус пользователя\n\n"
        f"ID: `{user_id}`\n"
        f"Username: @{user['username']}\n" if user.get('username') else f"ID: `{user_id}`\n"
    )


def _render_bonus_text() -> str:
    return "🎁 Начислить бонусы\n\nВыбери действие кнопкой ниже."


def _render_export_text() -> str:
    return "📤 Выгрузка пользователей\n\nВыбери, кого выгружать."


def _render_support_text(db: Database) -> str:
    tickets = db.get_open_support_tickets(limit=10)
    lines = ["🆘 Заявки поддержки", "", "Открытые заявки:"]
    if not tickets:
        lines.append("— нет открытых")
    else:
        for item in tickets:
            preview = (item["message"] or "")[:50].replace("\n", " ")
            lines.append(f"• `{item['id']}` | user `{item['user_id']}` | {preview}")
    return "\n".join(lines)


def search_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("search", [["🆔 Поиск по ID или username"]])


def grant_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("grant", [["3 дня", "7 дней", "30 дней"], ["Свое значение"]])


def revoke_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("revoke", [["🗑 Указать пользователя"]])


def user_limit_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("user_limit", [["🧾 Выбрать пользователя"]])


def prices_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("prices", [["3 дня", "7 дней", "30 дней"], ["Показать цены"]])


def prices_currency_keyboard() -> ReplyKeyboardMarkup:
    return simple_keyboard([["⭐ Stars", "💳 RUB"], [BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]])


def support_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("support", [["📋 Открытые заявки", "🔍 Показать заявку"], ["💬 Ответить", "✅ Закрыть заявку"]])


def ban_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("ban", [["🚫 Забанить", "✅ Разбанить"], ["📍 Проверить статус"]])


def maintenance_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("maintenance", [["🟢 Включить", "⚪ Выключить"], ["📄 Показать статус", "✏️ Изменить текст"]])


def global_limit_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("global_limit", [["🔢 Установить лимит всем"]])


def broadcast_section_keyboard(kind: str) -> ReplyKeyboardMarkup:
    title = "📢 Написать сообщение" if kind == "all" else "💸 Написать сообщение"
    return section_keyboard(kind, [[title]])


def promo_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("promos", [["📋 Список", "➕ Создать"], ["🟢 Включить", "⚪ Выключить"], ["ℹ️ Инфо"]])


def promo_reward_keyboard() -> ReplyKeyboardMarkup:
    return simple_keyboard([["➕ Запросы", "📅 Premium дни"], ["⭐ VIP"], [BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]])


def bonus_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("bonus", [["👤 Пользователю запросы", "👤 Пользователю premium"], ["🌍 Всем запросы", "💸 Платным запросы"]])


def export_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("export", [["👥 Все пользователи", "💸 Платные пользователи"]])


def admins_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("admins", [["📋 Список", "➕ Добавить"], ["🗑 Удалить"]])


def required_sub_section_keyboard() -> ReplyKeyboardMarkup:
    return section_keyboard("required_sub", [["🟢 Включить по username", "🟢 Включить по ID + username"], ["⚪ Выключить", "📄 Показать статус"], ["✏️ Изменить текст"]])


def _clean_username(username: str) -> str:
    value = (username or "").strip()
    if value.startswith("@"):
        value = value[1:]
    return value.lower()


def resolve_user_identifier(db: Database, raw_value: str) -> tuple[Optional[int], Optional[dict[str, Any]], Optional[str]]:
    value = (raw_value or "").strip()
    if not value:
        return None, None, "Укажи USER_ID или username."

    if value.isdigit():
        user = db.get_user(int(value))
        if not user:
            return None, None, "Пользователь с таким ID не найден."
        return int(value), user, None

    username = _clean_username(value)
    if not username:
        return None, None, "Некорректный username."

    user = None
    if hasattr(db, "get_user_by_username"):
        try:
            user = db.get_user_by_username(username)
        except Exception:
            user = None

    if user is None:
        try:
            rows = db.export_users(paid_only=False)
        except Exception:
            rows = []
        for item in rows:
            if _clean_username(str(item.get("username") or "")) == username:
                user = item
                break

    if not user:
        return None, None, "Пользователь с таким username не найден в базе."
    return int(user["id"]), user, None


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


async def show_admin_menu(message: Message, state: FSMContext, text: Optional[str] = None) -> None:
    await state.set_state(AdminStates.menu)
    await state.update_data(section=None, pending_action=None)
    await message.answer(text or _render_admin_menu(), reply_markup=admin_keyboard())


async def handle_common_navigation(message: Message, state: FSMContext, db: Database) -> bool:
    text = (message.text or "").strip()
    if text in EXIT_ALIASES or text == SECTION_LABELS["to_menu"]:
        await state.clear()
        await message.answer("✅ Выход из админки.\nВозвращаю в обычное меню.", reply_markup=user_menu_keyboard())
        return True

    if text == BACK_TO_ADMIN:
        await show_admin_menu(message, state)
        return True

    if text == CANCEL_ACTION:
        await show_admin_menu(message, state, "❌ Действие отменено.")
        return True

    if text == BACK_TO_SECTION:
        data = await state.get_data()
        section = data.get("section")
        if section:
            await open_section(message, state, db, section)
        else:
            await show_admin_menu(message, state)
        return True

    return False


async def open_section(message: Message, state: FSMContext, db: Database, section: str) -> None:
    await state.update_data(section=section, pending_action=None)

    if section == "search":
        await state.set_state(AdminStates.search_wait_identifier)
        await message.answer("🔎 Введи USER_ID, @username или username.", reply_markup=search_section_keyboard())
        return

    if section == "stats":
        stats = db.get_stats()
        await state.set_state(AdminStates.menu)
        await message.answer(
            "📊 Статистика\n\n"
            f"Всего пользователей: {stats['users']}\n"
            f"Платных пользователей: {stats['paid']}\n"
            f"Запросов сегодня: {stats['requests_today']}\n"
            f"Доход Stars: {stats['stars']}\n"
            f"Доход RUB: {stats['rub']}",
            reply_markup=admin_keyboard(),
        )
        return

    if section == "grant":
        await state.set_state(AdminStates.grant_choose_days)
        await message.answer("🎁 Выбери срок подписки.", reply_markup=grant_section_keyboard())
        return

    if section == "revoke":
        await state.set_state(AdminStates.revoke_wait_identifier)
        await message.answer("❌ Введи USER_ID или username пользователя.", reply_markup=revoke_section_keyboard())
        return

    if section == "user_limit":
        await state.set_state(AdminStates.user_limit_wait_identifier)
        await message.answer("🎯 Введи USER_ID или username пользователя.", reply_markup=user_limit_section_keyboard())
        return

    if section == "prices":
        await state.set_state(AdminStates.prices_choose_days)
        await message.answer(_render_current_prices(db), reply_markup=prices_section_keyboard())
        return

    if section == "support":
        await state.set_state(AdminStates.support_wait_ticket_id)
        await message.answer(_render_support_text(db), reply_markup=support_section_keyboard())
        return

    if section == "ban":
        await state.set_state(AdminStates.ban_choose_action)
        await message.answer("🚫 Выбери действие по пользователю.", reply_markup=ban_section_keyboard())
        return

    if section == "maintenance":
        await state.set_state(AdminStates.menu)
        await message.answer(_render_maintenance_text(db), reply_markup=maintenance_section_keyboard())
        return

    if section == "global_limit":
        await state.set_state(AdminStates.global_limit_wait_value)
        await message.answer("🌍 Введи новый лимит для всех пользователей числом.", reply_markup=global_limit_section_keyboard())
        return

    if section == "broadcast_all":
        await state.set_state(AdminStates.broadcast_all_wait_text)
        await message.answer("📢 Введи текст рассылки для всех пользователей.", reply_markup=broadcast_section_keyboard("all"))
        return

    if section == "broadcast_paid":
        await state.set_state(AdminStates.broadcast_paid_wait_text)
        await message.answer("💸 Введи текст рассылки для платных пользователей.", reply_markup=broadcast_section_keyboard("paid"))
        return

    if section == "promos":
        await state.set_state(AdminStates.promo_choose_action)
        await message.answer(_render_promo_text(db), reply_markup=promo_section_keyboard())
        return

    if section == "bonus":
        await state.set_state(AdminStates.bonus_choose_action)
        await message.answer(_render_bonus_text(), reply_markup=bonus_section_keyboard())
        return

    if section == "export":
        await state.set_state(AdminStates.export_choose_scope)
        await message.answer(_render_export_text(), reply_markup=export_section_keyboard())
        return

    if section == "admins":
        await state.set_state(AdminStates.admins_choose_action)
        await message.answer(_render_admins_text(db), reply_markup=admins_section_keyboard())
        return

    if section == "required_sub":
        await state.set_state(AdminStates.required_sub_choose_action)
        await message.answer(_render_required_subscription_text(db), reply_markup=required_sub_section_keyboard())
        return

    await show_admin_menu(message, state)


def _render_current_prices(db: Database) -> str:
    prices = db.get_prices()
    return (
        "💰 Цены\n\n"
        f"3 дня: ⭐ {prices['stars_3']} | 💳 {prices['rub_3']}\n"
        f"7 дней: ⭐ {prices['stars_7']} | 💳 {prices['rub_7']}\n"
        f"30 дней: ⭐ {prices['stars_30']} | 💳 {prices['rub_30']}\n\n"
        "Выбери срок ниже."
    )


def _parse_days_button(text: str) -> Optional[int]:
    mapping = {"3 дня": 3, "7 дней": 7, "30 дней": 30}
    return mapping.get((text or "").strip())


def _render_user_card(user: dict[str, Any]) -> str:
    username = f"@{user['username']}" if user.get("username") else "—"
    return (
        "👤 Пользователь\n\n"
        f"ID: `{user['id']}`\n"
        f"Username: {username}\n"
        f"Запросов: {user.get('requests_left', 0)}\n"
        f"Premium: {'Да' if user.get('is_premium') else 'Нет'}\n"
        f"VIP: {'Да' if user.get('is_vip') else 'Нет'}\n"
        f"Бан: {'Да' if user.get('is_banned') else 'Нет'}\n"
        f"Sub until: {user.get('sub_until') or '—'}"
    )


@router.message(Command("admin"))
async def admin_entry(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    await show_admin_menu(message, state)


@router.message(StateFilter("*"), Command("start"))
async def admin_start_exit(message: Message, state: FSMContext):
    db = Database()
    if not is_admin(message, db):
        raise SkipHandler()
    await state.clear()
    await message.answer("✅ Выход из текущего режима.\nВозвращаю в обычное меню.", reply_markup=user_menu_keyboard())


@router.message(StateFilter("*"), F.text.in_(list(SECTION_LABELS.values())))
async def admin_menu_router(message: Message, state: FSMContext):
    db = Database()
    if not is_admin(message, db):
        raise SkipHandler()

    reverse = {value: key for key, value in SECTION_LABELS.items()}
    section = reverse.get((message.text or "").strip())
    if section == "to_menu":
        await state.clear()
        await message.answer("✅ Выход из админки.\nВозвращаю в обычное меню.", reply_markup=user_menu_keyboard())
        return
    if section:
        await open_section(message, state, db, section)


@router.message(StateFilter("*"), F.text.in_({BACK_TO_ADMIN, BACK_TO_SECTION, CANCEL_ACTION, *EXIT_ALIASES}))
async def admin_navigation_router(message: Message, state: FSMContext):
    db = Database()
    if not is_admin(message, db):
        raise SkipHandler()
    await handle_common_navigation(message, state, db)


@router.message(AdminStates.search_wait_identifier)
async def handle_user_search(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    user_id, user, error = resolve_user_identifier(db, (message.text or "").strip())
    if error or not user:
        await message.answer(error or "Пользователь не найден.", reply_markup=search_section_keyboard())
        return
    await message.answer(_render_user_card(user), reply_markup=search_section_keyboard())


@router.message(AdminStates.grant_choose_days)
async def handle_grant_choose_days(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    text = (message.text or "").strip()
    days = _parse_days_button(text)
    if text == "Свое значение":
        await state.update_data(grant_days=None)
        await state.set_state(AdminStates.grant_wait_identifier)
        await message.answer("Введи пользователя и срок в формате: `@username 14` или `123456789 14`.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if not days:
        await message.answer("Выбери один из сроков кнопкой ниже.", reply_markup=grant_section_keyboard())
        return
    await state.update_data(grant_days=days)
    await state.set_state(AdminStates.grant_wait_identifier)
    await message.answer(f"Введи USER_ID или username пользователя для подписки на {days} дн.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.grant_wait_identifier)
async def handle_grant_identifier(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    data = await state.get_data()
    stored_days = data.get("grant_days")
    text = (message.text or "").strip()

    if stored_days:
        identifier = text
        days = int(stored_days)
    else:
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Формат: `@username 14` или `123456789 14`.")
            return
        identifier = parts[0]
        days = int(parts[1])

    user_id, _user, error = resolve_user_identifier(db, identifier)
    if error or not user_id:
        await message.answer(error or "Пользователь не найден.")
        return

    db.activate_subscription(user_id, days)
    await message.answer(f"✅ Подписка выдана на {days} дн.", reply_markup=grant_section_keyboard())
    await state.set_state(AdminStates.grant_choose_days)
    await state.update_data(grant_days=None)


@router.message(AdminStates.revoke_wait_identifier)
async def handle_revoke_sub(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    user_id, _user, error = resolve_user_identifier(db, (message.text or "").strip())
    if error or not user_id:
        await message.answer(error or "Пользователь не найден.", reply_markup=revoke_section_keyboard())
        return
    db.revoke_subscription(user_id)
    await message.answer("✅ Подписка забрана.", reply_markup=revoke_section_keyboard())


@router.message(AdminStates.user_limit_wait_identifier)
async def handle_user_limit_identifier(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    user_id, user, error = resolve_user_identifier(db, (message.text or "").strip())
    if error or not user_id or not user:
        await message.answer(error or "Пользователь не найден.", reply_markup=user_limit_section_keyboard())
        return
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminStates.user_limit_wait_value)
    await message.answer(
        f"Текущий лимит пользователя {('@' + user['username']) if user.get('username') else user_id}: {user.get('requests_left', 0)}\n\nВведи новый лимит числом.",
        reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]),
    )


@router.message(AdminStates.user_limit_wait_value)
async def handle_user_limit_value(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно число.")
        return
    data = await state.get_data()
    user_id = data.get("target_user_id")
    if not user_id:
        await open_section(message, state, db, "user_limit")
        return
    db.set_user_requests(int(user_id), int(text))
    await message.answer("✅ Лимит пользователя обновлён.", reply_markup=user_limit_section_keyboard())
    await state.set_state(AdminStates.user_limit_wait_identifier)
    await state.update_data(target_user_id=None)


@router.message(AdminStates.prices_choose_days)
async def handle_prices_choose_days(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    text = (message.text or "").strip()
    if text == "Показать цены":
        await message.answer(_render_current_prices(db), reply_markup=prices_section_keyboard())
        return
    days = _parse_days_button(text)
    if not days:
        await message.answer("Выбери срок кнопкой ниже.", reply_markup=prices_section_keyboard())
        return
    await state.update_data(price_days=days)
    await state.set_state(AdminStates.prices_choose_currency)
    await message.answer(f"Выбран срок: {days} дн. Теперь выбери валюту.", reply_markup=prices_currency_keyboard())


@router.message(AdminStates.prices_choose_currency)
async def handle_prices_choose_currency(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    text = (message.text or "").strip()
    mapping = {"⭐ Stars": "stars", "💳 RUB": "rub"}
    currency = mapping.get(text)
    if not currency:
        await message.answer("Выбери валюту кнопкой ниже.", reply_markup=prices_currency_keyboard())
        return
    await state.update_data(price_currency=currency)
    await state.set_state(AdminStates.prices_wait_value)
    await message.answer("Введи новое значение цены числом.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.prices_wait_value)
async def handle_prices_wait_value(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно число.")
        return
    data = await state.get_data()
    days = int(data.get("price_days") or 0)
    currency = data.get("price_currency")
    value = int(text)
    if not days or currency not in {"stars", "rub"}:
        await open_section(message, state, db, "prices")
        return
    if currency == "stars":
        db.set_price(days, stars=value)
    else:
        db.set_price(days, rub=value)
    await message.answer("✅ Цена обновлена.\n\n" + _render_current_prices(db), reply_markup=prices_section_keyboard())
    await state.set_state(AdminStates.prices_choose_days)


@router.message(AdminStates.support_wait_ticket_id)
async def handle_support_section(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return

    text = (message.text or "").strip()
    if text == "📋 Открытые заявки":
        await message.answer(_render_support_text(db), reply_markup=support_section_keyboard())
        return
    if text == "🔍 Показать заявку":
        await state.set_state(AdminStates.support_wait_ticket_id)
        await state.update_data(support_action="show")
        await message.answer("Введи ID заявки.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if text == "💬 Ответить":
        await state.set_state(AdminStates.support_wait_reply_ticket_id)
        await message.answer("Введи ID заявки для ответа.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if text == "✅ Закрыть заявку":
        await state.set_state(AdminStates.support_wait_close_ticket_id)
        await message.answer("Введи ID заявки для закрытия.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return

    data = await state.get_data()
    if data.get("support_action") == "show" and text.isdigit():
        ticket = db.get_support_ticket(int(text))
        if not ticket:
            await message.answer("Заявка не найдена.")
        else:
            await message.answer(
                f"🆘 Заявка #{ticket['id']}\n"
                f"User: `{ticket['user_id']}`\n"
                f"Status: {ticket['status']}\n\n"
                f"Сообщение:\n{ticket['message']}\n\n"
                f"Ответ:\n{ticket['admin_reply'] or '—'}",
                reply_markup=support_section_keyboard(),
            )
        await state.update_data(support_action=None)
        return

    await message.answer(_render_support_text(db), reply_markup=support_section_keyboard())


@router.message(AdminStates.support_wait_reply_ticket_id)
async def handle_support_reply_ticket_id(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужен ID заявки числом.")
        return
    ticket = db.get_support_ticket(int(text))
    if not ticket:
        await message.answer("Заявка не найдена.")
        return
    await state.update_data(reply_ticket_id=int(text))
    await state.set_state(AdminStates.support_wait_reply_text)
    await message.answer("Введи текст ответа пользователю.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.support_wait_reply_text)
async def handle_support_reply_text(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Ответ не должен быть пустым.")
        return
    data = await state.get_data()
    ticket_id = data.get("reply_ticket_id")
    ticket = db.get_support_ticket(int(ticket_id)) if ticket_id else None
    if not ticket:
        await open_section(message, state, db, "support")
        return
    db.reply_support_ticket(int(ticket_id), text)
    try:
        await message.bot.send_message(ticket["user_id"], f"💬 Ответ поддержки\n\n{text}")
    except Exception:
        logger.exception("Failed to deliver support reply")
    await message.answer("✅ Ответ отправлен.", reply_markup=support_section_keyboard())
    await state.set_state(AdminStates.support_wait_ticket_id)
    await state.update_data(reply_ticket_id=None)


@router.message(AdminStates.support_wait_close_ticket_id)
async def handle_support_close_ticket_id(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужен ID заявки числом.")
        return
    db.close_support_ticket(int(text))
    await message.answer("✅ Заявка закрыта.", reply_markup=support_section_keyboard())
    await state.set_state(AdminStates.support_wait_ticket_id)


@router.message(AdminStates.ban_choose_action)
async def handle_ban_choose_action(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    mapping = {
        "🚫 Забанить": "ban",
        "✅ Разбанить": "unban",
        "📍 Проверить статус": "status",
    }
    action = mapping.get(text)
    if not action:
        await message.answer("Выбери действие кнопкой ниже.", reply_markup=ban_section_keyboard())
        return
    await state.update_data(ban_action=action)
    await state.set_state(AdminStates.ban_wait_identifier)
    await message.answer("Введи USER_ID или username пользователя.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.ban_wait_identifier)
async def handle_ban_identifier(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    data = await state.get_data()
    action = data.get("ban_action")
    user_id, user, error = resolve_user_identifier(db, (message.text or "").strip())
    if error or not user_id or not user:
        await message.answer(error or "Пользователь не найден.")
        return
    if action == "status":
        st = db.get_ban_status(user_id)
        username = f"@{user['username']}" if user.get('username') else '—'
        await message.answer(
            f"👤 {username}\nID: `{user_id}`\nСтатус: {'BAN' if st['is_banned'] else 'OK'}\nПричина: {st['reason'] or '—'}",
            reply_markup=ban_section_keyboard(),
        )
        await state.set_state(AdminStates.ban_choose_action)
        return
    await state.update_data(target_user_id=user_id)
    if action == "unban":
        db.unban_user(user_id)
        await message.answer("✅ Пользователь разбанен.", reply_markup=ban_section_keyboard())
        await state.set_state(AdminStates.ban_choose_action)
        return
    await state.set_state(AdminStates.ban_wait_reason)
    await message.answer("Введи причину бана.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.ban_wait_reason)
async def handle_ban_reason(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip() or "Без причины"
    data = await state.get_data()
    user_id = data.get("target_user_id")
    if not user_id:
        await open_section(message, state, db, "ban")
        return
    db.ban_user(int(user_id), text, message.from_user.id)
    await message.answer("✅ Пользователь забанен.", reply_markup=ban_section_keyboard())
    await state.set_state(AdminStates.ban_choose_action)
    await state.update_data(target_user_id=None, ban_action=None)


@router.message(AdminStates.menu, F.text.in_({"🟢 Включить", "⚪ Выключить", "📄 Показать статус", "✏️ Изменить текст"}))
async def maintenance_button_router(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    data = await state.get_data()
    if data.get("section") != "maintenance":
        raise SkipHandler()
    text = (message.text or "").strip()
    if text == "🟢 Включить":
        db.set_maintenance_mode(True)
        await message.answer("✅ Техработы включены.", reply_markup=maintenance_section_keyboard())
        return
    if text == "⚪ Выключить":
        db.set_maintenance_mode(False)
        await message.answer("✅ Техработы выключены.", reply_markup=maintenance_section_keyboard())
        return
    if text == "📄 Показать статус":
        await message.answer(_render_maintenance_text(db), reply_markup=maintenance_section_keyboard())
        return
    if text == "✏️ Изменить текст":
        await state.set_state(AdminStates.maintenance_wait_text)
        await message.answer("Введи новый текст техработ.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return


@router.message(AdminStates.maintenance_wait_text)
async def handle_maintenance_text(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст не должен быть пустым.")
        return
    db.set_maintenance_mode(db.is_maintenance_enabled(), text)
    await message.answer("✅ Текст техработ обновлён.", reply_markup=maintenance_section_keyboard())
    await state.set_state(AdminStates.menu)
    await state.update_data(section="maintenance")


@router.message(AdminStates.global_limit_wait_value)
async def handle_global_limit(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно число.", reply_markup=global_limit_section_keyboard())
        return
    db.set_all_users_requests(int(text))
    await message.answer("✅ Лимит для всех обновлён.", reply_markup=global_limit_section_keyboard())


@router.message(AdminStates.broadcast_all_wait_text)
async def handle_broadcast_all(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    sent, failed = await broadcast(message.bot, db.get_all_user_ids(), (message.text or "").strip())
    await message.answer(f"✅ Рассылка завершена.\nОтправлено: {sent}, ошибок: {failed}", reply_markup=broadcast_section_keyboard("all"))


@router.message(AdminStates.broadcast_paid_wait_text)
async def handle_broadcast_paid(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    sent, failed = await broadcast(message.bot, db.get_paid_user_ids(), (message.text or "").strip())
    await message.answer(f"✅ Рассылка платным завершена.\nОтправлено: {sent}, ошибок: {failed}", reply_markup=broadcast_section_keyboard("paid"))


@router.message(AdminStates.promo_choose_action)
async def handle_promo_choose_action(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if text == "📋 Список":
        await message.answer(_render_promo_text(db), reply_markup=promo_section_keyboard())
        return
    if text == "➕ Создать":
        await state.set_state(AdminStates.promo_wait_code)
        await message.answer("Введи код промокода, например START5.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if text == "🟢 Включить":
        await state.update_data(promo_toggle_value=True)
        await state.set_state(AdminStates.promo_wait_toggle_code)
        await message.answer("Введи код промокода для включения.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if text == "⚪ Выключить":
        await state.update_data(promo_toggle_value=False)
        await state.set_state(AdminStates.promo_wait_toggle_code)
        await message.answer("Введи код промокода для выключения.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if text == "ℹ️ Инфо":
        await state.set_state(AdminStates.promo_wait_info_code)
        await message.answer("Введи код промокода.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    await message.answer(_render_promo_text(db), reply_markup=promo_section_keyboard())


@router.message(AdminStates.promo_wait_code)
async def handle_promo_wait_code(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    code = (message.text or "").strip().upper()
    if not code:
        await message.answer("Код не должен быть пустым.")
        return
    await state.update_data(promo_code=code)
    await state.set_state(AdminStates.promo_wait_create_reward_type)
    await message.answer("Выбери тип награды.", reply_markup=promo_reward_keyboard())


@router.message(AdminStates.promo_wait_create_reward_type)
async def handle_promo_reward_type(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    reward_type = PROMO_REWARD_LABELS.get((message.text or "").strip())
    if not reward_type:
        await message.answer("Выбери тип награды кнопкой ниже.", reply_markup=promo_reward_keyboard())
        return
    await state.update_data(promo_reward_type=reward_type)
    await state.set_state(AdminStates.promo_wait_create_reward_value)
    await message.answer("Введи значение награды числом.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.promo_wait_create_reward_value)
async def handle_promo_reward_value(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно число.")
        return
    data = await state.get_data()
    code = data.get("promo_code")
    reward_type = data.get("promo_reward_type")
    if not code or not reward_type:
        await open_section(message, state, db, "promos")
        return
    db.create_promo_code(code, reward_type, int(text))
    await message.answer("✅ Промокод создан.\n\n" + _render_promo_text(db), reply_markup=promo_section_keyboard())
    await state.set_state(AdminStates.promo_choose_action)
    await state.update_data(promo_code=None, promo_reward_type=None)


@router.message(AdminStates.promo_wait_toggle_code)
async def handle_promo_toggle_code(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    code = (message.text or "").strip().upper()
    data = await state.get_data()
    toggle_value = bool(data.get("promo_toggle_value"))
    db.set_promo_active(code, toggle_value)
    await message.answer("✅ Статус промокода обновлён.", reply_markup=promo_section_keyboard())
    await state.set_state(AdminStates.promo_choose_action)


@router.message(AdminStates.promo_wait_info_code)
async def handle_promo_info_code(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    code = (message.text or "").strip().upper()
    promo = db.get_promo_code(code)
    if not promo:
        await message.answer("Промокод не найден.")
        return
    await message.answer(
        f"`{promo['code']}`\n"
        f"Тип: {promo['reward_type']}\n"
        f"Значение: {promo['reward_value']}\n"
        f"Used: {promo['used_count']}\n"
        f"Статус: {'ON' if promo['is_active'] else 'OFF'}",
        reply_markup=promo_section_keyboard(),
    )
    await state.set_state(AdminStates.promo_choose_action)


@router.message(AdminStates.bonus_choose_action)
async def handle_bonus_choose_action(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    action = BONUS_ACTION_LABELS.get((message.text or "").strip())
    if not action:
        await message.answer(_render_bonus_text(), reply_markup=bonus_section_keyboard())
        return
    await state.update_data(bonus_action=action)
    if action in {"user_requests", "user_premium"}:
        await state.set_state(AdminStates.bonus_wait_identifier)
        await message.answer("Введи USER_ID или username пользователя.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    await state.set_state(AdminStates.bonus_wait_scope_value)
    await message.answer("Введи количество запросов числом.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.bonus_wait_identifier)
async def handle_bonus_identifier(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    user_id, _user, error = resolve_user_identifier(db, (message.text or "").strip())
    if error or not user_id:
        await message.answer(error or "Пользователь не найден.")
        return
    await state.update_data(target_user_id=user_id)
    data = await state.get_data()
    action = data.get("bonus_action")
    prompt = "Введи количество запросов числом." if action == "user_requests" else "Введи количество premium дней числом."
    await state.set_state(AdminStates.bonus_wait_value)
    await message.answer(prompt, reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.bonus_wait_value)
async def handle_bonus_value(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text.lstrip("-").isdigit():
        await message.answer("Нужно число.")
        return
    value = int(text)
    data = await state.get_data()
    action = data.get("bonus_action")
    user_id = data.get("target_user_id")
    if not user_id or action not in {"user_requests", "user_premium"}:
        await open_section(message, state, db, "bonus")
        return
    if action == "user_requests":
        db.add_user_requests(int(user_id), value)
        await message.answer("✅ Запросы начислены.", reply_markup=bonus_section_keyboard())
    else:
        db.activate_subscription(int(user_id), value)
        await message.answer("✅ Подписка выдана.", reply_markup=bonus_section_keyboard())
    await state.set_state(AdminStates.bonus_choose_action)


@router.message(AdminStates.bonus_wait_scope_value)
async def handle_bonus_scope_value(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text.lstrip("-").isdigit():
        await message.answer("Нужно число.")
        return
    value = int(text)
    data = await state.get_data()
    action = data.get("bonus_action")
    if action == "all_requests":
        count = db.add_requests_to_all(value, paid_only=False)
        await message.answer(f"✅ Начислено всем.\nОбновлено пользователей: {count}", reply_markup=bonus_section_keyboard())
    elif action == "paid_requests":
        count = db.add_requests_to_all(value, paid_only=True)
        await message.answer(f"✅ Начислено платным.\nОбновлено пользователей: {count}", reply_markup=bonus_section_keyboard())
    else:
        await open_section(message, state, db, "bonus")
        return
    await state.set_state(AdminStates.bonus_choose_action)


@router.message(AdminStates.export_choose_scope)
async def handle_export_scope(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if text not in {"👥 Все пользователи", "💸 Платные пользователи"}:
        await message.answer(_render_export_text(), reply_markup=export_section_keyboard())
        return
    paid_only = text == "💸 Платные пользователи"
    data = db.export_users_csv(paid_only=paid_only)
    suffix = "paid" if paid_only else "all"
    await message.answer_document(BufferedInputFile(data, filename=f"users_{suffix}.csv"), reply_markup=export_section_keyboard())


@router.message(AdminStates.admins_choose_action)
async def handle_admins_choose_action(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if text == "📋 Список":
        await message.answer(_render_admins_text(db), reply_markup=admins_section_keyboard())
        return
    if text == "➕ Добавить":
        await state.update_data(admin_action="add")
        await state.set_state(AdminStates.admins_wait_user_id)
        await message.answer("Введи USER_ID нового админа.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if text == "🗑 Удалить":
        await state.update_data(admin_action="del")
        await state.set_state(AdminStates.admins_wait_user_id)
        await message.answer("Введи USER_ID админа для удаления.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    await message.answer(_render_admins_text(db), reply_markup=admins_section_keyboard())


@router.message(AdminStates.admins_wait_user_id)
async def handle_admins_user_id(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужен USER_ID числом.")
        return
    data = await state.get_data()
    action = data.get("admin_action")
    user_id = int(text)
    if action == "del":
        db.remove_admin(user_id)
        await message.answer("✅ Админ удалён.", reply_markup=admins_section_keyboard())
        await state.set_state(AdminStates.admins_choose_action)
        return
    await state.update_data(admin_target_user_id=user_id)
    await state.set_state(AdminStates.admins_wait_role)
    await message.answer("Введи роль админа, например `admin`.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.admins_wait_role)
async def handle_admins_role(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    role = (message.text or "").strip() or "admin"
    data = await state.get_data()
    user_id = data.get("admin_target_user_id")
    if not user_id:
        await open_section(message, state, db, "admins")
        return
    db.add_admin(int(user_id), role)
    await message.answer("✅ Админ добавлен.", reply_markup=admins_section_keyboard())
    await state.set_state(AdminStates.admins_choose_action)
    await state.update_data(admin_target_user_id=None, admin_action=None)


@router.message(AdminStates.required_sub_choose_action)
async def handle_required_sub_choose_action(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if text == "⚪ Выключить":
        db.set_required_channel(None, None, False)
        await message.answer("✅ Обязательная подписка выключена.", reply_markup=required_sub_section_keyboard())
        return
    if text == "📄 Показать статус":
        await message.answer(_render_required_subscription_text(db), reply_markup=required_sub_section_keyboard())
        return
    if text == "✏️ Изменить текст":
        await state.set_state(AdminStates.required_sub_wait_text)
        await message.answer("Введи новый текст блока обязательной подписки.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if text == "🟢 Включить по username":
        await state.update_data(required_sub_mode="username_only")
        await state.set_state(AdminStates.required_sub_wait_username)
        await message.answer("Введи username канала, например @mychannel.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    if text == "🟢 Включить по ID + username":
        await state.update_data(required_sub_mode="id_and_username")
        await state.set_state(AdminStates.required_sub_wait_channel_id)
        await message.answer("Введи channel_id, например -1001234567890.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))
        return
    await message.answer(_render_required_subscription_text(db), reply_markup=required_sub_section_keyboard())


@router.message(AdminStates.required_sub_wait_channel_id)
async def handle_required_sub_channel_id(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    channel_id = (message.text or "").strip()
    if not channel_id:
        await message.answer("Channel ID не должен быть пустым.")
        return
    await state.update_data(required_channel_id=channel_id)
    await state.set_state(AdminStates.required_sub_wait_username)
    await message.answer("Теперь введи username канала, например @mychannel.", reply_markup=simple_keyboard([[BACK_TO_SECTION, BACK_TO_ADMIN, CANCEL_ACTION]]))


@router.message(AdminStates.required_sub_wait_username)
async def handle_required_sub_username(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    username = (message.text or "").strip()
    if not username:
        await message.answer("Username не должен быть пустым.")
        return
    data = await state.get_data()
    channel_id = data.get("required_channel_id") if data.get("required_sub_mode") == "id_and_username" else None
    db.set_required_channel(channel_id, username, True)
    await message.answer("✅ Канал обязательной подписки установлен.", reply_markup=required_sub_section_keyboard())
    await state.set_state(AdminStates.required_sub_choose_action)
    await state.update_data(required_channel_id=None, required_sub_mode=None)


@router.message(AdminStates.required_sub_wait_text)
async def handle_required_sub_text(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    if await handle_common_navigation(message, state, db):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст не должен быть пустым.")
        return
    db.set_required_subscription_text(text)
    await message.answer("✅ Текст обязательной подписки обновлён.", reply_markup=required_sub_section_keyboard())
    await state.set_state(AdminStates.required_sub_choose_action)


def get_admin_router(db: Optional[Database] = None) -> Router:
    return router
