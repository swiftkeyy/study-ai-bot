import logging
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

from db import Database

logger = logging.getLogger(__name__)


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


router = Router(name="admin")


def user_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Решить задачу"), KeyboardButton(text="✍️ Написать текст")],
            [KeyboardButton(text="🖼 Создать изображение"), KeyboardButton(text="👤 Личный кабинет")],
            [KeyboardButton(text="💎 Купить доступ"), KeyboardButton(text="🎁 Ввести промокод")],
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
            [KeyboardButton(text="➕ Выдать лимит"), KeyboardButton(text="👑 VIP")],
            [KeyboardButton(text="🌍 Лимит всем"), KeyboardButton(text="🎯 Лимит пользователю")],
            [KeyboardButton(text="💲 Цены"), KeyboardButton(text="📢 Рассылка всем")],
            [KeyboardButton(text="💎 Рассылка платным"), KeyboardButton(text="🎟 Промокоды")],
            [KeyboardButton(text="🎁 Начислить бонусы"), KeyboardButton(text="📤 Выгрузка пользователей")],
            [KeyboardButton(text="📨 Заявки поддержки"), KeyboardButton(text="🚫 Бан / разбан")],
            [KeyboardButton(text="🛠 Тех.работы"), KeyboardButton(text="🤠 Админы")],
            [KeyboardButton(text="📡 Обязательная подписка"), KeyboardButton(text="🎛 Управление кнопками")],
            [KeyboardButton(text="🧩 Доп. функции"), KeyboardButton(text="🧠 Настройки AI")],
            [KeyboardButton(text="🧪 Тестовые команды"), KeyboardButton(text="🔙 В меню")],
        ],
        resize_keyboard=True,
    )


def is_admin(message: Message, db: Database) -> bool:
    return bool(message.from_user and db.is_admin(message.from_user.id))


async def deny_if_not_admin(message: Message, db: Database) -> bool:
    if not is_admin(message, db):
        await message.answer("⛔ У тебя нет доступа к админ-панели.")
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
    return "🛠 <b>Админ-панель</b>\n\nВыбери раздел кнопкой ниже."


def _render_admins_text(db: Database) -> str:
    rows = db.list_admins()
    parts = ["🤠 <b>Админы</b>", "", "Команды:", "• <code>list</code>", "• <code>add USER_ID</code>", "• <code>add USER_ID роль</code>", "• <code>del USER_ID</code>", "", "Список:"]
    if not rows:
        parts.append("— пусто")
    else:
        for item in rows:
            username = f"@{item['username']}" if item.get("username") else "—"
            parts.append(f"• <code>{item['user_id']}</code> | {username} | роль: <b>{item['role']}</b>")
    return "\n".join(parts)


def _render_required_subscription_text(db: Database) -> str:
    channel = db.get_required_channel()
    enabled = "включена" if channel.get("enabled") else "выключена"
    return (
        "📡 <b>Обязательная подписка</b>\n\n"
        f"Статус: <b>{enabled}</b>\n"
        f"Канал ID: <code>{channel.get('channel_id') or '—'}</code>\n"
        f"Username: <code>{channel.get('channel_username') or '—'}</code>\n"
        f"Ссылка: {db.get_required_channel_link() or '—'}\n\n"
        "Команды:\n"
        "• <code>on @channelusername</code>\n"
        "• <code>on -100123456789 @channelusername</code>\n"
        "• <code>off</code>\n"
        "• <code>status</code>\n"
        "• <code>text Новый текст блока</code>"
    )


def _render_maintenance_text(db: Database) -> str:
    enabled = "включены" if db.is_maintenance_enabled() else "выключены"
    return (
        "🛠 <b>Тех.работы</b>\n\n"
        f"Сейчас техработы: <b>{enabled}</b>\n\n"
        "Команды:\n"
        "• <code>on</code>\n"
        "• <code>off</code>\n"
        "• <code>status</code>\n"
        "• <code>text Новый текст</code>\n\n"
        f"Текущий текст:\n{db.get_maintenance_text()}"
    )


def _render_promo_text(db: Database) -> str:
    rows = db.list_promo_codes(limit=10)
    lines = [
        "🎟 <b>Промокоды</b>", "", "Команды:",
        "• <code>list</code>",
        "• <code>create CODE requests 5</code>",
        "• <code>create CODE premium_days 7</code>",
        "• <code>create CODE vip 1</code>",
        "• <code>on CODE</code>",
        "• <code>off CODE</code>",
        "• <code>info CODE</code>", "", "Последние:"
    ]
    if not rows:
        lines.append("— пусто")
    else:
        for item in rows:
            lines.append(f"• <code>{item['code']}</code> | {item['reward_type']}={item['reward_value']} | used {item['used_count']} | {'ON' if item['is_active'] else 'OFF'}")
    return "\n".join(lines)


def _render_ban_text() -> str:
    return (
        "🚫 <b>Бан / разбан</b>\n\n"
        "Команды:\n"
        "• <code>ban USER_ID причина</code>\n"
        "• <code>unban USER_ID</code>\n"
        "• <code>status USER_ID</code>"
    )


def _render_bonus_text() -> str:
    return (
        "🎁 <b>Начислить бонусы</b>\n\n"
        "Команды:\n"
        "• <code>user USER_ID REQUESTS</code>\n"
        "• <code>premium USER_ID DAYS</code>\n"
        "• <code>vip USER_ID on</code>\n"
        "• <code>vip USER_ID off</code>\n"
        "• <code>all REQUESTS</code>\n"
        "• <code>paid REQUESTS</code>"
    )


def _render_export_text() -> str:
    return (
        "📤 <b>Выгрузка пользователей</b>\n\n"
        "Команды:\n"
        "• <code>all</code> — выгрузить всех\n"
        "• <code>paid</code> — выгрузить платных"
    )


def _render_support_text(db: Database) -> str:
    tickets = db.get_open_support_tickets(limit=10)
    lines = ["📨 <b>Заявки поддержки</b>", "", "Команды:", "• <code>list</code>", "• <code>show ID</code>", "• <code>reply ID текст</code>", "• <code>close ID</code>", "", "Открытые заявки:"]
    if not tickets:
        lines.append("— нет открытых")
    else:
        for item in tickets:
            preview = (item['message'] or '')[:50].replace('\n', ' ')
            lines.append(f"• <code>{item['id']}</code> | user <code>{item['user_id']}</code> | {preview}")
    return "\n".join(lines)


def _render_menu_buttons_text(db: Database) -> str:
    rows = db.list_menu_buttons()
    lines = ["🎛 <b>Управление кнопками</b>", "", "Команды:", "• <code>list</code>", "• <code>add_text Название | Текст кнопки</code>", "• <code>add_url Название | https://example.com</code>", "• <code>on ID</code>", "• <code>off ID</code>", "• <code>sort ID ПОРЯДОК</code>", "• <code>del ID</code>", "", "Кнопки:"]
    if not rows:
        lines.append("— нет")
    else:
        for item in rows[:20]:
            lines.append(f"• <code>{item['id']}</code> | {'ON' if item['is_active'] else 'OFF'} | {item['action_type']} | {item['title']} | sort={item['sort_order']}")
    return "\n".join(lines)


def _render_features_text(db: Database) -> str:
    features = db.get_all_features()
    lines = ["🧩 <b>Доп. функции</b>", "", "Команды:", "• <code>list</code>", "• <code>on FEATURE</code>", "• <code>off FEATURE</code>", "", "Текущие значения:"]
    for key in ["promocodes", "support", "news", "materials", "image_generation", "solve_by_photo", "referrals"]:
        lines.append(f"• <code>{key}</code> = {'ON' if features.get(key, True) else 'OFF'}")
    return "\n".join(lines)


def _render_ai_settings_text(db: Database) -> str:
    ai = db.get_ai_settings()
    return "\n".join([
        "🧠 <b>Настройки AI</b>", "",
        f"Provider: <b>{ai.get('provider') or '—'}</b>",
        f"Fallback #1: <b>{ai.get('fallback_1') or 'off'}</b>",
        f"Fallback #2: <b>{ai.get('fallback_2') or 'off'}</b>",
        f"Model: <b>{ai.get('model') or '—'}</b>",
        f"System prompt: <b>{'задан' if ai.get('system_prompt') else 'пусто'}</b>",
        "",
        "Команды:",
        "• <code>status</code>",
        "• <code>provider gemini|groq|openrouter</code>",
        "• <code>fallback1 gemini|groq|openrouter|off</code>",
        "• <code>fallback2 gemini|groq|openrouter|off</code>",
        "• <code>prompt Текст системного промпта</code>",
        "• <code>prompt_clear</code>",
    ])


def _render_tests_text(db: Database) -> str:
    ai = db.get_ai_settings()
    features = db.get_all_features()
    return "\n".join([
        "🧪 <b>Тестовые команды</b>", "", "Команды:",
        "• <code>status</code>",
        "• <code>features</code>",
        "• <code>ai</code>",
        "• <code>user USER_ID</code>",
        "",
        f"AI provider: <b>{ai.get('provider')}</b>",
        f"Features loaded: <b>{len(features)}</b>",
    ])


async def _open_admin_section(message: Message, state: FSMContext, text: str, db: Database):
    mapping = {
        "🔎 Найти пользователя": (AdminStates.user_search, "🔎 <b>Поиск пользователя</b>\n\nОтправь <code>USER_ID</code>"),
        "🎁 Выдать подписку": (AdminStates.grant_sub, "🎁 <b>Выдать подписку</b>\n\nФормат: <code>USER_ID DAYS</code>"),
        "❌ Забрать подписку": (AdminStates.revoke_sub, "❌ <b>Забрать подписку</b>\n\nОтправь <code>USER_ID</code>"),
        "➕ Выдать лимит": (AdminStates.add_limit, "➕ <b>Выдать лимит</b>\n\nФормат: <code>USER_ID REQUESTS</code>"),
        "👑 VIP": (AdminStates.toggle_vip, "👑 <b>VIP</b>\n\nФормат: <code>USER_ID on</code> или <code>USER_ID off</code>"),
        "🌍 Лимит всем": (AdminStates.global_limit, "🌍 <b>Лимит всем</b>\n\nОтправь новое значение лимита, например <code>10</code>"),
        "🎯 Лимит пользователю": (AdminStates.user_limit, "🎯 <b>Лимит пользователю</b>\n\nФормат: <code>USER_ID LIMIT</code>"),
        "💲 Цены": (AdminStates.set_price, "💲 <b>Цены</b>\n\nФормат: <code>DAYS stars 100</code> или <code>DAYS rub 199</code>"),
        "📢 Рассылка всем": (AdminStates.broadcast_all, "📢 <b>Рассылка всем</b>\n\nОтправь текст сообщения."),
        "💎 Рассылка платным": (AdminStates.broadcast_paid, "💎 <b>Рассылка платным</b>\n\nОтправь текст сообщения."),
        "🎟 Промокоды": (AdminStates.promo_manage, _render_promo_text(db)),
        "🎁 Начислить бонусы": (AdminStates.bonus_manage, _render_bonus_text()),
        "📤 Выгрузка пользователей": (AdminStates.export_manage, _render_export_text()),
        "📨 Заявки поддержки": (AdminStates.support_manage, _render_support_text(db)),
        "🚫 Бан / разбан": (AdminStates.ban_manage, _render_ban_text()),
        "🛠 Тех.работы": (AdminStates.maintenance_manage, _render_maintenance_text(db)),
        "🤠 Админы": (AdminStates.admin_manage, _render_admins_text(db)),
        "📡 Обязательная подписка": (AdminStates.required_subscription_manage, _render_required_subscription_text(db)),
        "🎛 Управление кнопками": (AdminStates.buttons_manage, _render_menu_buttons_text(db)),
        "🧩 Доп. функции": (AdminStates.features_manage, _render_features_text(db)),
        "🧠 Настройки AI": (AdminStates.ai_manage, _render_ai_settings_text(db)),
        "🧪 Тестовые команды": (AdminStates.tests_manage, _render_tests_text(db)),
    }
    if text == "📊 Статистика":
        stats = db.get_stats()
        await state.clear()
        await message.answer(
            "📊 <b>Статистика</b>\n\n"
            f"Всего пользователей: <b>{stats['users']}</b>\n"
            f"Платных пользователей: <b>{stats['paid']}</b>\n"
            f"Запросов сегодня: <b>{stats['requests_today']}</b>\n"
            f"Доход Stars: <b>{stats['stars']}</b>\n"
            f"Доход RUB: <b>{stats['rub']}</b>",
            reply_markup=admin_keyboard(),
        )
        return
    target = mapping.get(text)
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


@router.message(StateFilter("*"), F.text.in_({"🔙 В меню", "↩ В меню", "❌ Отмена", "Отмена", "Назад"}))
async def admin_exit(message: Message, state: FSMContext):
    db = Database()
    if not is_admin(message, db):
        return
    await state.clear()
    await message.answer("✅ Выход из админки. Возвращаю в обычное меню.", reply_markup=user_menu_keyboard())


@router.message(StateFilter("*"), Command("start"))
async def admin_start_exit(message: Message, state: FSMContext):
    db = Database()
    if not is_admin(message, db):
        return
    await state.clear()
    await message.answer("✅ Выход из текущего режима. Возвращаю в обычное меню.", reply_markup=user_menu_keyboard())


@router.message(StateFilter("*"), F.text.in_({
    "🔎 Найти пользователя", "📊 Статистика", "🎁 Выдать подписку", "❌ Забрать подписку",
    "➕ Выдать лимит", "👑 VIP", "🌍 Лимит всем", "🎯 Лимит пользователю", "💲 Цены",
    "📢 Рассылка всем", "💎 Рассылка платным", "🎟 Промокоды", "🎁 Начислить бонусы",
    "📤 Выгрузка пользователей", "📨 Заявки поддержки", "🚫 Бан / разбан", "🛠 Тех.работы",
    "🤠 Админы", "📡 Обязательная подписка", "🎛 Управление кнопками", "🧩 Доп. функции",
    "🧠 Настройки AI", "🧪 Тестовые команды"
}))
async def admin_state_switch(message: Message, state: FSMContext):
    db = Database()
    if not is_admin(message, db):
        return
    await _open_admin_section(message, state, (message.text or "").strip(), db)


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
    username = f"@{user['username']}" if user['username'] else '—'
    await message.answer(
        f"👤 <b>Пользователь</b>\n\nID: <code>{user['id']}</code>\nUsername: {username}\nЗапросов: <b>{user['requests_left']}</b>\nКартинок: <b>{user['images_left']}</b>\nPremium: <b>{'Да' if user['is_premium'] else 'Нет'}</b>\nVIP: <b>{'Да' if user['is_vip'] else 'Нет'}</b>\nSub until: <b>{user['sub_until'] or '—'}</b>"
    )


@router.message(AdminStates.grant_sub)
async def handle_grant_sub(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db): return
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
    if await deny_if_not_admin(message, db): return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Отправь USER_ID")
        return
    db.revoke_subscription(int(text))
    await message.answer("✅ Подписка забрана.")


@router.message(AdminStates.add_limit)
async def handle_add_limit(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db): return
    parts = (message.text or "").split()
    if len(parts) != 2 or not all(p.lstrip('-').isdigit() for p in parts):
        await message.answer("Формат: USER_ID REQUESTS")
        return
    db.add_user_requests(int(parts[0]), int(parts[1]))
    await message.answer("✅ Лимит выдан.")


@router.message(AdminStates.toggle_vip)
async def handle_vip(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db): return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1].lower() not in {"on", "off"}:
        await message.answer("Формат: USER_ID on/off")
        return
    db.set_vip(int(parts[0]), parts[1].lower() == 'on')
    await message.answer("✅ VIP обновлён.")


@router.message(AdminStates.global_limit)
async def handle_global_limit(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db): return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно число")
        return
    db.set_all_users_requests(int(text))
    await message.answer("✅ Лимит для всех обновлён.")


@router.message(AdminStates.user_limit)
async def handle_user_limit(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db): return
    parts = (message.text or "").split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        await message.answer("Формат: USER_ID LIMIT")
        return
    db.set_user_requests(int(parts[0]), int(parts[1]))
    await message.answer("✅ Лимит пользователя обновлён.")


@router.message(AdminStates.set_price)
async def handle_set_price(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db): return
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
    if await deny_if_not_admin(message, db): return
    sent, failed = await broadcast(message.bot, db.get_all_user_ids(), message.text or "")
    await message.answer(f"✅ Рассылка завершена. Отправлено: {sent}, ошибок: {failed}")


@router.message(AdminStates.broadcast_paid)
async def handle_broadcast_paid(message: Message, state: FSMContext):
    db = Database()
    if await deny_if_not_admin(message, db): return
    sent, failed = await broadcast(message.bot, db.get_paid_user_ids(), message.text or "")
    await message.answer(f"✅ Рассылка платным завершена. Отправлено: {sent}, ошибок: {failed}")


@router.message(AdminStates.ban_manage)
async def handle_ban(message: Message, state: FSMContext):
    db = Database()
    if awai
