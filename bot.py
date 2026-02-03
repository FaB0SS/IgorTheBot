import os
import json
import time
import logging
import platform
import asyncio
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.enums import ContentType
from aiogram.filters import Command

# ----------------- Environment -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PUBLIC_URL = os.getenv("PUBLIC_URL")  # https://xxx.up.railway.app

USERS_FILE = "users.json"
LOG_FILE = "deleted.log"
START_TIME = time.time()

# ----------------- Logging -----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

# ----------------- Helper functions -----------------
def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return set(json.load(f))

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

blocked_users = load_users()

async def notify_admin(text: str):
    try:
        await bot.send_message(ADMIN_ID, f"🚨 {text}")
    except:
        pass

# ----------------- Bot setup -----------------
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ----------------- Photo handler -----------------
@dp.message(lambda m: m.from_user and m.from_user.id in blocked_users and m.content_type == ContentType.PHOTO)
async def delete_photo(message: Message):
    try:
        await message.delete()
        logging.info(f"Deleted photo | user={message.from_user.id} | chat={message.chat.id}")
    except Exception as e:
        logging.error(f"Delete failed: {e}")

# ----------------- Commands -----------------
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
    await message.answer(f"✅ Додано {uid}")

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
    await message.answer(f"❌ Видалено {uid}")

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
        )

    if info.last_error_message:
        text += f"\n⚠️ Last error:\n{info.last_error_message}"

    await message.answer(text, parse_mode="Markdown")

# ----------------- Webhook -----------------
async def handle_webhook(request):
    try:
        data = await request.json()
        await dp.feed_raw_update(bot, data)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        await notify_admin(f"Webhook error:\n{e}")
    return web.Response()

async def health(request):
    return web.json_response({
        "status": "ok",
        "users": len(blocked_users)
    })

# ----------------- Auto wake-up -----------------
async def auto_wakeup():
    await asyncio.sleep(10)
    while True:
        try:
            # health check
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{PUBLIC_URL}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logging.info(f"Health OK, users={data['users']}")
                    else:
                        logging.warning(f"Health failed: {resp.status}")
        except Exception as e:
            logging.error(f"Health error: {e}")

        # webhook check
        try:
            info = await bot.get_webhook_info()
            if not info.url:
                logging.warning("Webhook missing! Reinstalling...")
                await bot.set_webhook(f"{PUBLIC_URL}/webhook")
                await notify_admin("Webhook missing — reinstalled!")
        except Exception as e:
            logging.error(f"Webhook check error: {e}")
            await notify_admin(f"Webhook check error: {e}")

        await asyncio.sleep(60)

# ----------------- Startup / Shutdown -----------------
async def on_startup(app):
    await bot.set_webhook(f"{PUBLIC_URL}/webhook")
    info = await bot.get_webhook_info()
    if not info.url:
        await notify_admin("Webhook NOT set")
    # старт auto wake-up
    app.loop.create_task(auto_wakeup())

async def on_shutdown(app):
    await bot.delete_webhook()

# ----------------- Web server -----------------
app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.router.add_get("/health", health)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, port=port)
