# bot.py
import asyncio
import logging
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import init_db, UserDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


# ─── Webhook ЮKassa ───
async def yukassa_webhook_handler(request: web.Request) -> web.Response:
    try:
        from payment_service import payment_service
        event_json = await request.json()
        logger.info(f"YooKassa webhook: {event_json.get('event', 'unknown')}")

        result = await payment_service.process_webhook(event_json)

        if result.get("status") == "succeeded" and result.get("telegram_id"):
            bot = request.app.get("bot")
            if bot:
                try:
                    await bot.send_message(
                        chat_id=result["telegram_id"],
                        text="🎉 <b>Оплата подтверждена!</b>\n⭐️ Premium активирован!",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Notify error: {e}")

        return web.Response(status=200, text="OK")
    except Exception as e:
        logger.error(f"YooKassa error: {e}")
        return web.Response(status=200, text="OK")


# ─── Фоновые задачи ───
async def periodic_tasks():
    while True:
        try:
            await UserDB.check_expired_premiums()
        except Exception as e:
            logger.error(f"Periodic task error: {e}")
        await asyncio.sleep(3600)


# ─── Startup ───
async def on_startup(bot: Bot):
    logger.info("Initializing database...")
    await init_db()

    if config.WEBHOOK_HOST:
        webhook_url = config.webhook_url
        logger.info(f"Setting webhook: {webhook_url}")
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
    else:
        logger.info("No WEBHOOK_HOST — skipping webhook setup")

    asyncio.create_task(periodic_tasks())
    logger.info("Bot started successfully!")


async def on_shutdown(bot: Bot):
    logger.info("Shutting down...")
    try:
        await bot.delete_webhook()
    except Exception:
        pass


def create_bot_and_dp():
    """Создаёт бот и диспетчер"""
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware
    from middlewares import RateLimitMiddleware
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    # Роутеры
    from handlers import setup_routers
    main_router = setup_routers()
    dp.include_router(main_router)

    # Events
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return bot, dp


# ─── Production: Webhook (Railway) ───
def create_app() -> web.Application:
    bot, dp = create_bot_and_dp()

    app = web.Application()
    app["bot"] = bot

    # Telegram webhook
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=config.WEBHOOK_PATH)

    # ЮKassa webhook
    app.router.add_post(config.PAYMENT_CALLBACK_PATH, yukassa_webhook_handler)

    # Health check
    async def health(request):
        return web.Response(text="OK")

    app.router.add_get("/health", health)
    app.router.add_get("/", health)

    setup_application(app, dp, bot=bot)
    return app


# ─── Dev: Polling ───
async def run_polling():
    bot, dp = create_bot_and_dp()
    await init_db()
    logger.info("Starting polling...")
    asyncio.create_task(periodic_tasks())
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    if "--polling" in sys.argv:
        asyncio.run(run_polling())
    else:
        app = create_app()
        web.run_app(
            app,
            host=config.WEBAPP_HOST,
            port=config.WEBAPP_PORT
        )
