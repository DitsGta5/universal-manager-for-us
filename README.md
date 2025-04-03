# Telegram Bot Manager

Многофункциональный телеграм бот с возможностями поиска в Википедии, перевода текста, просмотра погоды и многим другим.

## Функции

- 📑 Жалобы/Предложения
- 🔎 Поиск в Википедии
- 🌤 Погода
- 🈹 Переводчик
- 💰 Курс валют
- 📅 Дата и время
- 🎲 Случайное число
- 📊 Статистика
- ⭐️ Избранное
- 📜 История запросов

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` и добавьте необходимые переменные окружения:
```
BOT_TOKEN=your_bot_token
ADMIN_ID=your_admin_id
CHANNEL_ID=your_channel_id
CHANNEL_URL=your_channel_url
```

## Запуск

```bash
python main.py
```

## Деплой

Бот готов к деплою на Heroku или другой сервис. Необходимые файлы:
- Procfile
- requirements.txt
- runtime.txt

## База данных

Бот использует SQLite для хранения:
- Истории запросов
- Избранных запросов
- Статистики пользователей

## Разработка

Бот написан на Python с использованием:
- aiogram 3.x
- python-dotenv
- wikipediaapi
- googletrans
- sqlite3