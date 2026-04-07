import html
import logging
import os
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote_plus

from aiohttp import web

from db import Database
from payments import robokassa_enabled, verify_result_signature

logger = logging.getLogger(__name__)

ROBOKASSA_WEBHOOK_HOST = os.getenv("ROBOKASSA_WEBHOOK_HOST", "0.0.0.0").strip()
ROBOKASSA_WEBHOOK_PORT = int(os.getenv("ROBOKASSA_WEBHOOK_PORT", "8081"))


def _collect_shp(params: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in params.items() if k.startswith("Shp_")}


def _parse_raw_query_string(raw_query: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not raw_query:
        return result

    for chunk in raw_query.split("&"):
        if not chunk:
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
        else:
            key, value = chunk, ""
        result[unquote_plus(key)] = value
    return result


def _amount_matches(stored_amount, out_sum: str) -> bool:
    try:
        left = Decimal(str(stored_amount)).quantize(Decimal("0.01"))
        right = Decimal(str(out_sum)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return False
    return left == right


async def result_handler(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    bot = request.app["bot"]

    if request.method.upper() == "POST":
        form = await request.post()
        params = {k: str(v) for k, v in form.items()}
    else:
        params = dict(request.rel_url.query)

    out_sum = str(params.get("OutSum", ""))
    inv_id = str(params.get("InvId", ""))
    signature = str(params.get("SignatureValue", ""))
    shp_params = _collect_shp(params)

    if not out_sum or not inv_id or not signature:
        return web.Response(text="bad request", status=400)

    if not verify_result_signature(out_sum, inv_id, signature, shp_params):
        logger.warning("Robokassa bad signature inv_id=%s", inv_id)
        return web.Response(text="bad sign", status=400)

    payment = db.get_payment_by_external_id(inv_id, payment_type="robokassa")
    if not payment:
        logger.warning("Robokassa payment not found inv_id=%s", inv_id)
        return web.Response(text=f"OK{inv_id}")

    if not _amount_matches(payment.get("amount"), out_sum):
        logger.warning(
            "Robokassa amount mismatch inv_id=%s stored=%s got=%s",
            inv_id,
            payment.get("amount"),
            out_sum,
        )
        return web.Response(text="bad amount", status=400)

    if payment.get("status") not in {"paid", "succeeded"}:
        db.update_payment_status(inv_id, "succeeded", payment_type="robokassa")
        user_id = int(payment.get("user_id") or shp_params.get("Shp_user_id") or 0)
        days = int(payment.get("days") or shp_params.get("Shp_days") or 0)
        if user_id and days:
            db.activate_subscription(user_id, days)
            try:
                await bot.send_message(
                    user_id,
                    f"✅ Оплата через Robokassa подтверждена.\nПодписка на <b>{days}</b> дней активирована."
                )
            except Exception:
                logger.exception("Failed to notify user %s about Robokassa payment", user_id)

    return web.Response(text=f"OK{inv_id}")



async def payment_form_handler(request: web.Request) -> web.Response:
    params = dict(request.rel_url.query)
    if not params:
        return web.Response(text="bad request", status=400)

    required = ["MerchantLogin", "OutSum", "InvId", "SignatureValue"]
    if any(not str(params.get(key, "")).strip() for key in required):
        return web.Response(text="bad request", status=400)

    raw_query = request.raw_path.split("?", 1)[1] if "?" in request.raw_path else ""
    raw_params = _parse_raw_query_string(raw_query)

    hidden_inputs = []
    for key, value in params.items():
        form_value = str(value)
        if key == "Receipt" and key in raw_params:
            # Для Robokassa поле Receipt в POST-форме должно уйти уже в URL-encoded виде.
            # Браузер сам повторно закодирует значение при отправке формы.
            form_value = raw_params[key]
        hidden_inputs.append(
            f'<input type="hidden" name="{html.escape(str(key))}" value="{html.escape(form_value)}">'
        )

    form_html = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Переход к оплате Robokassa</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{
      font-family: Arial, sans-serif;
      background: #f5f7fb;
      color: #111827;
      margin: 0;
      display: flex;
      min-height: 100vh;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      width: 100%;
      max-width: 520px;
      background: #ffffff;
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.08);
      padding: 28px;
      text-align: center;
    }}
    h1 {{
      font-size: 24px;
      margin: 0 0 12px;
    }}
    p {{
      margin: 0 0 12px;
      line-height: 1.5;
    }}
    .muted {{
      color: #6b7280;
      font-size: 14px;
    }}
    .btn {{
      display: inline-block;
      margin-top: 12px;
      background: #4f46e5;
      color: #fff;
      border: 0;
      border-radius: 12px;
      padding: 14px 22px;
      font-size: 16px;
      cursor: pointer;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Переходим к оплате…</h1>
    <p>Сейчас откроется защищённая платёжная страница Robokassa.</p>
    <p class="muted">Если переход не выполнится автоматически, нажми кнопку ниже.</p>
    <form id="robo-form" method="post" action="https://auth.robokassa.ru/Merchant/Index.aspx">
      {''.join(hidden_inputs)}
      <button class="btn" type="submit">Оплатить через Robokassa</button>
    </form>
  </div>
  <script>
    window.addEventListener('load', function() {{
      const form = document.getElementById('robo-form');
      if (form) {{
        setTimeout(function() {{ form.submit(); }}, 250);
      }}
    }});
  </script>
</body>
</html>"""
    return web.Response(text=form_html, content_type="text/html")


async def success_handler(request: web.Request) -> web.Response:
    return web.Response(
        text="Оплата принята. Вернитесь в Telegram-бот — подписка активируется автоматически.",
        content_type="text/plain",
    )


async def fail_handler(request: web.Request) -> web.Response:
    return web.Response(
        text="Платёж не завершён. Можно вернуться в бот и попробовать ещё раз.",
        content_type="text/plain",
    )


def create_robokassa_app(bot, db: Database) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app["db"] = db
    app.router.add_get("/robokassa/pay", payment_form_handler)
    app.router.add_route("*", "/robokassa/result", result_handler)
    app.router.add_get("/robokassa/success", success_handler)
    app.router.add_get("/robokassa/fail", fail_handler)
    return app


async def start_robokassa_server(bot, db: Database):
    if not robokassa_enabled():
        logger.info("Robokassa disabled: webhook server not started")
        return None

    app = create_robokassa_app(bot, db)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, ROBOKASSA_WEBHOOK_HOST, ROBOKASSA_WEBHOOK_PORT)
    await site.start()
    logger.info("Robokassa webhook started on %s:%s", ROBOKASSA_WEBHOOK_HOST, ROBOKASSA_WEBHOOK_PORT)
    return runner
