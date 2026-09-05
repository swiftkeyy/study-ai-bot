from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qs, quote_plus

import pytest

import payments
import robokassa


def sign(out_sum: str, inv_id: str, shp: dict[str, str], password: str) -> str:
    parts = [out_sum, inv_id, password] + [f"{key}={value}" for key, value in sorted(shp.items(), key=lambda i: i[0].lower())]
    return hashlib.md5(":".join(parts).encode("utf-8")).hexdigest()


class FakeRequest:
    """Minimal stand-in for aiohttp's web.Request."""

    def __init__(self, query: dict[str, str] | None = None, raw_query: str = "", method: str = "GET", app: dict | None = None):
        self.method = method
        self.query = query or {}
        self.raw_path = f"/robokassa/pay?{raw_query}" if raw_query else "/robokassa/pay"
        self.rel_url = type("URL", (), {"query": self.query})()
        self.app = app or {}

    async def post(self) -> dict[str, str]:
        return self.query


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.sent.append((chat_id, text))


def make_app(db=None, bot=None) -> dict:
    return {robokassa.APP_DB: db, robokassa.APP_BOT: bot or FakeBot()}


def test_normalize_amount_test_mode_uses_integers():
    assert payments._normalize_amount(99) == "99"
    assert payments._normalize_amount(99.5) == "99"  # ROBOKASSA_IS_TEST=1 in the test env


def test_receipt_json_shape():
    receipt = json.loads(payments._build_receipt(7, 199))
    item = receipt["items"][0]
    assert item["sum"] == 199.0
    assert item["quantity"] == 1
    assert item["tax"] == "none"
    assert item["payment_method"] == "full_payment"
    assert len(item["name"]) <= payments.RECEIPT_ITEM_NAME_LIMIT


def test_days_label_pluralization():
    assert payments._format_days_label(1) == "1 день"
    assert payments._format_days_label(3) == "3 дня"
    assert payments._format_days_label(30) == "30 дней"


def test_prices_text_contains_all_tariffs(db):
    text = payments.format_prices_text(db)
    assert "59 Stars" in text and "199 ₽" in text
    assert "Robokassa" in text  # enabled through the test env


def test_buy_keyboard_offers_both_providers(db):
    keyboard = payments.get_buy_keyboard(db, user_id=1)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert {button.callback_data for button in buttons} >= {"buy_stars_3", "buy_stars_7", "buy_stars_30", "buy_robo_30"}


def test_buy_keyboard_hides_robokassa_when_disabled(db, monkeypatch):
    monkeypatch.setattr(payments, "ROBOKASSA_MERCHANT_LOGIN", "")
    buttons = [button for row in payments.get_buy_keyboard(db).inline_keyboard for button in row]
    assert all(not (button.callback_data or "").startswith("buy_robo_") for button in buttons)
    assert "Robokassa" not in payments.format_prices_text(db)


@pytest.mark.asyncio
async def test_stars_invoice_parameters(db):
    sent = {}

    class InvoiceBot:
        async def send_invoice(self, **kwargs):
            sent.update(kwargs)

    await payments.send_stars_invoice(InvoiceBot(), chat_id=7, user_id=7, days=3, db=db)
    assert sent["currency"] == "XTR"
    assert sent["provider_token"] == ""
    assert sent["prices"][0].amount == payments._get_price(db.get_prices(), 3, "stars")
    days, user_id = sent["payload"].split(":")[1:3]
    assert (int(days), int(user_id)) == (3, 7)

    with pytest.raises(ValueError):
        await payments.send_stars_invoice(InvoiceBot(), 7, 7, 11, db)


@pytest.mark.asyncio
async def test_create_robokassa_payment_registers_pending_payment(db):
    inv_id, url = await payments.create_robokassa_payment(user_id=42, days=7, db=db)

    payment = db.get_payment_by_external_id(inv_id, payment_type="robokassa")
    assert payment["status"] == "pending"
    assert payment["user_id"] == 42
    assert payment["days"] == 7
    assert payment["amount"] == payments._get_price(db.get_prices(), 7, "rub")

    query = parse_qs(url.split("?", 1)[1])
    assert query["InvId"] == [inv_id]
    assert query["Shp_user_id"] == ["42"]
    assert query["IsTest"] == ["1"]

    # signature must be reproducible from the same parameters
    receipt = query.get("Receipt", [""])[0]
    parts = [payments.ROBOKASSA_MERCHANT_LOGIN, query["OutSum"][0], inv_id]
    if receipt:
        parts.append(quote_plus(receipt))
    parts.append(payments.ROBOKASSA_PASSWORD1)
    parts += [f"{key}={query[key][0]}" for key in sorted(query) if key.startswith("Shp_")]
    assert query["SignatureValue"] == [hashlib.md5(":".join(parts).encode("utf-8")).hexdigest()]


@pytest.mark.asyncio
async def test_create_robokassa_payment_uses_local_form_with_public_url(db, monkeypatch):
    monkeypatch.setattr(payments, "ROBOKASSA_PUBLIC_BASE_URL", "https://bot.example.com")
    _inv_id, url = await payments.create_robokassa_payment(user_id=1, days=3, db=db)
    assert url.startswith("https://bot.example.com/robokassa/pay?")


@pytest.mark.asyncio
async def test_create_robokassa_payment_rejects_unknown_tariff(db):
    with pytest.raises(ValueError):
        await payments.create_robokassa_payment(user_id=1, days=11, db=db)


@pytest.mark.asyncio
async def test_create_robokassa_payment_requires_credentials(db, monkeypatch):
    monkeypatch.setattr(payments, "ROBOKASSA_MERCHANT_LOGIN", "")
    with pytest.raises(RuntimeError):
        await payments.create_robokassa_payment(user_id=1, days=3, db=db)


def test_result_signature_verification():
    shp = {"Shp_user_id": "5", "Shp_days": "3"}
    good = sign("99", "INV5", shp, payments.ROBOKASSA_PASSWORD2)
    assert payments.verify_result_signature("99", "INV5", good, shp) is True
    assert payments.verify_result_signature("1", "INV5", good, shp) is False
    assert payments.verify_result_signature("99", "INV5", good, {**shp, "Shp_days": "30"}) is False
    assert payments.verify_result_signature("99", "INV5", good.upper(), shp) is True


@pytest.mark.asyncio
async def test_result_handler_activates_subscription_once(db):
    bot = FakeBot()
    request_app = make_app(db, bot)
    db.get_or_create_user(77, "buyer")
    inv_id, _url = await payments.create_robokassa_payment(user_id=77, days=30, db=db)
    amount = str(int(db.get_payment_by_external_id(inv_id)["amount"]))
    shp = {"Shp_user_id": "77", "Shp_days": "30"}
    query = {"OutSum": amount, "InvId": inv_id, "SignatureValue": sign(amount, inv_id, shp, payments.ROBOKASSA_PASSWORD2), **shp}

    response = await robokassa.result_handler(FakeRequest(query, app=request_app))
    assert response.text == f"OK{inv_id}"
    assert db.get_payment_by_external_id(inv_id)["status"] == "succeeded"
    assert db.get_user(77)["is_premium"] == 1
    assert len(bot.sent) == 1

    # a repeated notification must not extend the subscription again
    sub_until = db.get_user(77)["sub_until"]
    await robokassa.result_handler(FakeRequest(query, app=request_app))
    assert db.get_user(77)["sub_until"] == sub_until
    assert len(bot.sent) == 1


@pytest.mark.asyncio
async def test_result_handler_rejects_bad_requests(db):
    request_app = make_app(db)
    shp = {"Shp_user_id": "1", "Shp_days": "3"}

    missing = await robokassa.result_handler(FakeRequest({"OutSum": "10"}, app=request_app))
    assert missing.status == 400

    bad_sign = await robokassa.result_handler(
        FakeRequest({"OutSum": "10", "InvId": "1", "SignatureValue": "nope", **shp}, app=request_app)
    )
    assert bad_sign.status == 400

    unknown = await robokassa.result_handler(
        FakeRequest({"OutSum": "10", "InvId": "424242", "SignatureValue": sign("10", "424242", shp, payments.ROBOKASSA_PASSWORD2), **shp}, app=request_app)
    )
    assert unknown.status == 200  # Robokassa only wants "OK", nothing to settle here

    # valid signature but a different amount than the stored price
    db.get_or_create_user(88, None)
    inv_id, _url = await payments.create_robokassa_payment(user_id=88, days=3, db=db)
    shp = {"Shp_user_id": "88", "Shp_days": "3"}
    tampered = await robokassa.result_handler(
        FakeRequest({"OutSum": "1", "InvId": inv_id, "SignatureValue": sign("1", inv_id, shp, payments.ROBOKASSA_PASSWORD2), **shp}, app=request_app)
    )
    assert tampered.status == 400
    assert db.get_payment_by_external_id(inv_id)["status"] == "pending"


@pytest.mark.asyncio
async def test_result_handler_accepts_post_form(db):
    bot = FakeBot()
    db.get_or_create_user(99, None)
    inv_id, _url = await payments.create_robokassa_payment(user_id=99, days=7, db=db)
    amount = str(int(db.get_payment_by_external_id(inv_id)["amount"]))
    shp = {"Shp_user_id": "99", "Shp_days": "7"}
    query = {"OutSum": amount, "InvId": inv_id, "SignatureValue": sign(amount, inv_id, shp, payments.ROBOKASSA_PASSWORD2), **shp}
    response = await robokassa.result_handler(FakeRequest(query, method="POST", app=make_app(db, bot)))
    assert response.text == f"OK{inv_id}"
    assert db.get_user(99)["is_premium"] == 1


@pytest.mark.asyncio
async def test_payment_form_handler_filters_and_escapes(db):
    raw_receipt = '{"items":[{"name":"Подписка"}]}'
    query = {
        "MerchantLogin": "m",
        "OutSum": "99",
        "InvId": "1",
        "SignatureValue": "sig",
        "Receipt": quote_plus(raw_receipt),
        "Shp_user_id": "3",
        "Evil": "<script>alert(1)</script>",
    }
    response = await robokassa.payment_form_handler(FakeRequest(query, raw_query="Receipt=" + quote_plus(raw_receipt)))
    body = response.text
    assert response.content_type == "text/html"
    assert "method=\"post\"" in body
    assert "Evil" not in body
    assert "<script>alert(1)</script>" not in body
    assert "name=\"Receipt\"" in body
    assert 'action="https://auth.robokassa.ru/Merchant/Index.aspx"' in body

    incomplete = await robokassa.payment_form_handler(FakeRequest({"MerchantLogin": "m"}))
    assert incomplete.status == 400
    empty = await robokassa.payment_form_handler(FakeRequest({}))
    assert empty.status == 400


def test_webhook_routes_are_registered(db):
    app = robokassa.create_robokassa_app(FakeBot(), db)
    routes = {rule.resource.canonical for rule in app.router.routes()}
    assert {"/robokassa/result", "/robokassa/success", "/robokassa/fail", "/robokassa/pay", "/healthz"} <= routes


@pytest.mark.asyncio
async def test_healthz_reports_database_problem(db):
    response = await robokassa.healthz_handler(FakeRequest(app=make_app(db)))
    assert response.text == "ok"

    broken = type("Broken", (), {"total_users": lambda self: (_ for _ in ()).throw(RuntimeError("locked"))})()
    failed = await robokassa.healthz_handler(FakeRequest(app=make_app(broken, FakeBot())))
    assert failed.status == 503
