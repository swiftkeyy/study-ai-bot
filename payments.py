import hashlib
import json
import logging
import os
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import quote, urlencode

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
ROBOKASSA_PAYMENT_URL = os.getenv(
    "ROBOKASSA_PAYMENT_URL",
    "https://auth.robokassa.ru/Merchant/Index.aspx",
).strip()

# Fiscalization / Receipt
ROBOKASSA_RECEIPT_ENABLED = os.getenv("ROBOKASSA_RECEIPT_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
ROBOKASSA_RECEIPT_TAX = os.getenv("ROBOKASSA_RECEIPT_TAX", "none").strip() or "none"
ROBOKASSA_RECEIPT_PAYMENT_METHOD = os.getenv("ROBOKASSA_RECEIPT_PAYMENT_METHOD", "full_payment").strip() or "full_payment"
ROBOKASSA_RECEIPT_PAYMENT_OBJECT = os.getenv("ROBOKASSA_RECEIPT_PAYMENT_OBJECT", "service").strip() or "service"
ROBOKASSA_RECEIPT_SNO = os.getenv("ROBOKASSA_RECEIPT_SNO", "").strip()
ROBOKASSA_DEBUG_SIGNATURE = os.getenv("ROBOKASSA_DEBUG_SIGNATURE", "0").strip().lower() in {"1", "true", "yes"}


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


def _urlencode_for_signature(value: str) -> str:
    return quote(value, safe="")


def _mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}***{value[-keep:]}"


def _build_receipt(days: int, amount_rub: int | float | str | Decimal) -> str:
    amount = float(Decimal(str(amount_rub)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    item_name = f"Доступ к Study AI Bot на {days} дней"
    if len(item_name) > 128:
        item_name = item_name[:128]

    item = {
        "name": item_name,
        "quantity": 1,
        "sum": amount,
        "payment_method": ROBOKASSA_RECEIPT_PAYMENT_METHOD,
        "payment_object": ROBOKASSA_RECEIPT_PAYMENT_OBJECT,
        "tax": ROBOKASSA_RECEIPT_TAX,
    }

    receipt: dict[str, Any] = {"items": [item]}
    if ROBOKASSA_RECEIPT_SNO:
        receipt["sno"] = ROBOKASSA_RECEIPT_SNO

    return json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))


def _build_payment_signature(
    out_sum: str,
    inv_id: str,
    shp_params: dict[str, Any],
    receipt: str | None = None,
) -> str:
    parts = [ROBOKASSA_MERCHANT_LOGIN, out_sum, inv_id]
    if receipt:
        parts.append(_urlencode_for_signature(receipt))
    parts.append(ROBOKASSA_PASSWORD1)
    for key, value in _sorted_shp_items(shp_params):
        parts.append(f"{key}={value}")

    if ROBOKASSA_DEBUG_SIGNATURE:
        debug_parts = [ROBOKASSA_MERCHANT_LOGIN, out_sum, inv_id]
        if receipt:
            debug_parts.append(_urlencode_for_signature(receipt))
        debug_parts.append(_mask_secret(ROBOKASSA_PASSWORD1))
        for key, value in _sorted_shp_items(shp_params):
            debug_parts.append(f"{key}={value}")
        logger.info("Robokassa signature base: %s", ":".join(debug_parts))

    return _hash_signature(":".join(parts))


def verify_result_signature(out_sum: str, inv_id: str, signature_value: str, shp_params: dict[str, Any]) -> bool:
    parts = [out_sum, inv_id, ROBOKASSA_PASSWORD2]
    for key, value in _sorted_shp_items(shp_params):
        parts.append(f"{key}={value}")
    expected = _hash_signature(":".join(parts))
    return expected.lower() == (signature_value or "").strip().lower()


def verify_success_signature(out_sum: str, inv_id: str, signature_value: str, shp_params: dict[str, Any]) -> bool:
    parts = [out_sum, inv_id, ROBOKASSA_PASSWORD1]
    for key, value in _sorted_shp_items(shp_params):
        parts.append(f"{key}={value}")
    expected = _hash_signature(":".join(parts))
    return expected.lower() == (signature_value or "").strip().lower()


def _get_prices(db: Database) -> dict[str, Any]:
    prices = db.get_prices()
    if not isinstance(prices, dict):
        raise RuntimeError("db.get_prices() вернул неожиданный формат")
    return prices


def _get_price(prices: dict[str, Any], days: int, currency: str) -> int:
    if days in prices and isinstance(prices[days], dict):
        value = prices[days].get(currency)
        if value is None:
            raise KeyError(f"Не найдена цена {currency} для {days} дней")
        return int(value)

    key = f"{currency}_{days}"
    if key in prices:
        return int(prices[key])

    raise KeyError(f"Не найдена цена {key}")


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
    prices = _get_prices(db)
    text = (
        "💎 <b>Покупка доступа</b>\n\n"
        "Выбери удобный способ оплаты:\n\n"
        f"⭐ <b>Telegram Stars</b>\n"
        f"• 3 дня — <b>{_get_price(prices, 3, 'stars')} Stars</b>\n"
        f"• 7 дней — <b>{_get_price(prices, 7, 'stars')} Stars</b>\n"
        f"• 30 дней — <b>{_get_price(prices, 30, 'stars')} Stars</b>\n"
    )

    if robokassa_enabled():
        text += (
            "\n💳 <b>Robokassa</b>\n"
            f"• 3 дня — <b>{_get_price(prices, 3, 'rub')} ₽</b>\n"
            f"• 7 дней — <b>{_get_price(prices, 7, 'rub')} ₽</b>\n"
            f"• 30 дней — <b>{_get_price(prices, 30, 'rub')} ₽</b>\n"
            "Оплата откроется на защищённой странице Robokassa.\n"
        )

    text += "\nПосле оплаты подписка активируется автоматически."
    return text


async def send_stars_invoice(bot: Bot, chat_id: int, user_id: int, days: int, db: Database) -> None:
    prices = _get_prices(db)
    amount_stars = _get_price(prices, days, "stars")
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

    prices = _get_prices(db)
    amount_rub = _get_price(prices, days, "rub")
    out_sum = _normalize_amount(amount_rub)
    inv_id = str(uuid.uuid4().int)[:12]

    receipt = _build_receipt(days=days, amount_rub=amount_rub) if ROBOKASSA_RECEIPT_ENABLED else None

    shp_params = {
        "Shp_user_id": str(user_id),
        "Shp_days": str(days),
    }
    signature = _build_payment_signature(
        out_sum=out_sum,
        inv_id=inv_id,
        shp_params=shp_params,
        receipt=receipt,
    )

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
    if receipt:
        query["Receipt"] = receipt
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
    logger.info(
        "Robokassa payment created inv_id=%s user_id=%s days=%s test=%s receipt_enabled=%s",
        inv_id,
        user_id,
        days,
        ROBOKASSA_IS_TEST,
        bool(receipt),
    )
    return inv_id, payment_url
