import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

from ai import ask_ai
from db import Database

logger = logging.getLogger(__name__)


class AdminStates(StatesGroup):
    waiting_user_search = State()
    waiting_grant_sub = State()
    waiting_revoke_sub = State()
    waiting_add_limit = State()
    waiting_toggle_vip = State()
    waiting_global_limit = State()
    waiting_user_limit = State()
    waiting_set_price = State()
    waiting_broadcast_all = State()
    waiting_broadcast_paid = State()
    waiting_ban_manage = State()
    waiting_maintenance_manage = State()
    waiting_admin_manage = State()
    waiting_required_subscription_manage = State()
    waiting_promo_manage = State()
    waiting_bonus_manage = State()
    waiting_export_manage = State()
    waiting_support_manage = State()
    waiting_buttons_manage = State()
    waiting_features_manage = State()
    waiting_tests_manage = State()
    waiting_ai_manage = State()


ADMIN_MENU_TEXT = (
    "🛠 <b>Админ-панель</b>\n\n"
    "Этап 3 подключён. Теперь здесь есть промокоды, поддержка, бонусы и выгрузка пользователей.\n\n"
    "Выбери действие кнопкой ниже."
)


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Найти пользователя"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🎁 Выдать подписку"), KeyboardButton(text="❌ Забрать подписку")],
            [KeyboardButton(text="➕ Выдать лимит"), KeyboardButton(text="👑 VIP")],
            [KeyboardButton(text="🌍 Лимит всем"), KeyboardButton(text="🎯 Лимит пользователю")],
            [KeyboardButton(text="💲 Цены"), KeyboardButton(text="🎟 Промокоды")],
            [KeyboardButton(text="🎁 Начислить бонусы"), KeyboardButton(text="📤 Выгрузка пользователей")],
            [KeyboardButton(text="📨 Заявки поддержки"), KeyboardButton(text="🚫 Бан / разбан")],
            [KeyboardButton(text="🛠 Тех.работы"), KeyboardButton(text="🤠 Админы")],
            [KeyboardButton(text="📡 Обязательная подписка"), KeyboardButton(text="🎛 Управление кнопками")],
            [KeyboardButton(text="🧩 Доп. функции"), KeyboardButton(text="🧠 Настройки AI")],
            [KeyboardButton(text="🧪 Тестовые команды"), KeyboardButton(text="📢 Рассылка всем")],
            [KeyboardButton(text="💎 Рассылка платным"), KeyboardButton(text="🔙 В меню")],
        ],
        resize_keyboard=True,
    )


def is_admin(message: Message, db: Database) -> bool:
    return bool(message.from_user is not None and db.is_admin(message.from_user.id))


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


def _render_admins_text(db: Database) -> str:
    rows = db.list_admins()
    if not rows:
        return "🤠 <b>Админы</b>\n\nСписок пуст."

    parts = ["🤠 <b>Список админов</b>\n"]
    for item in rows:
        username = f"@{item['username']}" if item.get("username") else "—"
        parts.append(f"• <code>{item['user_id']}</code> | {username} | роль: <b>{item['role']}</b>")
    return "\n".join(parts)


def _render_required_subscription_text(db: Database) -> str:
    channel = db.get_required_channel()
    link = db.get_required_channel_link() or "—"
    chat_ref = channel.get("channel_id") or channel.get("channel_username") or "—"
    enabled = "включена" if channel.get("enabled") else "выключена"
    return (
        "📡 <b>Обязательная подписка</b>\n\n"
        f"Статус: <b>{enabled}</b>\n"
        f"Канал: <code>{chat_ref}</code>\n"
        f"Ссылка: {link}\n\n"
        "Команды:\n"
        "• <code>on @channelusername</code> — включить по username\n"
        "• <code>on -100123456789 @channelusername</code> — включить по id + username\n"
        "• <code>off</code> — выключить\n"
        "• <code>status</code> — показать текущие настройки\n"
        "• <code>text Новый текст блока</code> — поменять текст экрана подписки\n\n"
        "Важно: добавь бота админом в канал, иначе Telegram может не дать проверить подписку."
    )


def _render_maintenance_text(db: Database) -> str:
    enabled = "включены" if db.is_maintenance_enabled() else "выключены"
    return (
        "🛠 <b>Тех.работы</b>\n\n"
        f"Сейчас техработы: <b>{enabled}</b>\n\n"
        "Команды:\n"
        "• <code>on</code> — включить\n"
        "• <code>off</code> — выключить\n"
        "• <code>status</code> — показать статус\n"
        "• <code>text Новый текст уведомления</code> — поменять сообщение пользователям\n\n"
        f"Текущий текст:\n{db.get_maintenance_text()}"
    )


def _render_promo_text(db: Database) -> str:
    rows = db.list_promo_codes(limit=10)
    lines = [
        "🎟 <b>Промокоды</b>",
        "",
        "Команды:",
        "• <code>list</code>",
        "• <code>create CODE requests 5</code>",
        "• <code>create CODE premium_days 7</code>",
        "• <code>create CODE vip 1</code>",
        "• <code>on CODE</code>",
        "• <code>off CODE</code>",
        "• <code>info CODE</code>",
        "",
        "Последние промокоды:",
    ]
    if not rows:
        lines.append("— пока пусто")
    else:
        for item in rows:
            lines.append(
                f"• <code>{item['code']}</code> | {item['reward_type']}={item['reward_value']} | used {item['used_count']} | {'ON' if item['is_active'] else 'OFF'}"
            )
    return "\n".join(lines)


def _render_support_text(db: Database) -> str:
    tickets = db.get_open_support_tickets(limit=10)
    lines = [
        "💬 <b>Поддержка</b>",
        "",
        "Команды:",
        "• <code>list</code>",
        "• <code>show TICKET_ID</code>",
        "• <code>reply TICKET_ID текст ответа</code>",
        "• <code>close TICKET_ID</code>",
        "",
        "Открытые обращения:",
    ]
    if not tickets:
        lines.append("— нет открытых обращений")
    else:
        for item in tickets:
            preview = (item["message"] or "")[:50].replace("\n", " ")
            lines.append(f"• <code>{item['id']}</code> | user <code>{item['user_id']}</code> | {preview}")
    return "\n".join(lines)


def _render_menu_buttons_text(db: Database) -> str:
    rows = db.list_menu_buttons()
    lines = [
        "🎛 <b>Управление кнопками</b>",
        "",
        "Команды:",
        "• <code>list</code>",
        "• <code>add_text Название | Текст кнопки</code>",
        "• <code>add_url Название | https://example.com</code>",
        "• <code>on ID</code>",
        "• <code>off ID</code>",
        "• <code>sort ID ПОРЯДОК</code>",
        "• <code>del ID</code>",
        "",
        "Текущие кнопки:",
    ]
    if not rows:
        lines.append("— пока нет дополнительных кнопок")
    else:
        for item in rows[:20]:
            lines.append(
                f"• <code>{item['id']}</code> | {'ON' if item['is_active'] else 'OFF'} | {item['action_type']} | {item['title']} | sort={item['sort_order']}"
            )
    return "\n".join(lines)


def _render_features_text(db: Database) -> str:
    names = {
        "promocodes": "Промокоды",
        "support": "Поддержка",
        "news": "Новости",
        "materials": "Полезные материалы",
        "image_generation": "Генерация изображений",
        "solve_by_photo": "Решение задач по фото",
        "referrals": "Реферальная программа",
    }
    lines = [
        "🧩 <b>Доп. функции</b>",
        "",
        "Команды:",
        "• <code>list</code>",
        "• <code>on FEATURE</code>",
        "• <code>off FEATURE</code>",
        "",
        "Доступные FEATURE:",
    ]
    for key, title in names.items():
        lines.append(f"• <code>{key}</code> — {title} | {'ON' if db.is_feature_enabled(key, True) else 'OFF'}")
    return "\n".join(lines)


def _render_ai_settings_text(db: Database) -> str:
    ai = db.get_ai_settings()
    lines = [
        "🧠 <b>Настройки AI</b>",
        "",
        f"Основной провайдер: <b>{ai['provider']}</b>",
        f"Fallback #1: <b>{ai['fallback_1'] or 'off'}</b>",
        f"Fallback #2: <b>{ai['fallback_2'] or 'off'}</b>",
        f"Image provider: <b>{ai['image_provider']}</b>",
        f"System prompt: <b>{'задан' if ai['system_prompt'] else 'не задан'}</b>",
        "",
        "Команды:",
        "• <code>status</code>",
        "• <code>provider gemini</code>",
        "• <code>fallback1 groq</code>",
        "• <code>fallback2 openrouter</code>",
        "• <code>fallback1 off</code>",
        "• <code>fallback2 off</code>",
        "• <code>prompt Твой новый системный промпт</code>",
        "• <code>prompt_clear</code>",
    ]
    if ai['system_prompt']:
        lines.extend(["", "Текущий prompt:", ai['system_prompt']])
    return "\n".join(lines)


def _render_test_commands_text(db: Database) -> str:
    ai = db.get_ai_settings()
    lines = [
        "🧪 <b>Тестовые команды</b>",
        "",
        "Команды:",
        "• <code>status</code> — краткий статус системы",
        "• <code>features</code> — список флагов",
        "• <code>ai</code> — тестовый AI-запрос",
        "• <code>user USER_ID</code> — краткая проверка пользователя",
        "",
        f"Сейчас AI-цепочка: <b>{ai['provider']}</b> → <b>{ai['fallback_1'] or 'off'}</b> → <b>{ai['fallback_2'] or 'off'}</b>",
    ]
    return "\n".join(lines)


def get_admin_router(db: Database) -> Router:
    router = Router(name="admin")

    @router.message(Command("admin"))
    async def admin_start(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.clear()
        await message.answer(ADMIN_MENU_TEXT, reply_markup=admin_keyboard())

    @router.message(F.text == "🔎 Найти пользователя")
    async def admin_find_user(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_user_search)
        await message.answer("Введи ID пользователя.\nПример: <code>123456789</code>")

    @router.message(AdminStates.waiting_user_search)
    async def admin_find_user_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        try:
            user_id = int((message.text or "").strip())
        except ValueError:
            await message.answer("Нужен числовой ID. Попробуй ещё раз.")
            return
        await message.answer(db.export_user_profile_text(user_id))
        await state.clear()

    @router.message(F.text == "📊 Статистика")
    async def admin_stats(message: Message):
        if await deny_if_not_admin(message, db):
            return
        income = db.income_stats()
        required = db.get_required_channel()
        text = (
            "📊 <b>Статистика</b>\n\n"
            f"Всего пользователей: <b>{db.user_count()}</b>\n"
            f"Платных пользователей: <b>{db.paid_user_count()}</b>\n"
            f"Запросов сегодня: <b>{db.requests_today_count()}</b>\n"
            f"Доход Stars: <b>{int(income['stars'])}</b> ⭐\n"
            f"Доход ЮKassa: <b>{income['rub']:.2f}</b> ₽\n"
            f"Техработы: <b>{'ON' if db.is_maintenance_enabled() else 'OFF'}</b>\n"
            f"Обязательная подписка: <b>{'ON' if required['enabled'] else 'OFF'}</b>"
        )
        await message.answer(text)

    @router.message(F.text == "🎁 Выдать подписку")
    async def admin_grant_sub(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_grant_sub)
        await message.answer("Введи: <code>user_id дни</code>\nПример: <code>123456789 30</code>")

    @router.message(AdminStates.waiting_grant_sub)
    async def admin_grant_sub_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        try:
            user_id_str, days_str = (message.text or "").split()
            user_id = int(user_id_str)
            days = int(days_str)
        except ValueError:
            await message.answer("Формат неверный. Нужен формат: <code>user_id дни</code>")
            return
        db.get_or_create_user(user_id)
        db.activate_subscription(user_id, days)
        await message.answer(f"✅ Подписка выдана пользователю <code>{user_id}</code> на <b>{days}</b> дней.")
        await state.clear()

    @router.message(F.text == "❌ Забрать подписку")
    async def admin_revoke_sub(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_revoke_sub)
        await message.answer("Введи ID пользователя.\nПример: <code>123456789</code>")

    @router.message(AdminStates.waiting_revoke_sub)
    async def admin_revoke_sub_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        try:
            user_id = int((message.text or "").strip())
        except ValueError:
            await message.answer("Нужен числовой ID.")
            return
        db.revoke_subscription(user_id)
        await message.answer(f"✅ Подписка у пользователя <code>{user_id}</code> отключена.")
        await state.clear()

    @router.message(F.text == "➕ Выдать лимит")
    async def admin_add_limit(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_add_limit)
        await message.answer("Введи: <code>user_id количество</code>\nПример: <code>123456789 10</code>")

    @router.message(AdminStates.waiting_add_limit)
    async def admin_add_limit_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        try:
            user_id_str, amount_str = (message.text or "").split()
            user_id = int(user_id_str)
            amount = int(amount_str)
        except ValueError:
            await message.answer("Формат неверный. Нужен: <code>user_id количество</code>")
            return
        db.get_or_create_user(user_id)
        db.add_requests(user_id, amount)
        await message.answer(f"✅ Пользователю <code>{user_id}</code> добавлено <b>{amount}</b> запросов.")
        await state.clear()

    @router.message(F.text == "👑 VIP")
    async def admin_vip(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_toggle_vip)
        await message.answer("Введи: <code>user_id on/off</code>\nПример: <code>123456789 on</code>")

    @router.message(AdminStates.waiting_toggle_vip)
    async def admin_vip_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        try:
            user_id_str, mode = (message.text or "").split()
            user_id = int(user_id_str)
        except ValueError:
            await message.answer("Формат неверный. Используй: <code>user_id on/off</code>")
            return
        mode = mode.lower().strip()
        if mode not in {"on", "off"}:
            await message.answer("Второй параметр должен быть <code>on</code> или <code>off</code>.")
            return
        db.get_or_create_user(user_id)
        db.set_vip(user_id, mode == "on")
        await message.answer(f"✅ VIP для <code>{user_id}</code>: <b>{'включён' if mode == 'on' else 'выключен'}</b>.")
        await state.clear()

    @router.message(F.text == "🌍 Лимит всем")
    async def admin_global_limit(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_global_limit)
        await message.answer("Введи новый лимит для всех бесплатных пользователей.\nПример: <code>5</code>")

    @router.message(AdminStates.waiting_global_limit)
    async def admin_global_limit_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        try:
            value = int((message.text or "").strip())
        except ValueError:
            await message.answer("Нужно число.")
            return
        db.apply_free_limit_to_all(value)
        await message.answer(f"✅ Новый общий лимит установлен: <b>{value}</b> запросов.")
        await state.clear()

    @router.message(F.text == "🎯 Лимит пользователю")
    async def admin_user_limit(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_user_limit)
        await message.answer("Введи: <code>user_id новый_лимит</code>\nПример: <code>123456789 25</code>")

    @router.message(AdminStates.waiting_user_limit)
    async def admin_user_limit_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        try:
            user_id_str, value_str = (message.text or "").split()
            user_id = int(user_id_str)
            value = int(value_str)
        except ValueError:
            await message.answer("Формат неверный. Используй: <code>user_id новый_лимит</code>")
            return
        db.get_or_create_user(user_id)
        db.set_user_limit(user_id, value)
        await message.answer(f"✅ Лимит пользователя <code>{user_id}</code> теперь <b>{value}</b>.")
        await state.clear()

    @router.message(F.text == "💲 Цены")
    async def admin_prices(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        prices = db.get_prices()
        await state.set_state(AdminStates.waiting_set_price)
        await message.answer(
            "💲 <b>Текущие цены</b>\n\n"
            f"3 дня: {prices[3]['stars']} ⭐ / {prices[3]['rub']} ₽\n"
            f"7 дней: {prices[7]['stars']} ⭐ / {prices[7]['rub']} ₽\n"
            f"30 дней: {prices[30]['stars']} ⭐ / {prices[30]['rub']} ₽\n\n"
            "Введи новую цену в формате:\n"
            "<code>дни stars rub</code>\n"
            "Пример: <code>30 149 399</code>"
        )

    @router.message(AdminStates.waiting_set_price)
    async def admin_prices_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        try:
            days_str, stars_str, rub_str = (message.text or "").split()
            days = int(days_str)
            stars_price = int(stars_str)
            rub_price = int(rub_str)
        except ValueError:
            await message.answer("Формат неверный. Используй: <code>дни stars rub</code>")
            return
        try:
            db.set_prices(days, stars_price, rub_price)
        except ValueError as e:
            await message.answer(str(e))
            return
        await message.answer(f"✅ Цены для тарифа <b>{days} дней</b> обновлены:\n⭐ {stars_price}\n💳 {rub_price} ₽")
        await state.clear()

    @router.message(F.text == "🎟 Промокоды")
    async def admin_promo_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_promo_manage)
        await message.answer(_render_promo_text(db))

    @router.message(AdminStates.waiting_promo_manage)
    async def admin_promo_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "list":
            await message.answer(_render_promo_text(db))
            return
        if lower.startswith("create "):
            parts = text.split()
            if len(parts) != 4:
                await message.answer("Используй: <code>create CODE requests 5</code>")
                return
            _, code, reward_type, reward_value = parts
            if reward_type not in {"requests", "premium_days", "vip"}:
                await message.answer("Тип награды: requests / premium_days / vip")
                return
            try:
                reward_value = int(reward_value)
            except ValueError:
                await message.answer("Значение награды должно быть числом.")
                return
            try:
                db.create_promo_code(code, reward_type, reward_value)
            except Exception as e:
                await message.answer(f"Не удалось создать промокод: {e}")
                return
            await message.answer(f"✅ Промокод <code>{code.upper()}</code> создан.")
            await state.clear()
            return
        if lower.startswith("off "):
            code = text.split(maxsplit=1)[1]
            ok = db.set_promo_code_active(code, False)
            await message.answer("✅ Промокод выключен." if ok else "Промокод не найден.")
            if ok:
                await state.clear()
            return
        if lower.startswith("on "):
            code = text.split(maxsplit=1)[1]
            ok = db.set_promo_code_active(code, True)
            await message.answer("✅ Промокод включён." if ok else "Промокод не найден.")
            if ok:
                await state.clear()
            return
        if lower.startswith("info "):
            code = text.split(maxsplit=1)[1]
            promo = db.get_promo_code(code)
            if not promo:
                await message.answer("Промокод не найден.")
                return
            await message.answer(
                "🎟 <b>Информация о промокоде</b>\n\n"
                f"Код: <code>{promo['code']}</code>\n"
                f"Тип награды: <b>{promo['reward_type']}</b>\n"
                f"Значение: <b>{promo['reward_value']}</b>\n"
                f"Использований: <b>{promo['used_count']}</b>\n"
                f"Активен: <b>{'да' if promo['is_active'] else 'нет'}</b>"
            )
            return
        await message.answer("Используй: <code>list</code>, <code>create</code>, <code>on</code>, <code>off</code> или <code>info</code>.")

    @router.message(F.text == "🎁 Начислить бонусы")
    async def admin_bonus_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_bonus_manage)
        await message.answer(
            "🎁 <b>Начислить бонусы</b>\n\n"
            "Команды:\n"
            "• <code>user USER_ID REQUESTS</code>\n"
            "• <code>premium USER_ID DAYS</code>\n"
            "• <code>vip USER_ID on/off</code>\n"
            "• <code>all REQUESTS</code>\n"
            "• <code>paid REQUESTS</code>"
        )

    @router.message(AdminStates.waiting_bonus_manage)
    async def admin_bonus_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        parts = text.split()
        if lower.startswith("user ") and len(parts) == 3:
            try:
                user_id = int(parts[1])
                amount = int(parts[2])
            except ValueError:
                await message.answer("USER_ID и REQUESTS должны быть числами.")
                return
            db.get_or_create_user(user_id)
            db.add_requests(user_id, amount, bonus=True)
            await message.answer(f"✅ Пользователю <code>{user_id}</code> начислено <b>{amount}</b> запросов.")
            await state.clear()
            return
        if lower.startswith("premium ") and len(parts) == 3:
            try:
                user_id = int(parts[1])
                days = int(parts[2])
            except ValueError:
                await message.answer("USER_ID и DAYS должны быть числами.")
                return
            db.get_or_create_user(user_id)
            db.activate_subscription(user_id, days)
            await message.answer(f"✅ Пользователю <code>{user_id}</code> выдано <b>{days}</b> дней подписки.")
            await state.clear()
            return
        if lower.startswith("vip ") and len(parts) == 3:
            try:
                user_id = int(parts[1])
            except ValueError:
                await message.answer("USER_ID должен быть числом.")
                return
            mode = parts[2].lower()
            if mode not in {"on", "off"}:
                await message.answer("Используй on/off")
                return
            db.get_or_create_user(user_id)
            db.set_vip(user_id, mode == "on")
            await message.answer(f"✅ VIP для <code>{user_id}</code>: <b>{'включён' if mode == 'on' else 'выключен'}</b>.")
            await state.clear()
            return
        if lower.startswith("all ") and len(parts) == 2:
            try:
                amount = int(parts[1])
            except ValueError:
                await message.answer("REQUESTS должно быть числом.")
                return
            for user_id in db.all_user_ids(only_paid=False):
                db.add_requests(user_id, amount, bonus=True)
            await message.answer(f"✅ Всем пользователям начислено по <b>{amount}</b> запросов.")
            await state.clear()
            return
        if lower.startswith("paid ") and len(parts) == 2:
            try:
                amount = int(parts[1])
            except ValueError:
                await message.answer("REQUESTS должно быть числом.")
                return
            for user_id in db.all_user_ids(only_paid=True):
                db.add_requests(user_id, amount, bonus=True)
            await message.answer(f"✅ Всем платным пользователям начислено по <b>{amount}</b> запросов.")
            await state.clear()
            return
        await message.answer("Используй: <code>user</code>, <code>premium</code>, <code>vip</code>, <code>all</code>, <code>paid</code>.")

    @router.message(F.text == "📤 Выгрузка пользователей")
    async def admin_export_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_export_manage)
        await message.answer(
            "📤 <b>Выгрузка пользователей</b>\n\n"
            "Команды:\n"
            "• <code>all</code> — выгрузить всех\n"
            "• <code>paid</code> — выгрузить только платных"
        )

    @router.message(AdminStates.waiting_export_manage)
    async def admin_export_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        command = (message.text or "").strip().lower()
        if command not in {"all", "paid"}:
            await message.answer("Используй: <code>all</code> или <code>paid</code>")
            return
        csv_text = db.export_users_csv(only_paid=(command == "paid"))
        filename = "paid_users.csv" if command == "paid" else "all_users.csv"
        file = BufferedInputFile(csv_text.encode("utf-8"), filename=filename)
        await message.answer_document(file, caption="✅ Выгрузка готова")
        await state.clear()

    @router.message(F.text == "📨 Заявки поддержки")
    async def admin_support_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_support_manage)
        await message.answer(_render_support_text(db))

    @router.message(AdminStates.waiting_support_manage)
    async def admin_support_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "list":
            await message.answer(_render_support_text(db))
            return
        if lower.startswith("show "):
            try:
                ticket_id = int(text.split(maxsplit=1)[1])
            except Exception:
                await message.answer("Используй: <code>show TICKET_ID</code>")
                return
            ticket = db.get_support_ticket(ticket_id)
            if not ticket:
                await message.answer("Обращение не найдено.")
                return
            await message.answer(
                "💬 <b>Обращение</b>\n\n"
                f"Ticket ID: <code>{ticket['id']}</code>\n"
                f"User ID: <code>{ticket['user_id']}</code>\n"
                f"Статус: <b>{ticket['status']}</b>\n\n"
                f"Сообщение:\n{ticket['message']}\n\n"
                f"Ответ:\n{ticket.get('admin_reply') or '—'}"
            )
            return
        if lower.startswith("reply "):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                await message.answer("Используй: <code>reply TICKET_ID текст ответа</code>")
                return
            try:
                ticket_id = int(parts[1])
            except ValueError:
                await message.answer("TICKET_ID должен быть числом.")
                return
            reply_text = parts[2].strip()
            ticket = db.get_support_ticket(ticket_id)
            if not ticket:
                await message.answer("Обращение не найдено.")
                return
            db.reply_support_ticket(ticket_id, reply_text)
            try:
                await message.bot.send_message(
                    ticket["user_id"],
                    "💬 <b>Ответ поддержки</b>\n\n"
                    f"По обращению <code>{ticket_id}</code>:\n{reply_text}"
                )
            except Exception as e:
                await message.answer(f"Ответ сохранён, но не удалось отправить пользователю: {e}")
                return
            await message.answer(f"✅ Ответ по обращению <code>{ticket_id}</code> отправлен.")
            await state.clear()
            return
        if lower.startswith("close "):
            try:
                ticket_id = int(text.split(maxsplit=1)[1])
            except Exception:
                await message.answer("Используй: <code>close TICKET_ID</code>")
                return
            ok = db.close_support_ticket(ticket_id)
            await message.answer("✅ Обращение закрыто." if ok else "Обращение не найдено.")
            if ok:
                await state.clear()
            return
        await message.answer("Используй: <code>list</code>, <code>show</code>, <code>reply</code>, <code>close</code>.")

    @router.message(F.text == "🚫 Бан / разбан")
    async def admin_ban_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_ban_manage)
        await message.answer(
            "🚫 <b>Бан / разбан</b>\n\n"
            "Команды:\n"
            "• <code>ban user_id причина</code>\n"
            "• <code>unban user_id</code>\n"
            "• <code>status user_id</code>"
        )

    @router.message(AdminStates.waiting_ban_manage)
    async def admin_ban_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower.startswith("ban "):
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                await message.answer("Используй: <code>ban user_id причина</code>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                await message.answer("ID пользователя должен быть числом.")
                return
            if db.is_admin(user_id):
                await message.answer("Нельзя забанить администратора через эту команду.")
                return
            reason = parts[2].strip() if len(parts) > 2 else "Без причины"
            db.ban_user(user_id, reason=reason, banned_by=message.from_user.id)
            await message.answer(f"✅ Пользователь <code>{user_id}</code> забанен.\nПричина: <b>{reason}</b>")
            await state.clear()
            return
        if lower.startswith("unban "):
            parts = text.split(maxsplit=1)
            if len(parts) != 2:
                await message.answer("Используй: <code>unban user_id</code>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                await message.answer("ID пользователя должен быть числом.")
                return
            db.unban_user(user_id)
            await message.answer(f"✅ Пользователь <code>{user_id}</code> разбанен.")
            await state.clear()
            return
        if lower.startswith("status "):
            parts = text.split(maxsplit=1)
            try:
                user_id = int(parts[1])
            except Exception:
                await message.answer("Используй: <code>status user_id</code>")
                return
            user = db.get_user(user_id)
            if not user:
                await message.answer("Пользователь не найден.")
                return
            await message.answer(
                f"Статус пользователя <code>{user_id}</code>:\n"
                f"Бан: <b>{'да' if user.get('is_banned') else 'нет'}</b>\n"
                f"Причина: <b>{user.get('ban_reason') or '—'}</b>"
            )
            return
        await message.answer("Не понял команду. Используй: <code>ban</code>, <code>unban</code> или <code>status</code>.")

    @router.message(F.text == "🛠 Тех.работы")
    async def admin_maintenance_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_maintenance_manage)
        await message.answer(_render_maintenance_text(db))

    @router.message(AdminStates.waiting_maintenance_manage)
    async def admin_maintenance_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "status":
            await message.answer(_render_maintenance_text(db))
            return
        if lower == "on":
            db.set_maintenance_mode(True)
            await message.answer("✅ Техработы включены. Теперь обычные пользователи будут видеть экран техработ.")
            await state.clear()
            return
        if lower == "off":
            db.set_maintenance_mode(False)
            await message.answer("✅ Техработы выключены.")
            await state.clear()
            return
        if lower.startswith("text "):
            new_text = text[5:].strip()
            if not new_text:
                await message.answer("После <code>text</code> нужен новый текст.")
                return
            db.set_maintenance_mode(db.is_maintenance_enabled(), text=new_text)
            await message.answer("✅ Текст техработ обновлён.")
            return
        await message.answer("Используй: <code>on</code>, <code>off</code>, <code>status</code> или <code>text ...</code>")

    @router.message(F.text == "🤠 Админы")
    async def admin_manage_admins_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_admin_manage)
        await message.answer(
            _render_admins_text(db)
            + "\n\nКоманды:\n"
              "• <code>list</code>\n"
              "• <code>add user_id</code>\n"
              "• <code>add user_id роль</code>\n"
              "• <code>del user_id</code>"
        )

    @router.message(AdminStates.waiting_admin_manage)
    async def admin_manage_admins_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "list":
            await message.answer(_render_admins_text(db))
            return
        if lower.startswith("add "):
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                await message.answer("Используй: <code>add user_id</code> или <code>add user_id роль</code>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                await message.answer("ID должен быть числом.")
                return
            role = parts[2].strip() if len(parts) == 3 else "admin"
            db.add_admin(user_id, role=role)
            await message.answer(f"✅ Админ <code>{user_id}</code> добавлен с ролью <b>{role}</b>.")
            await state.clear()
            return
        if lower.startswith("del "):
            parts = text.split(maxsplit=1)
            try:
                user_id = int(parts[1])
            except Exception:
                await message.answer("Используй: <code>del user_id</code>")
                return
            db.remove_admin(user_id)
            await message.answer(f"✅ Админ <code>{user_id}</code> удалён.")
            await state.clear()
            return
        await message.answer("Используй: <code>list</code>, <code>add</code> или <code>del</code>.")

    @router.message(F.text == "📡 Обязательная подписка")
    async def admin_required_sub_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_required_subscription_manage)
        await message.answer(_render_required_subscription_text(db))

    @router.message(AdminStates.waiting_required_subscription_manage)
    async def admin_required_sub_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "status":
            stats = (
                f"👤 Users: <b>{db.user_count()}</b>\n"
                f"💎 Paid: <b>{db.paid_user_count()}</b>\n"
                f"🛠 Maintenance: <b>{'ON' if db.is_maintenance_enabled() else 'OFF'}</b>\n"
                f"📡 Required subscription: <b>{'ON' if db.get_required_channel().get('enabled') else 'OFF'}</b>"
            )
            await message.answer("🧪 <b>Статус системы</b>\n\n" + stats)
            return
        if lower == "features":
            await message.answer(_render_features_text(db))
            return
        if lower == "ai":
            ai_settings = db.get_ai_settings()
            provider_order = [ai_settings.get("provider"), ai_settings.get("fallback_1"), ai_settings.get("fallback_2")]
            try:
                answer, provider = await ask_ai(
                    "Ответь одним коротким словом: ok",
                    system_prompt="Ты выполняешь техническую самопроверку бота.",
                    provider_order=provider_order,
                )
                await message.answer(
                    "✅ <b>AI-тест прошёл</b>\n\n"
                    f"Провайдер: <b>{provider}</b>\n"
                    f"Ответ: <code>{answer}</code>"
                )
            except Exception as e:
                await message.answer(f"⚠️ AI-тест завершился ошибкой:\n<code>{e}</code>")
            return
        if lower.startswith("user "):
            try:
                user_id = int(text.split(maxsplit=1)[1])
            except Exception:
                await message.answer("Используй: <code>user USER_ID</code>")
                return
            await message.answer(db.export_user_profile_text(user_id))
            return
        await message.answer("Используй: <code>status</code>, <code>features</code>, <code>ai</code> или <code>user USER_ID</code>.")

    @router.message(F.text == "🎛 Управление кнопками")
    async def admin_buttons_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_buttons_manage)
        await message.answer(_render_menu_buttons_text(db))

    @router.message(AdminStates.waiting_buttons_manage)
    async def admin_buttons_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "list":
            await message.answer(_render_menu_buttons_text(db))
            return
        if lower.startswith("add_text "):
            payload = text[9:].strip()
            if "|" not in payload:
                await message.answer("Используй: <code>add_text Название | Текст кнопки</code>")
                return
            title, value = [part.strip() for part in payload.split("|", 1)]
            if not title or not value:
                await message.answer("И название, и текст должны быть заполнены.")
                return
            db.add_menu_button(title=title, action_type="show_text", action_value=value)
            await message.answer(f"✅ Кнопка <b>{title}</b> добавлена.")
            return
        if lower.startswith("add_url "):
            payload = text[8:].strip()
            if "|" not in payload:
                await message.answer("Используй: <code>add_url Название | https://example.com</code>")
                return
            title, value = [part.strip() for part in payload.split("|", 1)]
            if not title or not value:
                await message.answer("И название, и ссылка должны быть заполнены.")
                return
            db.add_menu_button(title=title, action_type="open_url", action_value=value)
            await message.answer(f"✅ Ссылочная кнопка <b>{title}</b> добавлена.")
            return
        if lower.startswith("on "):
            try:
                button_id = int(text.split(maxsplit=1)[1])
            except Exception:
                await message.answer("Используй: <code>on ID</code>")
                return
            ok = db.set_menu_button_active(button_id, True)
            await message.answer("✅ Кнопка включена." if ok else "⚠️ Кнопка не найдена.")
            return
        if lower.startswith("off "):
            try:
                button_id = int(text.split(maxsplit=1)[1])
            except Exception:
                await message.answer("Используй: <code>off ID</code>")
                return
            ok = db.set_menu_button_active(button_id, False)
            await message.answer("✅ Кнопка выключена." if ok else "⚠️ Кнопка не найдена.")
            return
        if lower.startswith("sort "):
            parts = text.split()
            if len(parts) != 3:
                await message.answer("Используй: <code>sort ID ПОРЯДОК</code>")
                return
            try:
                button_id = int(parts[1])
                sort_order = int(parts[2])
            except Exception:
                await message.answer("ID и порядок должны быть числами.")
                return
            ok = db.update_menu_button_sort(button_id, sort_order)
            await message.answer("✅ Порядок обновлён." if ok else "⚠️ Кнопка не найдена.")
            return
        if lower.startswith("del "):
            try:
                button_id = int(text.split(maxsplit=1)[1])
            except Exception:
                await message.answer("Используй: <code>del ID</code>")
                return
            ok = db.delete_menu_button(button_id)
            await message.answer("✅ Кнопка удалена." if ok else "⚠️ Кнопка не найдена.")
            return
        await message.answer(_render_menu_buttons_text(db))

    @router.message(F.text == "🧩 Доп. функции")
    async def admin_features_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_features_manage)
        await message.answer(_render_features_text(db))

    @router.message(AdminStates.waiting_features_manage)
    async def admin_features_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "list":
            await message.answer(_render_features_text(db))
            return
        if lower.startswith("on "):
            feature = text.split(maxsplit=1)[1].strip().lower()
            db.set_feature_enabled(feature, True)
            await message.answer(f"✅ Функция <code>{feature}</code> включена.")
            return
        if lower.startswith("off "):
            feature = text.split(maxsplit=1)[1].strip().lower()
            db.set_feature_enabled(feature, False)
            await message.answer(f"✅ Функция <code>{feature}</code> выключена.")
            return
        await message.answer(_render_features_text(db))

    @router.message(F.text == "🧠 Настройки AI")
    async def admin_ai_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_ai_manage)
        await message.answer(_render_ai_settings_text(db))

    @router.message(AdminStates.waiting_ai_manage)
    async def admin_ai_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "status":
            await message.answer(_render_ai_settings_text(db))
            return
        if lower.startswith("provider "):
            provider = text.split(maxsplit=1)[1].strip().lower()
            db.set_ai_provider(provider)
            await message.answer(f"✅ Основной AI-провайдер: <b>{provider}</b>")
            return
        if lower.startswith("fallback1 "):
            provider = text.split(maxsplit=1)[1].strip().lower()
            db.set_ai_fallback(1, "" if provider == "off" else provider)
            await message.answer(f"✅ Fallback #1: <b>{provider}</b>")
            return
        if lower.startswith("fallback2 "):
            provider = text.split(maxsplit=1)[1].strip().lower()
            db.set_ai_fallback(2, "" if provider == "off" else provider)
            await message.answer(f"✅ Fallback #2: <b>{provider}</b>")
            return
        if lower.startswith("prompt "):
            prompt = text[7:].strip()
            db.set_ai_system_prompt(prompt)
            await message.answer("✅ Системный prompt обновлён.")
            return
        if lower == "prompt_clear":
            db.set_ai_system_prompt("")
            await message.answer("✅ Системный prompt очищен.")
            return
        await message.answer(_render_ai_settings_text(db))

    @router.message(F.text == "🧪 Тестовые команды")
    async def admin_tests_entry(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_tests_manage)
        await message.answer(_render_test_commands_text(db))

    @router.message(AdminStates.waiting_tests_manage)
    async def admin_tests_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        text = (message.text or "").strip()
        lower = text.lower()
        if lower == "status":
            stats = (
                f"👤 Users: <b>{db.user_count()}</b>\n"
                f"💎 Paid: <b>{db.paid_user_count()}</b>\n"
                f"🛠 Maintenance: <b>{'ON' if db.is_maintenance_enabled() else 'OFF'}</b>\n"
                f"📡 Required subscription: <b>{'ON' if db.get_required_channel().get('enabled') else 'OFF'}</b>"
            )
            await message.answer("🧪 <b>Статус системы</b>\n\n" + stats)
            return
        if lower == "features":
            await message.answer(_render_features_text(db))
            return
        if lower == "ai":
            ai_settings = db.get_ai_settings()
            provider_order = [ai_settings.get("provider"), ai_settings.get("fallback_1"), ai_settings.get("fallback_2")]
            try:
                answer, provider = await ask_ai(
                    "Ответь одним коротким словом: ok",
                    system_prompt="Ты выполняешь техническую самопроверку бота.",
                    provider_order=provider_order,
                )
                await message.answer(
                    "✅ <b>AI-тест прошёл</b>\n\n"
                    f"Провайдер: <b>{provider}</b>\n"
                    f"Ответ: <code>{answer}</code>"
                )
            except Exception as e:
                await message.answer(f"⚠️ AI-тест завершился ошибкой:\n<code>{e}</code>")
            return
        if lower.startswith("user "):
            try:
                user_id = int(text.split(maxsplit=1)[1])
            except Exception:
                await message.answer("Используй: <code>user USER_ID</code>")
                return
            await message.answer(db.export_user_profile_text(user_id))
            return
        await message.answer("Используй: <code>status</code>, <code>features</code>, <code>ai</code> или <code>user USER_ID</code>.")

    @router.message(F.text == "📢 Рассылка всем")
    async def admin_broadcast_all(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_broadcast_all)
        await message.answer("Пришли текст рассылки для всех пользователей.")

    @router.message(AdminStates.waiting_broadcast_all)
    async def admin_broadcast_all_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        user_ids = db.all_user_ids(only_paid=False)
        sent, failed = await broadcast(message.bot, user_ids, message.html_text or message.text or "")
        await message.answer(f"✅ Рассылка завершена. Отправлено: <b>{sent}</b>, ошибок: <b>{failed}</b>.")
        await state.clear()

    @router.message(F.text == "💎 Рассылка платным")
    async def admin_broadcast_paid(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.set_state(AdminStates.waiting_broadcast_paid)
        await message.answer("Пришли текст рассылки только для платных пользователей.")

    @router.message(AdminStates.waiting_broadcast_paid)
    async def admin_broadcast_paid_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        user_ids = db.all_user_ids(only_paid=True)
        sent, failed = await broadcast(message.bot, user_ids, message.html_text or message.text or "")
        await message.answer(f"✅ Рассылка завершена. Отправлено: <b>{sent}</b>, ошибок: <b>{failed}</b>.")
        await state.clear()

    @router.message(F.text == "🔙 В меню")
    async def admin_exit(message: Message, state: FSMContext):
        if await deny_if_not_admin(message, db):
            return
        await state.clear()
        await message.answer("Выход из админки. Нажми /start, чтобы открыть обычное меню.")

    return router
