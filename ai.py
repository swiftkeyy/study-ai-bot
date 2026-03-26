import asyncio
import json
import logging
from typing import Optional

import aiohttp

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
)

logger = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=45, connect=10, sock_read=35)


async def ask_ai(prompt: str, system_prompt: Optional[str] = None) -> tuple[str, str]:
    """
    Возвращает: (text, provider_name)
    Логика:
    1) Gemini
    2) Groq
    3) OpenRouter
    """
    errors: list[str] = []

    providers = [
        ("Gemini", _ask_gemini),
        ("Groq", _ask_groq),
        ("OpenRouter", _ask_openrouter),
    ]

    for provider_name, provider_func in providers:
        try:
            logger.info("AI request started via %s", provider_name)
            text = await provider_func(prompt=prompt, system_prompt=system_prompt)
            if text and text.strip():
                logger.info("AI request success via %s", provider_name)
                return text.strip(), provider_name
            errors.append(f"{provider_name}: пустой ответ")
            logger.warning("AI provider %s returned empty response", provider_name)
        except Exception as e:
            logger.exception("AI provider %s failed", provider_name)
            errors.append(f"{provider_name}: {e}")

    error_text = " | ".join(errors) if errors else "Неизвестная ошибка"
    raise RuntimeError(f"Все AI-провайдеры недоступны. Детали: {error_text}")


async def _ask_gemini(prompt: str, system_prompt: Optional[str] = None) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY не указан")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    payload: dict = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
        },
    }

    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [
                {
                    "text": system_prompt,
                }
            ]
        }

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(url, json=payload) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {text[:500]}")

            data = json.loads(text)

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini не вернул candidates: {data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    result = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    if not result.strip():
        raise RuntimeError(f"Gemini вернул пустой текст: {data}")
    return result


async def _ask_groq(prompt: str, system_prompt: Optional[str] = None) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY не указан")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {text[:500]}")
            data = json.loads(text)

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"Groq не вернул choices: {data}")

    content = choices[0].get("message", {}).get("content", "")
    if not content.strip():
        raise RuntimeError(f"Groq вернул пустой текст: {data}")
    return content


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

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {text[:500]}")
            data = json.loads(text)

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"OpenRouter не вернул choices: {data}")

    content = choices[0].get("message", {}).get("content", "")
    if not content.strip():
        raise RuntimeError(f"OpenRouter вернул пустой текст: {data}")
    return content
