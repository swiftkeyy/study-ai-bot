import base64
import json
import logging
from typing import Any, Iterable, Optional

import aiohttp

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_VISION_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_VISION_MODEL,
    MISTRAL_API_BASE,
    MISTRAL_API_KEY,
    MISTRAL_MODEL,
    MISTRAL_VISION_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_VISION_MODEL,
)

logger = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=90, connect=20, sock_read=70)

TEXT_DEFAULT_ORDER = ["Mistral", "OpenRouter", "Groq", "Gemini"]
IMAGE_DEFAULT_ORDER = ["Mistral", "OpenRouter", "Groq", "Gemini"]


def _normalize_provider_name(name: str) -> str:
    value = (name or "").strip().lower()
    if value in {"mistral", "mistralai"}:
        return "Mistral"
    if value in {"openrouter", "or"}:
        return "OpenRouter"
    if value in {"groq"}:
        return "Groq"
    if value in {"gemini", "google"}:
        return "Gemini"
    return name


def _merge_provider_order(provider_order: Optional[Iterable[str]], defaults: list[str]) -> list[str]:
    order = list(defaults)
    if provider_order:
        cleaned: list[str] = []
        for item in provider_order:
            normalized = _normalize_provider_name(item)
            if normalized in defaults and normalized not in cleaned:
                cleaned.append(normalized)
        if cleaned:
            order = cleaned + [item for item in defaults if item not in cleaned]
    return order


def _extract_message_content(data: dict[str, Any], provider_name: str) -> str:
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"{provider_name} не вернул choices: {data}")

    message = choices[0].get("message", {})
    content = message.get("content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, dict):
                if chunk.get("type") in {"text", "output_text"} and chunk.get("text"):
                    parts.append(str(chunk["text"]))
                elif chunk.get("content"):
                    parts.append(str(chunk["content"]))
            elif isinstance(chunk, str):
                parts.append(chunk)
        text = "\n".join(part for part in parts if part).strip()
        if text:
            return text

    raise RuntimeError(f"{provider_name} вернул пустой текст: {data}")


def _image_data_url(image_bytes: bytes, mime_type: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{image_b64}"


async def ask_ai(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider_order: Optional[Iterable[str]] = None,
) -> tuple[str, str]:
    providers_map = {
        "Mistral": _ask_mistral,
        "OpenRouter": _ask_openrouter,
        "Groq": _ask_groq,
        "Gemini": _ask_gemini,
    }

    order = _merge_provider_order(provider_order, TEXT_DEFAULT_ORDER)
    errors: list[str] = []

    for provider_name in order:
        provider_func = providers_map[provider_name]
        try:
            logger.info("AI request started via %s", provider_name)
            text = await provider_func(prompt=prompt, system_prompt=system_prompt)
            if text and text.strip():
                logger.info("AI request success via %s", provider_name)
                return text.strip(), provider_name
            errors.append(f"{provider_name}: пустой ответ")
        except Exception as e:
            logger.exception("AI provider %s failed", provider_name)
            errors.append(f"{provider_name}: {e}")

    raise RuntimeError("Все AI-провайдеры недоступны. " + " | ".join(errors))


async def ask_ai_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_prompt: Optional[str] = None,
    provider_order: Optional[Iterable[str]] = None,
) -> tuple[str, str]:
    providers_map = {
        "Mistral": _ask_mistral_with_image,
        "OpenRouter": _ask_openrouter_with_image,
        "Groq": _ask_groq_with_image,
        "Gemini": _ask_gemini_with_image,
    }

    order = _merge_provider_order(provider_order, IMAGE_DEFAULT_ORDER)
    errors: list[str] = []

    for provider_name in order:
        provider_func = providers_map[provider_name]
        try:
            logger.info("AI image request started via %s", provider_name)
            text = await provider_func(
                prompt=prompt,
                image_bytes=image_bytes,
                mime_type=mime_type,
                system_prompt=system_prompt,
            )
            if text and text.strip():
                logger.info("AI image request success via %s", provider_name)
                return text.strip(), provider_name
            errors.append(f"{provider_name}: пустой ответ")
        except Exception as e:
            logger.exception("AI image provider %s failed", provider_name)
            errors.append(f"{provider_name}: {e}")

    raise RuntimeError("Все AI vision-провайдеры недоступны. " + " | ".join(errors))


async def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], provider_name: str) -> dict[str, Any]:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {text[:500]}")
            return json.loads(text)


async def _ask_mistral(prompt: str, system_prompt: Optional[str] = None) -> str:
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY не указан")

    url = f"{MISTRAL_API_BASE}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 4096,
    }
    data = await _post_json(url, headers, payload, "Mistral")
    return _extract_message_content(data, "Mistral")


async def _ask_mistral_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_prompt: Optional[str] = None,
) -> str:
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY не указан")

    url = f"{MISTRAL_API_BASE}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    content = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    content.append({"type": "image_url", "image_url": _image_data_url(image_bytes, mime_type)})

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content})

    payload = {
        "model": MISTRAL_VISION_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 4096,
    }
    data = await _post_json(url, headers, payload, "Mistral")
    return _extract_message_content(data, "Mistral")


async def _ask_openrouter(prompt: str, system_prompt: Optional[str] = None) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY не указан")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "Study AI Telegram Bot",
    }
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 4096,
    }
    data = await _post_json(url, headers, payload, "OpenRouter")
    return _extract_message_content(data, "OpenRouter")


async def _ask_openrouter_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_prompt: Optional[str] = None,
) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY не указан")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "Study AI Telegram Bot",
    }
    data_url = _image_data_url(image_bytes, mime_type)

    content = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    content.append({"type": "image_url", "image_url": {"url": data_url}})

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content})

    payload = {
        "model": OPENROUTER_VISION_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 4096,
    }
    data = await _post_json(url, headers, payload, "OpenRouter")
    return _extract_message_content(data, "OpenRouter")


async def _ask_groq(prompt: str, system_prompt: Optional[str] = None) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY не указан")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 4096,
    }
    data = await _post_json(url, headers, payload, "Groq")
    return _extract_message_content(data, "Groq")


async def _ask_groq_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_prompt: Optional[str] = None,
) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY не указан")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    data_url = _image_data_url(image_bytes, mime_type)

    content = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    content.append({"type": "image_url", "image_url": {"url": data_url}})

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content})

    payload = {
        "model": GROQ_VISION_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 4096,
    }
    data = await _post_json(url, headers, payload, "Groq")
    return _extract_message_content(data, "Groq")


async def _ask_gemini(prompt: str, system_prompt: Optional[str] = None) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY не указан")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 4096},
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    data = await _post_json(url, {"Content-Type": "application/json"}, payload, "Gemini")
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini не вернул candidates: {data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    result = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    if not result.strip():
        raise RuntimeError(f"Gemini вернул пустой текст: {data}")
    return result


async def _ask_gemini_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_prompt: Optional[str] = None,
) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY не указан")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_VISION_MODEL}:generateContent?key={GEMINI_API_KEY}"
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    parts = []
    if prompt:
        parts.append({"text": prompt})
    parts.append({"inline_data": {"mime_type": mime_type, "data": image_b64}})

    payload: dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4096},
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    data = await _post_json(url, {"Content-Type": "application/json"}, payload, "Gemini")
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini не вернул candidates: {data}")

    out_parts = candidates[0].get("content", {}).get("parts", [])
    result = "\n".join(part.get("text", "") for part in out_parts if part.get("text"))
    if not result.strip():
        raise RuntimeError(f"Gemini вернул пустой текст по изображению: {data}")
    return result
