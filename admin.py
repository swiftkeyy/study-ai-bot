import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from config import ADMIN_ID
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


ADMIN_MENU_TEXT = (
    "🛠 <b>Админ-панель</b>\n\n"
    "Выбери действие кнопкой ниже."
)


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Найти пользователя"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🎁 Выдать подписку"), KeyboardButton(text="❌ Забрать подписку")],
            [KeyboardButton(text="➕ Выдать лимит"), KeyboardButton(text="👑 VIP")],
            [KeyboardButton(text="🌍 Лимит всем"), KeyboardButton(text="🎯 Лимит пользователю")],
            [KeyboardButton(text="💲 Цены"), KeyboardButton(text="📢 Рассылка всем")],
            [KeyboardButton(text="💎 Рассылка платным"), KeyboardButton(text="🔙 В меню")],
        ],
        resize_keyboard=True,
    )


def is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == ADMIN_ID


async def deny_if_not_admin(message: Message) -> bool:
    if not is_admin(message):
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


def get_admin_router(db: Database) -> Router:
    router = Router(name="admin")

    @router.message(Command("admin"))
    async def admin_start(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
            return
        await state.clear()
        await message.answer(ADMIN_MENU_TEXT, reply_markup=admin_keyboard())

    @router.message(F.text == "🔎 Найти пользователя")
    async def admin_find_user(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_user_search)
        await message.answer("Введи ID пользователя.\nПример: <code>123456789</code>")

    @router.message(AdminStates.waiting_user_search)
    async def admin_find_user_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
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
        if await deny_if_not_admin(message):
            return

        income = db.income_stats()
        text = (
            "📊 <b>Статистика</b>\n\n"
            f"Всего пользователей: <b>{db.user_count()}</b>\n"
            f"Платных пользователей: <b>{db.paid_user_count()}</b>\n"
            f"Запросов сегодня: <b>{db.requests_today_count()}</b>\n"
            f"Доход Stars: <b>{int(income['stars'])}</b> ⭐\n"
            f"Доход ЮKassa: <b>{income['rub']:.2f}</b> ₽"
        )
        await message.answer(text)

    @router.message(F.text == "🎁 Выдать подписку")
    async def admin_grant_sub(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_grant_sub)
        await message.answer(
            "Введи: <code>user_id дни</code>\n"
            "Пример: <code>123456789 30</code>"
        )

    @router.message(AdminStates.waiting_grant_sub)
    async def admin_grant_sub_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
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
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_revoke_sub)
        await message.answer("Введи ID пользователя.\nПример: <code>123456789</code>")

    @router.message(AdminStates.waiting_revoke_sub)
    async def admin_revoke_sub_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
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
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_add_limit)
        await message.answer(
            "Введи: <code>user_id количество</code>\n"
            "Пример: <code>123456789 10</code>"
        )

    @router.message(AdminStates.waiting_add_limit)
    async def admin_add_limit_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
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
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_toggle_vip)
        await message.answer(
            "Введи: <code>user_id on</code> или <code>user_id off</code>\n"
            "Пример: <code>123456789 on</code>"
        )

    @router.message(AdminStates.waiting_toggle_vip)
    async def admin_vip_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
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
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_global_limit)
        await message.answer("Введи новый лимит для всех бесплатных пользователей.\nПример: <code>5</code>")

    @router.message(AdminStates.waiting_global_limit)
    async def admin_global_limit_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
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
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_user_limit)
        await message.answer(
            "Введи: <code>user_id новый_лимит</code>\n"
            "Пример: <code>123456789 25</code>"
        )

    @router.message(AdminStates.waiting_user_limit)
    async def admin_user_limit_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
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
        if await deny_if_not_admin(message):
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
        if await deny_if_not_admin(message):
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

    @router.message(F.text == "📢 Рассылка всем")
    async def admin_broadcast_all(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_broadcast_all)
        await message.answer("Пришли текст рассылки для всех пользователей.")

    @router.message(AdminStates.waiting_broadcast_all)
    async def admin_broadcast_all_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
            return
        user_ids = db.all_user_ids(only_paid=False)
        sent, failed = await broadcast(message.bot, user_ids, message.html_text or message.text or "")
        await message.answer(f"✅ Рассылка завершена. Отправлено: <b>{sent}</b>, ошибок: <b>{failed}</b>.")
        await state.clear()

    @router.message(F.text == "💎 Рассылка платным")
    async def admin_broadcast_paid(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
            return
        await state.set_state(AdminStates.waiting_broadcast_paid)
        await message.answer("Пришли текст рассылки только для платных пользователей.")

    @router.message(AdminStates.waiting_broadcast_paid)
    async def admin_broadcast_paid_input(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
            return
        user_ids = db.all_user_ids(only_paid=True)
        sent, failed = await broadcast(message.bot, user_ids, message.html_text or message.text or "")
        await message.answer(f"✅ Рассылка завершена. Отправлено: <b>{sent}</b>, ошибок: <b>{failed}</b>.")
        await state.clear()

    @router.message(F.text == "🔙 В меню")
    async def admin_exit(message: Message, state: FSMContext):
        if await deny_if_not_admin(message):
            return
        await state.clear()
        await message.answer("Выход из админки. Нажми /start, чтобы открыть обычное меню.")

    return router
