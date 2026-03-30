import asyncio
import json
import logging
from typing import Any

import aiohttp
from aiogram import Bot

from config import CRYPTO_PAY_API_BASE, CRYPTO_PAY_API_TOKEN, CRYPTO_PAY_POLL_INTERVAL, crypto_pay_enabled
from db import Database

logger = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)


def _headers() -> dict[str, str]:
    return {"Crypto-Pay-API-Token": CRYPTO_PAY_API_TOKEN}


def _extract_invoice_data(invoice: dict[str, Any]) -> tuple[int, int]:
    payload = str(invoice.get("payload") or "")
    parts = payload.split(":")
    if len(parts) < 4 or parts[0] != "crypto":
        return 0, 0
    try:
        return int(parts[2]), int(parts[1])
    except (TypeError, ValueError):
        return 0, 0


def _invoice_amount(invoice: dict[str, Any]) -> float:
    raw = invoice.get("paid_amount") or invoice.get("amount") or 0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


async def get_cryptobot_invoices(invoice_ids: list[str]) -> list[dict[str, Any]]:
    if not invoice_ids or not crypto_pay_enabled():
        return []

    params = {
        "invoice_ids": ",".join(invoice_ids),
        "count": min(len(invoice_ids), 100),
    }

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(
            f"{CRYPTO_PAY_API_BASE.rstrip('/')}/getInvoices",
            headers=_headers(),
            params=params,
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"CryptoBot getInvoices error {response.status}: {text[:500]}")
            data = json.loads(text)

    if not data.get("ok"):
        raise RuntimeError(f"CryptoBot getInvoices failed: {data}")

    return data.get("result") or []


async def process_cryptobot_invoice(bot: Bot, db: Database, invoice: dict[str, Any]) -> str:
    invoice_id = str(invoice.get("invoice_id") or "")
    if not invoice_id:
        return "not_found"

    status = str(invoice.get("status") or "unknown")
    existing = db.get_payment_by_external_id(invoice_id, payment_type="cryptobot")

    if status == "paid":
        if existing and existing.get("status") == "paid":
            return "paid"

        user_id, days = _extract_invoice_data(invoice)
        if not user_id or not days:
            logger.warning("CryptoBot invoice %s has invalid payload", invoice_id)
            return "invalid_payload"

        db.upsert_payment(
            user_id=user_id,
            amount=_invoice_amount(invoice),
            payment_type="cryptobot",
            status="paid",
            external_id=invoice_id,
            days=days,
        )
        db.activate_subscription(user_id, days)

        try:
            await bot.send_message(
                user_id,
                (
                    "✅ <b>Оплата прошла успешно</b>\n\n"
                    f"Подписка активирована на <b>{days}</b> дней.\n"
                    "Способ оплаты: <b>CryptoBot</b>"
                ),
            )
        except Exception as e:
            logger.exception("Failed to notify user about CryptoBot payment %s: %s", invoice_id, e)
        return "paid"

    if existing and status in {"active", "expired"}:
        db.update_payment_status(invoice_id, status, payment_type="cryptobot")

    return status


async def sync_cryptobot_invoice(bot: Bot, db: Database, invoice_id: str) -> str:
    invoices = await get_cryptobot_invoices([invoice_id])
    if not invoices:
        return "not_found"
    return await process_cryptobot_invoice(bot, db, invoices[0])


async def poll_cryptobot_invoices(bot: Bot, db: Database) -> None:
    if not crypto_pay_enabled():
        logger.info("CryptoBot polling disabled: CRYPTO_PAY_API_TOKEN is empty")
        return

    logger.info("CryptoBot polling started with interval=%ss", CRYPTO_PAY_POLL_INTERVAL)
    while True:
        try:
            pending = db.list_pending_payments("cryptobot", limit=100)
            if pending:
                invoice_ids = [str(item["external_id"]) for item in pending if item.get("external_id")]
                if invoice_ids:
                    invoices = await get_cryptobot_invoices(invoice_ids)
                    for invoice in invoices:
                        try:
                            await process_cryptobot_invoice(bot, db, invoice)
                        except Exception as e:
                            logger.exception("Failed to process CryptoBot invoice: %s", e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("CryptoBot polling iteration failed: %s", e)

        await asyncio.sleep(max(CRYPTO_PAY_POLL_INTERVAL, 10))
