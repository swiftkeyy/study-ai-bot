import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

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


ADMIN_MENU_TEXT = (
    "🛠 <b>Админ-панель</b>\n\n"
    "Этап 2 подключён. Теперь здесь есть управление банами, техработами, админами и обязательной подпиской.\n\n"
    "Выбери действие кнопкой ниже."
)


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Найти пользователя"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🎁 Выдать подписку"), KeyboardButton(text="❌ Забрать подписку")],
            [KeyboardButton(text="➕ Выдать лимит"), KeyboardButton(text="👑 VIP")],
            [KeyboardButton(text="🌍 Лимит всем"), KeyboardButton(text="🎯 Лимит пользователю")],
            [KeyboardButton(text="💲 Цены"), KeyboardButton(text="🚫 Бан / разбан")],
            [KeyboardButton(text="🛠 Тех.работы"), KeyboardButton(text="🤠 Админы")],
            [KeyboardButton(text="📡 Обязательная подписка"), KeyboardButton(text="📢 Рассылка всем")],
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
        parts.append(
            f"• <code>{item['user_id']}</code> | {username} | роль: <b>{item['role']}</b>"
        )
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
        await message.answer(
            "Введи: <code>user_id дни</code>\n"
            "Пример: <code>123456789 30</code>"
        )

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
        await message.answer(
            "Введи: <code>user_id количество</code>\n"
            "Пример: <code>123456789 10</code>"
        )

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
        await message.answer(
            "Введи: <code>user_id on</code> или <code>user_id off</code>\n"
            "Пример: <code>123456789 on</code>"
        )

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
        await message.answer(
            "Введи: <code>user_id новый_лимит</code>\n"
            "Пример: <code>123456789 25</code>"
        )

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

        await message.answer(
            f"✅ Цены для тарифа <b>{days} дней</b> обновлены:\n"
            f"⭐ {stars_price}\n"
            f"💳 {rub_price} ₽"
        )
        await state.clear()

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
            await message.answer(_render_required_subscription_text(db))
            return

        if lower == "off":
            current = db.get_required_channel()
            db.set_required_channel(current.get("channel_id"), current.get("channel_username"), enabled=False)
            await message.answer("✅ Обязательная подписка выключена.")
            await state.clear()
            return

        if lower.startswith("text "):
            new_text = text[5:].strip()
            if not new_text:
                await message.answer("После <code>text</code> нужен новый текст.")
                return
            db.set_required_subscription_text(new_text)
            await message.answer("✅ Текст экрана обязательной подписки обновлён.")
            return

        if lower.startswith("on "):
            payload = text[3:].strip().split()
            if not payload:
                await message.answer("Используй: <code>on @channelusername</code> или <code>on -100... @channelusername</code>")
                return
            channel_id = None
            channel_username = None
            for token in payload:
                cleaned = token.strip()
                if cleaned.startswith("https://t.me/") or cleaned.startswith("http://t.me/"):
                    channel_username = cleaned.rsplit("/", 1)[-1]
                elif cleaned.startswith("@"):
                    channel_username = cleaned
                elif cleaned.startswith("-100") or cleaned.lstrip("-").isdigit():
                    channel_id = cleaned
                else:
                    channel_username = cleaned
            db.set_required_channel(channel_id, channel_username, enabled=True)
            await message.answer(
                "✅ Обязательная подписка включена.\n\n"
                f"ID канала: <code>{channel_id or '—'}</code>\n"
                f"Username: <code>{channel_username or '—'}</code>"
            )
            await state.clear()
            return

        await message.answer("Используй: <code>on ...</code>, <code>off</code>, <code>status</code> или <code>text ...</code>")

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
