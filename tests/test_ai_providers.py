from __future__ import annotations

import pytest

import ai


def _failing(exc_text: str):
    async def _call(*args, **kwargs):
        raise RuntimeError(exc_text)

    return _call


def test_provider_names_are_normalized():
    assert ai._normalize_provider_name("mistralai") == "Mistral"
    assert ai._normalize_provider_name(" openrouter ") == "OpenRouter"
    assert ai._normalize_provider_name("google") == "Gemini"
    assert ai._normalize_provider_name("unknown") == "unknown"


def test_provider_order_puts_configured_first_and_deduplicates():
    order = ai._merge_provider_order(["groq", "groq", "Mistral"], ai.TEXT_DEFAULT_ORDER)
    assert order == ["Groq", "Mistral", "OpenRouter", "Gemini"]
    assert ai._merge_provider_order([], ai.TEXT_DEFAULT_ORDER) == ai.TEXT_DEFAULT_ORDER
    assert ai._merge_provider_order(["нет-такого"], ai.TEXT_DEFAULT_ORDER) == ai.TEXT_DEFAULT_ORDER


def test_extract_message_content_variants():
    assert ai._extract_message_content({"choices": [{"message": {"content": " ответ "}}]}, "Mistral") == "ответ"
    parts = {"choices": [{"message": {"content": [{"type": "text", "text": "раз"}, {"type": "text", "text": "два"}]}}]}
    assert ai._extract_message_content(parts, "OpenRouter") == "раз\nдва"
    with pytest.raises(RuntimeError, match="choices"):
        ai._extract_message_content({"choices": []}, "Groq")
    # an empty string is returned as-is; ask_ai() treats it as a failed provider
    assert ai._extract_message_content({"choices": [{"message": {"content": ""}}]}, "Groq") == ""
    with pytest.raises(RuntimeError, match="пустой текст"):
        ai._extract_message_content({"choices": [{"message": {"content": [{"type": "image"}]}}]}, "Groq")


@pytest.mark.asyncio
async def test_ask_ai_falls_back_to_the_next_provider(monkeypatch):
    calls: list[str] = []

    async def broken(prompt, system_prompt=None):
        calls.append("failed")
        raise RuntimeError("429 rate limit")

    async def working(prompt, system_prompt=None):
        calls.append("groq")
        return "  итоговый ответ  "

    monkeypatch.setattr(ai, "_ask_mistral", broken)
    monkeypatch.setattr(ai, "_ask_openrouter", broken)
    monkeypatch.setattr(ai, "_ask_groq", working)
    monkeypatch.setattr(ai, "_ask_gemini", broken)

    text, provider = await ai.ask_ai("вопрос", system_prompt="system", provider_order=["Mistral", "Groq"])
    assert (text, provider) == ("итоговый ответ", "Groq")
    # Groq is tried second, Gemini must never be reached
    assert calls == ["failed", "groq"]


@pytest.mark.asyncio
async def test_ask_ai_skips_empty_answers(monkeypatch):
    async def empty(prompt, system_prompt=None):
        return "   "

    async def working(prompt, system_prompt=None):
        return "нормальный ответ"

    monkeypatch.setattr(ai, "_ask_mistral", empty)
    monkeypatch.setattr(ai, "_ask_openrouter", working)

    text, provider = await ai.ask_ai("вопрос")
    assert (text, provider) == ("нормальный ответ", "OpenRouter")


@pytest.mark.asyncio
async def test_ask_ai_reports_every_failed_provider(monkeypatch):
    for name in ("_ask_mistral", "_ask_openrouter", "_ask_groq", "_ask_gemini"):
        monkeypatch.setattr(ai, name, _failing("network down"))

    with pytest.raises(RuntimeError) as excinfo:
        await ai.ask_ai("вопрос")
    message = str(excinfo.value)
    assert "Mistral" in message and "Gemini" in message and "network down" in message


@pytest.mark.asyncio
async def test_vision_requests_use_configured_provider_order(monkeypatch):
    async def groq_image(prompt, image_bytes, mime_type="image/jpeg", system_prompt=None):
        assert prompt == "реши"
        assert image_bytes == b"fake-image"
        return "решение по фото"

    monkeypatch.setattr(ai, "_ask_mistral_with_image", _failing("MISTRAL_API_KEY не указан"))
    monkeypatch.setattr(ai, "_ask_openrouter_with_image", _failing("OPENROUTER_API_KEY не указан"))
    monkeypatch.setattr(ai, "_ask_groq_with_image", groq_image)
    monkeypatch.setattr(ai, "_ask_gemini_with_image", _failing("should not be reached"))

    text, provider = await ai.ask_ai_with_image(
        "реши",
        b"fake-image",
        provider_order=["Mistral", "OpenRouter", "Groq"],
    )
    assert text == "решение по фото"
    assert provider == "Groq"


@pytest.mark.asyncio
async def test_unconfigured_provider_raises_before_http_call():
    """Only GEMINI_API_KEY is set in the test environment."""
    assert ai.GROQ_API_KEY == ""
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        await ai._ask_groq("привет")


def test_image_generation_module_is_importable_without_key():
    """image_ai.py used to fail on import: config had no DEEPAI_API_KEY."""
    import image_ai

    assert callable(image_ai.generate_image)


@pytest.mark.asyncio
async def test_deepai_without_key_raises_runtime_error():
    import image_ai

    assert image_ai.DEEPAI_API_KEY == ""
    with pytest.raises(RuntimeError, match="DEEPAI_API_KEY"):
        await image_ai.generate_image("кот в космосе")
