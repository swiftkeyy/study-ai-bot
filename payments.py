import hashlib
import logging
import os
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import Database

logger = logging.getLogger(__name__)

ROBOKASSA_MERCHANT_LOGIN = os.getenv("ROBOKASSA_MERCHANT_LOGIN", "").strip()
ROBOKASSA_PASSWORD1 = os.getenv("ROBOKASSA_PASSWORD1", "").strip()
ROBOKASSA_PASSWORD2 = os.getenv("ROBOKASSA_PASSWORD2", "").strip()
ROBOKASSA_HASH_ALGO = os.getenv("ROBOKASSA_HASH_ALGO", "md5").strip().lower()
ROBOKASSA_IS_TEST = os.getenv("ROBOKASSA_IS_TEST", "0").strip().lower() in {"1", "true", "yes"}
ROBOKASSA_PAYMENT_URL = os.getenv("ROBOKASSA_PAYMENT_URL", "https://auth.robokassa.ru/Merchant/Index.aspx").strip()


def robokassa_enabled() -> bool:
    return bool(ROBOKASSA_MERCHANT_LOGIN and ROBOKASSA_PASSWORD1 and ROBOKASSA_PASSWORD2)


def _hash_signature(value: str) -> str:
    try:
        digest = hashlib.new(ROBOKASSA_HASH_ALGO)
    except ValueError as exc:
        raise RuntimeError(f"Неподдерживаемый ROBOKASSA_HASH_ALGO: {ROBOKASSA_HASH_ALGO}") from exc
    digest.update(value.encode("utf-8"))
    return digest.hexdigest()


def _normalize_amount(value: int | float | str | Decimal) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(amount, "f")


def _sorted_shp_items(params: dict[str, Any]) -> list[tuple[str, str]]:
    items = [(k, str(v)) for k, v in params.items() if k.startswith("Shp_")]
    items.sort(key=lambda item: item[0].lower())
    return items


def _build_payment_signature(out_sum: str, inv_id: str, shp_params: dict[str, Any]) -> str:
    parts = [ROBOKASSA_MERCHANT_LOGIN, out_sum, inv_id, ROBOKASSA_PASSWORD1]
    for key, value in _sorted_shp_items(shp_params):
        parts.append(f"{key}={value}")
    return _hash_signature(":".join(parts))


def verify_result_signature(out_sum: str, inv_id: str, signature_value: str, shp_params: dict[str, Any]) -> bool:
    parts = [out_sum, inv_id, ROBOKASSA_PASSWORD2]
    for key, value in _sorted_shp_items(shp_params):
        parts.append(f"{key}={value}")
    expected = _hash_signature(":".join(parts))
    return expected.lower() == (signature_value or "").strip().lower()


def get_buy_keyboard(db: Database) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(InlineKeyboardButton(text="⭐ 3 дня", callback_data="buy_stars_3"))
    kb.row(InlineKeyboardButton(text="⭐ 7 дней", callback_data="buy_stars_7"))
    kb.row(InlineKeyboardButton(text="⭐ 30 дней", callback_data="buy_stars_30"))

    if robokassa_enabled():
        kb.row(InlineKeyboardButton(text="💳 3 дня (Robokassa)", callback_data="buy_robo_3"))
        kb.row(InlineKeyboardButton(text="💳 7 дней (Robokassa)", callback_data="buy_robo_7"))
        kb.row(InlineKeyboardButton(text="💳 30 дней (Robokassa)", callback_data="buy_robo_30"))

    kb.row(InlineKeyboardButton(text="🔄 Обновить цены", callback_data="refresh_prices"))
    return kb.as_markup()


def format_prices_text(db: Database) -> str:
    prices = db.get_prices()
    text = (
        "💎 <b>Покупка доступа</b>\n\n"
        "Выбери удобный способ оплаты:\n\n"
        f"⭐ <b>Telegram Stars</b>\n"
        f"• 3 дня — <b>{prices[3]['stars']} Stars</b>\n"
        f"• 7 дней — <b>{prices[7]['stars']} Stars</b>\n"
        f"• 30 дней — <b>{prices[30]['stars']} Stars</b>\n"
    )

    if robokassa_enabled():
        text += (
            "\n💳 <b>Robokassa</b>\n"
            f"• 3 дня — <b>{prices[3]['rub']} ₽</b>\n"
            f"• 7 дней — <b>{prices[7]['rub']} ₽</b>\n"
            f"• 30 дней — <b>{prices[30]['rub']} ₽</b>\n"
            "Оплата откроется на защищённой странице Robokassa.\n"
        )

    text += "\nПосле оплаты подписка активируется автоматически."
    return text


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


def build_robokassa_payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить через Robokassa", url=payment_url))
    return kb.as_markup()


async def create_robokassa_payment(user_id: int, days: int, db: Database) -> tuple[str, str]:
    if not robokassa_enabled():
        raise RuntimeError("Robokassa не настроена: проверь ROBOKASSA_MERCHANT_LOGIN / PASSWORD1 / PASSWORD2")

    prices = db.get_prices()
    amount_rub = prices[days]["rub"]
    out_sum = _normalize_amount(amount_rub)
    inv_id = str(uuid.uuid4().int)[:12]

    shp_params = {
        "Shp_user_id": str(user_id),
        "Shp_days": str(days),
    }
    signature = _build_payment_signature(out_sum, inv_id, shp_params)

    query = {
        "MerchantLogin": ROBOKASSA_MERCHANT_LOGIN,
        "OutSum": out_sum,
        "InvId": inv_id,
        "Description": f"Подписка Study AI Bot на {days} дней",
        "Culture": "ru",
        "Encoding": "utf-8",
        "SignatureValue": signature,
        **shp_params,
    }
    if ROBOKASSA_IS_TEST:
        query["IsTest"] = "1"

    payment_url = f"{ROBOKASSA_PAYMENT_URL}?{urlencode(query)}"

    db.upsert_payment(
        user_id=user_id,
        amount=float(amount_rub),
        payment_type="robokassa",
        status="pending",
        external_id=inv_id,
        days=days,
    )
    logger.info("Robokassa payment created inv_id=%s user_id=%s days=%s", inv_id, user_id, days)
    return inv_id, payment_url
