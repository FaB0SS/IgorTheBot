import os
import json
import logging
import time
import platform

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.enums import ContentType
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://xxx.onrender.com
ADMIN_ID = int(os.getenv("ADMIN_ID"))   # твій user_id

USERS_FILE = "users.json"
LOG_FILE = "deleted.log"

# ---------- logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

# ---------- helpers ----------
def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return set(json.load(f))

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

blocked_users = load_users()

# ---------- bot ----------
bot = Bot(BOT_TOKEN)
START_TIME = time.time()
dp = Dispatcher()

# ---------- photo handler ----------
@dp.message(lambda m: m.from_user and m.from_user.id in blocked_users and m.content_type == ContentType.PHOTO)
async def delete_photo(message: Message):
    try:
        await message.delete()
        logging.info(
            f"Deleted photo | user={message.from_user.id} | chat={message.chat.id}"
        )
    except Exception as e:
        logging.error(f"Delete failed: {e}")

# ---------- commands ----------
@dp.message(Command("add_user"))
async def add_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Використання: /add_user USER_ID")
        return

    uid = int(parts[1])
    blocked_users.add(uid)
    save_users(blocked_users)
    await message.answer(f"✅ Користувача {uid} додано")

@dp.message(Command("remove_user"))
async def remove_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Використання: /remove_user USER_ID")
        return

    uid = int(parts[1])
    blocked_users.discard(uid)
    save_users(blocked_users)
    await message.answer(f"❌ Користувача {uid} видалено")

@dp.message(Command("list_users"))
async def list_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not blocked_users:
        await message.answer("Список порожній")
    else:
        await message.answer("🚫 Заблоковані:\n" + "\n".join(map(str, blocked_users)))

@dp.message(Command("status"))
async def status(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    verbose = "verbose" in message.text

    info = await bot.get_webhook_info()
    uptime = int(time.time() - START_TIME)

    text = (
        "🤖 *Bot status*\n\n"
        f"🟢 Alive: yes\n"
        f"🔗 Webhook URL:\n{info.url or 'not set'}\n\n"
        f"📦 Pending updates: {info.pending_update_count}\n"
        f"🚫 Blocked users: {len(blocked_users)}\n"
        f"⏱ Uptime: {uptime}s\n"
    )

    if verbose:
        text += (
            "\n🧠 *Verbose info*\n"
            f"🐍 Python: {platform.python_version()}\n"
            f"🖥 Platform: {platform.system()}\n"
            f"📁 Users file: {USERS_FILE}\n"
            f"📝 Log file: {LOG_FILE}\n"
        )

    if info.last_error_message:
        text += f"\n⚠️ Last error:\n{info.last_error_message}"

    await message.answer(text, parse_mode="Markdown")
  
# ---------- webhook ----------
async def on_startup(app):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logging.info("Webhook set")

async def on_shutdown(app):
    await bot.delete_webhook()
    logging.info("Webhook removed")

async def handle_webhook(request):
    data = await request.json()
    await dp.feed_raw_update(bot, data)
    return web.Response()

async def health(request):
    return web.json_response({
        "status": "ok",
        "blocked_users": len(blocked_users)
    })

app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.router.add_get("/health", health)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=10000)
