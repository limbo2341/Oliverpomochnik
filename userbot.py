import asyncio
import os
import logging
from pyrogram import Client, filters
from groq import AsyncGroq

logging.disable(logging.CRITICAL)

API_ID = int(os.getenv("API_ID", "32042255"))
API_HASH = os.getenv("API_HASH", "895daaa9991b9359226cc30b17846830")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SESSION_STRING = os.getenv("SESSION_STRING")

groq_client = AsyncGroq(api_key=GROQ_API_KEY)
app = Client("oliver", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

SYSTEM_PROMPT = "Ти — Oliver, розумний AI-асистент. Відповідай коротко і по суті. Підтримуй мову користувача."

@app.on_message(filters.outgoing & filters.text)
async def handle_oliver(client, message):
    try:
        if not message.text or not message.text.startswith(".Oliver"):
            return
        prompt = message.text[len(".Oliver"):].strip()
        if not prompt:
            return
        await message.edit("⏳ Oliver думає...")
        response = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        await message.edit(response.choices[0].message.content)
    except Exception:
        pass

app.run()
