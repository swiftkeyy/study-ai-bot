import asyncio
import json
import logging

import aiohttp
from aiogram import Bot

from config import CRYPTO_PAY_API_BASE, CRYPTO_PAY_API_TOKEN, CRYPTO_PAY_POLL_INTERVAL
from db import Database

logger = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)


async def _get_invoices(invoice_ids: list[str]) -> list[dict]:
    if not CRYPTO_PAY_API_TOKEN or not invoice_ids:
        return []

    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_API_TOKEN,
        "Content-Type": "application/json",
    }
    params = {"invoice_ids": ",".join(invoice_ids)}

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(
            f"{CRYPTO_PAY_API_BASE.rstrip('/')}/getInvoices",
            headers=headers,
            params=params,
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"CryptoBot getInvoices error {response.status}: {text[:500]}")
            data = json.loads(text)

    if not data.get("ok"):
        raise RuntimeError(f"CryptoBot getInvoices failed: {data}")

    return data.get("result", {}).get("items", [])


def _normalize_invoice_ids(invoice_ids: list[str]) -> list[str]:
    result = []
    seen = set()
    for invoice_id in invoice_ids:
        value = str(invoice_id).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


async def sync_cryptobot_invoice(bot: Bot, db: Database, invoice_id: str) -> str:
    invoice_id = str(invoice_id).strip()
    items = await _get_invoices([invoice_id])
    if not items:
        return "not_found"

    invoice = items[0]
    status = str(invoice.get("status") or "unknown")
    payment = db.get_payment_by_external_id(invoice_id, payment_type="cryptobot")

    if payment:
        db.update_payment_status(invoice_id, status, payment_type="cryptobot")

    if status == "paid" and payment and payment.get("status") != "paid":
        db.activate_subscription(int(payment["user_id"]), int(payment.get("days") or 0))
        try:
            await bot.send_message(
                int(payment["user_id"]),
                (
                    "✅ <b>Оплата прошла успешно</b>\n\n"
                    f"Подписка активирована на <b>{payment.get('days') or 0}</b> дней.\n"
                    "Способ оплаты: <b>CryptoBot</b>"
                ),
            )
        except Exception as e:
            logger.exception("Failed to notify user about CryptoBot payment %s: %s", invoice_id, e)

    return status


async def poll_cryptobot_invoices(bot: Bot, db: Database) -> None:
    if not CRYPTO_PAY_API_TOKEN:
        logger.info("CryptoBot polling disabled: CRYPTO_PAY_API_TOKEN is not set")
        return

    while True:
        try:
            pending = db.list_pending_payments("cryptobot", limit=100)
            invoice_ids = _normalize_invoice_ids([item["external_id"] for item in pending if item.get("external_id")])
            for chunk_start in range(0, len(invoice_ids), 50):
                chunk = invoice_ids[chunk_start:chunk_start + 50]
                items = await _get_invoices(chunk)
                by_id = {str(item.get("invoice_id")): item for item in items}
                for invoice_id in chunk:
                    invoice = by_id.get(invoice_id)
                    if not invoice:
                        continue
                    status = str(invoice.get("status") or "unknown")
                    payment = db.get_payment_by_external_id(invoice_id, payment_type="cryptobot")
                    if not payment:
                        continue
                    previous_status = payment.get("status")
                    db.update_payment_status(invoice_id, status, payment_type="cryptobot")
                    if status == "paid" and previous_status != "paid":
                        db.activate_subscription(int(payment["user_id"]), int(payment.get("days") or 0))
                        try:
                            await bot.send_message(
                                int(payment["user_id"]),
                                (
                                    "✅ <b>Оплата прошла успешно</b>\n\n"
                                    f"Подписка активирована на <b>{payment.get('days') or 0}</b> дней.\n"
                                    "Способ оплаты: <b>CryptoBot</b>"
                                ),
                            )
                        except Exception as e:
                            logger.exception("Failed to notify user about CryptoBot payment %s: %s", invoice_id, e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("CryptoBot polling iteration failed: %s", e)

        await asyncio.sleep(max(CRYPTO_PAY_POLL_INTERVAL, 10))
