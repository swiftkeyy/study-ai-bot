"""Resilience under load: shared HTTP session, flood-control handling, log rotation."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging

import pytest
from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import SendMessage

import ai
import bot as bot_module
import config
import http_client


def _value(obj):
    async def _coro():
        return obj

    return _coro()


class FakeResponse:
    def __init__(self, body: str, status: int = 200):
        self._body = body
        self.status = status

    async def text(self) -> str:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, body: str, status: int = 200):
        self.body = body
        self.status = status
        self.calls = 0
        self.closed = False

    def post(self, url, **kwargs):
        self.calls += 1
        return FakeResponse(self.body, self.status)


@pytest.mark.asyncio
async def test_providers_reuse_one_http_session(monkeypatch):
    """Creating a ClientSession per request meant a fresh TLS handshake on every AI call."""
    fake = FakeSession(json.dumps({"choices": [{"message": {"content": "готово"}}]}))
    monkeypatch.setattr(ai, "get_session", lambda: _value(fake))

    result = await ai._post_json("https://example.invalid", {"a": "b"}, {"x": 1}, "Mistral")
    assert result == {"choices": [{"message": {"content": "готово"}}]}
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_post_json_reports_http_and_decode_errors(monkeypatch):
    http_error = FakeSession("rate limited", status=429)
    monkeypatch.setattr(ai, "get_session", lambda: _value(http_error))
    with pytest.raises(RuntimeError, match="HTTP 429"):
        await ai._post_json("https://example.invalid", {}, {}, "Groq")

    broken_json = FakeSession("<html>bad gateway</html>")
    monkeypatch.setattr(ai, "get_session", lambda: _value(broken_json))
    with pytest.raises(RuntimeError, match="не JSON"):
        await ai._post_json("https://example.invalid", {}, {}, "Groq")


@pytest.mark.asyncio
async def test_shared_session_is_reused_between_requests():
    await http_client.close_session()
    first = await http_client.get_session()
    second = await http_client.get_session()
    try:
        assert first is second
        assert first.connector is not None
    finally:
        await http_client.close_session()
    assert first.closed
    # closing twice is harmless
    await http_client.close_session()


@pytest.mark.asyncio
async def test_session_respects_the_configured_connection_limit():
    await http_client.close_session()
    session = await http_client.get_session()
    try:
        assert session.connector._limit == config.AI_CONNECTION_LIMIT
    finally:
        await http_client.close_session()


def test_session_is_not_reused_across_event_loops():
    async def in_loop_a():
        return await http_client.get_session()

    async def in_loop_b():
        return await http_client.get_session()

    loop_a = asyncio.new_event_loop()
    loop_b = asyncio.new_event_loop()
    try:
        session_a = loop_a.run_until_complete(in_loop_a())
        session_b = loop_b.run_until_complete(in_loop_b())
        assert session_a is not session_b
        loop_a.run_until_complete(session_a.close())
        loop_b.run_until_complete(session_b.close())
    finally:
        loop_a.close()
        loop_b.close()
        http_client._session = None
        http_client._session_loop = None


@pytest.mark.asyncio
async def test_safe_answer_waits_out_flood_control(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    class Msg:
        def __init__(self):
            self.sent: list[str] = []
            self.raised = False

        async def answer(self, text, **kwargs):
            if not self.raised:
                self.raised = True
                raise TelegramRetryAfter(
                    method=SendMessage(chat_id=1, text="x"),
                    message="Too Many Requests: retry later in 4 seconds",
                    retry_after=4,
                )
            self.sent.append(text)

    msg = Msg()
    monkeypatch.setattr(bot_module, "_sleep", fake_sleep)
    await bot_module.safe_answer(msg, "ответ")

    assert slept == [5]
    assert msg.sent == ["ответ"]


@pytest.mark.asyncio
async def test_safe_answer_caps_the_backoff_and_gives_up(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    class AlwaysFlooded:
        async def answer(self, text, **kwargs):
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=1, text="x"), message="slow down", retry_after=600
            )

    monkeypatch.setattr(bot_module, "_sleep", fake_sleep)
    with pytest.raises(TelegramRetryAfter):
        await bot_module.safe_answer(AlwaysFlooded(), "ответ")
    assert slept == [15], "the wait must be capped so a stalled queue cannot hang the bot"


@pytest.mark.asyncio
async def test_safe_answer_falls_back_to_plain_text(monkeypatch):
    class BadMarkup:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        async def answer(self, text, **kwargs):
            self.calls.append((text, kwargs))
            if "parse_mode" not in kwargs:
                raise TelegramBadRequest(method="sendMessage", message="400: can't parse entities")

    msg = BadMarkup()
    await bot_module.safe_answer(msg, "<b>текст</b> и <code>x</code>")
    assert msg.calls[0][1] == {}
    assert msg.calls[1] == ("текст и x", {"parse_mode": None})


def test_logging_survives_unwritable_log_file(tmp_path, monkeypatch, capsys):
    """A full or read-only disk must not stop the bot: console logging is enough."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    monkeypatch.setattr(bot_module, "LOG_FILE", str(blocked / "bot.log"))

    handlers = bot_module._build_log_handlers()
    try:
        assert any(isinstance(h, logging.StreamHandler) for h in handlers)
        assert len(handlers) == 1
    finally:
        for handler in handlers:
            handler.close()


def test_rotating_file_handler_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_module, "LOG_FILE", str(tmp_path / "bot.log"))
    handlers = bot_module._build_log_handlers()
    rotating = [h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    try:
        assert rotating, "the log file must rotate, or a burst of errors fills the disk"
        assert rotating[0].maxBytes == bot_module.LOG_MAX_BYTES
        assert rotating[0].backupCount == bot_module.LOG_BACKUP_COUNT
    finally:
        for handler in handlers:
            handler.close()


def test_polling_is_configured_with_backpressure():
    assert "tasks_concurrency_limit" in inspect.signature(Dispatcher.start_polling).parameters
    assert bot_module.MAX_CONCURRENT_UPDATES >= 1
    assert "tasks_concurrency_limit=MAX_CONCURRENT_UPDATES" in inspect.getsource(bot_module.main)
