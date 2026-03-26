# Study AI Bot MVP

## Быстрый запуск
1. Установи Python 3.11+
2. Открой папку проекта
3. Создай `.env` по примеру `.env.example`
4. Установи зависимости:
   pip install -r requirements.txt
5. Запусти бота:
   python bot.py

## Что важно
- Бот работает через long polling
- YooKassa webhook поднимается внутри `bot.py` на порту 8080
- Для webhook нужен публичный HTTPS URL (например, через ngrok)

## ngrok для webhook
1. Скачай ngrok
2. Запусти:
   ngrok http 8080
3. Возьми HTTPS URL вида:
   https://abc123.ngrok-free.app
4. В кабинете ЮKassa укажи webhook:
   https://abc123.ngrok-free.app/yookassa/webhook

## Проверка
- /start — старт бота
- /admin — админка (только для ADMIN_ID)
