import asyncio
import os
import httpx
import io
import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BusinessConnection
from aiogram.filters import CommandStart
from aiogram.methods import SetBusinessAccountName, SetBusinessAccountBio, SetBusinessAccountUsername
from groq import AsyncGroq

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_USERS = {8909320142, 7245932902, 8528807150}
HF_TOKEN = os.getenv("HF_TOKEN", "")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncGroq(api_key=GROQ_API_KEY)
db_pool = None

SYSTEM_PROMPT = """Ти — Oliver, розумний персональний AI-асистент в Telegram.
Автоматично запам'ятовуй важливу інформацію: імена, вподобання, факти, завдання.
Використовуй контекст попередніх повідомлень.
Відповідай мовою користувача. Будь корисним і лаконічним."""

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                user_id BIGINT PRIMARY KEY,
                bc_id TEXT,
                is_enabled BOOLEAN DEFAULT FALSE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                chat_id BIGINT,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Додаємо bc_id якщо не існує
        try:
            await conn.execute("ALTER TABLE connections ADD COLUMN IF NOT EXISTS bc_id TEXT")
        except:
            pass

async def save_connection(bc: BusinessConnection):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO connections (user_id, bc_id, is_enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET bc_id=$2, is_enabled=$3
        """, bc.user.id, bc.id, bc.is_enabled)

async def get_bc_id(user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT bc_id FROM connections WHERE user_id=$1 AND is_enabled=TRUE", user_id)
        return row['bc_id'] if row else None

async def add_history(user_id: int, chat_id: int, role: str, content: str):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO chat_history (user_id, chat_id, role, content)
            VALUES ($1, $2, $3, $4)
        """, user_id, chat_id, role, content)
        await conn.execute("""
            DELETE FROM chat_history WHERE id IN (
                SELECT id FROM chat_history
                WHERE user_id=$1 AND chat_id=$2
                ORDER BY created_at DESC OFFSET 30
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


async def generate_image(prompt: str) -> bytes | None:
    """Генерує зображення через Hugging Face FLUX"""
    url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                return r.content
            return None
    except:
        return None

def get_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡ Як користуватись"), KeyboardButton(text="🛠 Функції")],
            [KeyboardButton(text="ℹ️ Про Oliver"), KeyboardButton(text="🆘 Підтримка")],
            [KeyboardButton(text="🔗 Підключити Business")]
        ],
        resize_keyboard=True
    )

@dp.business_connection()
async def on_business_connect(bc: BusinessConnection):
    await save_connection(bc)
    if bc.is_enabled:
        if bc.user.id in ALLOWED_USERS:
            r = bc.rights
            # права приходять як dict
            rights_dict = dict(r) if r else {}
            perms = []
            if rights_dict.get('can_edit_name'): perms.append("✅ Змінювати ім'я")
            if rights_dict.get('can_edit_bio'): perms.append("✅ Змінювати біо")
            if rights_dict.get('can_edit_username'): perms.append("✅ Змінювати username")
            if rights_dict.get('can_manage_stories'): perms.append("✅ Керувати історіями")
            perms_text = "\n".join(perms) if perms else "Немає дозволів профілю"
            await bot.send_message(bc.user.id,
                f"✅ <b>Oliver підключений!</b>\n\n"
                f"📋 <b>Дозволи:</b>\n{perms_text}\n\n"
                f"Пишіть <code>.Oliver [запит]</code> в будь-якому чаті!",
                parse_mode="HTML")
        else:
            await bot.send_message(bc.user.id,
                "⚠️ Підключений, але немає доступу. Зверніться до @katanaxu")
    else:
        await bot.send_message(bc.user.id, "❌ <b>Oliver відключений</b>", parse_mode="HTML")

async def get_rights_dict(business_connection_id: str) -> dict:
    """Отримує права як dict"""
    if not business_connection_id:
        return {}
    try:
        bc_info = await bot.get_business_connection(business_connection_id)
        r = bc_info.rights
        if r is None:
            return {}
        # Може бути dict або об'єкт
        if isinstance(r, dict):
            return r
        # Якщо об'єкт — конвертуємо
        return {k: v for k, v in r.__dict__.items() if not k.startswith('_')}
    except Exception as e:
        return {}

async def process_oliver(message: Message, business_connection_id: str = None):
    prompt = message.text[len(".Oliver"):].strip()
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Якщо немає bc_id в повідомленні — беремо збережений
    if not business_connection_id:
        business_connection_id = await get_bc_id(user_id)

    async def reply(text, parse_mode=None):
        if not business_connection_id and chat_id == user_id:
            # Пишемо напряму без business_connection_id
            await bot.send_message(user_id, text, parse_mode=parse_mode)
        else:
            await bot.send_message(chat_id, text,
                parse_mode=parse_mode,
                business_connection_id=business_connection_id)

    rights = await get_rights_dict(business_connection_id)
    p = prompt.lower()

    # Зміна імені
    if p.startswith("змін ім'я на ") or p.startswith("змін имя на ") or p.startswith("змін name на "):
        if not rights.get('can_edit_name'):
            await reply("❌ Немає дозволу змінювати ім'я.\nАвтоматизація чатів → Профіль → Змінювати ім'я")
            return
        new_name = prompt.split(" на ", 1)[1].strip()
        parts = new_name.split(" ", 1)
        try:
            await bot(SetBusinessAccountName(business_connection_id=business_connection_id, first_name=parts[0], last_name=parts[1] if len(parts) > 1 else None))
            await reply(f"✅ Ім'я змінено на: {new_name}")
        except Exception as e:
            await reply(f"⚠️ Помилка: {e}")
        return

    # Зміна біо
    if p.startswith("змін біо на ") or p.startswith("змін bio на "):
        if not rights.get('can_edit_bio'):
            await reply("❌ Немає дозволу змінювати біо.")
            return
        new_bio = prompt.split(" на ", 1)[1].strip()
        try:
            await bot(SetBusinessAccountBio(business_connection_id=business_connection_id, bio=new_bio))
            await reply(f"✅ Біо змінено на: {new_bio}")
        except Exception as e:
            await reply(f"⚠️ Помилка: {e}")
        return

    # Зміна username
    if p.startswith("змін юзернейм на ") or p.startswith("змін username на "):
        if not rights.get('can_edit_username'):
            await reply("❌ Немає дозволу змінювати username.")
            return
        new_username = prompt.split(" на ", 1)[1].strip().replace("@", "")
        try:
            await bot(SetBusinessAccountUsername(business_connection_id=business_connection_id, username=new_username))
            await reply(f"✅ Username змінено на: @{new_username}")
        except Exception as e:
            await reply(f"⚠️ Помилка: {e}")
        return

    # Генерація зображення
    if p.startswith("намалюй ") or p.startswith("згенеруй фото ") or p.startswith("згенеруй картинку ") or p.startswith("generate "):
        if not HF_TOKEN:
            await reply("❌ HF_TOKEN не налаштований")
            return
        img_prompt = prompt.split(" ", 1)[1].strip()
        await reply("🎨 Генерую зображення...")
        img_bytes = await generate_image(img_prompt)
        if img_bytes:
            from aiogram.types import BufferedInputFile
            photo = BufferedInputFile(img_bytes, filename="image.jpg")
            await bot.send_photo(chat_id, photo,
                caption=f"🎨 {img_prompt}",
                business_connection_id=business_connection_id)
        else:
            await reply("⚠️ Не вдалось згенерувати. Спробуй ще раз.")
        return

    # Очистити історію
    if p in ["очисти історію", "очисти историю", "clear history", "скинь пам'ять"]:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM chat_history WHERE user_id=$1 AND chat_id=$2", user_id, chat_id)
        await reply("🗑️ Пам'ять очищена!")
        return

    # AI з пам'яттю
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
        await reply(f"⚠️ Помилка AI: {str(e)}")

@dp.business_message(F.text.startswith(".Oliver"))
async def handle_oliver_business(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await bot.send_message(message.chat.id,
            "❌ Немає доступу. @katanaxu",
            business_connection_id=message.business_connection_id)
        return
    await process_oliver(message, business_connection_id=message.business_connection_id)

@dp.message(F.text.startswith(".Oliver"))
async def handle_oliver(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("❌ Немає доступу. @katanaxu")
        return
    await process_oliver(message)

@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("❌ Немає доступу.\n📩 @katanaxu")
        return
    await message.answer(
        "╔══════════════════╗\n"
        "║   🤖  OLIVER AI  ║\n"
        "╚══════════════════╝\n\n"
        "👋 Вітаю! Я твій особистий AI-асистент\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Як використовувати:</b>\n"
        "<code>.Oliver [твій запит]</code>\n\n"
        "🔧 <b>Керування профілем:</b>\n"
        "<code>.Oliver змін ім'я на Ігор</code>\n"
        "<code>.Oliver змін біо на [текст]</code>\n"
        "<code>.Oliver змін юзернейм на [нік]</code>\n\n"
        "🧠 <b>Пам'ять:</b> пам'ятаю кожен чат\n"
        "<code>.Oliver очисти історію</code>\n"
        "━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
        reply_markup=get_keyboard())

@dp.message(F.text == "🔗 Підключити Business")
async def how_to_connect(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━\n"
        "🔗 <b>Підключення Oliver</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Налаштування Telegram\n"
        "2️⃣ Telegram Business\n"
        "3️⃣ Автоматизація чатів\n"
        "4️⃣ Вибери <code>@OliverpomoschikAI_Bot</code>\n"
        "5️⃣ Дай потрібні дозволи\n"
        "6️⃣ Збережи ✅", parse_mode="HTML")

@dp.message(F.text == "⚡ Як користуватись")
async def how_to(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Використання Oliver</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<code>.Oliver [запит]</code>\n\n"
        "📌 <b>Приклади:</b>\n"
        "• <code>.Oliver змін ім'я на Ігор</code>\n"
        "• <code>.Oliver змін біо на Люблю кодити</code>\n"
        "• <code>.Oliver переклади: текст</code>\n"
        "• <code>.Oliver напиши пост про...</code>\n"
        "• <code>.Oliver очисти історію</code>",
        parse_mode="HTML")

@dp.message(F.text == "🛠 Функції")
async def features(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━\n"
        "🛠 <b>Можливості Oliver</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🧠 AI з пам'яттю розмов\n"
        "📝 Зміна імені профілю\n"
        "📄 Зміна біо\n"
        "🔤 Зміна username\n"
        "🌐 Переклад будь-якою мовою\n"
        "✍️ Написання постів і текстів\n"
        "💡 Відповіді на будь-які питання",
        parse_mode="HTML")

@dp.message(F.text == "ℹ️ Про Oliver")
async def about(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ <b>Про Oliver</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🤖 Модель: Llama 3.3 70B\n"
        "⚙️ Платформа: Telegram Business\n"
        "🧠 Пам'ять: до 30 повідомлень\n"
        "⚡ Швидкість: миттєво",
        parse_mode="HTML")

@dp.message(F.text == "🆘 Підтримка")
async def support(message: Message):
    if message.from_user.id not in ALLOWED_USERS: return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━\n"
        "🆘 <b>Підтримка</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👤 Адмін: @katanaxu\n\n"
        "Пишіть для:\n"
        "• Додавання доступу\n"
        "• Вирішення проблем",
        parse_mode="HTML")

async def main():
    await init_db()
    await dp.start_polling(bot, allowed_updates=["message", "business_message", "business_connection"])

if __name__ == "__main__":
    asyncio.run(main())
