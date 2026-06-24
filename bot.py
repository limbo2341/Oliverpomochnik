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
        await conn.execute("DROP TABLE IF EXISTS connections")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                user_id BIGINT PRIMARY KEY,
                is_enabled BOOLEAN DEFAULT FALSE,
                can_reply BOOLEAN DEFAULT FALSE,
                can_read_messages BOOLEAN DEFAULT FALSE,
                can_delete_sent_messages BOOLEAN DEFAULT FALSE,
                can_delete_all_messages BOOLEAN DEFAULT FALSE,
                can_edit_name BOOLEAN DEFAULT FALSE,
                can_edit_bio BOOLEAN DEFAULT FALSE,
                can_edit_profile_photo BOOLEAN DEFAULT FALSE,
                can_edit_username BOOLEAN DEFAULT FALSE,
                can_manage_stories BOOLEAN DEFAULT FALSE
            )
        """)

async def save_connection(bc: BusinessConnection):
    r = bc.rights
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO connections (
                user_id, is_enabled,
                can_reply, can_read_messages,
                can_delete_sent_messages, can_delete_all_messages,
                can_edit_name, can_edit_bio,
                can_edit_profile_photo, can_edit_username,
                can_manage_stories
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (user_id) DO UPDATE SET
                is_enabled=$2,
                can_reply=$3, can_read_messages=$4,
                can_delete_sent_messages=$5, can_delete_all_messages=$6,
                can_edit_name=$7, can_edit_bio=$8,
                can_edit_profile_photo=$9, can_edit_username=$10,
                can_manage_stories=$11
        """,
        bc.user.id, bc.is_enabled,
        getattr(r, 'can_reply', False) if r else False,
        getattr(r, 'can_read_messages', False) if r else False,
        getattr(r, 'can_delete_sent_messages', False) if r else False,
        getattr(r, 'can_delete_all_messages', False) if r else False,
        getattr(r, 'can_edit_name', False) if r else False,
        getattr(r, 'can_edit_bio', False) if r else False,
        getattr(r, 'can_edit_profile_photo', False) if r else False,
        getattr(r, 'can_edit_username', False) if r else False,
        getattr(r, 'can_manage_stories', False) if r else False,
        )

async def get_rights(user_id: int) -> dict:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM connections WHERE user_id=$1", user_id)
        return dict(row) if row else {}

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
                "✅ <b>Oliver підключений!</b>\n\nПишіть <code>.Oliver [запит]</code> в будь-якому чаті!",
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

    def no_perm(action):
        return f"❌ Немає дозволу: {action}\nДайте дозвіл у Налаштування → Business → Автоматизація чатів"

    async def reply(text):
        await bot.send_message(message.chat.id, text,
            parse_mode="HTML",
            business_connection_id=business_connection_id)

    p = prompt.lower()

    # Зміна імені
    if p.startswith("змін ім'я на ") or p.startswith("змін имя на ") or p.startswith("змін name на "):
        if not rights.get('can_edit_name'):
            await reply(no_perm("змінювати ім'я (Профіль → Змінювати ім'я)"))
            return
        new_name = prompt.split(" на ", 1)[1].strip()
        parts = new_name.split(" ", 1)
        try:
            await bot.set_business_account_name(
                business_connection_id=business_connection_id,
                first_name=parts[0],
                last_name=parts[1] if len(parts) > 1 else None)
            await reply(f"✅ Ім'я змінено на: <b>{new_name}</b>")
        except Exception as e:
            await reply(f"⚠️ Помилка: {e}")
        return

    # Зміна біо
    if p.startswith("змін біо на ") or p.startswith("змін bio на "):
        if not rights.get('can_edit_bio'):
            await reply(no_perm("змінювати біо (Профіль → Змінювати «Про себе»)"))
            return
        new_bio = prompt.split(" на ", 1)[1].strip()
        try:
            await bot.set_business_account_bio(
                business_connection_id=business_connection_id,
                bio=new_bio)
            await reply(f"✅ Біо змінено на: <b>{new_bio}</b>")
        except Exception as e:
            await reply(f"⚠️ Помилка: {e}")
        return

    # Зміна username
    if p.startswith("змін юзернейм на ") or p.startswith("змін username на "):
        if not rights.get('can_edit_username'):
            await reply(no_perm("змінювати username (Профіль → Змінювати ім'я користувача)"))
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

    # AI відповідь
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        await reply(response.choices[0].message.content)
    except Exception as e:
        await reply(f"⚠️ Помилка: {str(e)}")

@dp.business_message(F.text.startswith(".Oliver"))
async def handle_oliver_business(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
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
        await message.answer("❌ У вас немає доступу.\n📩 Для додавання: @katanaxu")
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
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "🔗 <b>Як підключити Oliver:</b>\n\n"
        "1️⃣ Налаштування Telegram\n"
        "2️⃣ Telegram Business\n"
        "3️⃣ Автоматизація чатів\n"
        "4️⃣ Вибери @OliverpomoschikAI_Bot\n"
        "5️⃣ Дай потрібні дозволи\n"
        "6️⃣ Збережи", parse_mode="HTML")

@dp.message(F.text == "🤖 Як користуватись")
async def how_to(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "⚡ <b>Як користуватись Oliver:</b>\n\n"
        "<code>.Oliver [твій запит]</code>\n\n"
        "📌 <b>Приклади:</b>\n"
        "• <code>.Oliver змін ім'я на Ігор</code>\n"
        "• <code>.Oliver змін біо на Люблю кодити</code>\n"
        "• <code>.Oliver змін юзернейм на mynick</code>\n"
        "• <code>.Oliver переклади на англійську: текст</code>",
        parse_mode="HTML")

@dp.message(F.text == "📋 Функції")
async def features(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "🛠 <b>Що вміє Oliver:</b>\n\n"
        "💬 AI відповіді на будь-які питання\n"
        "📝 Зміна імені профілю\n"
        "📄 Зміна біо\n"
        "🔤 Зміна username\n"
        "🌐 Переклад текстів\n"
        "⚡ І багато іншого!", parse_mode="HTML")

@dp.message(F.text == "🖥️ Про Oliver")
async def about(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "🖥️ <b>Про Oliver:</b>\n\n"
        "Oliver — персональний AI-асистент на базі Llama 3.3 70B\n"
        "Працює через Telegram Business\n"
        "Керує профілем якщо є дозволи", parse_mode="HTML")

@dp.message(F.text == "💬 Підтримка")
async def support(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "💬 <b>Підтримка Oliver:</b>\n\n"
        "👤 Адміністратор: @katanaxu\n\n"
        "📩 Пишіть для:\n"
        "• Додавання нових користувачів\n"
        "• Вирішення проблем", parse_mode="HTML")

async def main():
    await init_db()
    await dp.start_polling(bot, allowed_updates=["message", "business_message", "business_connection"])

if __name__ == "__main__":
    asyncio.run(main())
