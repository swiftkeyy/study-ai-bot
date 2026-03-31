import hashlib
import logging
import os
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import Database

logger = logging.getLogger(__name__)

try:
    from config import ROBOKASSA_MERCHANT_LOGIN as _CFG_ROBOKASSA_MERCHANT_LOGIN
except Exception:
    _CFG_ROBOKASSA_MERCHANT_LOGIN = None

try:
    from config import ROBOKASSA_PASSWORD1 as _CFG_ROBOKASSA_PASSWORD1
except Exception:
    _CFG_ROBOKASSA_PASSWORD1 = None

try:
    from config import ROBOKASSA_PASSWORD2 as _CFG_ROBOKASSA_PASSWORD2
except Exception:
    _CFG_ROBOKASSA_PASSWORD2 = None

try:
    from config import ROBOKASSA_HASH_ALGO as _CFG_ROBOKASSA_HASH_ALGO
except Exception:
    _CFG_ROBOKASSA_HASH_ALGO = None

try:
    from config import ROBOKASSA_IS_TEST as _CFG_ROBOKASSA_IS_TEST
except Exception:
    _CFG_ROBOKASSA_IS_TEST = None

try:
    from config import ROBOKASSA_PAYMENT_URL as _CFG_ROBOKASSA_PAYMENT_URL
except Exception:
    _CFG_ROBOKASSA_PAYMENT_URL = None

ROBOKASSA_MERCHANT_LOGIN = _CFG_ROBOKASSA_MERCHANT_LOGIN or os.getenv("ROBOKASSA_MERCHANT_LOGIN", "")
ROBOKASSA_PASSWORD1 = _CFG_ROBOKASSA_PASSWORD1 or os.getenv("ROBOKASSA_PASSWORD1", "")
ROBOKASSA_PASSWORD2 = _CFG_ROBOKASSA_PASSWORD2 or os.getenv("ROBOKASSA_PASSWORD2", "")
ROBOKASSA_HASH_ALGO = (_CFG_ROBOKASSA_HASH_ALGO or os.getenv("ROBOKASSA_HASH_ALGO", "md5")).lower()
ROBOKASSA_IS_TEST = str(_CFG_ROBOKASSA_IS_TEST or os.getenv("ROBOKASSA_IS_TEST", "0")).strip() in {"1", "true", "True"}
ROBOKASSA_PAYMENT_URL = _CFG_ROBOKASSA_PAYMENT_URL or os.getenv(
    "ROBOKASSA_PAYMENT_URL",
    "https://auth.robokassa.ru/Merchant/Index.aspx",
)


def robokassa_enabled() -> bool:
    return bool(ROBOKASSA_MERCHANT_LOGIN and ROBOKASSA_PASSWORD1 and ROBOKASSA_PASSWORD2)


def _hash_signature(base: str) -> str:
    try:
        digest = hashlib.new(ROBOKASSA_HASH_ALGO)
    except ValueError as exc:
        raise RuntimeError(f"Неподдерживаемый ROBOKASSA_HASH_ALGO: {ROBOKASSA_HASH_ALGO}") from exc
    digest.update(base.encode("utf-8"))
    return digest.hexdigest()


def _normalize_amount(value: int | float | str | Decimal) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(amount, "f")


def _get_prices(db: Database) -> dict[str, int]:
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


def _sorted_shp_items(params: dict[str, Any]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for key, value in params.items():
        if key.startswith("Shp_"):
            items.append((key, str(value)))
    items.sort(key=lambda item: item[0].lower())
    return items


def _build_signature_for_payment(out_sum: str, inv_id: str, shp_params: dict[str, Any]) -> str:
    base_parts = [ROBOKASSA_MERCHANT_LOGIN, out_sum, inv_id, ROBOKASSA_PASSWORD1]
    for key, value in _sorted_shp_items(shp_params):
        base_parts.append(f"{key}={value}")
    return _hash_signature(":".join(base_parts))


def verify_result_signature(out_sum: str, inv_id: str, signature_value: str, shp_params: dict[str, Any]) -> bool:
    base_parts = [out_sum, inv_id, ROBOKASSA_PASSWORD2]
    for key, value in _sorted_shp_items(shp_params):
        base_parts.append(f"{key}={value}")
    expected = _hash_signature(":".join(base_parts))
    return expected.lower() == (signature_value or "").strip().lower()


def verify_success_signature(out_sum: str, inv_id: str, signature_value: str, shp_params: dict[str, Any]) -> bool:
    base_parts = [out_sum, inv_id, ROBOKASSA_PASSWORD1]
    for key, value in _sorted_shp_items(shp_params):
        base_parts.append(f"{key}={value}")
    expected = _hash_signature(":".join(base_parts))
    return expected.lower() == (signature_value or "").strip().lower()


def _generate_inv_id(user_id: int) -> str:
    # Robokassa рекомендует передавать InvId для контроля оплаты.
    suffix = user_id % 100000
    return f"{int(time.time() * 1000)}{suffix:05d}"


def get_buy_keyboard(db: Database) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(InlineKeyboardButton(text="⭐ 3 дня", callback_data="buy_stars_3"))
    kb.row(InlineKeyboardButton(text="⭐ 7 дней", callback_data="buy_stars_7"))
    kb.row(InlineKeyboardButton(text="⭐ 30 дней", callback_data="buy_stars_30"))

    if robokassa_enabled():
        kb.row(InlineKeyboardButton(text="💳 3 дня (Robokassa)", callback_data="buy_robo_3"))
        kb.row(InlineKeyboardButton(text="💳 7 дней (Robokassa)", callback_data="buy_robo_7"))
        kb.row(InlineKeyboardButton(text="💳 30 дней (Robokassa)", callback_data="buy_robo_30"))

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

    if robokassa_enabled():
        text += (
            "\n💳 <b>Robokassa</b>\n"
            f"• 3 дня — <b>{_rub_price(prices, 3)} ₽</b>\n"
            f"• 7 дней — <b>{_rub_price(prices, 7)} ₽</b>\n"
            f"• 30 дней — <b>{_rub_price(prices, 30)} ₽</b>\n"
            "Оплата откроется на защищённой платёжной странице Robokassa.\n"
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


def build_robokassa_payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить через Robokassa", url=payment_url))
    return kb.as_markup()


async def create_robokassa_payment(user_id: int, days: int, db: Database) -> tuple[str, str]:
    if not robokassa_enabled():
        raise RuntimeError("Robokassa не настроена: проверь MerchantLogin и пароли")

    prices = _get_prices(db)
    amount_rub = _rub_price(prices, days)
    out_sum = _normalize_amount(amount_rub)
    inv_id = _generate_inv_id(user_id)

    shp_params = {
        "Shp_days": str(days),
        "Shp_user_id": str(user_id),
    }

    signature_value = _build_signature_for_payment(out_sum, inv_id, shp_params)

    query: dict[str, str] = {
        "MerchantLogin": ROBOKASSA_MERCHANT_LOGIN,
        "OutSum": out_sum,
        "InvId": inv_id,
        "Description": f"Подписка Study AI Bot на {days} дней",
        "Culture": "ru",
        "SignatureValue": signature_value,
        **shp_params,
    }
    if ROBOKASSA_IS_TEST:
        query["IsTest"] = "1"

    payment_url = f"{ROBOKASSA_PAYMENT_URL}?{urlencode(query)}"

    if hasattr(db, "upsert_payment"):
        db.upsert_payment(
            user_id=user_id,
            amount=float(amount_rub),
            payment_type="robokassa",
            status="pending",
            external_id=inv_id,
            days=days,
        )
    else:
        existing = None
        if hasattr(db, "get_payment_by_external_id"):
            existing = db.get_payment_by_external_id(inv_id, payment_type="robokassa")
        if existing:
            if hasattr(db, "update_payment_status"):
                db.update_payment_status(inv_id, "pending", payment_type="robokassa")
        else:
            db.create_payment(
                user_id=user_id,
                amount=float(amount_rub),
                payment_type="robokassa",
                status="pending",
                external_id=inv_id,
                days=days,
            )

    logger.info("Robokassa payment created inv_id=%s user_id=%s days=%s amount=%s", inv_id, user_id, days, out_sum)
    return inv_id, payment_url
