import json
import logging

import aiohttp

from config import DEEPAI_API_KEY

logger = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=90, connect=15, sock_read=75)


async def generate_image(prompt: str) -> tuple[str, str]:
    if not DEEPAI_API_KEY:
        raise RuntimeError("DEEPAI_API_KEY не указан")

    url = "https://api.deepai.org/api/text2img"
    headers = {"api-key": DEEPAI_API_KEY}
    data = aiohttp.FormData()
    data.add_field("text", prompt)
    data.add_field("width", "1024")
    data.add_field("height", "1024")
    data.add_field("image_generator_version", "standard")

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(url, headers=headers, data=data) as response:
            text = await response.text()
            logger.info("DeepAI response status=%s body=%s", response.status, text[:1000])
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {text[:500]}")
            payload = json.loads(text)

    image_url = payload.get("output_url") or payload.get("output")
    if not image_url:
        raise RuntimeError(f"DeepAI не вернул output_url: {payload}")
    return image_url, "DeepAI"
