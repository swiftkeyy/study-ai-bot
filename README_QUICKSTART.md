# Study AI Bot MVP

## Быстрый запуск
1. Установи Python 3.11+
2. Открой папку проекта
3. Создай `.env` по примеру `.env.example`
4. Установи зависимости:
   `pip install -r requirements.txt`
5. Запусти бота:
   `python bot.py`

## Что важно
- Бот работает через long polling
- Robokassa webhook поднимается вместе с ботом
- Внутренний HTTP-сервер для Robokassa слушает порт `8081`
- Для webhook нужен публичный HTTPS URL

## ngrok для webhook
1. Скачай ngrok
2. Запусти:
   `ngrok http 8081`
3. Возьми HTTPS URL вида:
   `https://abc123.ngrok-free.app`
4. В кабинете Robokassa укажи:
   - **Result URL**: `https://abc123.ngrok-free.app/robokassa/result`
   - **Success URL**: `https://abc123.ngrok-free.app/robokassa/success`
   - **Fail URL**: `https://abc123.ngrok-free.app/robokassa/fail`

## Переменные окружения
Минимально нужны:
- `BOT_TOKEN`
- `ADMIN_ID`
- хотя бы один AI-ключ:
  - `GEMINI_API_KEY`
  - `GROQ_API_KEY`
  - `OPENROUTER_API_KEY`

Для Robokassa:
- `ROBOKASSA_MERCHANT_LOGIN`
- `ROBOKASSA_PASSWORD1`
- `ROBOKASSA_PASSWORD2`
- `ROBOKASSA_HASH_ALGO` (обычно `md5`)
- `ROBOKASSA_IS_TEST` (`1` для теста, `0` для боевого режима)
- `ROBOKASSA_WEBHOOK_HOST` (обычно `0.0.0.0`)
- `ROBOKASSA_WEBHOOK_PORT` (обычно `8081`)

## Проверка
- `/start` — старт бота
- `/admin` — админка (только для `ADMIN_ID`)
- `💎 Купить доступ` — экран покупки
- тестовая оплата через Robokassa должна приходить на `/robokassa/result`

## Очистка репозитория
После добавления нормального `.gitignore` удали уже закоммиченные артефакты:
- `bot.db`
- `bot.log`
- `test_bot.db`

Команды:
```bash
git rm --cached bot.db bot.log test_bot.db
rm -f bot.db bot.log test_bot.db
git add .gitignore README_QUICKSTART.md config.py
git commit -m "chore: cleanup config, gitignore and docs"
```
