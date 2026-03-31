import logging
import os
from decimal import Decimal, InvalidOperation

from aiohttp import web

from db import Database
from payments import (
    ROBOKASSA_IS_TEST,
    verify_result_signature,
    verify_success_signature,
)

logger = logging.getLogger(__name__)

try:
    from config import ROBOKASSA_WEBHOOK_HOST as _CFG_ROBOKASSA_WEBHOOK_HOST
except Exception:
    _CFG_ROBOKASSA_WEBHOOK_HOST = None

try:
    from config import ROBOKASSA_WEBHOOK_PORT as _CFG_ROBOKASSA_WEBHOOK_PORT
except Exception:
    _CFG_ROBOKASSA_WEBHOOK_PORT = None

ROBOKASSA_WEBHOOK_HOST = _CFG_ROBOKASSA_WEBHOOK_HOST or os.getenv("ROBOKASSA_WEBHOOK_HOST", "0.0.0.0")
ROBOKASSA_WEBHOOK_PORT = int(_CFG_ROBOKASSA_WEBHOOK_PORT or os.getenv("ROBOKASSA_WEBHOOK_PORT", "8081"))


def _collect_params(request: web.Request) -> dict[str, str]:
    params = dict(request.rel_url.query)
    if request.method.upper() == "POST":
        return params
    return params


def _collect_shp_params(params: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in params.items() if k.startswith("Shp_")}


def _amount_matches(stored_amount: float | int | str | None, out_sum: str) -> bool:
    if stored_amount is None:
        return False
    try:
        left = Decimal(str(stored_amount)).quantize(Decimal("0.01"))
        right = Decimal(str(out_sum)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return False
    return left == right


async def handle_result(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    bot = request.app["bot"]

    if request.method.upper() == "POST":
        form = await request.post()
        params = {k: str(v) for k, v in form.items()}
    else:
        params = _collect_params(request)

    out_sum = str(params.get("OutSum", ""))
    inv_id = str(params.get("InvId", ""))
    signature_value = str(params.get("SignatureValue", ""))
    shp_params = _collect_shp_params(params)

    if not out_sum or not inv_id or not signature_value:
        logger.warning("Robokassa ResultURL missing required params: %s", params)
        return web.Response(text="bad request", status=400)

    if not verify_result_signature(out_sum, inv_id, signature_value, shp_params):
        logger.warning("Robokassa ResultURL invalid signature inv_id=%s", inv_id)
        return web.Response(text="bad sign", status=400)

    payment = db.get_payment_by_external_id(inv_id, payment_type="robokassa")
    if not payment:
        logger.warning("Robokassa ResultURL payment not found inv_id=%s", inv_id)
        return web.Response(text=f"OK{inv_id}")

    if not _amount_matches(payment.get("amount"), out_sum):
        logger.warning(
            "Robokassa ResultURL amount mismatch inv_id=%s stored=%s got=%s",
            inv_id,
            payment.get("amount"),
            out_sum,
        )
        return web.Response(text="bad amount", status=400)

    if payment.get("status") not in {"succeeded", "paid"}:
        db.update_payment_status(inv_id, "succeeded", payment_type="robokassa")
        days = int(payment.get("days") or shp_params.get("Shp_days") or 0)
        user_id = int(payment.get("user_id") or shp_params.get("Shp_user_id") or 0)
        if user_id and days:
            db.activate_subscription(user_id, days)
            try:
                await bot.send_message(
                    user_id,
                    f"✅ Оплата через Robokassa подтверждена.\nПодписка на <b>{days} дней</b> активирована.",
                )
            except Exception:
                logger.exception("Failed to notify user about Robokassa payment success user_id=%s", user_id)

    return web.Response(text=f"OK{inv_id}")


async def handle_success(request: web.Request) -> web.Response:
    params = dict(request.rel_url.query)
    out_sum = str(params.get("OutSum", ""))
    inv_id = str(params.get("InvId", ""))
    signature_value = str(params.get("SignatureValue", ""))
    shp_params = _collect_shp_params(params)

    if out_sum and inv_id and signature_value:
        ok = verify_success_signature(out_sum, inv_id, signature_value, shp_params)
        logger.info("Robokassa SuccessURL inv_id=%s verified=%s", inv_id, ok)

    text = (
        "Оплата принята. Если подписка не активировалась автоматически в течение пары минут, "
        "вернитесь в бот и напишите в поддержку."
    )
    return web.Response(text=text, content_type="text/plain")


async def handle_fail(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    params = dict(request.rel_url.query)
    inv_id = str(params.get("InvId", ""))

    if inv_id:
        payment = db.get_payment_by_external_id(inv_id, payment_type="robokassa")
        if payment and payment.get("status") not in {"succeeded", "paid"}:
            db.update_payment_status(inv_id, "failed", payment_type="robokassa")

    return web.Response(
        text="Платёж не был завершён. Можно вернуться в бот и попробовать ещё раз.",
        content_type="text/plain",
    )


def create_robokassa_app(bot, db: Database) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app["db"] = db
    app.router.add_route("*", "/robokassa/result", handle_result)
    app.router.add_get("/robokassa/success", handle_success)
    app.router.add_get("/robokassa/fail", handle_fail)
    return app


async def start_robokassa_server(bot, db: Database):
    app = create_robokassa_app(bot, db)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, ROBOKASSA_WEBHOOK_HOST, ROBOKASSA_WEBHOOK_PORT)
    await site.start()
    logger.info(
        "Robokassa server started host=%s port=%s test=%s",
        ROBOKASSA_WEBHOOK_HOST,
        ROBOKASSA_WEBHOOK_PORT,
        ROBOKASSA_IS_TEST,
    )
    return runner
