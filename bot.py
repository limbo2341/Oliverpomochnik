import asyncio
import os
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BusinessConnection
from aiogram.filters import CommandStart
from groq import AsyncGroq

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ALLOWED_USERS = {8909320142, 7245932902, 8528807150}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncGroq(api_key=GROQ_API_KEY)
DB_PATH = "oliver.db"

SYSTEM_PROMPT = "Ти — Oliver, розумний AI-асистент в Telegram. Допомагай з будь-якими завданнями. Відповідай мовою користувача."

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                user_id INTEGER PRIMARY KEY,
                is_connected INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def set_connected(user_id: int, status: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO connections (user_id, is_connected)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET is_connected=?
        """, (user_id, int(status), int(status)))
        await db.commit()

async def is_connected(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_connected FROM connections WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])

def get_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 Як користуватись"), KeyboardButton(text="📋 Функції")],
            [KeyboardButton(text="ℹ️ Про Oliver"), KeyboardButton(text="💬 Підтримка")],
            [KeyboardButton(text="🔌 Як підключити")]
        ],
        resize_keyboard=True
    )

@dp.business_connection()
async def on_business_connect(bc: BusinessConnection):
    await set_connected(bc.user.id, bc.is_enabled)
    if bc.is_enabled:
        if bc.user.id in ALLOWED_USERS:
            await bot.send_message(bc.user.id,
                "✅ <b>Oliver підключений!</b>\n\n"
                "Пишіть <code>.Oliver [запит]</code> в будь-якому чаті!",
                parse_mode="HTML")
        else:
            await bot.send_message(bc.user.id,
                "⚠️ <b>Oliver підключений, але у вас немає доступу.</b>\n\n"
                "Зверніться до @katanaxu",
                parse_mode="HTML")
    else:
        await bot.send_message(bc.user.id,
            "❌ <b>Oliver відключений</b>\n\n"
            "Щоб підключити — Налаштування → Business → Автоматизація чатів.",
            parse_mode="HTML")

@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer(
            "╔═══════════════════╗\n"
            "║    🤖 <b>OLIVER AI</b>    ║\n"
            "╚═══════════════════╝\n\n"
            "❌ У вас немає доступу.\n"
            "📩 Для додавання: @katanaxu",
            parse_mode="HTML")
        return
    await message.answer(
        "╔═══════════════════╗\n"
        "║    🤖 <b>OLIVER AI</b>    ║\n"
        "╚═══════════════════╝\n\n"
        "👋 Привіт! Я твій особистий AI-асистент!\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Як користуватись:</b>\n"
        "<code>.Oliver [твій запит]</code>\n\n"
        "📌 <b>Приклади:</b>\n"
        "• <code>.Oliver дай відповідь на це</code>\n"
        "• <code>.Oliver переклади текст</code>\n"
        "• <code>.Oliver напиши вибачення</code>\n"
        "━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
        reply_markup=get_keyboard())

@dp.message(F.text == "🔌 Як підключити")
async def how_to_connect(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔌 <b>Як підключити Oliver:</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Відкрий <b>Налаштування</b> Telegram\n"
        "2️⃣ Перейди в <b>Telegram Business</b>\n"
        "3️⃣ Натисни <b>Автоматизація чатів</b>\n"
        "4️⃣ Вибери <b>@OliverpomoschikAI_Bot</b>\n"
        "5️⃣ Вибери чати до яких бот має доступ\n"
        "6️⃣ Натисни <b>Зберегти</b>\n\n"
        "✅ Oliver напише підтвердження після підключення!",
        parse_mode="HTML")

@dp.message(F.text == "🤖 Як користуватись")
async def how_to(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Як користуватись Oliver:</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "<code>.Oliver [твій запит]</code>\n\n"
        "📌 <b>Приклади:</b>\n"
        "• <code>.Oliver дай відповідь на це</code>\n"
        "• <code>.Oliver переклади на англійську: текст</code>\n"
        "• <code>.Oliver напиши привітання з ДР</code>\n\n"
        "💡 Можливості необмежені!",
        parse_mode="HTML")

@dp.message(F.text == "📋 Функції")
async def features(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━\n"
        "🛠 <b>Що вміє Oliver:</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 Відповіді на повідомлення\n"
        "🌐 Переклад на будь-яку мову\n"
        "✍️ Написання постів і листів\n"
        "🧠 Пояснення будь-яких тем\n"
        "🔢 Математика і логіка\n"
        "💡 Генерація ідей та жартів\n\n"
        "⚡ І багато іншого!",
        parse_mode="HTML")

@dp.message(F.text == "ℹ️ Про Oliver")
async def about(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>Oliver AI v1.0</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "⚙️ AI: Groq (Llama 3.3 70B)\n"
        "📡 Платформа: Telegram Business\n"
        "🔑 Тригер: <code>.Oliver</code>\n"
        "🔒 Доступ: тільки авторизовані",
        parse_mode="HTML")

@dp.message(F.text == "💬 Підтримка")
async def support(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━\n"
        "💬 <b>Підтримка Oliver:</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 Адміністратор: @katanaxu\n\n"
        "📩 Пишіть для:\n"
        "• Додавання нових користувачів\n"
        "• Вирішення проблем",
        parse_mode="HTML")

async def process_oliver(message: Message):
    prompt = message.text[len(".Oliver"):].strip()
    if not prompt:
        await bot.send_message(message.chat.id,
            "❓ Напиши що зробити після <code>.Oliver</code>",
            parse_mode="HTML",
            business_connection_id=message.business_connection_id)
        return
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        await bot.send_message(message.chat.id,
            response.choices[0].message.content,
            business_connection_id=message.business_connection_id)
    except Exception as e:
        await bot.send_message(message.chat.id,
            f"⚠️ Помилка: {str(e)}",
            business_connection_id=message.business_connection_id)

@dp.business_message(F.text.startswith(".Oliver"))
async def handle_oliver_business(message: Message):
    user_id = message.from_user.id
    if user_id not in ALLOWED_USERS:
        await bot.send_message(message.chat.id,
            "❌ У вас немає доступу до Oliver.\n"
            "Зверніться до @katanaxu",
            business_connection_id=message.business_connection_id)
        return
    connected = await is_connected(user_id)
    if not connected:
        await set_connected(user_id, True)
    await process_oliver(message)

@dp.message(F.text.startswith(".Oliver"))
async def handle_oliver(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("❌ Немає доступу.\nПишіть @katanaxu")
        return
    await process_oliver(message)

async def main():
    await init_db()
    await dp.start_polling(bot, allowed_updates=["message", "business_message", "business_connection"])

if __name__ == "__main__":
    asyncio.run(main())
