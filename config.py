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

# SQLite
DB_PATH = os.getenv("DB_PATH", "bot.db")

# AI keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# AI models
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

# Limits and prices
DEFAULT_FREE_LIMIT = _to_int("DEFAULT_FREE_LIMIT", 3)
# Legacy compatibility: DB schema still stores image counters, but image generation is disabled in MVP.
DEFAULT_FREE_IMAGE_LIMIT = _to_int("DEFAULT_FREE_IMAGE_LIMIT", 0)
DEFAULT_STARS_PRICE_3 = _to_int("DEFAULT_STARS_PRICE_3", 59)
DEFAULT_STARS_PRICE_7 = _to_int("DEFAULT_STARS_PRICE_7", 99)
DEFAULT_STARS_PRICE_30 = _to_int("DEFAULT_STARS_PRICE_30", 199)
DEFAULT_RUB_PRICE_3 = _to_int("DEFAULT_RUB_PRICE_3", 99)
DEFAULT_RUB_PRICE_7 = _to_int("DEFAULT_RUB_PRICE_7", 199)
DEFAULT_RUB_PRICE_30 = _to_int("DEFAULT_RUB_PRICE_30", 499)

# Crypto Pay / CryptoBot
CRYPTO_PAY_API_TOKEN = os.getenv("CRYPTO_PAY_API_TOKEN", "")
CRYPTO_PAY_API_BASE = os.getenv("CRYPTO_PAY_API_BASE", "https://pay.crypt.bot/api")
CRYPTO_PAY_RETURN_URL = os.getenv("CRYPTO_PAY_RETURN_URL", "https://t.me")
CRYPTO_PAY_POLL_INTERVAL = _to_int("CRYPTO_PAY_POLL_INTERVAL", 20)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

# Default texts/settings
DEFAULT_HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "Я умею:\n"
    "• решать задачи\n"
    "• писать тексты\n"
    "• объяснять темы простыми словами\n"
    "• решать задачи по фото\n"
    "Как пользоваться:\n"
    "1) Нажми нужный режим\n"
    "2) Отправь свой запрос\n"
    "3) Получи ответ от AI\n\n"
    "После бесплатного лимита можно купить доступ в разделе <b>💎 Купить доступ</b>."
)

DEFAULT_PAYWALL_TEXT = (
    "💎 <b>Бесплатный лимит закончился</b>\n\n"
    "Ты уже использовал бесплатные запросы.\n"
    "Подключи доступ и продолжай пользоваться ботом без ограничений по подписке.\n\n"
    "Что получишь:\n"
    "• ответы без ожидания ручной проверки\n"
    "• помощь с учебой 24/7\n"
    "• решение задач и написание текстов в одном боте"
)

DEFAULT_SUPPORT_TEXT = (
    "💬 <b>Поддержка</b>\n\n"
    "Опиши проблему или вопрос одним сообщением. "
    "Администратор получит его и ответит тебе через бота."
)

DEFAULT_NEWS_CHANNEL_URL = os.getenv("DEFAULT_NEWS_CHANNEL_URL", "https://t.me/studyai_rubot")

DEFAULT_REQUIRED_SUBSCRIPTION_TEXT = (
    "📡 <b>Подписка обязательна</b>\n\n"
    "Чтобы пользоваться ботом, подпишись на наш канал и нажми кнопку проверки."
)

DEFAULT_MAINTENANCE_TEXT = (
    "🛠 <b>Технические работы</b>\n\n"
    "Сейчас бот временно обновляется. Попробуй ещё раз чуть позже."
)


def crypto_pay_enabled() -> bool:
    return bool(CRYPTO_PAY_API_TOKEN.strip())


def validate_config() -> list[str]:
    errors = []
    if not BOT_TOKEN:
        errors.append("Не указан BOT_TOKEN")
    if not ADMIN_ID:
        errors.append("Не указан ADMIN_ID")
    return errors
