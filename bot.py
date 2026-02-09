# bot.py
import asyncio
import logging
import sys
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

WEBHOOK_HOST = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("WEBHOOK_HOST", ""))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 8080))

# Глобальные объекты
bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())


def setup_dp():
    """Настройка диспетчера"""
    from middlewares import RateLimitMiddleware
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    from handlers import setup_routers
    dp.include_router(setup_routers())


async def on_app_startup(app: web.Application):
    """Вызывается ПОСЛЕ запуска aiohttp сервера"""
    logger.info("=== APP STARTUP ===")

    # 1. БД
    await init_db()
    logger.info("Database OK")

    # 2. Ставим webhook ЗДЕСЬ — сервер уже слушает
    logger.info(f"Setting webhook: {WEBHOOK_URL}")
    await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True
    )

    # 3. Проверяем
    info = await bot.get_webhook_info()
    logger.info(f"Webhook URL set: {info.url}")
    logger.info(f"Pending updates: {info.pending_update_count}")
    if info.last_error_message:
        logger.error(f"Webhook ERROR: {info.last_error_message}")
    else:
        logger.info("Webhook OK — no errors")

    logger.info("=== READY ===")


async def on_app_shutdown(app: web.Application):
    """Вызывается при остановке"""
    logger.info("Shutting down...")
    await bot.delete_webhook()
    await bot.session.close()


def create_app() -> web.Application:
    setup_dp()

    app = web.Application()

    # Логируем запросы
    @web.middleware
    async def log_requests(request, handler):
        logger.info(f">>> {request.method} {request.path}")
        try:
            response = await handler(request)
            logger.info(f"<<< {response.status}")
            return response
        except Exception as e:
            logger.error(f"Handler error: {e}", exc_info=True)
            return web.Response(status=500, text="Error")

    app.middlewares.append(log_requests)

    # ─── Telegram webhook handler ───
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # ─── Health ───
    async def health(request):
        return web.Response(text="OK")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    # ─── ЮKassa ───
    async def yukassa_handler(request):
        try:
            from payment_service import payment_service
            data = await request.json()
            result = await payment_service.process_webhook(data)
            if result.get("status") == "succeeded" and result.get("telegram_id"):
                try:
                    await bot.send_message(result["telegram_id"], "🎉 Premium активирован!")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"YooKassa error: {e}")
        return web.Response(status=200)

    app.router.add_post("/payment/callback", yukassa_handler)

    # ─── Lifecycle (НЕ setup_application!) ───
    app.on_startup.append(on_app_startup)
    app.on_shutdown.append(on_app_shutdown)

    return app


async def run_polling():
    setup_dp()
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting polling...")
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    if "--polling" in sys.argv:
        asyncio.run(run_polling())
    else:
        if not WEBHOOK_HOST:
            logger.error("WEBHOOK_HOST / RAILWAY_PUBLIC_DOMAIN not set!")
            sys.exit(1)

        logger.info(f"Webhook URL: {WEBHOOK_URL}")
        logger.info(f"Port: {PORT}")

        app = create_app()
        web.run_app(app, host="0.0.0.0", port=PORT)
