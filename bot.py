# bot.py — ФИНАЛЬНАЯ ВЕРСИЯ
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

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())


def setup_dp():
    from middlewares import RateLimitMiddleware
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    from handlers import setup_routers
    dp.include_router(setup_routers())


async def set_webhook_with_retry():
    """Устанавливаем webhook с повторными попытками"""
    for attempt in range(5):
        try:
            await asyncio.sleep(2)  # Ждём чтобы сервер точно поднялся

            await bot.delete_webhook(drop_pending_updates=True)
            await asyncio.sleep(1)

            await bot.set_webhook(
                url=WEBHOOK_URL,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True
            )

            info = await bot.get_webhook_info()
            logger.info(f"[Attempt {attempt+1}] Webhook URL: {info.url}")

            if info.url == WEBHOOK_URL:
                logger.info("Webhook SET SUCCESSFULLY!")
                if info.last_error_message:
                    logger.warning(f"Last error: {info.last_error_message}")
                return True
            else:
                logger.warning(f"Webhook URL mismatch: expected {WEBHOOK_URL}, got {info.url}")

        except Exception as e:
            logger.error(f"[Attempt {attempt+1}] Webhook error: {e}")

        await asyncio.sleep(3)

    logger.error("FAILED to set webhook after 5 attempts!")
    return False


async def on_app_startup(app: web.Application):
    logger.info("=== APP STARTUP ===")
    await init_db()
    logger.info("Database OK")

    # Ставим webhook через 3 секунды (сервер уже слушает)
    asyncio.create_task(set_webhook_with_retry())


async def on_app_shutdown(app: web.Application):
    logger.info("Shutting down...")
    try:
        await bot.delete_webhook()
        await bot.session.close()
    except Exception:
        pass


def create_app() -> web.Application:
    setup_dp()
    app = web.Application()

    # Логируем ВСЕ запросы
    @web.middleware
    async def log_all(request, handler):
        logger.info(f">>> {request.method} {request.path} [{request.content_type}] from {request.remote}")
        try:
            response = await handler(request)
            logger.info(f"<<< {response.status}")
            return response
        except Exception as e:
            logger.error(f"!!! Handler error: {e}", exc_info=True)
            return web.Response(status=500)

    app.middlewares.append(log_all)

    # ─── Telegram webhook ───
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    # ─── Health ───
    async def health(request):
        return web.Response(text="OK")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    # ─── Тест: GET /webhook ───
    async def test_wh(request):
        info = await bot.get_webhook_info()
        return web.Response(
            text=f"Webhook URL: {info.url}\n"
                 f"Pending: {info.pending_update_count}\n"
                 f"Last error: {info.last_error_message or 'none'}",
            content_type="text/plain"
        )

    app.router.add_get("/webhook", test_wh)

    # ─── Тест: GET /set — принудительная установка webhook ───
    async def force_set_webhook(request):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.set_webhook(
                url=WEBHOOK_URL,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True
            )
            info = await bot.get_webhook_info()
            return web.Response(
                text=f"DONE!\nURL: {info.url}\nError: {info.last_error_message or 'none'}",
                content_type="text/plain"
            )
        except Exception as e:
            return web.Response(text=f"ERROR: {e}", content_type="text/plain")

    app.router.add_get("/set", force_set_webhook)

    # ─── ЮKassa ───
    async def yukassa_handler(request):
        try:
            from payment_service import payment_service
            data = await request.json()
            result = await payment_service.process_webhook(data)
            if result.get("status") == "succeeded" and result.get("telegram_id"):
                await bot.send_message(result["telegram_id"], "🎉 Premium активирован!")
        except Exception as e:
            logger.error(f"YooKassa: {e}")
        return web.Response(status=200)

    app.router.add_post("/payment/callback", yukassa_handler)

    # Lifecycle
    app.on_startup.append(on_app_startup)
    app.on_shutdown.append(on_app_shutdown)

    return app


async def run_polling():
    setup_dp()
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Polling mode...")
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    if "--polling" in sys.argv:
        asyncio.run(run_polling())
    else:
        if not WEBHOOK_HOST:
            logger.error("Set RAILWAY_PUBLIC_DOMAIN!")
            sys.exit(1)
        logger.info(f"URL: {WEBHOOK_URL} | Port: {PORT}")
        app = create_app()
        web.run_app(app, host="0.0.0.0", port=PORT)
