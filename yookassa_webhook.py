import logging

from aiohttp import web
from aiogram import Bot

from db import Database
from payments import get_yookassa_payment

logger = logging.getLogger(__name__)


def create_yookassa_app(bot: Bot, db: Database) -> web.Application:
    app = web.Application()

    async def healthcheck(request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def yookassa_webhook(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
            event = payload.get("event")
            obj = payload.get("object", {})
            payment_id = obj.get("id")

            logger.info("YooKassa webhook received: event=%s payment_id=%s", event, payment_id)

            if not payment_id:
                return web.Response(status=200, text="missing payment id")

            # Дополнительная защита: перепроверяем платёж по API ЮKassa,
            # как рекомендует документация.
            payment = await get_yookassa_payment(payment_id)
            metadata = payment.get("metadata", {}) or {}
            user_id = int(metadata.get("user_id", 0))
            days = int(metadata.get("days", 0))
            status = payment.get("status")
            amount_value = float(payment.get("amount", {}).get("value", 0))

            if event == "payment.succeeded" and status == "succeeded" and user_id and days:
                existing = db.get_payment_by_external_id(payment_id)
                if not existing or existing.get("status") != "succeeded":
                    db.upsert_payment(
                        user_id=user_id,
                        amount=amount_value,
                        payment_type="yookassa",
                        status="succeeded",
                        external_id=payment_id,
                        days=days,
                    )
                    db.activate_subscription(user_id, days)

                    try:
                        await bot.send_message(
                            user_id,
                            (
                                "✅ <b>Оплата прошла успешно</b>\n\n"
                                f"Подписка активирована на <b>{days}</b> дней."
                            ),
                        )
                    except Exception as e:
                        logger.exception("Failed to notify user about YooKassa payment: %s", e)
                return web.Response(status=200, text="ok")

            if event == "payment.canceled":
                db.update_payment_status(payment_id, "canceled")
                return web.Response(status=200, text="ok")

            return web.Response(status=200, text="ignored")
        except Exception as e:
            logger.exception("YooKassa webhook error: %s", e)
            return web.Response(status=500, text="error")

    app.router.add_get("/health", healthcheck)
    app.router.add_post("/yookassa/webhook", yookassa_webhook)
    return app
