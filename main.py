import os
import datetime
import random
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
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
CHANNEL_ID = os.getenv("CHANNEL_ID")  # ID канала для обязательной подписки
CHANNEL_URL = os.getenv("CHANNEL_URL")  # URL для вступления в канал

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
translator = Translator()
wiki_wiki = wikipediaapi.Wikipedia(language='ru', user_agent='your_email@example.com')

# Клавиатуры
menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📑 Жалобы/Предложения"), KeyboardButton(text="🔎 Википедия")],
        [KeyboardButton(text="🌤 Погода"), KeyboardButton(text="🈹 Переводчик"), KeyboardButton(text="💰 Курс валют")],
        [KeyboardButton(text="📅 Дата и время"), KeyboardButton(text="🎲 Случайное число"), KeyboardButton(text="📍 Местоположение")],
        [KeyboardButton(text="📊 Моя статистика"), KeyboardButton(text="⭐️ Избранное"), KeyboardButton(text="📜 История"), KeyboardButton(text="🗑 Очистить историю")]
    ],
    resize_keyboard=True
)

stats_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Моя статистика"), KeyboardButton(text="📜 История")],
        [KeyboardButton(text="⭐️ Избранное"), KeyboardButton(text="🗑 Очистить историю")],
        [KeyboardButton(text="🔙 Назад в главное меню")]
    ],
    resize_keyboard=True
)

favorites_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить в избранное"), KeyboardButton(text="➖ Удалить из избранного")],
        [KeyboardButton(text="🔙 Назад в главное меню")]
    ],
    resize_keyboard=True
)

confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Подтвердить"), KeyboardButton(text="❌ Отмена")]
    ],
    resize_keyboard=True
)

# Создаем клавиатуру для подписки на канал
subscribe_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")]
    ]
)

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

# Функция для сохранения запроса в базу данных
def save_query(user_id, username, query_type, query_text):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO query_history (user_id, username, query_type, query_text) VALUES (?, ?, ?, ?)',
              (user_id, username, query_type, query_text))
    conn.commit()
    conn.close()
    update_user_stats(user_id, username, query_type)

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

# Функция проверки подписки на канал
async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке подписки: {e}")
        return False

# Функция-middleware для проверки подписки
async def subscription_filter(handler, event, data):
    user = data["event_from_user"]
    if isinstance(event, types.Message) or isinstance(event, types.CallbackQuery):
        # Проверяем, является ли пользователь администратором
        if user.id == ADMIN_ID:
            return await handler(event, data)
        
        # Проверяем подписку
        is_subscribed = await check_subscription(user.id)
        if not is_subscribed:
            if isinstance(event, types.CallbackQuery) and event.data == "check_subscription":
                # Если это проверка подписки через callback
                await event.answer("Вы еще не подписались на канал!", show_alert=True)
                return
            
            # Отправляем сообщение с предложением подписаться
            if isinstance(event, types.Message):
                await event.answer("Для использования бота необходимо подписаться на наш канал!", reply_markup=subscribe_kb)
            elif isinstance(event, types.CallbackQuery):
                await event.message.answer("Для использования бота необходимо подписаться на наш канал!", reply_markup=subscribe_kb)
            return
    
    return await handler(event, data)

# Регистрация middleware
dp.message.middleware(subscription_filter)
dp.callback_query.middleware(subscription_filter)

# Классы состояний
class ComplaintForm(StatesGroup):
    full_name = State()
    contact = State()
    complaint_text = State()
    confirm = State()

class WikiSearch(StatesGroup):
    searching = State()

class TranslateText(StatesGroup):
    translating = State()

class WeatherCity(StatesGroup):
    waiting_city = State()

class FavoriteManage(StatesGroup):
    adding = State()
    removing = State()

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я бот-справочник. Чем могу помочь?", reply_markup=menu_kb, parse_mode="HTML")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
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
    await message.answer(help_text, parse_mode="HTML")

# Обработчик callback-запросов
@dp.callback_query(F.data == "check_subscription")
async def callback_check_subscription(callback: types.CallbackQuery):
    is_subscribed = await check_subscription(callback.from_user.id)
    if is_subscribed:
        await callback.message.delete()
        await callback.message.answer("✅ Спасибо за подписку! Теперь вы можете использовать все функции бота.", reply_markup=menu_kb)
    else:
        await callback.answer("Вы ещё не подписались на канал!", show_alert=True)

# Жалобы/Предложения
@dp.message(F.text == "📑 Жалобы/Предложения")
async def process_complaint_start(message: types.Message, state: FSMContext):
    await state.set_state(ComplaintForm.full_name)
    await message.answer("📝 Пожалуйста, введите ваше ФИО:")

@dp.message(ComplaintForm.full_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(ComplaintForm.contact)
    await message.answer("📞 Введите ваш контакт (телефон, email или Telegram):")

@dp.message(ComplaintForm.contact)
async def process_contact(message: types.Message, state: FSMContext):
    await state.update_data(contact=message.text)
    await state.set_state(ComplaintForm.complaint_text)
    await message.answer("✍️ Опишите вашу жалобу или предложение:")

@dp.message(ComplaintForm.complaint_text)
async def process_complaint_text(message: types.Message, state: FSMContext):
    await state.update_data(complaint_text=message.text)
    data = await state.get_data()
    confirmation_text = (f"🔹 ФИО: {data['full_name']}\n"
                         f"🔹 Контакт: {data['contact']}\n"
                         f"🔹 Текст: {data['complaint_text']}\n\n"
                         "✅ Подтвердите отправку или ❌ отмените.")
    await state.set_state(ComplaintForm.confirm)
    await message.answer(confirmation_text, reply_markup=confirm_kb)

@dp.message(ComplaintForm.confirm, F.text.in_(["✅ Подтвердить", "❌ Отмена"]))
async def process_confirmation(message: types.Message, state: FSMContext):
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
    await state.clear()

# Википедия
@dp.message(F.text == "🔎 Википедия")
async def process_wiki_start(message: types.Message, state: FSMContext):
    await state.set_state(WikiSearch.searching)
    await message.answer("🔎 Введите запрос для поиска в Википедии:", parse_mode="HTML")

@dp.message(WikiSearch.searching)
async def process_wiki_search(message: types.Message, state: FSMContext):
    page = wiki_wiki.page(message.text)
    if page.exists():
        save_query(message.from_user.id, message.from_user.username or str(message.from_user.id), "wiki", message.text)
        await message.answer(f"📚 {page.summary[:1000]}...", parse_mode="HTML")
    else:
        await message.answer("❌ Страница не найдена.", parse_mode="HTML")
    await state.clear()

# Переводчик
@dp.message(F.text == "🈹 Переводчик")
async def process_translate_start(message: types.Message, state: FSMContext):
    await state.set_state(TranslateText.translating)
    await message.answer("🌍 Введите текст для перевода на английский:", parse_mode="HTML")

@dp.message(TranslateText.translating)
async def process_translate(message: types.Message, state: FSMContext):
    text_to_translate = message.text.strip()
    translated = translator.translate(text_to_translate, dest='en')
    save_query(message.from_user.id, message.from_user.username or str(message.from_user.id), "translate", text_to_translate)
    await message.answer(f"🔠 Перевод: {translated.text}", parse_mode="HTML")
    await state.clear()

# Погода
@dp.message(F.text == "🌤 Погода")
async def process_weather_start(message: types.Message, state: FSMContext):
    await state.set_state(WeatherCity.waiting_city)
    await message.answer("🌍 Введите название города:", parse_mode="HTML")

@dp.message(WeatherCity.waiting_city)
async def process_weather(message: types.Message, state: FSMContext):
    city = message.text
    weather_info = f"Погода в {city}: Ясно, 6°C"
    await message.answer(weather_info, parse_mode="HTML")
    await state.clear()

# Курс валют
@dp.message(F.text == "💰 Курс валют")
async def process_exchange_rate(message: types.Message):
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

# Дата и время
@dp.message(F.text == "📅 Дата и время")
async def process_datetime(message: types.Message):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await message.answer(f"📅 Текущая дата и время: {now}")

# Случайное число
@dp.message(F.text == "🎲 Случайное число")
async def process_random_number(message: types.Message):
    number = random.randint(1, 100)
    await message.answer(f"🎲 Ваше случайное число: {number}")

# Местоположение
@dp.message(F.text == "📍 Местоположение")
async def process_location(message: types.Message):
    await message.answer("📍 Извините, но определение местоположения недоступно в этом боте.")

# Моя статистика
@dp.message(F.text == "📊 Моя статистика")
async def process_stats(message: types.Message):
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

# История
@dp.message(F.text == "📜 История")
async def process_history(message: types.Message):
    history = get_user_history(message.from_user.id)
    if history:
        history_text = "📜 Ваша история запросов:\n\n"
        for query_type, query_text, timestamp in history:
            history_text += f"🔹 {query_type}: {query_text}\n"
            history_text += f"⏰ {timestamp}\n\n"
        await message.answer(history_text, reply_markup=stats_kb)
    else:
        await message.answer("📝 У вас пока нет истории запросов.", reply_markup=stats_kb)

# Избранное
@dp.message(F.text == "⭐️ Избранное")
async def process_favorites(message: types.Message):
    favorites = get_favorites(message.from_user.id)
    if favorites:
        favorites_text = "⭐️ Ваши избранные запросы:\n\n"
        for query_type, query_text, timestamp in favorites:
            favorites_text += f"🔹 {query_type}: {query_text}\n"
            favorites_text += f"⏰ {timestamp}\n\n"
        await message.answer(favorites_text, reply_markup=favorites_kb)
    else:
        await message.answer("📝 У вас пока нет избранных запросов.", reply_markup=favorites_kb)

# Очистить историю
@dp.message(F.text == "🗑 Очистить историю")
async def process_clear_history(message: types.Message):
    clear_user_history(message.from_user.id)
    await message.answer("🗑 Ваша история запросов очищена.", reply_markup=stats_kb)

# Добавить в избранное
@dp.message(F.text == "➕ Добавить в избранное")
async def process_add_favorite_start(message: types.Message, state: FSMContext):
    await state.set_state(FavoriteManage.adding)
    await message.answer("💾 Введите запрос, который хотите добавить в избранное:", reply_markup=favorites_kb, parse_mode="HTML")

@dp.message(FavoriteManage.adding)
async def process_add_favorite(message: types.Message, state: FSMContext):
    query_text = message.text.strip()
    add_to_favorites(message.from_user.id, "general", query_text)
    await message.answer("✅ Запрос добавлен в избранное!", reply_markup=favorites_kb, parse_mode="HTML")
    await state.clear()

# Удалить из избранного
@dp.message(F.text == "➖ Удалить из избранного")
async def process_remove_favorite_start(message: types.Message, state: FSMContext):
    await state.set_state(FavoriteManage.removing)
    await message.answer("🗑 Введите запрос, который хотите удалить из избранного:", reply_markup=favorites_kb, parse_mode="HTML")

@dp.message(FavoriteManage.removing)
async def process_remove_favorite(message: types.Message, state: FSMContext):
    query_text = message.text.strip()
    remove_from_favorites(message.from_user.id, query_text)
    await message.answer("✅ Запрос удален из избранного!", reply_markup=favorites_kb, parse_mode="HTML")
    await state.clear()

# Назад в главное меню
@dp.message(F.text == "🔙 Назад в главное меню")
async def process_back_to_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=menu_kb)

# Команды администратора
@dp.message(Command("admin_stats"))
async def cmd_admin_stats(message: types.Message):
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

@dp.message(Command("popular"))
async def cmd_popular(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        popular = get_popular_queries()
        if popular:
            popular_text = "🔥 Популярные запросы:\n\n"
            for query_text, count in popular:
                popular_text += f"🔹 {query_text}: {count} раз\n"
            await message.answer(popular_text)
        else:
            await message.answer("📝 Пока нет популярных запросов.")
    else:
        await message.answer("⛔️ У вас нет доступа к этой команде.")

# Обработчик для всех остальных сообщений
@dp.message()
async def process_other_messages(message: types.Message):
    await message.answer("Не понимаю эту команду. Используйте клавиатуру или /help для просмотра доступных команд.")

# Запуск бота
async def main():
    # Инициализация базы данных
    init_db()
    logger.info("Бот запущен")
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
