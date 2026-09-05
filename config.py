import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# Project root (the folder this file lives in), so relative paths keep working
# when the bot is started from another current directory.
BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _to_int(name: str, default: int) -> int:
    value = _env(name, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def _to_bool(name: str, default: bool) -> bool:
    value = _env(name, "1" if default else "0").lower()
    return value in {"1", "true", "yes", "on", "y"}


def _abs_path(raw_path: str, fallback: Path) -> Path:
    path = Path(raw_path).expanduser() if raw_path else fallback
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


def _resolve_data_dir() -> Path:
    """Return a usable DATA_DIR.

    Containers usually mount /app/data, a local run gets ./data next to the
    sources. An explicitly configured path is never silently replaced: another
    folder would simply look like an empty database.
    """
    raw = _env("DATA_DIR")
    path = _abs_path(raw, BASE_DIR / "data")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if raw:
            raise RuntimeError(
                f"DATA_DIR={path} недоступен для записи ({exc}). "
                "Проверь права или укажи другую папку в переменной окружения DATA_DIR."
            ) from exc
        raise
    return path


def _resolve_file_path(raw_path: str, fallback: Path) -> Path:
    """Absolute file path with its parent directory created upfront."""
    path = _abs_path(raw_path, fallback)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Каталог {path.parent} для файла {path.name} недоступен для записи ({exc})") from exc
    return path


# Persistent storage for bot data (DB + logs).
DATA_DIR = _resolve_data_dir()


# Optional one-time migration from old paths in project root.
# This helps keep existing subscriptions/promocodes when moving to /app/data.
def _migrate_file(old_path: str | Path, new_path: str | Path) -> None:
    old_p = Path(old_path)
    new_p = Path(new_path)
    try:
        if not str(old_path).startswith("/") and not old_p.is_absolute():
            old_p = BASE_DIR / old_p
        if old_p.exists() and not new_p.exists():
            new_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_p, new_p)
    except Exception:
        # Never crash bot startup because of migration helper.
        pass


# Tokens / ids
BOT_TOKEN = _env("BOT_TOKEN")
ADMIN_ID = _to_int("ADMIN_ID", 0)

# Optional bot username for links/docs
BOT_USERNAME = _env("BOT_USERNAME").lstrip("@")

# SQLite / logs in persistent folder (relative paths are resolved from BASE_DIR)
DB_PATH = str(_resolve_file_path(_env("DB_PATH"), DATA_DIR / "bot.db"))
LOG_FILE = str(_resolve_file_path(_env("LOG_FILE"), DATA_DIR / "bot.log"))
LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()

# One-time migration from legacy root files
_migrate_file("bot.db", DB_PATH)
_migrate_file("bot.log", LOG_FILE)

# AI keys
DEEPAI_API_KEY = _env("DEEPAI_API_KEY")
MISTRAL_API_KEY = _env("MISTRAL_API_KEY")
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GROQ_API_KEY = _env("GROQ_API_KEY")
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")

# AI models
MISTRAL_API_BASE = _env("MISTRAL_API_BASE", "https://api.mistral.ai").rstrip("/")
MISTRAL_MODEL = _env("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_VISION_MODEL = _env("MISTRAL_VISION_MODEL", MISTRAL_MODEL)

OPENROUTER_MODEL = _env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OPENROUTER_VISION_MODEL = _env("OPENROUTER_VISION_MODEL", "meta-llama/llama-3.2-11b-vision-instruct")

GROQ_MODEL = _env("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = _env("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_VISION_MODEL = _env("GEMINI_VISION_MODEL", GEMINI_MODEL)

# Limits, prices and bonuses
DEFAULT_FREE_LIMIT = _to_int("DEFAULT_FREE_LIMIT", 3)
DEFAULT_FREE_IMAGE_LIMIT = _to_int("DEFAULT_FREE_IMAGE_LIMIT", 0)
DEFAULT_STARS_PRICE_3 = _to_int("DEFAULT_STARS_PRICE_3", 59)
DEFAULT_STARS_PRICE_7 = _to_int("DEFAULT_STARS_PRICE_7", 99)
DEFAULT_STARS_PRICE_30 = _to_int("DEFAULT_STARS_PRICE_30", 199)
DEFAULT_RUB_PRICE_3 = _to_int("DEFAULT_RUB_PRICE_3", 99)
DEFAULT_RUB_PRICE_7 = _to_int("DEFAULT_RUB_PRICE_7", 199)
DEFAULT_RUB_PRICE_30 = _to_int("DEFAULT_RUB_PRICE_30", 499)
DEFAULT_REFERRAL_BONUS = _to_int("DEFAULT_REFERRAL_BONUS", 5)

# Robokassa (also used by payments.py / robokassa.py, so env parsing lives here only)
ROBOKASSA_MERCHANT_LOGIN = _env("ROBOKASSA_MERCHANT_LOGIN")
ROBOKASSA_PASSWORD1 = _env("ROBOKASSA_PASSWORD1")
ROBOKASSA_PASSWORD2 = _env("ROBOKASSA_PASSWORD2")
ROBOKASSA_HASH_ALGO = _env("ROBOKASSA_HASH_ALGO", "md5").lower()
ROBOKASSA_IS_TEST = _to_bool("ROBOKASSA_IS_TEST", False)
ROBOKASSA_PAYMENT_URL = _env("ROBOKASSA_PAYMENT_URL", "https://auth.robokassa.ru/Merchant/Index.aspx").rstrip("/")
# Public HTTPS address of this bot's webhook server. Required for receipt (54-ФЗ)
# payments: the local POST form is served on /robokassa/pay. Leave empty to send
# the user straight to the Robokassa page.
ROBOKASSA_PUBLIC_BASE_URL = _env("ROBOKASSA_PUBLIC_BASE_URL").rstrip("/")
ROBOKASSA_WEBHOOK_HOST = _env("ROBOKASSA_WEBHOOK_HOST", "0.0.0.0")
ROBOKASSA_WEBHOOK_PORT = _to_int("ROBOKASSA_WEBHOOK_PORT", 8081)

ROBOKASSA_RECEIPT_ENABLED = _to_bool("ROBOKASSA_RECEIPT_ENABLED", True)
ROBOKASSA_RECEIPT_TAX = _env("ROBOKASSA_RECEIPT_TAX", "none") or "none"
ROBOKASSA_RECEIPT_PAYMENT_METHOD = _env("ROBOKASSA_RECEIPT_PAYMENT_METHOD", "full_payment") or "full_payment"
ROBOKASSA_RECEIPT_PAYMENT_OBJECT = _env("ROBOKASSA_RECEIPT_PAYMENT_OBJECT", "service") or "service"
ROBOKASSA_RECEIPT_SNO = _env("ROBOKASSA_RECEIPT_SNO")
ROBOKASSA_DEBUG_SIGNATURE = _to_bool("ROBOKASSA_DEBUG_SIGNATURE", False)


# Default texts/settings
DEFAULT_HELP_TEXT = (
    "❓ Помощь\n\n"
    "Я умею:\n"
    "• решать задачи\n"
    "• писать тексты\n"
    "• объяснять темы простыми словами\n"
    "• решать задачи по фото\n\n"
    "Как пользоваться:\n"
    "1) Нажми нужный режим\n"
    "2) Отправь свой запрос\n"
    "3) Получи ответ от AI\n\n"
    "После бесплатного лимита можно купить доступ в разделе «Купить доступ»."
)

DEFAULT_PAYWALL_TEXT = (
    "⛔ Бесплатный лимит закончился\n\n"
    "Ты уже использовал бесплатные запросы.\n"
    "Подключи доступ и продолжай пользоваться ботом без ограничений по подписке.\n\n"
    "Что получишь:\n"
    "• помощь с учебой 24/7\n"
    "• решение задач и написание текстов\n"
    "• приоритетный доступ к функциям бота"
)

DEFAULT_SUPPORT_TEXT = (
    "🛟 Поддержка\n\n"
    "Опиши проблему или вопрос одним сообщением.\n"
    "Администратор получит его и ответит тебе через бота."
)

DEFAULT_NEWS_CHANNEL_URL = _env("DEFAULT_NEWS_CHANNEL_URL", "https://t.me/studyai_rubot")

DEFAULT_REQUIRED_SUBSCRIPTION_TEXT = (
    "📢 Подписка обязательна\n\n"
    "Чтобы пользоваться ботом, подпишись на наш канал и нажми кнопку проверки."
)

DEFAULT_MAINTENANCE_TEXT = (
    "🛠 Технические работы\n\n"
    "Сейчас бот временно обновляется. Попробуй ещё раз чуть позже."
)


def validate_config() -> list[str]:
    errors: list[str] = []

    if not BOT_TOKEN:
        errors.append("Не указан BOT_TOKEN")
    if not ADMIN_ID:
        errors.append("Не указан ADMIN_ID")
    if not (DEEPAI_API_KEY or MISTRAL_API_KEY or OPENROUTER_API_KEY or GROQ_API_KEY or GEMINI_API_KEY):
        errors.append(
            "Не указан ни один AI API key (MISTRAL_API_KEY / OPENROUTER_API_KEY / GROQ_API_KEY / GEMINI_API_KEY)"
        )
    if BOT_USERNAME and (" " in BOT_USERNAME or "@" in BOT_USERNAME):
        errors.append("BOT_USERNAME не должен содержать пробелы и символ @")
    if ROBOKASSA_MERCHANT_LOGIN and not (ROBOKASSA_PASSWORD1 and ROBOKASSA_PASSWORD2):
        errors.append("Robokassa задана только частично: нужны ROBOKASSA_MERCHANT_LOGIN, ROBOKASSA_PASSWORD1 и ROBOKASSA_PASSWORD2")
    if ROBOKASSA_HASH_ALGO not in {"md5", "sha256"}:
        errors.append("ROBOKASSA_HASH_ALGO должен быть md5 или sha256")

    return errors
