import os
import datetime
import random
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from dotenv import load_dotenv
import requests
import wikipediaapi
from googletrans import Translator
import logging
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Инициализация
bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())
translator = Translator()
wiki_wiki = wikipediaapi.Wikipedia(language='ru', user_agent='your_email@example.com')

# Главное меню
menu_kb = ReplyKeyboardMarkup(resize_keyboard=True)
menu_kb.row("📑 Жалобы/Предложения", "🔎 Википедия", "🌤 Погода", "🈹 Переводчик", "💰 Курс валют")
menu_kb.row("📅 Дата и время", "🎲 Случайное число", "📍 Местоположение")
menu_kb.row("📊 Моя статистика", "⭐️ Избранное", "📜 История", "🗑 Очистить историю")

# Меню статистики
stats_kb = ReplyKeyboardMarkup(resize_keyboard=True)
stats_kb.row("📊 Моя статистика", "📜 История")
stats_kb.row("⭐️ Избранное", "🗑 Очистить историю")
stats_kb.row("🔙 Назад в главное меню")

# Меню избранного
favorites_kb = ReplyKeyboardMarkup(resize_keyboard=True)
favorites_kb.row("➕ Добавить в избранное", "➖ Удалить из избранного")
favorites_kb.row("🔙 Назад в главное меню")

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    # Таблица истории запросов
    c.execute('''CREATE TABLE IF NOT EXISTS query_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  query_type TEXT,
                  query_text TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    # Таблица избранных запросов
    c.execute('''CREATE TABLE IF NOT EXISTS favorites
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  query_type TEXT,
                  query_text TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    # Таблица статистики пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS user_stats
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  total_queries INTEGER DEFAULT 0,
                  wiki_queries INTEGER DEFAULT 0,
                  translate_queries INTEGER DEFAULT 0,
                  last_active DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Функция для обновления статистики пользователя
def update_user_stats(user_id, username, query_type):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO user_stats 
                 (user_id, username, total_queries, wiki_queries, translate_queries, last_active)
                 VALUES (?, ?, COALESCE((SELECT total_queries + 1 FROM user_stats WHERE user_id = ?), 1),
                         COALESCE((SELECT wiki_queries + ? FROM user_stats WHERE user_id = ?), ?),
                         COALESCE((SELECT translate_queries + ? FROM user_stats WHERE user_id = ?), ?),
                         CURRENT_TIMESTAMP)''',
              (user_id, username, user_id, 1 if query_type == "wiki" else 0, user_id, 1 if query_type == "wiki" else 0,
               1 if query_type == "translate" else 0, user_id, 1 if query_type == "translate" else 0))
    conn.commit()
    conn.close()

# Функция для добавления в избранное
def add_to_favorites(user_id, query_type, query_text):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO favorites (user_id, query_type, query_text) VALUES (?, ?, ?)',
              (user_id, query_type, query_text))
    conn.commit()
    conn.close()

# Функция для получения избранных запросов
def get_favorites(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT query_type, query_text, timestamp FROM favorites WHERE user_id = ? ORDER BY timestamp DESC',
              (user_id,))
    favorites = c.fetchall()
    conn.close()
    return favorites

# Функция для удаления из избранного
def remove_from_favorites(user_id, query_text):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('DELETE FROM favorites WHERE user_id = ? AND query_text = ?', (user_id, query_text))
    conn.commit()
    conn.close()

# Функция для получения статистики пользователя
def get_user_stats(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
    stats = c.fetchone()
    conn.close()
    return stats

# Обновляем функцию save_query
def save_query(user_id, username, query_type, query_text):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO query_history (user_id, username, query_type, query_text) VALUES (?, ?, ?, ?)',
              (user_id, username, query_type, query_text))
    conn.commit()
    conn.close()
    update_user_stats(user_id, username, query_type)

# Функция для получения статистики
def get_statistics():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT query_type, COUNT(*) FROM query_history GROUP BY query_type')
    stats = c.fetchall()
    conn.close()
    return stats

# Функция для получения истории запросов пользователя
def get_user_history(user_id, limit=5):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT query_type, query_text, timestamp 
                 FROM query_history 
                 WHERE user_id = ? 
                 ORDER BY timestamp DESC 
                 LIMIT ?''', (user_id, limit))
    history = c.fetchall()
    conn.close()
    return history

# Функция для получения популярных запросов
def get_popular_queries(limit=5):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT query_text, COUNT(*) as count 
                 FROM query_history 
                 GROUP BY query_text 
                 ORDER BY count DESC 
                 LIMIT ?''', (limit,))
    popular = c.fetchall()
    conn.close()
    return popular

# Функция для очистки истории пользователя
def clear_user_history(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('DELETE FROM query_history WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# Команда /start
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.answer("👋 Привет! Я бот-справочник. Чем могу помочь?", reply_markup=menu_kb)

# Команда /help
@dp.message_handler(commands=['help'])
async def send_help(message: types.Message):
    help_text = ("📌 Доступные команды:\n"
                 "/start - Начать работу с ботом\n"
                 "/help - Получить справку по функциям бота\n"
                 "/history - Показать историю ваших запросов\n"
                 "/clear_history - Очистить историю запросов\n"
                 "/stats - Показать вашу статистику\n"
                 "/favorites - Показать избранные запросы\n"
                 "/add_favorite - Добавить запрос в избранное\n"
                 "/remove_favorite - Удалить запрос из избранного\n"
                 "📑 Жалобы/Предложения - Оставить сообщение администратору\n"
                 "🔎 Википедия - Поиск информации\n"
                 "🌤 Погода - Узнать прогноз\n"
                 "🈹 Переводчик - Перевести текст на английский\n"
                 "📅 Дата и время - Узнать текущее время\n"
                 "🎲 Случайное число - Сгенерировать случайное число\n"
                 "📍 Местоположение - Заглушка")
    await message.answer(help_text)

# Жалобы/Предложения
class ComplaintForm(StatesGroup):
    full_name = State()
    contact = State()
    complaint_text = State()
    confirm = State()

@dp.message_handler(lambda message: message.text == "📑 Жалобы/Предложения")
async def complaints_suggestions_start(message: types.Message, state: FSMContext):
    await message.answer("📝 Пожалуйста, введите ваше ФИО:")
    await ComplaintForm.full_name.set()

@dp.message_handler(state=ComplaintForm.full_name)
async def complaint_get_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("📞 Введите ваш контакт (телефон, email или Telegram):")
    await ComplaintForm.contact.set()

@dp.message_handler(state=ComplaintForm.contact)
async def complaint_get_contact(message: types.Message, state: FSMContext):
    await state.update_data(contact=message.text)
    await message.answer("✍️ Опишите вашу жалобу или предложение:")
    await ComplaintForm.complaint_text.set()

@dp.message_handler(state=ComplaintForm.complaint_text)
async def complaint_get_text(message: types.Message, state: FSMContext):
    await state.update_data(complaint_text=message.text)
    data = await state.get_data()
    confirmation_text = (f"🔹 ФИО: {data['full_name']}\n"
                         f"🔹 Контакт: {data['contact']}\n"
                         f"🔹 Текст: {data['complaint_text']}\n\n"
                         "✅ Подтвердите отправку или ❌ отмените.")
    confirm_kb = ReplyKeyboardMarkup(resize_keyboard=True)
    confirm_kb.row("✅ Подтвердить", "❌ Отмена")
    await message.answer(confirmation_text, reply_markup=confirm_kb)
    await ComplaintForm.confirm.set()

@dp.message_handler(lambda message: message.text in ["✅ Подтвердить", "❌ Отмена"], state=ComplaintForm.confirm)
async def complaint_confirm(message: types.Message, state: FSMContext):
    if message.text == "✅ Подтвердить":
        data = await state.get_data()
        admin_message = (f"📩 Новая жалоба/предложение\n\n"
                         f"👤 ФИО: {data['full_name']}\n"
                         f"📞 Контакт: {data['contact']}\n"
                         f"📝 Текст: {data['complaint_text']}")
        await bot.send_message(ADMIN_ID, admin_message)
        await message.answer("✅ Ваше сообщение успешно отправлено администратору.", reply_markup=menu_kb)
    else:
        await message.answer("❌ Отправка отменена.", reply_markup=menu_kb)
    await state.finish()

# Википедия
@dp.message_handler(lambda message: message.text == "🔎 Википедия")
async def wiki_search_start(message: types.Message, state: FSMContext):
    await message.answer("🔎 Введите запрос для поиска в Википедии:")
    await state.set_state("wiki_search")

@dp.message_handler(state="wiki_search")
async def wiki_search(message: types.Message, state: FSMContext):
    page = wiki_wiki.page(message.text)
    if page.exists():
        save_query(message.from_user.id, message.from_user.username, "wiki", message.text)
        await message.answer(f"📚 {page.summary[:1000]}...")
    else:
        await message.answer("❌ Страница не найдена.")
    await state.finish()

# Переводчик
@dp.message_handler(lambda message: message.text == "🈹 Переводчик")
async def translate_start(message: types.Message, state: FSMContext):
    await message.answer("🌍 Введите текст для перевода на английский:")
    await state.set_state("translate_text")

@dp.message_handler(state="translate_text")
async def translate_text(message: types.Message, state: FSMContext):
    text_to_translate = message.text.strip()
    translated = translator.translate(text_to_translate, dest='en')
    save_query(message.from_user.id, message.from_user.username, "translate", text_to_translate)
    await message.answer(f"🔠 Перевод: {translated.text}")
    await state.finish()

# Погода (заглушка)
@dp.message_handler(lambda message: message.text == "🌤 Погода")
async def weather_start(message: types.Message, state: FSMContext):
    await message.answer("🌍 Введите название города:")
    await state.set_state("weather_city")

@dp.message_handler(state="weather_city")
async def get_weather(message: types.Message, state: FSMContext):
    city = message.text
    weather_info = f"Погода в {city}: Ясно, 6°C"
    await message.answer(weather_info)
    await state.finish()

# Курс валют
@dp.message_handler(lambda message: message.text == "💰 Курс валют")
async def exchange_rate(message: types.Message):
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    response = requests.get(url).json()
    rates = response.get("rates", {})
    
    if rates:
        uzs_rate = rates.get('UZS', 1)
        currency_list = [
            f"💵 1 USD = {round(rates.get('USD', 1) * uzs_rate, 2)} UZS",
            f"💶 1 EUR = {round(rates.get('EUR', 1) * uzs_rate, 2)} UZS",
            f"💷 1 GBP = {round(rates.get('GBP', 1) * uzs_rate, 2)} UZS",
            f"💳 1 RUB = {round(rates.get('RUB', 1) * uzs_rate, 2)} UZS",
            f"💴 1 UAH = {round(rates.get('UAH', 1) * uzs_rate, 2)} UZS"
        ]
        
        await message.answer("💵 Курс валют относительно 1 UZS:\n" + "\n".join(currency_list))
    else:
        await message.answer("❌ Не удалось загрузить курс валют.")

# Отображение текущей даты и времени
@dp.message_handler(lambda message: message.text == "📅 Дата и время")
async def get_datetime(message: types.Message):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await message.answer(f"📅 Текущая дата и время: {now}")

# Генерация случайного числа
@dp.message_handler(lambda message: message.text == "🎲 Случайное число")
async def random_number(message: types.Message):
    number = random.randint(1, 100)
    await message.answer(f"🎲 Ваше случайное число: {number}")

# Заглушка для информации о местоположении
@dp.message_handler(lambda message: message.text == "📍 Местоположение")
async def location_placeholder(message: types.Message):
    await message.answer("📍 Извините, но определение местоположения недоступно в этом боте.")

# Команда /history - показать историю запросов пользователя
@dp.message_handler(commands=['history'])
async def show_history(message: types.Message):
    history = get_user_history(message.from_user.id)
    if history:
        history_text = "📜 Ваша история запросов:\n\n"
        for query_type, query_text, timestamp in history:
            history_text += f"🔹 {query_type}: {query_text}\n"
            history_text += f"⏰ {timestamp}\n\n"
        await message.answer(history_text)
    else:
        await message.answer("📝 У вас пока нет истории запросов.")

# Команда /popular - показать популярные запросы (только для администратора)
@dp.message_handler(commands=['popular'])
async def show_popular(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        popular = get_popular_queries()
        popular_text = "🔥 Популярные запросы:\n\n"
        for query_text, count in popular:
            popular_text += f"🔹 {query_text}: {count} раз\n"
        await message.answer(popular_text)
    else:
        await message.answer("⛔️ У вас нет доступа к этой команде.")

# Команда /clear_history - очистить историю запросов
@dp.message_handler(commands=['clear_history'])
async def clear_history(message: types.Message):
    clear_user_history(message.from_user.id)
    await message.answer("🗑 Ваша история запросов очищена.")

# Команда /stats - показать личную статистику
@dp.message_handler(commands=['stats'])
async def show_personal_stats(message: types.Message):
    stats = get_user_stats(message.from_user.id)
    if stats:
        stats_text = (f"📊 Ваша статистика:\n\n"
                     f"👤 Всего запросов: {stats[2]}\n"
                     f"📚 Запросов в Википедии: {stats[3]}\n"
                     f"🔄 Переводов: {stats[4]}\n"
                     f"⏰ Последняя активность: {stats[5]}")
        await message.answer(stats_text)
    else:
        await message.answer("📝 У вас пока нет статистики.")

# Команда /favorites - показать избранные запросы
@dp.message_handler(commands=['favorites'])
async def show_favorites(message: types.Message):
    favorites = get_favorites(message.from_user.id)
    if favorites:
        favorites_text = "⭐️ Ваши избранные запросы:\n\n"
        for query_type, query_text, timestamp in favorites:
            favorites_text += f"🔹 {query_type}: {query_text}\n"
            favorites_text += f"⏰ {timestamp}\n\n"
        await message.answer(favorites_text)
    else:
        await message.answer("📝 У вас пока нет избранных запросов.")

# Команда /add_favorite - добавить текущий запрос в избранное
@dp.message_handler(commands=['add_favorite'])
async def add_favorite(message: types.Message, state: FSMContext):
    await message.answer("💾 Введите запрос, который хотите добавить в избранное:")
    await state.set_state("add_favorite")

@dp.message_handler(state="add_favorite")
async def process_add_favorite(message: types.Message, state: FSMContext):
    query_text = message.text.strip()
    add_to_favorites(message.from_user.id, "general", query_text)
    await message.answer("✅ Запрос добавлен в избранное!")
    await state.finish()

# Команда /remove_favorite - удалить запрос из избранного
@dp.message_handler(commands=['remove_favorite'])
async def remove_favorite(message: types.Message, state: FSMContext):
    await message.answer("🗑 Введите запрос, который хотите удалить из избранного:")
    await state.set_state("remove_favorite")

@dp.message_handler(state="remove_favorite")
async def process_remove_favorite(message: types.Message, state: FSMContext):
    query_text = message.text.strip()
    remove_from_favorites(message.from_user.id, query_text)
    await message.answer("✅ Запрос удален из избранного!")
    await state.finish()

# Команда /admin_stats - показать статистику всех пользователей (только для администратора)
@dp.message_handler(commands=['admin_stats'])
async def show_admin_stats(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute('SELECT username, total_queries, wiki_queries, translate_queries FROM user_stats')
        all_stats = c.fetchall()
        conn.close()
        
        if all_stats:
            stats_text = "📊 Статистика всех пользователей:\n\n"
            for username, total, wiki, translate in all_stats:
                stats_text += f"👤 {username}:\n"
                stats_text += f"📚 Всего: {total}\n"
                stats_text += f"🔍 Википедия: {wiki}\n"
                stats_text += f"🔄 Переводы: {translate}\n\n"
            await message.answer(stats_text)
        else:
            await message.answer("📝 Пока нет статистики пользователей.")
    else:
        await message.answer("⛔️ У вас нет доступа к этой команде.")

# Обработчик кнопки "📊 Моя статистика"
@dp.message_handler(lambda message: message.text == "📊 Моя статистика")
async def show_stats_button(message: types.Message):
    stats = get_user_stats(message.from_user.id)
    if stats:
        stats_text = (f"📊 Ваша статистика:\n\n"
                     f"👤 Всего запросов: {stats[2]}\n"
                     f"📚 Запросов в Википедии: {stats[3]}\n"
                     f"🔄 Переводов: {stats[4]}\n"
                     f"⏰ Последняя активность: {stats[5]}")
        await message.answer(stats_text, reply_markup=stats_kb)
    else:
        await message.answer("📝 У вас пока нет статистики.", reply_markup=stats_kb)

# Обработчик кнопки "📜 История"
@dp.message_handler(lambda message: message.text == "📜 История")
async def show_history_button(message: types.Message):
    history = get_user_history(message.from_user.id)
    if history:
        history_text = "📜 Ваша история запросов:\n\n"
        for query_type, query_text, timestamp in history:
            history_text += f"🔹 {query_type}: {query_text}\n"
            history_text += f"⏰ {timestamp}\n\n"
        await message.answer(history_text, reply_markup=stats_kb)
    else:
        await message.answer("📝 У вас пока нет истории запросов.", reply_markup=stats_kb)

# Обработчик кнопки "⭐️ Избранное"
@dp.message_handler(lambda message: message.text == "⭐️ Избранное")
async def show_favorites_button(message: types.Message):
    favorites = get_favorites(message.from_user.id)
    if favorites:
        favorites_text = "⭐️ Ваши избранные запросы:\n\n"
        for query_type, query_text, timestamp in favorites:
            favorites_text += f"🔹 {query_type}: {query_text}\n"
            favorites_text += f"⏰ {timestamp}\n\n"
        await message.answer(favorites_text, reply_markup=favorites_kb)
    else:
        await message.answer("📝 У вас пока нет избранных запросов.", reply_markup=favorites_kb)

# Обработчик кнопки "🗑 Очистить историю"
@dp.message_handler(lambda message: message.text == "🗑 Очистить историю")
async def clear_history_button(message: types.Message):
    clear_user_history(message.from_user.id)
    await message.answer("🗑 Ваша история запросов очищена.", reply_markup=stats_kb)

# Обработчик кнопки "➕ Добавить в избранное"
@dp.message_handler(lambda message: message.text == "➕ Добавить в избранное")
async def add_favorite_button(message: types.Message, state: FSMContext):
    await message.answer("💾 Введите запрос, который хотите добавить в избранное:", reply_markup=favorites_kb)
    await state.set_state("add_favorite")

# Обработчик кнопки "➖ Удалить из избранного"
@dp.message_handler(lambda message: message.text == "➖ Удалить из избранного")
async def remove_favorite_button(message: types.Message, state: FSMContext):
    await message.answer("🗑 Введите запрос, который хотите удалить из избранного:", reply_markup=favorites_kb)
    await state.set_state("remove_favorite")

# Обработчик кнопки "🔙 Назад в главное меню"
@dp.message_handler(lambda message: message.text == "🔙 Назад в главное меню")
async def back_to_main_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=menu_kb)

# Добавим обработчик ошибок
@dp.errors_handler()
async def errors_handler(update, exception):
    try:
        raise exception
    except Exception as e:
        logger.exception(f"Произошла ошибка: {e}")
        return True

if __name__ == '__main__':
    try:
        logger.info("Бот запущен")
        init_db()  # Инициализируем базу данных при запуске
        from aiogram import executor
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        logger.info("Бот остановлен")
