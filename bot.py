# bot.py
import asyncio
import logging
import sys
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import init_db, UserDB

# ─── Логирование ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    logger.info("=== BOT STARTING ===")

    # 1. Инициализация БД
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database OK")

    # 2. Определяем webhook URL
    # Railway даёт домен через переменную или мы задаём вручную
    host = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if not host:
        host = os.getenv("WEBHOOK_HOST", "")

    if not host:
        logger.error("!!! WEBHOOK_HOST is EMPTY! Bot won't receive updates!")
        logger.error("Set RAILWAY_PUBLIC_DOMAIN or WEBHOOK_HOST in Railway variables")
        return

    webhook_url = f"https://{host}/webhook"
    logger.info(f"Setting webhook to: {webhook_url}")

    # 3. Удаляем старый webhook и ставим новый
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True
    )

    # 4. Проверяем
    info = await bot.get_webhook_info()
    logger.info(f"Webhook URL: {info.url}")
    logger.info(f"Webhook pending updates: {info.pending_update_count}")
    logger.info(f"Webhook max connections: {info.max_connections}")
    if info.last_error_message:
        logger.error(f"Webhook LAST ERROR: {info.last_error_message}")
        logger.error(f"Webhook error date: {info.last_error_date}")
    else:
        logger.info("Webhook: no errors")

    logger.info("=== BOT STARTED OK ===")


async def on_shutdown(bot: Bot):
    logger.info("Shutting down, removing webhook...")
    await bot.delete_webhook()


def create_app() -> web.Application:
    """Главная функция — создаёт приложение"""

    # ─── Бот ───
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # ─── Диспетчер ───
    dp = Dispatcher(storage=MemoryStorage())

    # ─── Middleware ───
    from middlewares import RateLimitMiddleware
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    # ─── Роутеры ───
    from handlers import setup_routers
    dp.include_router(setup_routers())

    # ─── Events ───
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # ─── Web App ───
    app = web.Application()
    app["bot"] = bot

    # Логируем каждый входящий запрос
    @web.middleware
    async def request_logger(request, handler):
        logger.info(f">>> {request.method} {request.path} from {request.remote}")
        response = await handler(request)
        logger.info(f"<<< {response.status}")
        return response

    app.middlewares.append(request_logger)

    # ─── Telegram webhook ───
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path="/webhook")

    # ─── Health check ───
    async def health(request):
        return web.Response(text="OK")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    # ─── Тестовый эндпоинт ───
    async def test_webhook(request):
        return web.Response(text="Webhook endpoint is alive")

    app.router.add_get("/webhook", test_webhook)

    # ─── ЮKassa ───
    async def yukassa_handler(request):
        try:
            from payment_service import payment_service
            data = await request.json()
            result = await payment_service.process_webhook(data)
            if result.get("status") == "succeeded" and result.get("telegram_id"):
                try:
                    await bot.send_message(
                        result["telegram_id"],
                        "🎉 Premium активирован!"
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"YooKassa error: {e}")
        return web.Response(status=200)

    app.router.add_post("/payment/callback", yukassa_handler)

    # ─── Интеграция aiogram с aiohttp ───
    setup_application(app, dp, bot=bot)

    return app


# ─── Polling для локальной разработки ───
async def run_polling():
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    from middlewares import RateLimitMiddleware
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    from handlers import setup_routers
    dp.include_router(setup_routers())

    await init_db()

    # Удаляем webhook для polling
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Starting polling mode...")
    await dp.start_polling(bot, drop_pending_updates=True)


# ─── Точка входа ───
if __name__ == "__main__":
    if "--polling" in sys.argv:
        asyncio.run(run_polling())
    else:
        # Railway production
        port = int(os.getenv("PORT", 8080))
        logger.info(f"Starting web server on port {port}")
        app = create_app()
        web.run_app(app, host="0.0.0.0", port=port)
