import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from groq import AsyncGroq

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ALLOWED_USERS = {8909320142, 7245932902}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncGroq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = "Ти — Oliver, розумний AI-асистент в Telegram. Допомагай з будь-якими завданнями. Відповідай мовою користувача."

def get_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 Як користуватись"), KeyboardButton(text="📋 Функції")],
            [KeyboardButton(text="ℹ️ Про Oliver"), KeyboardButton(text="💬 Підтримка")]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("❌ Ви не додані в список.\nПишіть @katanaxu")
        return
    await message.answer(
        "👋 Привіт! Я <b>Oliver</b> — твій AI-асистент!\n\n"
        "⚡ <b>Як користуватись:</b>\n"
        "В будь-якому чаті напиши:\n"
        "<code>.Oliver [твій запит]</code>\n\n"
        "📌 <b>Приклади:</b>\n"
        "• <code>.Oliver дай відповідь на це</code>\n"
        "• <code>.Oliver переклади на англійську: текст</code>\n"
        "• <code>.Oliver напиши вибачення другу</code>",
        parse_mode="HTML",
        reply_markup=get_keyboard()
    )

@dp.message(F.text == "🤖 Як користуватись")
async def how_to(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer("⚡ Пиши в будь-якому чаті:\n<code>.Oliver [запит]</code>", parse_mode="HTML")

@dp.message(F.text == "📋 Функції")
async def features(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer("🛠 Oliver вміє все що ти попросиш:\n• Відповідати на повідомлення\n• Перекладати тексти\n• Писати листи, пости\n• Пояснювати теми\n• Генерувати ідеї\n• І багато іншого!")

@dp.message(F.text == "ℹ️ Про Oliver")
async def about(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer("🤖 Oliver v1.0\nAI: Groq (Llama 3.3)\nТригер: .Oliver")

@dp.message(F.text == "💬 Підтримка")
async def support(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer("💬 Підтримка: @katanaxu")

async def process_oliver(message: Message):
    prompt = message.text[len(".Oliver"):].strip()
    if not prompt:
        await message.reply("❓ Напиши що зробити після .Oliver")
        return
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        await message.reply(response.choices[0].message.content)
    except Exception as e:
        await message.reply(f"⚠️ Помилка: {str(e)}")

@dp.message(F.text.startswith(".Oliver"))
async def handle_oliver(message: Message):
    if message.business_connection_id:
        await process_oliver(message)
        return
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("❌ Ви не додані в список.\nПишіть @katanaxu")
        return
    await process_oliver(message)

async def main():
    await dp.start_polling(bot, allowed_updates=["message", "business_message"])

if __name__ == "__main__":
    asyncio.run(main())
