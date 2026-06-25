import asyncio
import os
import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BusinessConnection
from aiogram.filters import CommandStart
from groq import AsyncGroq

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USERS = {8909320142, 7245932902, 8528807150}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncGroq(api_key=GROQ_API_KEY)
db_pool = None

SYSTEM_PROMPT = "Ти — Oliver, розумний AI-асистент в Telegram. Допомагай з будь-якими завданнями. Відповідай мовою користувача."

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS connections CASCADE")
        await conn.execute("DROP TABLE IF EXISTS chat_history CASCADE")
        await conn.execute("""
            CREATE TABLE connections (
                user_id BIGINT PRIMARY KEY,
                bc_id TEXT,
                is_enabled BOOLEAN DEFAULT FALSE
            )
        """)
        await conn.execute("""
            CREATE TABLE chat_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                chat_id BIGINT,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

async def save_connection(bc: BusinessConnection):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO connections (user_id, bc_id, is_enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET bc_id=$2, is_enabled=$3
        """, bc.user.id, bc.id, bc.is_enabled)

async def add_history(user_id: int, chat_id: int, role: str, content: str):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO chat_history (user_id, chat_id, role, content)
            VALUES ($1, $2, $3, $4)
        """, user_id, chat_id, role, content)
        # Зберігаємо тільки останні 20 повідомлень на чат
        await conn.execute("""
            DELETE FROM chat_history WHERE id IN (
                SELECT id FROM chat_history
                WHERE user_id=$1 AND chat_id=$2
                ORDER BY created_at DESC
                OFFSET 20
            )
        """, user_id, chat_id)

async def get_history(user_id: int, chat_id: int) -> list:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content FROM chat_history
            WHERE user_id=$1 AND chat_id=$2
            ORDER BY created_at ASC
        """, user_id, chat_id)
        return [{"role": r["role"], "content": r["content"]} for r in rows]

def get_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 Як користуватись"), KeyboardButton(text="📋 Функції")],
            [KeyboardButton(text="🖥️ Про Oliver"), KeyboardButton(text="💬 Підтримка")],
            [KeyboardButton(text="🔗 Як підключити")]
        ],
        resize_keyboard=True
    )

@dp.business_connection()
async def on_business_connect(bc: BusinessConnection):
    await save_connection(bc)
    # Показуємо всі поля об'єкта для дебагу
    if bc.user.id in ALLOWED_USERS:
        r = bc.rights
        debug = f"rights type: {type(r)}\nrights value: {r}"
        await bot.send_message(bc.user.id, f"🔍 DEBUG:\n{debug}")

    if bc.is_enabled:
        if bc.user.id in ALLOWED_USERS:
            await bot.send_message(bc.user.id,
                "✅ <b>Oliver підключений!</b>\n\nПишіть <code>.Oliver [запит]</code> в будь-якому чаті!",
                parse_mode="HTML")
        else:
            await bot.send_message(bc.user.id,
                "⚠️ Підключений, але немає доступу. Зверніться до @katanaxu",
                parse_mode="HTML")
    else:
        await bot.send_message(bc.user.id, "❌ <b>Oliver відключений</b>", parse_mode="HTML")

async def process_oliver(message: Message, business_connection_id: str = None):
    prompt = message.text[len(".Oliver"):].strip()
    user_id = message.from_user.id
    chat_id = message.chat.id

    async def reply(text, parse_mode=None):
        await bot.send_message(chat_id, text,
            parse_mode=parse_mode,
            business_connection_id=business_connection_id)

    # Отримуємо права напряму через API
    rights = None
    if business_connection_id:
        try:
            bc_info = await bot.get_business_connection(business_connection_id)
            rights = dict(bc_info.rights) if bc_info.rights else {}
        except Exception as e:
            pass

    p = prompt.lower()

    # Зміна імені
    if p.startswith("змін ім'я на ") or p.startswith("змін имя на ") or p.startswith("змін name на "):
        can = rights.get('can_edit_name', False) if rights else False
        if not can:
            await reply("❌ Немає дозволу змінювати ім'я.\nНалаштування → Business → Автоматизація → Профіль → Змінювати ім'я")
            return
        new_name = prompt.split(" на ", 1)[1].strip()
        parts = new_name.split(" ", 1)
        try:
            await bot.set_business_account_name(
                business_connection_id=business_connection_id,
                first_name=parts[0],
                last_name=parts[1] if len(parts) > 1 else None)
            await reply(f"✅ Ім'я змінено на: {new_name}")
        except Exception as e:
            await reply(f"⚠️ Помилка: {e}")
        return

    # Зміна біо
    if p.startswith("змін біо на ") or p.startswith("змін bio на "):
        can = rights.get('can_edit_bio', False) if rights else False
        if not can:
            await reply("❌ Немає дозволу змінювати біо.")
            return
        new_bio = prompt.split(" на ", 1)[1].strip()
        try:
            await bot.set_business_account_bio(
                business_connection_id=business_connection_id,
                bio=new_bio)
            await reply(f"✅ Біо змінено на: {new_bio}")
        except Exception as e:
            await reply(f"⚠️ Помилка: {e}")
        return

    # Зміна username
    if p.startswith("змін юзернейм на ") or p.startswith("змін username на "):
        can = rights.get('can_edit_username', False) if rights else False
        if not can:
            await reply("❌ Немає дозволу змінювати username.")
            return
        new_username = prompt.split(" на ", 1)[1].strip().replace("@", "")
        try:
            await bot.set_business_account_username(
                business_connection_id=business_connection_id,
                username=new_username)
            await reply(f"✅ Username змінено на: @{new_username}")
        except Exception as e:
            await reply(f"⚠️ Помилка: {e}")
        return

    # Очистити історію
    if p in ["очисти історію", "очисти историю", "clear history"]:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM chat_history WHERE user_id=$1 AND chat_id=$2", user_id, chat_id)
        await reply("🗑️ Історія чату очищена!")
        return

    # AI відповідь з пам'яттю
    history = await get_history(user_id, chat_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": prompt}]

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=1024
        )
        answer = response.choices[0].message.content
        await add_history(user_id, chat_id, "user", prompt)
        await add_history(user_id, chat_id, "assistant", answer)
        await reply(answer)
    except Exception as e:
        await reply(f"⚠️ Помилка: {str(e)}")

@dp.business_message(F.text.startswith(".Oliver"))
async def handle_oliver_business(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await bot.send_message(message.chat.id,
            "❌ Немає доступу. Зверніться до @katanaxu",
            business_connection_id=message.business_connection_id)
        return
    await process_oliver(message, business_connection_id=message.business_connection_id)

@dp.message(F.text.startswith(".Oliver"))
async def handle_oliver(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("❌ Немає доступу. Пишіть @katanaxu")
        return
    await process_oliver(message)

@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("❌ Немає доступу.\n📩 @katanaxu")
        return
    await message.answer(
        "🤖 <b>OLIVER AI</b>\n\n"
        "👋 Привіт! Я твій особистий AI-асистент!\n\n"
        "⚡ <b>Як користуватись:</b>\n"
        "<code>.Oliver [твій запит]</code>\n\n"
        "🔧 <b>Команди профілю:</b>\n"
        "<code>.Oliver змін ім'я на Ігор</code>\n"
        "<code>.Oliver змін біо на [текст]</code>\n"
        "<code>.Oliver змін юзернейм на [username]</code>\n\n"
        "🧠 <b>Пам'ять:</b> Oliver пам'ятає розмову в кожному чаті\n"
        "<code>.Oliver очисти історію</code> — скинути пам'ять",
        parse_mode="HTML", reply_markup=get_keyboard())

@dp.message(F.text == "🔗 Як підключити")
async def how_to_connect(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "🔗 <b>Як підключити Oliver:</b>\n\n"
        "1️⃣ Налаштування Telegram\n2️⃣ Telegram Business\n"
        "3️⃣ Автоматизація чатів\n4️⃣ Вибери @OliverpomoschikAI_Bot\n"
        "5️⃣ Дай потрібні дозволи\n6️⃣ Збережи", parse_mode="HTML")

@dp.message(F.text == "🤖 Як користуватись")
async def how_to(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "⚡ <b>Як користуватись Oliver:</b>\n\n"
        "<code>.Oliver [запит]</code>\n\n"
        "📌 <b>Приклади:</b>\n"
        "• <code>.Oliver змін ім'я на Ігор</code>\n"
        "• <code>.Oliver змін біо на Люблю кодити</code>\n"
        "• <code>.Oliver переклади: текст</code>\n"
        "• <code>.Oliver очисти історію</code>",
        parse_mode="HTML")

@dp.message(F.text == "📋 Функції")
async def features(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "🛠 <b>Що вміє Oliver:</b>\n\n"
        "💬 AI відповіді з пам'яттю\n"
        "📝 Зміна імені профілю\n"
        "📄 Зміна біо\n"
        "🔤 Зміна username\n"
        "🌐 Переклад текстів\n"
        "🧠 Пам'ятає контекст розмови", parse_mode="HTML")

@dp.message(F.text == "🖥️ Про Oliver")
async def about(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer("🖥️ Oliver — AI-асистент на базі Llama 3.3 70B через Telegram Business")

@dp.message(F.text == "💬 Підтримка")
async def support(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer("💬 Підтримка: @katanaxu")

async def main():
    await init_db()
    await dp.start_polling(bot, allowed_updates=["message", "business_message", "business_connection"])

if __name__ == "__main__":
    asyncio.run(main())
