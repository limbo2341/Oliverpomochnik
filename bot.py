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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                user_id BIGINT PRIMARY KEY,
                is_connected BOOLEAN DEFAULT FALSE,
                can_reply BOOLEAN DEFAULT FALSE,
                can_read BOOLEAN DEFAULT FALSE,
                can_mark_read BOOLEAN DEFAULT FALSE,
                can_delete_sent BOOLEAN DEFAULT FALSE,
                can_delete_received BOOLEAN DEFAULT FALSE,
                can_change_name BOOLEAN DEFAULT FALSE,
                can_change_bio BOOLEAN DEFAULT FALSE,
                can_change_photo BOOLEAN DEFAULT FALSE,
                can_change_username BOOLEAN DEFAULT FALSE
            )
        """)

async def save_connection(bc: BusinessConnection):
    rights = bc.rights
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO connections (
                user_id, is_connected,
                can_reply, can_read, can_mark_read,
                can_delete_sent, can_delete_received,
                can_change_name, can_change_bio,
                can_change_photo, can_change_username
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (user_id) DO UPDATE SET
                is_connected=$2,
                can_reply=$3, can_read=$4, can_mark_read=$5,
                can_delete_sent=$6, can_delete_received=$7,
                can_change_name=$8, can_change_bio=$9,
                can_change_photo=$10, can_change_username=$11
        """,
        bc.user.id, bc.is_enabled,
        getattr(rights, 'can_reply', False),
        getattr(rights, 'can_read_messages', False),
        getattr(rights, 'can_mark_as_read', False),
        getattr(rights, 'can_delete_sent_messages', False),
        getattr(rights, 'can_delete_received_messages', False),
        getattr(rights, 'can_change_name', False),
        getattr(rights, 'can_change_bio', False),
        getattr(rights, 'can_edit_profile_photo', False),
        getattr(rights, 'can_change_username', False),
        )

async def get_rights(user_id: int) -> dict:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM connections WHERE user_id=$1", user_id)
        if row:
            return dict(row)
        return {}

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
    if bc.is_enabled:
        if bc.user.id in ALLOWED_USERS:
            await bot.send_message(bc.user.id,
                "✅ <b>Oliver підключений!</b>\n\n"
                "Пишіть <code>.Oliver [запит]</code> в будь-якому чаті!",
                parse_mode="HTML")
        else:
            await bot.send_message(bc.user.id,
                "⚠️ <b>Oliver підключений, але у вас немає доступу.</b>\n\nЗверніться до @katanaxu",
                parse_mode="HTML")
    else:
        await bot.send_message(bc.user.id, "❌ <b>Oliver відключений</b>", parse_mode="HTML")

async def process_oliver(message: Message, business_connection_id: str = None):
    prompt = message.text[len(".Oliver"):].strip()
    user_id = message.from_user.id
    rights = await get_rights(user_id)

    # Команди профілю
    if prompt.lower().startswith("змін ім'я на ") or prompt.lower().startswith("змін имя на "):
        if not rights.get('can_change_name'):
            await bot.send_message(message.chat.id,
                "❌ Немає дозволу змінювати ім'я.\nДайте дозвіл у Налаштування → Business → Автоматизація чатів → Профіль",
                business_connection_id=business_connection_id)
            return
        parts = prompt.split(" на ", 1)
        new_name = parts[1].strip() if len(parts) > 1 else ""
        name_parts = new_name.split(" ", 1)
        first = name_parts[0]
        last = name_parts[1] if len(name_parts) > 1 else None
        try:
            await bot.set_business_account_name(business_connection_id=business_connection_id, first_name=first, last_name=last)
            await bot.send_message(message.chat.id, f"✅ Ім'я змінено на: <b>{new_name}</b>", parse_mode="HTML", business_connection_id=business_connection_id)
        except Exception as e:
            await bot.send_message(message.chat.id, f"⚠️ Помилка: {e}", business_connection_id=business_connection_id)
        return

    if prompt.lower().startswith("змін біо на ") or prompt.lower().startswith("змін bio на "):
        if not rights.get('can_change_bio'):
            await bot.send_message(message.chat.id,
                "❌ Немає дозволу змінювати біо.",
                business_connection_id=business_connection_id)
            return
        new_bio = prompt.split(" на ", 1)[1].strip()
        try:
            await bot.set_business_account_bio(business_connection_id=business_connection_id, bio=new_bio)
            await bot.send_message(message.chat.id, f"✅ Біо змінено на: <b>{new_bio}</b>", parse_mode="HTML", business_connection_id=business_connection_id)
        except Exception as e:
            await bot.send_message(message.chat.id, f"⚠️ Помилка: {e}", business_connection_id=business_connection_id)
        return

    if prompt.lower().startswith("змін юзернейм на ") or prompt.lower().startswith("змін username на "):
        if not rights.get('can_change_username'):
            await bot.send_message(message.chat.id,
                "❌ Немає дозволу змінювати username.",
                business_connection_id=business_connection_id)
            return
        new_username = prompt.split(" на ", 1)[1].strip().replace("@", "")
        try:
            await bot.set_business_account_username(business_connection_id=business_connection_id, username=new_username)
            await bot.send_message(message.chat.id, f"✅ Username змінено на: @{new_username}", business_connection_id=business_connection_id)
        except Exception as e:
            await bot.send_message(message.chat.id, f"⚠️ Помилка: {e}", business_connection_id=business_connection_id)
        return

    # AI відповідь
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
            business_connection_id=business_connection_id)
    except Exception as e:
        await bot.send_message(message.chat.id,
            f"⚠️ Помилка: {str(e)}",
            business_connection_id=business_connection_id)

@dp.business_message(F.text.startswith(".Oliver"))
async def handle_oliver_business(message: Message):
    user_id = message.from_user.id
    if user_id not in ALLOWED_USERS:
        await bot.send_message(message.chat.id,
            "❌ У вас немає доступу до Oliver.\nЗверніться до @katanaxu",
            business_connection_id=message.business_connection_id)
        return
    await process_oliver(message, business_connection_id=message.business_connection_id)

@dp.message(F.text.startswith(".Oliver"))
async def handle_oliver(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("❌ Немає доступу.\nПишіть @katanaxu")
        return
    await process_oliver(message)

@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer(
            "❌ У вас немає доступу.\n📩 Для додавання: @katanaxu",
            parse_mode="HTML")
        return
    await message.answer(
        "🤖 <b>OLIVER AI</b>\n\n"
        "👋 Привіт! Я твій особистий AI-асистент!\n\n"
        "⚡ <b>Як користуватись:</b>\n"
        "<code>.Oliver [твій запит]</code>\n\n"
        "🔧 <b>Команди профілю:</b>\n"
        "<code>.Oliver змін ім'я на Ігор</code>\n"
        "<code>.Oliver змін біо на [текст]</code>\n"
        "<code>.Oliver змін юзернейм на [username]</code>",
        parse_mode="HTML",
        reply_markup=get_keyboard())

@dp.message(F.text == "🔗 Як підключити")
async def how_to_connect(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "🔗 <b>Як підключити Oliver:</b>\n\n"
        "1️⃣ Налаштування Telegram\n"
        "2️⃣ Telegram Business\n"
        "3️⃣ Автоматизація чатів\n"
        "4️⃣ Вибери @OliverpomoschikAI_Bot\n"
        "5️⃣ Дай потрібні дозволи\n"
        "6️⃣ Збережи\n\n"
        "✅ Oliver напише підтвердження після підключення!",
        parse_mode="HTML")

@dp.message(F.text == "🤖 Як користуватись")
async def how_to(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "⚡ <b>Як користуватись Oliver:</b>\n\n"
        "<code>.Oliver [твій запит]</code>\n\n"
        "📌 <b>Приклади:</b>\n"
        "• <code>.Oliver дай відповідь на це</code>\n"
        "• <code>.Oliver переклади на англійську: текст</code>\n"
        "• <code>.Oliver змін ім'я на Ігор</code>\n"
        "• <code>.Oliver змін біо на Люблю кодити</code>",
        parse_mode="HTML")

@dp.message(F.text == "📋 Функції")
async def features(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "🛠 <b>Що вміє Oliver:</b>\n\n"
        "💬 Відповіді на повідомлення\n"
        "🌐 Переклад на будь-яку мову\n"
        "✍️ Написання постів і листів\n"
        "🧠 Пояснення будь-яких тем\n"
        "📝 Зміна імені профілю\n"
        "📄 Зміна біо профілю\n"
        "🔤 Зміна username\n"
        "⚡ І багато іншого!",
        parse_mode="HTML")

@dp.message(F.text == "🖥️ Про Oliver")
async def about(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "🖥️ <b>Про Oliver:</b>\n\n"
        "Oliver — персональний AI-асистент на базі Llama 3.3 70B\n"
        "Працює через Telegram Business\n"
        "Розроблено для зручного використання прямо в чатах",
        parse_mode="HTML")

@dp.message(F.text == "💬 Підтримка")
async def support(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer(
        "💬 <b>Підтримка Oliver:</b>\n\n"
        "👤 Адміністратор: @katanaxu\n\n"
        "📩 Пишіть для:\n"
        "• Додавання нових користувачів\n"
        "• Вирішення проблем",
        parse_mode="HTML")

async def main():
    await init_db()
    await dp.start_polling(bot, allowed_updates=["message", "business_message", "business_connection"])

if __name__ == "__main__":
    asyncio.run(main())
