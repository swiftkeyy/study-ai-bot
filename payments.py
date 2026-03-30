import json
import logging
import os
import uuid
from typing import Any

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import Database

logger = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)

# Берём настройки из config.py, если они там есть, но не падаем,
# если проект ещё не полностью синхронизирован.
try:
    from config import CRYPTO_PAY_API_BASE as _CFG_CRYPTO_PAY_API_BASE
except Exception:
    _CFG_CRYPTO_PAY_API_BASE = None

try:
    from config import CRYPTO_PAY_API_TOKEN as _CFG_CRYPTO_PAY_API_TOKEN
except Exception:
    _CFG_CRYPTO_PAY_API_TOKEN = None

try:
    from config import CRYPTO_PAY_RETURN_URL as _CFG_CRYPTO_PAY_RETURN_URL
except Exception:
    _CFG_CRYPTO_PAY_RETURN_URL = None

try:
    from config import CRYPTO_PAY_ACCEPTED_ASSETS as _CFG_CRYPTO_PAY_ACCEPTED_ASSETS
except Exception:
    _CFG_CRYPTO_PAY_ACCEPTED_ASSETS = None


CRYPTO_PAY_API_BASE = (
    _CFG_CRYPTO_PAY_API_BASE
    or os.getenv("CRYPTO_PAY_API_BASE")
    or "https://pay.crypt.bot/api"
)
CRYPTO_PAY_API_TOKEN = _CFG_CRYPTO_PAY_API_TOKEN or os.getenv("CRYPTO_PAY_API_TOKEN", "")
CRYPTO_PAY_RETURN_URL = _CFG_CRYPTO_PAY_RETURN_URL or os.getenv("CRYPTO_PAY_RETURN_URL", "")
CRYPTO_PAY_ACCEPTED_ASSETS = _CFG_CRYPTO_PAY_ACCEPTED_ASSETS or os.getenv(
    "CRYPTO_PAY_ACCEPTED_ASSETS", "USDT,TON"
)


def crypto_pay_enabled() -> bool:
    return bool(CRYPTO_PAY_API_TOKEN)


def _get_prices(db: Database) -> dict[str, int]:
    """
    Нормализуем формат цен.

    В текущем db.py get_prices() возвращает плоский словарь:
    {
        "stars_3": 59,
        "stars_7": 99,
        "stars_30": 199,
        "rub_3": 149,
        ...
    }
    """
    prices = db.get_prices()
    if not isinstance(prices, dict):
        raise RuntimeError("db.get_prices() вернул неожиданный формат")
    return prices


def _stars_price(prices: dict[str, int], days: int) -> int:
    key = f"stars_{days}"
    if key not in prices:
        raise KeyError(f"Не найдена цена {key}")
    return int(prices[key])



def _rub_price(prices: dict[str, int], days: int) -> int:
    key = f"rub_{days}"
    if key not in prices:
        raise KeyError(f"Не найдена цена {key}")
    return int(prices[key])



def get_buy_keyboard(db: Database) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(InlineKeyboardButton(text="⭐ 3 дня", callback_data="buy_stars_3"))
    kb.row(InlineKeyboardButton(text="⭐ 7 дней", callback_data="buy_stars_7"))
    kb.row(InlineKeyboardButton(text="⭐ 30 дней", callback_data="buy_stars_30"))

    if crypto_pay_enabled():
        kb.row(InlineKeyboardButton(text="💎 3 дня (CryptoBot)", callback_data="buy_crypto_3"))
        kb.row(InlineKeyboardButton(text="💎 7 дней (CryptoBot)", callback_data="buy_crypto_7"))
        kb.row(InlineKeyboardButton(text="💎 30 дней (CryptoBot)", callback_data="buy_crypto_30"))

    return kb.as_markup()



def format_prices_text(db: Database) -> str:
    prices = _get_prices(db)

    text = (
        "💳 <b>Покупка доступа</b>\n\n"
        "Выбери удобный способ оплаты:\n\n"
        "⭐ <b>Telegram Stars</b>\n"
        f"• 3 дня — <b>{_stars_price(prices, 3)} Stars</b>\n"
        f"• 7 дней — <b>{_stars_price(prices, 7)} Stars</b>\n"
        f"• 30 дней — <b>{_stars_price(prices, 30)} Stars</b>\n"
    )

    if crypto_pay_enabled():
        text += (
            "\n💎 <b>CryptoBot</b>\n"
            f"• 3 дня — <b>{_rub_price(prices, 3)} ₽</b>\n"
            f"• 7 дней — <b>{_rub_price(prices, 7)} ₽</b>\n"
            f"• 30 дней — <b>{_rub_price(prices, 30)} ₽</b>\n"
            "Оплата откроется во внешнем счёте CryptoBot.\n"
        )

    text += "\nПосле оплаты подписка активируется автоматически."
    return text


async def send_stars_invoice(bot: Bot, chat_id: int, user_id: int, days: int, db: Database) -> None:
    prices = _get_prices(db)
    amount_stars = _stars_price(prices, days)
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
    kb.row(InlineKeyboardButton(text="💎 Оплатить в CryptoBot", url=invoice_url))
    kb.row(InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_crypto:{invoice_id}"))
    return kb.as_markup()



def _save_crypto_payment(db: Database, user_id: int, amount_rub: int, invoice_id: str, status: str, days: int) -> None:
    # Совместимость и с create_payment, и с upsert_payment, если вы его уже добавили.
    if hasattr(db, "upsert_payment"):
        db.upsert_payment(
            user_id=user_id,
            amount=float(amount_rub),
            payment_type="cryptobot",
            status=status,
            external_id=invoice_id,
            days=days,
        )
        return

    existing = None
    if hasattr(db, "get_payment_by_external_id"):
        try:
            existing = db.get_payment_by_external_id(invoice_id)
        except Exception:
            existing = None

    if existing:
        if hasattr(db, "update_payment_status"):
            db.update_payment_status(invoice_id, status)
        return

    db.create_payment(
        user_id=user_id,
        amount=float(amount_rub),
        payment_type="cryptobot",
        status=status,
        external_id=invoice_id,
        days=days,
    )



def _crypto_headers() -> dict[str, str]:
    return {
        "Crypto-Pay-API-Token": CRYPTO_PAY_API_TOKEN,
        "Content-Type": "application/json",
    }


async def create_cryptobot_invoice(user_id: int, days: int, db: Database) -> tuple[str, str]:
    if not CRYPTO_PAY_API_TOKEN:
        raise RuntimeError("CryptoBot не настроен: проверь CRYPTO_PAY_API_TOKEN")

    prices = _get_prices(db)
    amount_rub = _rub_price(prices, days)
    payload = f"crypto:{days}:{user_id}:{uuid.uuid4().hex[:10]}"

    request_payload: dict[str, Any] = {
        "currency_type": "fiat",
        "fiat": "RUB",
        "amount": str(amount_rub),
        "description": f"Подписка AI-бота на {days} дней",
        "hidden_message": f"Подписка на {days} дней будет активирована автоматически.",
        "payload": payload,
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 3600,
    }

    if CRYPTO_PAY_RETURN_URL:
        request_payload["paid_btn_name"] = "openBot"
        request_payload["paid_btn_url"] = CRYPTO_PAY_RETURN_URL

    if CRYPTO_PAY_ACCEPTED_ASSETS:
        request_payload["accepted_assets"] = CRYPTO_PAY_ACCEPTED_ASSETS

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(
            f"{CRYPTO_PAY_API_BASE.rstrip('/')}/createInvoice",
            headers=_crypto_headers(),
            json=request_payload,
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"CryptoBot createInvoice error {response.status}: {text[:500]}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CryptoBot вернул невалидный JSON: {text[:500]}") from exc

    if not data.get("ok"):
        raise RuntimeError(f"CryptoBot createInvoice failed: {data}")

    invoice = data["result"]
    invoice_id = str(invoice["invoice_id"])
    invoice_url = invoice["bot_invoice_url"]

    _save_crypto_payment(
        db=db,
        user_id=user_id,
        amount_rub=amount_rub,
        invoice_id=invoice_id,
        status=str(invoice.get("status", "active")),
        days=days,
    )

    return invoice_id, invoice_url


async def get_cryptobot_invoice(invoice_id: str) -> dict[str, Any] | None:
    if not CRYPTO_PAY_API_TOKEN:
        raise RuntimeError("CryptoBot не настроен: проверь CRYPTO_PAY_API_TOKEN")

    params = {"invoice_ids": invoice_id}

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(
            f"{CRYPTO_PAY_API_BASE.rstrip('/')}/getInvoices",
            headers=_crypto_headers(),
            params=params,
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"CryptoBot getInvoices error {response.status}: {text[:500]}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CryptoBot вернул невалидный JSON: {text[:500]}") from exc

    if not data.get("ok"):
        raise RuntimeError(f"CryptoBot getInvoices failed: {data}")

    items = data.get("result", {}).get("items", [])
    if not items:
        return None
    return items[0]
