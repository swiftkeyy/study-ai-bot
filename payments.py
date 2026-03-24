import json
import logging
import uuid
from decimal import Decimal

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import YOOKASSA_RETURN_URL, YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID
from db import Database

logger = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)


def get_buy_keyboard(db: Database) -> InlineKeyboardMarkup:
    prices = db.get_prices()
    kb = InlineKeyboardBuilder()

    kb.row(InlineKeyboardButton(text="⭐ 3 дня", callback_data="buy_stars_3"))
    kb.row(InlineKeyboardButton(text="⭐ 7 дней", callback_data="buy_stars_7"))
    kb.row(InlineKeyboardButton(text="⭐ 30 дней", callback_data="buy_stars_30"))

    kb.row(InlineKeyboardButton(text="💳 3 дня (ЮKassa)", callback_data="buy_yk_3"))
    kb.row(InlineKeyboardButton(text="💳 7 дней (ЮKassa)", callback_data="buy_yk_7"))
    kb.row(InlineKeyboardButton(text="💳 30 дней (ЮKassa)", callback_data="buy_yk_30"))

    kb.row(InlineKeyboardButton(text="🔄 Обновить цены", callback_data="refresh_prices"))

    return kb.as_markup()


def format_prices_text(db: Database) -> str:
    prices = db.get_prices()
    return (
        "💎 <b>Покупка доступа</b>\n\n"
        "Выбери удобный способ оплаты:\n\n"
        f"⭐ <b>Telegram Stars</b>\n"
        f"• 3 дня — <b>{prices[3]['stars']} Stars</b>\n"
        f"• 7 дней — <b>{prices[7]['stars']} Stars</b>\n"
        f"• 30 дней — <b>{prices[30]['stars']} Stars</b>\n\n"
        f"💳 <b>ЮKassa</b>\n"
        f"• 3 дня — <b>{prices[3]['rub']} ₽</b>\n"
        f"• 7 дней — <b>{prices[7]['rub']} ₽</b>\n"
        f"• 30 дней — <b>{prices[30]['rub']} ₽</b>\n\n"
        "После оплаты подписка активируется автоматически."
    )


async def send_stars_invoice(bot: Bot, chat_id: int, user_id: int, days: int, db: Database) -> None:
    prices = db.get_prices()
    amount_stars = prices[days]["stars"]
    payload = f"stars:{days}:{user_id}:{uuid.uuid4().hex[:10]}"

    await bot.send_invoice(
        chat_id=chat_id,
        title=f"Подписка на {days} дн.",
        description=f"Доступ к AI-помощнику на {days} дней.",
        payload=payload,
        currency="XTR",
        provider_token="",
        prices=[LabeledPrice(label=f"Подписка {days} дн.", amount=amount_stars)],
    )


async def create_yookassa_payment(user_id: int, days: int, db: Database) -> tuple[str, str]:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise RuntimeError("ЮKassa не настроена: проверь YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY")

    prices = db.get_prices()
    amount_rub = prices[days]["rub"]
    idempotence_key = str(uuid.uuid4())

    payload = {
        "amount": {
            "value": f"{Decimal(amount_rub):.2f}",
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL,
        },
        "description": f"Подписка AI-бота на {days} дней для user_id={user_id}",
        "metadata": {
            "user_id": str(user_id),
            "days": str(days),
            "source": "telegram_bot",
        },
    }

    headers = {
        "Idempotence-Key": idempotence_key,
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(timeout=TIMEOUT, auth=aiohttp.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)) as session:
        async with session.post("https://api.yookassa.ru/v3/payments", headers=headers, json=payload) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"ЮKassa create payment error {response.status}: {text[:500]}")
            data = json.loads(text)

    payment_id = data["id"]
    confirmation_url = data["confirmation"]["confirmation_url"]
    db.create_payment(
        user_id=user_id,
        amount=float(amount_rub),
        payment_type="yookassa",
        status=data.get("status", "pending"),
        external_id=payment_id,
        days=days,
    )
    return payment_id, confirmation_url


async def get_yookassa_payment(payment_id: str) -> dict:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise RuntimeError("ЮKassa не настроена")

    async with aiohttp.ClientSession(timeout=TIMEOUT, auth=aiohttp.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)) as session:
        async with session.get(f"https://api.yookassa.ru/v3/payments/{payment_id}") as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"ЮKassa get payment error {response.status}: {text[:500]}")
            return json.loads(text)
