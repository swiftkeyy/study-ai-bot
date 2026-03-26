import os
from dotenv import load_dotenv

load_dotenv()


def _to_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        return int(value)
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = _to_int("ADMIN_ID", 0)
DB_PATH = os.getenv("DB_PATH", "bot.db")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DEEPAI_API_KEY = os.getenv("DEEPAI_API_KEY", "")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

DEFAULT_FREE_LIMIT = _to_int("DEFAULT_FREE_LIMIT", 3)
DEFAULT_FREE_IMAGE_LIMIT = _to_int("DEFAULT_FREE_IMAGE_LIMIT", 1)
DEFAULT_STARS_PRICE_3 = _to_int("DEFAULT_STARS_PRICE_3", 59)
DEFAULT_STARS_PRICE_7 = _to_int("DEFAULT_STARS_PRICE_7", 99)
DEFAULT_STARS_PRICE_30 = _to_int("DEFAULT_STARS_PRICE_30", 199)
DEFAULT_RUB_PRICE_3 = _to_int("DEFAULT_RUB_PRICE_3", 99)
DEFAULT_RUB_PRICE_7 = _to_int("DEFAULT_RUB_PRICE_7", 199)
DEFAULT_RUB_PRICE_30 = _to_int("DEFAULT_RUB_PRICE_30", 499)

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me")
YOOKASSA_WEBHOOK_HOST = os.getenv("YOOKASSA_WEBHOOK_HOST", "0.0.0.0")
YOOKASSA_WEBHOOK_PORT = _to_int("YOOKASSA_WEBHOOK_PORT", 8080)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

DEFAULT_HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "Я умею:\n"
    "• решать задачи по тексту и по фото\n"
    "• писать тексты\n"
    "• создавать изображения\n"
    "• принимать промокоды\n"
    "• показывать новости и полезные материалы\n\n"
    "Нажми нужную кнопку в меню и следуй подсказкам."
)

DEFAULT_PAYWALL_TEXT = (
    "💎 <b>Бесплатный лимит закончился</b>\n\n"
    "Подключи доступ и продолжай пользоваться ботом без ограничений по подписке."
)

DEFAULT_SUPPORT_TEXT = (
    "💬 <b>Поддержка</b>\n\n"
    "Напиши свой вопрос одним сообщением. Администратор получит его и ответит тебе через бота."
)

DEFAULT_NEWS_CHANNEL_URL = os.getenv("DEFAULT_NEWS_CHANNEL_URL", "https://t.me/ai_helper_study")

DEFAULT_REQUIRED_SUBSCRIPTION_TEXT = (
    "📡 <b>Подписка обязательна</b>\n\n"
    "Чтобы пользоваться ботом, подпишись на канал и нажми «Проверить подписку»."
)

DEFAULT_MAINTENANCE_TEXT = (
    "🛠 <b>Технические работы</b>\n\n"
    "Сейчас бот временно обновляется. Попробуй ещё раз чуть позже."
)


def validate_config() -> list[str]:
    errors = []
    if not BOT_TOKEN:
        errors.append("Не указан BOT_TOKEN")
    if not ADMIN_ID:
        errors.append("Не указан ADMIN_ID")
    return errors
