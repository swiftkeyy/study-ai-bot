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
    add_limit = State()
    toggle_vip = State()
    global_limit = State()
    user_limit = State()
    set_price = State()
    broadcast_all = State()
    broadcast_paid = State()
    ban_manage = State()
    maintenance_manage = State()
    admin_manage = State()
    required_subscription_manage = State()
    promo_manage = State()
    bonus_manage = State()
    export_manage = State()
    support_manage = State()
    buttons_manage = State()
    features_manage = State()
    tests_manage = State()
    ai_manage = State()


ADMIN_BUTTON_LABELS = [
    "🔎 Найти пользователя",
    "📊 Статистика",
    "🎁 Выдать подписку",
    "❌ Забрать подписку",
    "➕ Выдать лимит",
    "⭐ VIP",
    "🌍 Лимит всем",
    "🎯 Лимит пользователю",
    "💰 Цены",
    "📢 Рассылка всем",
    "💸 Рассылка платным",
    "🎟 Промокоды",
    "🎁 Начислить бонусы",
    "📤 Выгрузка пользователей",
    "🆘 Заявки поддержки",
    "🚫 Бан / разбан",
    "🛠 Тех.работы",
    "🤠 Админы",
    "📡 Обязательная подписка",
    "🧩 Управление кнопками",
    "⚙️ Доп. функции",
    "🤖 Настройки AI",
    "🧪 Тестовые команды",
    "🔙 В меню",
]

EXIT_ALIASES = {
    "🔙 В меню",
    "↩ В меню",
    "❌ Отмена",
    "Отмена",
    "Назад",
    "В меню",
}

NORMALIZED_MENU_MAP = {
    "найти пользователя": "find_user",
    "статистика": "stats",
    "выдать подписку": "grant_sub",
    "забрать подписку": "revoke_sub",
    "выдать лимит": "add_limit",
    "vip": "vip",
    "лимит всем": "global_limit",
    "лимит пользователю": "user_limit",
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
    "управление кнопками": "buttons",
    "доп. функции": "features",
    "настройки ai": "ai",
    "тестовые команды": "tests",
    "в меню": "to_menu",
    "назад": "to_menu",
    "отмена": "to_menu",
}

ADMIN_MENU_CODES = {
    "find_user", "stats", "grant_sub", "revoke_sub", "add_limit", "vip",
    "global_limit", "user_limit", "prices", "broadcast_all", "broadcast_paid",
    "promos", "bonus", "export", "support", "ban", "maintenance", "admins",
    "required_sub", "buttons", "features", "ai", "tests", "to_menu",
}


def _is_admin_menu_text(value: str) -> bool:
    return normalize_admin_text(value) in ADMIN_MENU_CODES


def user_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Решить задачу"), KeyboardButton(text="✍️ Написать текст")],
            [KeyboardButton(text="👤 Личный кабинет"), KeyboardButton(text="💎 Купить доступ")],
            [KeyboardButton(text="🎁 Ввести промокод"), KeyboardButton(text="📣 Новости")],
            [KeyboardButton(text="💬 Поддержка"), KeyboardButton(text="👥 Реферальная программа")],
            [KeyboardButton(text="🎓 Полезные материалы"), KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
    )


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Найти пользователя"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🎁 Выдать подписку"), KeyboardButton(text="❌ Забрать подписку")],
            [KeyboardButton(text="➕ Выдать лимит"), KeyboardButton(text="⭐ VIP")],
            [KeyboardButton(text="🌍 Лимит всем"), KeyboardButton(text="🎯 Лимит пользователю")],
            [KeyboardButton(text="💰 Цены"), KeyboardButton(text="📢 Рассылка всем")],
            [KeyboardButton(text="💸 Рассылка платным"), KeyboardButton(text="🎟 Промокоды")],
            [KeyboardButton(text="🎁 Начислить бонусы"), KeyboardButton(text="📤 Выгрузка пользователей")],
            [KeyboardButton(text="🆘 Заявки поддержки"), KeyboardButton(text="🚫 Бан / разбан")],
            [KeyboardButton(text="🛠 Тех.работы"), KeyboardButton(text="🤠 Админы")],
            [KeyboardButton(text="📡 Обязательная подписка"), KeyboardButton(text="🧩 Управление кнопками")],
            [KeyboardButton(text="⚙️ Доп. функции"), KeyboardButton(text="🤖 Настройки AI")],
            [KeyboardButton(text="🧪 Тестовые команды"), KeyboardButton(text="🔙 В меню")],
        ],
        resize_keyboard=True,
    )


def normalize_admin_text(value: str) -> str:
    text = (value or "").replace("\xa0", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[^\wа-яё]+", "", text, flags=re.IGNORECASE)
    text = text.strip()

    for human, code in NORMALIZED_MENU_MAP.items():
        if human in text:
            return code

    return text


def is_admin(message: Message, db: Database) -> bool:
    return bool(message.from_user and db.is_admin(message.from_user.id))


async def deny_if_not_admin(message: Message, db: Database) -> bool:
    if not is_admin(message, db):
        return True
    return False


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
    return "🛠 Админ-панель\n\nВыбери раздел кнопкой ниже."


def _render_admins_text(db: Database) -> str:
    rows = db.list_admins()
    parts = ["🤠 Админы", "", "Команды:", "• `list`", "• `add USER_ID`", "• `add USER_ID роль`", "• `del USER_ID`", "", "Список:"]
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
        "Команды:\n"
        "• `on @channelusername`\n"
        "• `on -100123456789 @channelusername`\n"
        "• `off`\n"
        "• `status`\n"
        "• `text Новый текст блока`"
    )


def _render_maintenance_text(db: Database) -> str:
    enabled = "включены" if db.is_maintenance_enabled() else "выключены"
    return (
        "🛠 Тех.работы\n\n"
        f"Сейчас техработы: {enabled}\n\n"
        "Команды:\n"
        "• `on`\n"
        "• `off`\n"
        "• `status`\n"
        "• `text Новый текст`\n\n"
        f"Текущий текст:\n{db.get_maintenance_text()}"
    )


def _render_promo_text(db: Database) -> str:
    rows = db.list_promo_codes(limit=10)
    lines = [
        "🎟 Промокоды",
        "",
        "Команды:",
        "• `list`",
        "• `create CODE requests 5`",
        "• `create CODE premium_days 7`",
        "• `create CODE vip 1`",
        "• `on CODE`",
        "• `off CODE`",
        "• `info CODE`",
        "",
        "Последние:",
    ]
    if not rows:
        lines.append("— пусто")
    else:
        for item in rows:
            lines.append(
                f"• `{item['code']}` | {item['reward_type']}={item['reward_value']} | used {item['used_count']} | {'ON' if item['is_active'] else 'OFF'}"
            )
    return "\n".join(lines)


def _render_ban_text() -> str:
    return (
        "🚫 Бан / разбан\n\n"
        "Команды:\n"
        "• `ban USER_ID причина`\n"
        "• `unban USER_ID`\n"
        "• `status USER_ID`"
    )


def _render_bonus_text() -> str:
    return (
        "🎁 Начислить бонусы\n\n"
        "Команды:\n"
        "• `user USER_ID REQUESTS`\n"
        "• `premium USER_ID DAYS`\n"
        "• `vip USER_ID on`\n"
        "• `vip USER_ID off`\n"
        "• `all REQUESTS`\n"
        "• `paid REQUESTS`"
    )


def _render_export_text() -> str:
    return (
        "📤 Выгрузка пользователей\n\n"
        "Команды:\n"
        "• `all` — выгрузить всех\n"
        "• `paid` — выгрузить платных"
    )


def _render_support_text(db: Database) -> str:
    tickets = db.get_open_support_tickets(limit=10)
    lines = ["🆘 Заявки поддержки", "", "Команды:", "• `list`", "• `show ID`", "• `reply ID текст`", "• `close ID`", "", "Открытые заявки:"]
    if not tickets:
        lines.append("— нет открытых")
    else:
        for item in tickets:
            preview = (item["message"] or "")[:50].replace("\n", " ")
            lines.append(f"• `{item['id']}` | user `{item['user_id']}` | {preview}")
    return "\n".join(lines)


def _render_menu_buttons_text(db: Database) -> str:
    rows = db.list_menu_buttons()
    lines = [
        "🧩 Управление кнопками",
        "",
        "Команды:",
        "• `list`",
        "• `add_text Название | Текст кнопки`",
        "• `add_url Название | https://example.com`",
        "• `on ID`",
        "• `off ID`",
        "• `sort ID ПОРЯДОК`",
        "• `del ID`",
        "",
        "Кнопки:",
    ]
    if not rows:
        lines.append("— нет")
    else:
        for item in rows[:20]:
            lines.append(
                f"• `{item['id']}` | {'ON' if item['is_active'] else 'OFF'} | {item['action_type']} | {item['title']} | sort={item['sort_order']}"
            )
    return "\n".join(lines)


def _render_features_text(db: Database) -> str:
    features = db.get_all_features()
    lines = ["⚙️ Доп. функции", "", "Команды:", "• `list`", "• `on FEATURE`", "• `off FEATURE`", "", "Текущие значения:"]
    for key in ["promocodes", "support", "news", "materials", "solve_by_photo", "referrals"]:
        lines.append(f"• `{key}` = {'ON' if features.get(key, True) else 'OFF'}")
    return "\n".join(lines)


def _render_ai_settings_text(db: Database) -> str:
    ai = db.get_ai_settings()
    return "\n".join(
        [
            "🤖 Настройки AI",
            "",
            f"Provider: {ai.get('provider') or '—'}",
            f"Fallback #1: {ai.get('fallback_1') or 'off'}",
            f"Fallback #2: {ai.get('fallback_2') or 'off'}",
            f"Model: {ai.get('model') or '—'}",
            f"System prompt: {'задан' if ai.get('system_prompt') else 'пусто'}",
            "",
            "Команды:",
            "• `status`",
            "• `provider gemini|groq|openrouter`",
            "• `fallback1 gemini|groq|openrouter|off`",
            "• `fallback2 gemini|groq|openrouter|off`",
            "• `prompt Текст системного промпта`",
            "• `prompt_clear`",
        ]
    )


def _render_tests_text(db: Database) -> str:
    ai = db.get_ai_settings()
    features = db.get_all_features()
    return "\n".join(
        [
            "🧪 Тестовые команды",
            "",
            "Команды:",
            "• `status`",
            "• `features`",
            "• `ai`",
            "• `user USER_ID`",
            "",
            f"AI provider: {ai.get('provider')}",
            f"Features loaded: {len(features)}",
        ]
    )


async def _open_admin_section_normalized(message: Message, state: FSMContext, key: str, db: Database):
    mapping = {
        "find_user": (AdminStates.user_search, "🔎 Поиск пользователя\n\nОтправь `USER_ID`"),
        "grant_sub": (AdminStates.grant_sub, "🎁 Выдать подписку\n\nФормат: `USER_ID DAYS`"),
        "revoke_sub": (AdminStates.revoke_sub, "❌ Забрать подписку\n\nОтправь `USER_ID`"),
        "add_limit": (AdminStates.add_limit, "➕ Выдать лимит\n\nФормат: `USER_ID REQUESTS`"),
        "vip": (AdminStates.toggle_vip, "⭐ VIP\n\nФормат: `USER_ID on` или `USER_ID off`"),
        "global_limit": (AdminStates.global_limit, "🌍 Лимит всем\n\nОтправь новое значение лимита, например `10`"),
        "user_limit": (AdminStates.user_limit, "🎯 Лимит пользователю\n\nФормат: `USER_ID LIMIT`"),
        "prices": (AdminStates.set_price, "💰 Цены\n\nФормат: `DAYS stars 100` или `DAYS rub 199`"),
        "broadcast_all": (AdminStates.broadcast_all, "📢 Рассылка всем\n\nОтправь текст сообщения."),
        "broadcast_paid": (AdminStates.broadcast_paid, "💸 Рассылка платным\n\nОтправь текст сообщения."),
        "promos": (AdminStates.promo_manage, _render_promo_text(db)),
        "bonus": (AdminStates.bonus_manage, _render_bonus_text()),
        "export": (AdminStates.export_manage, _render_export_text()),
        "support": (AdminStates.support_manage, _render_support_text(db)),
        "ban": (AdminStates.ban_manage, _render_ban_text()),
        "maintenance": (AdminStates.maintenance_manage, _render_maintenance_text(db)),
        "admins": (AdminStates.admin_manage, _render_admins_text(db)),
        "required_sub": (AdminStates.required_subscription_manage, _render_required_subscription_text(db)),
        "buttons": (AdminStates.buttons_manage, _render_menu_buttons_text(db)),
        "features": (AdminStates.features_manage, _render_features_text(db)),
        "ai": (AdminStates.ai_manage, _render_ai_settings_text(db)),
        "tests": (AdminStates.tests_manage, _render_tests_text(db)),
    }

    if key == "stats":
        stats = db.get_stats()
        await state.clear()
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
    await message.answer("✅ Выход из текущего режима.\nВозвращаю в обычное меню.", reply_markup=user_menu_keyboard())


@router.message(StateFilter("*"), F.text.func(_is_admin_menu_text))
async def admin_menu_router(message: Message, state: FSMContext):
    db = Database()
    if not is_admin(message, db):
        raise SkipHandler()

    key = normalize_admin_text(message.text or "")

    if key == "to_menu":
        await state.clear()
        await message.answer("✅ Выход из админки.\nВозвращаю в обычное меню.", reply_markup=user_menu_keyboard())
        return

    await _open_admin_section_normalized(message, state, key, db)


@router.message(AdminStates.user_search)
async def handle_user_search(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужен USER_ID числом.")
        return
    user = db.get_user(int(text))
    if not user:
        await message.answer("Пользователь не найден.")
        return
    username = f"@{user['username']}" if user["username"] else "—"
    await message.answer(
        f"👤 Пользователь\n\n"
        f"ID: `{user['id']}`\n"
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
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await message.answer("Формат: USER_ID DAYS")
        return
    user_id, days = int(parts[0]), int(parts[1])
    db.activate_subscription(user_id, days)
    await message.answer(f"✅ Подписка выдана на {days} дн.")


@router.message(AdminStates.revoke_sub)
async def handle_revoke_sub(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Отправь USER_ID")
        return
    db.revoke_subscription(int(text))
    await message.answer("✅ Подписка забрана.")


@router.message(AdminStates.add_limit)
async def handle_add_limit(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not all(p.lstrip("-").isdigit() for p in parts):
        await message.answer("Формат: USER_ID REQUESTS")
        return
    db.add_user_requests(int(parts[0]), int(parts[1]))
    await message.answer("✅ Лимит выдан.")


@router.message(AdminStates.toggle_vip)
async def handle_vip(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1].lower() not in {"on", "off"}:
        await message.answer("Формат: USER_ID on/off")
        return
    db.set_vip(int(parts[0]), parts[1].lower() == "on")
    await message.answer("✅ VIP обновлён.")


@router.message(AdminStates.global_limit)
async def handle_global_limit(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно число")
        return
    db.set_all_users_requests(int(text))
    await message.answer("✅ Лимит для всех обновлён.")


@router.message(AdminStates.user_limit)
async def handle_user_limit(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        await message.answer("Формат: USER_ID LIMIT")
        return
    db.set_user_requests(int(parts[0]), int(parts[1]))
    await message.answer("✅ Лимит пользователя обновлён.")


@router.message(AdminStates.set_price)
async def handle_set_price(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[0] not in {"3", "7", "30"} or parts[1] not in {"stars", "rub"} or not parts[2].isdigit():
        await message.answer("Формат: DAYS stars|rub VALUE")
        return
    days = int(parts[0])
    value = int(parts[2])
    if parts[1] == "stars":
        db.set_price(days, stars=value)
    else:
        db.set_price(days, rub=value)
    await message.answer("✅ Цена обновлена.")


@router.message(AdminStates.broadcast_all)
async def handle_broadcast_all(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    sent, failed = await broadcast(message.bot, db.get_all_user_ids(), message.text or "")
    await message.answer(f"✅ Рассылка завершена.\nОтправлено: {sent}, ошибок: {failed}")


@router.message(AdminStates.broadcast_paid)
async def handle_broadcast_paid(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    sent, failed = await broadcast(message.bot, db.get_paid_user_ids(), message.text or "")
    await message.answer(f"✅ Рассылка платным завершена.\nОтправлено: {sent}, ошибок: {failed}")


@router.message(AdminStates.ban_manage)
async def handle_ban(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if text == "list":
        await message.answer(_render_ban_text())
        return
    if len(parts) >= 2 and parts[0] == "ban" and parts[1].isdigit():
        reason = parts[2] if len(parts) > 2 else "Без причины"
        db.ban_user(int(parts[1]), reason, message.from_user.id)
        await message.answer("✅ Пользователь забанен.")
        return
    if len(parts) == 2 and parts[0] == "unban" and parts[1].isdigit():
        db.unban_user(int(parts[1]))
        await message.answer("✅ Пользователь разбанен.")
        return
    if len(parts) == 2 and parts[0] == "status" and parts[1].isdigit():
        st = db.get_ban_status(int(parts[1]))
        await message.answer(f"Статус: {'BAN' if st['is_banned'] else 'OK'}\nПричина: {st['reason'] or '—'}")
        return
    await message.answer(_render_ban_text())


@router.message(AdminStates.maintenance_manage)
async def handle_maintenance(message: Message, state: FSMContext):
    db = Database()
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
    db = Database()
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
    db = Database()
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
    if len(parts) == 2 and parts[0] == "on":
        db.set_required_channel(None, parts[1], True)
        await message.answer("✅ Канал обязательной подписки установлен.")
        return
    if len(parts) == 3 and parts[0] == "on":
        db.set_required_channel(parts[1], parts[2], True)
        await message.answer("✅ Канал обязательной подписки установлен.")
        return
    await message.answer(_render_required_subscription_text(db))


@router.message(AdminStates.promo_manage)
async def handle_promo(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if not parts:
        await message.answer(_render_promo_text(db))
        return
    cmd = parts[0]
    if cmd == "list":
        await message.answer(_render_promo_text(db))
        return
    if cmd == "create" and len(parts) == 4 and parts[2] in {"requests", "premium_days", "vip"} and parts[3].isdigit():
        db.create_promo_code(parts[1], parts[2], int(parts[3]))
        await message.answer("✅ Промокод создан.")
        return
    if cmd in {"on", "off"} and len(parts) == 2:
        db.set_promo_active(parts[1], cmd == "on")
        await message.answer("✅ Статус промокода обновлён.")
        return
    if cmd == "info" and len(parts) == 2:
        promo = db.get_promo_code(parts[1])
        if not promo:
            await message.answer("Промокод не найден.")
        else:
            await message.answer(
                f"`{promo['code']}`\n"
                f"Тип: {promo['reward_type']}\n"
                f"Значение: {promo['reward_value']}\n"
                f"Used: {promo['used_count']}\n"
                f"Статус: {'ON' if promo['is_active'] else 'OFF'}"
            )
        return
    await message.answer(_render_promo_text(db))


@router.message(AdminStates.bonus_manage)
async def handle_bonus(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    parts = (message.text or "").split()
    if not parts:
        await message.answer(_render_bonus_text())
        return
    if parts[0] == "user" and len(parts) == 3 and parts[1].isdigit() and parts[2].lstrip("-").isdigit():
        db.add_user_requests(int(parts[1]), int(parts[2]))
        await message.answer("✅ Запросы начислены.")
        return
    if parts[0] == "premium" and len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        db.activate_subscription(int(parts[1]), int(parts[2]))
        await message.answer("✅ Подписка выдана.")
        return
    if parts[0] == "vip" and len(parts) == 3 and parts[1].isdigit() and parts[2] in {"on", "off"}:
        db.set_vip(int(parts[1]), parts[2] == "on")
        await message.answer("✅ VIP обновлён.")
        return
    if parts[0] == "all" and len(parts) == 2 and parts[1].lstrip("-").isdigit():
        count = db.add_requests_to_all(int(parts[1]), paid_only=False)
        await message.answer(f"✅ Начислено всем.\nОбновлено пользователей: {count}")
        return
    if parts[0] == "paid" and len(parts) == 2 and parts[1].lstrip("-").isdigit():
        count = db.add_requests_to_all(int(parts[1]), paid_only=True)
        await message.answer(f"✅ Начислено платным.\nОбновлено пользователей: {count}")
        return
    await message.answer(_render_bonus_text())


@router.message(AdminStates.export_manage)
async def handle_export(message: Message, state: FSMContext):
    db = Database()
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
    db = Database()
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
                f"🆘 Заявка #{ticket['id']}\n"
                f"User: `{ticket['user_id']}`\n"
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
                await message.bot.send_message(ticket["user_id"], f"💬 Ответ поддержки\n\n{parts[2]}")
            except Exception:
                logger.exception("Failed to deliver support reply")
        await message.answer("✅ Ответ отправлен.")
        return
    if parts[0] == "close" and len(parts) == 2 and parts[1].isdigit():
        db.close_support_ticket(int(parts[1]))
        await message.answer("✅ Заявка закрыта.")
        return
    await message.answer(_render_support_text(db))


@router.message(AdminStates.buttons_manage)
async def handle_buttons_manage(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if text == "list":
        await message.answer(_render_menu_buttons_text(db))
        return
    if text.startswith("add_text "):
        payload = text[len("add_text "):]
        if " | " not in payload:
            await message.answer(_render_menu_buttons_text(db))
            return
        title, value = payload.split(" | ", 1)
        db.add_menu_button(
            title=title.strip(),
            button_type="show_text",
            action_type="show_text",
            action_value=value.strip(),
        )
        await message.answer("✅ Текстовая кнопка добавлена.")
        return
    if text.startswith("add_url "):
        payload = text[len("add_url "):]
        if " | " not in payload:
            await message.answer(_render_menu_buttons_text(db))
            return
        title, value = payload.split(" | ", 1)
        db.add_menu_button(
            title=title.strip(),
            button_type="open_url",
            action_type="open_url",
            action_value=value.strip(),
        )
        await message.answer("✅ Ссылочная кнопка добавлена.")
        return
    parts = text.split()
    if len(parts) == 2 and parts[0] in {"on", "off", "del"} and parts[1].isdigit():
        button_id = int(parts[1])
        if parts[0] == "del":
            db.delete_menu_button(button_id)
        else:
            db.set_menu_button_active(button_id, parts[0] == "on")
        await message.answer("✅ Кнопка обновлена.")
        return
    if len(parts) == 3 and parts[0] == "sort" and parts[1].isdigit() and parts[2].lstrip("-").isdigit():
        db.set_menu_button_sort(int(parts[1]), int(parts[2]))
        await message.answer("✅ Порядок обновлён.")
        return
    await message.answer(_render_menu_buttons_text(db))


@router.message(AdminStates.features_manage)
async def handle_features_manage(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if text == "list":
        await message.answer(_render_features_text(db))
        return
    parts = text.split()
    if len(parts) == 2 and parts[0] in {"on", "off"}:
        db.set_feature_enabled(parts[1], parts[0] == "on")
        await message.answer(f"✅ {parts[1]} => {'ON' if parts[0] == 'on' else 'OFF'}")
        return
    await message.answer(_render_features_text(db))


@router.message(AdminStates.ai_manage)
async def handle_ai_manage(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if text == "status":
        await message.answer(_render_ai_settings_text(db))
        return
    if len(parts) == 2 and parts[0] == "provider":
        db.set_ai_provider(parts[1].lower())
        await message.answer("✅ Основной провайдер обновлён.")
        return
    if len(parts) == 2 and parts[0] in {"fallback1", "fallback2"}:
        value = parts[1].lower()
        db.set_ai_fallback(1 if parts[0] == "fallback1" else 2, None if value == "off" else value)
        await message.answer("✅ Fallback обновлён.")
        return
    if text == "prompt_clear":
        db.set_system_prompt("")
        await message.answer("✅ System prompt очищен.")
        return
    if text.startswith("prompt "):
        db.set_system_prompt(text[7:].strip())
        await message.answer("✅ System prompt обновлён.")
        return
    await message.answer(_render_ai_settings_text(db))


@router.message(AdminStates.tests_manage)
async def handle_tests(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db):
        return
    text = (message.text or "").strip()
    if text == "status":
        await message.answer(_render_tests_text(db))
        return
    if text == "features":
        await message.answer(_render_features_text(db))
        return
    if text == "ai":
        from ai import ask_ai

        try:
            answer, provider = await ask_ai("Напиши слово ТЕСТ")
            await message.answer(f"✅ AI-тест успешен через {provider}\n\n{answer}")
        except Exception as e:
            await message.answer(f"⚠️ AI-тест завершился ошибкой:\n`{e}`")
        return
    if text.startswith("user "):
        uid = text[5:].strip()
        if not uid.isdigit():
            await message.answer(_render_tests_text(db))
            return
        user = db.get_user(int(uid))
        await message.answer(f"`{user}`")
        return
    await message.answer(_render_tests_text(db))


def get_admin_router(db: Optional[Database] = None) -> Router:
    return router
