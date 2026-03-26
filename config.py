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
DEEPAI_API_KEY = os.getenv("DEEPAI_API_KEY", "")
DEFAULT_FREE_IMAGE_LIMIT = int(os.getenv("DEFAULT_FREE_IMAGE_LIMIT", "1"))

# AI models (можно менять без изменения кода)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

# Telegram Stars prices (по умолчанию; фактически бот берёт их из БД settings)
DEFAULT_FREE_LIMIT = _to_int("DEFAULT_FREE_LIMIT", 3)
DEFAULT_STARS_PRICE_3 = _to_int("DEFAULT_STARS_PRICE_3", 59)
DEFAULT_STARS_PRICE_7 = _to_int("DEFAULT_STARS_PRICE_7", 99)
DEFAULT_STARS_PRICE_30 = _to_int("DEFAULT_STARS_PRICE_30", 199)

# YooKassa prices in RUB
DEFAULT_RUB_PRICE_3 = _to_int("DEFAULT_RUB_PRICE_3", 99)
DEFAULT_RUB_PRICE_7 = _to_int("DEFAULT_RUB_PRICE_7", 199)
DEFAULT_RUB_PRICE_30 = _to_int("DEFAULT_RUB_PRICE_30", 499)

# YooKassa
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me")
YOOKASSA_WEBHOOK_HOST = os.getenv("YOOKASSA_WEBHOOK_HOST", "0.0.0.0")
YOOKASSA_WEBHOOK_PORT = _to_int("YOOKASSA_WEBHOOK_PORT", 8080)

# Логи
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

# Тексты по умолчанию
DEFAULT_HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "Я умею:\n"
    "• решать задачи\n"
    "• писать тексты\n"
    "• объяснять темы простыми словами\n\n"
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


def validate_config() -> list[str]:
    errors = []
    if not BOT_TOKEN:
        errors.append("Не указан BOT_TOKEN")
    if not ADMIN_ID:
        errors.append("Не указан ADMIN_ID")
    return errors
