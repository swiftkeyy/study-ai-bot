# Study AI Bot

Telegram-бот-помощник для учёбы на aiogram 3: решение задач, тексты, разбор ответов, шпаргалки по фото,
бесплатный лимит, подписка через Telegram Stars и Robokassa, админ-панель и промокоды.

## Быстрый запуск (локально)

1. Python 3.11+
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env` — минимум: `BOT_TOKEN`, `ADMIN_ID` и один AI-ключ
   (`GEMINI_API_KEY` / `GROQ_API_KEY` / `OPENROUTER_API_KEY` / `MISTRAL_API_KEY`)
5. `python bot.py`

Данные (`bot.db`, `bot.log`) по умолчанию лежат в `./data` рядом с исходниками.
Для контейнера это `/app/data` (переменная `DATA_DIR`).

## Docker

```bash
docker build -t study-ai-bot .
docker run -d --name study-ai-bot \
  -v study-data:/app/data \
  -p 8081:8081 \
  --env-file .env \
  study-ai-bot
```

- volume на `/app/data` обязателен, иначе база удалится при пересборке образа;
- бот работает внутри контейнера под непривилегированным пользователем, поэтому
  при bind-mount (`-v ./data:/app/data`) у каталога должны быть права на запись;
- порт `8081` нужен только для webhook'ов Robokassa.

## Переменные окружения

Полный список с комментариями — в `.env.example`. Коротко:

| Группа | Переменные |
| --- | --- |
| Telegram | `BOT_TOKEN`, `ADMIN_ID`, `BOT_USERNAME` |
| Хранилище | `DATA_DIR`, `DB_PATH`, `LOG_FILE`, `LOG_LEVEL` |
| AI | `*_API_KEY`, `*_MODEL`, `*_VISION_MODEL`, `MISTRAL_API_BASE` |
| Лимиты и цены | `DEFAULT_FREE_LIMIT`, `DEFAULT_REFERRAL_BONUS`, `DEFAULT_STARS_PRICE_*`, `DEFAULT_RUB_PRICE_*` |
| Robokassa | `ROBOKASSA_MERCHANT_LOGIN`, `ROBOKASSA_PASSWORD1/2`, `ROBOKASSA_HASH_ALGO`, `ROBOKASSA_IS_TEST`, `ROBOKASSA_PUBLIC_BASE_URL`, `ROBOKASSA_WEBHOOK_HOST/PORT`, `ROBOKASSA_RECEIPT_*` |

Бот не стартует без `BOT_TOKEN`, `ADMIN_ID` и хотя бы одного AI-ключа — в этом случае
в консоль выводится внятное сообщение, а не трейсбек.

## Robokassa

Внутренний HTTP-сервер поднимается вместе с ботом и слушает `ROBOKASSA_WEBHOOK_PORT`
(по умолчанию `8081`):

| Маршрут | Назначение |
| --- | --- |
| `GET /healthz` | проверка живости (возвращает 503, если БД недоступна) |
| `GET /robokassa/pay` | POST-форма для оплаты с фискальным чеком |
| `* /robokassa/result` | server-to-server уведомление (подпись `Password2`) |
| `GET /robokassa/success`, `GET /robokassa/fail` | страницы для покупателя |

Подписка активируется именно в `result` — он идемпотентен: повторная доставка
уведомления не продлевает подписку второй раз. Сумма сверяется с ценой платежа.

Для локальной разработки нужен публичный HTTPS-адрес, например ngrok:

```bash
ngrok http 8081
```

В кабинете Robokassa укажи (для `https://abc123.ngrok-free.app`):

- Result URL: `https://abc123.ngrok-free.app/robokassa/result`
- Success URL: `https://abc123.ngrok-free.app/robokassa/success`
- Fail URL: `https://abc123.ngrok-free.app/robokassa/fail`

Если включён чек (`ROBOKASSA_RECEIPT_ENABLED=1`), дополнительно задай
`ROBOKASSA_PUBLIC_BASE_URL=https://abc123.ngrok-free.app` — бот отдаст пользователю
ссылку на собственную страницу `/robokassa/pay`. Без `ROBOKASSA_PUBLIC_BASE_URL`
пользователь уходит на страницу Robokassa напрямую (чек летит в GET).

Отладка подписи: `ROBOKASSA_DEBUG_SIGNATURE=1` пишет в лог строку, по которой
считается подпись, с замаскированными паролями.

## Проверенные сценарии

- `/start` — приветствие и меню; `/help`, `/menu` — вернуть меню; `/admin` — админка
- `💎 Купить доступ` → Stars-инвойс или ссылка Robokassa
- `/start ref_<USER_ID>` — реферальный бонус (только для новых пользователей)
- промокоды, обязательная подписка на канал, техработы, бан — реагируют сразу

## Админ-панель

Кнопки: поиск пользователя, статистика, выдача/снятие подписки, лимиты, цены,
рассылки, промокоды, бонусы, выгрузка CSV, поддержка, бан/разбан, техработы,
админы, функции и кнопки меню, обязательная подписка.

- `⚙️ Функции` — `off support`, `on news`, `off solve_by_photo` и т.д.; ключи:
  `promocodes`, `support`, `news`, `materials`, `referrals`, `solve_by_photo`.
  Отключённая функция исчезает из пользовательской клавиатуры.
- `🧩 Кнопки меню` — свои кнопки у пользователей:
  `add Заголовок | text | текст`, `add Заголовок | url | https://…`,
  `show ID`, `on ID`, `off ID`, `sort ID N`, `del ID`.
- `🚫 Бан / разбан` — `list` показывает список заблокированных.

## Тесты

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Тесты покрывают миграции SQLite, лимиты и подписки, промокоды, рефералов,
разбиение длинных ответов AI, разбор админ-меню, подпись и вебхук Robokassa.
Они не требуют сети и реальных ключей.

## Частые проблемы

| Симптом | Причина и решение |
| --- | --- |
| `DATA_DIR=... недоступен для записи` | нет прав на каталог: поменяй `DATA_DIR` или права (в Docker — владелец volume) |
| `Не удалось запустить Robokassa webhook ... Address already in use` | порт `8081` занят: освободи или смени `ROBOKASSA_WEBHOOK_PORT` |
| `Не указан ни один AI API key` | в `.env` нет ни одного ключа из группы AI |
| Долгие ответы AI, «Все AI-провайдеры недоступны» | посмотри `provider` и текст ошибки в `data/bot.log` |
| Проверка подписки на канал всегда «не подписан» | бот не добавлен в канал администратором |
