import json
import logging
import uuid

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    CRYPTO_PAY_API_BASE,
    CRYPTO_PAY_API_TOKEN,
    CRYPTO_PAY_RETURN_URL,
    crypto_pay_enabled,
)
from db import Database

logger = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)


def get_buy_keyboard(db: Database) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(InlineKeyboardButton(text="⭐ 3 дня", callback_data="buy_stars_3"))
    kb.row(InlineKeyboardButton(text="⭐ 7 дней", callback_data="buy_stars_7"))
    kb.row(InlineKeyboardButton(text="⭐ 30 дней", callback_data="buy_stars_30"))

    if crypto_pay_enabled():
        kb.row(InlineKeyboardButton(text="🪙 3 дня (CryptoBot)", callback_data="buy_crypto_3"))
        kb.row(InlineKeyboardButton(text="🪙 7 дней (CryptoBot)", callback_data="buy_crypto_7"))
        kb.row(InlineKeyboardButton(text="🪙 30 дней (CryptoBot)", callback_data="buy_crypto_30"))

    kb.row(InlineKeyboardButton(text="🔄 Обновить цены", callback_data="refresh_prices"))
    return kb.as_markup()


def format_prices_text(db: Database) -> str:
    prices = db.get_prices()

    return (
        "💳 <b>Покупка доступа</b>\n\n"
        "Выбери удобный способ оплаты:\n\n"
        f"⭐ <b>Telegram Stars</b>\n"
        f"• 3 дня — <b>{prices['stars_3']} Stars</b>\n"
        f"• 7 дней — <b>{prices['stars_7']} Stars</b>\n"
        f"• 30 дней — <b>{prices['stars_30']} Stars</b>\n\n"
        f"💎 <b>CryptoBot</b>\n"
        f"• 3 дня — <b>{prices['rub_3']} ₽</b>\n"
        f"• 7 дней — <b>{prices['rub_7']} ₽</b>\n"
        f"• 30 дней — <b>{prices['rub_30']} ₽</b>\n\n"
        "После оплаты подписка активируется автоматически."
    )

    if crypto_pay_enabled():
        text += (
            "\n🪙 <b>CryptoBot</b>\n"
            f"• 3 дня — <b>{prices[3]['rub']} ₽</b>\n"
            f"• 7 дней — <b>{prices[7]['rub']} ₽</b>\n"
            f"• 30 дней — <b>{prices[30]['rub']} ₽</b>\n"
            "Оплата откроется во внешнем счёте CryptoBot.\n"
        )

    text += "\nПосле оплаты подписка активируется автоматически."
    return text


async def send_stars_invoice(bot: Bot, chat_id: int, user_id: int, days: int, db: Database) -> None:
    prices = db.get_prices()
    amount_stars = int(prices[f"stars_{days}"])
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


def build_cryptobot_invoice_keyboard(invoice_url: str, invoice_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🪙 Оплатить в CryptoBot", url=invoice_url))
    kb.row(InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_crypto:{invoice_id}"))
    return kb.as_markup()


async def create_cryptobot_invoice(user_id: int, days: int, db: Database) -> tuple[str, str]:
    if not CRYPTO_PAY_API_TOKEN:
        raise RuntimeError("CryptoBot не настроен: проверь CRYPTO_PAY_API_TOKEN")

    prices = db.get_prices()
    amount_rub = prices[days]["rub"]
    payload = f"crypto:{days}:{user_id}:{uuid.uuid4().hex[:10]}"

    request_payload = {
        "currency_type": "fiat",
        "fiat": "RUB",
        "amount": str(amount_rub),
        "description": f"Подписка AI-бота на {days} дней",
        "hidden_message": f"Подписка на {days} дней будет активирована автоматически.",
        "payload": payload,
        "paid_btn_name": "openBot",
        "paid_btn_url": CRYPTO_PAY_RETURN_URL,
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 3600,
    }

    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_API_TOKEN,
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(
            f"{CRYPTO_PAY_API_BASE.rstrip('/')}/createInvoice",
            headers=headers,
            json=request_payload,
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"CryptoBot create invoice error {response.status}: {text[:500]}")
            data = json.loads(text)

    if not data.get("ok"):
        raise RuntimeError(f"CryptoBot create invoice failed: {data}")

    invoice = data["result"]
    invoice_id = str(invoice["invoice_id"])
    invoice_url = invoice["bot_invoice_url"]
    db.upsert_payment(
        user_id=user_id,
        amount=float(amount_rub),
        payment_type="cryptobot",
        status=invoice.get("status", "active"),
        external_id=invoice_id,
        days=days,
    )
    return invoice_id, invoice_url
