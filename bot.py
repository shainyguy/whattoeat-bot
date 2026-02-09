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
    level=logging.DEBUG,  # <── ИЗМЕНЕНО НА DEBUG
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


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
                        text="🎉 Premium активирован!",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Notify error: {e}")

        return web.Response(status=200, text="OK")
    except Exception as e:
        logger.error(f"YooKassa error: {e}")
        return web.Response(status=200, text="OK")


async def periodic_tasks():
    while True:
        try:
            await UserDB.check_expired_premiums()
        except Exception as e:
            logger.error(f"Periodic task error: {e}")
        await asyncio.sleep(3600)


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

        # Проверяем что webhook установился
        webhook_info = await bot.get_webhook_info()
        logger.info(f"Webhook info: url={webhook_info.url}")
        logger.info(f"Webhook pending: {webhook_info.pending_update_count}")
        if webhook_info.last_error_message:
            logger.error(f"Webhook last error: {webhook_info.last_error_message}")
    else:
        logger.warning("No WEBHOOK_HOST set!")

    asyncio.create_task(periodic_tasks())
    logger.info("Bot started successfully!")


async def on_shutdown(bot: Bot):
    logger.info("Shutting down...")
    try:
        await bot.delete_webhook()
    except Exception:
        pass


def create_bot_and_dp():
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    from middlewares import RateLimitMiddleware
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    from handlers import setup_routers
    main_router = setup_routers()
    dp.include_router(main_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return bot, dp


def create_app() -> web.Application:
    bot, dp = create_bot_and_dp()

    app = web.Application()
    app["bot"] = bot

    # ─── КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ───
    # Webhook handler для Telegram
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_handler.register(app, path=config.WEBHOOK_PATH)

    # Добавляем логирование ВСЕХ входящих запросов
    @web.middleware
    async def log_middleware(request, handler):
        logger.info(f"Incoming: {request.method} {request.path}")
        try:
            response = await handler(request)
            logger.info(f"Response: {response.status}")
            return response
        except Exception as e:
            logger.error(f"Handler error: {e}", exc_info=True)
            raise

    app.middlewares.append(log_middleware)

    # ЮKassa webhook
    app.router.add_post(config.PAYMENT_CALLBACK_PATH, yukassa_webhook_handler)

    # Health check
    async def health(request):
        return web.Response(text="OK")

    app.router.add_get("/health", health)
    app.router.add_get("/", health)

    setup_application(app, dp, bot=bot)

    return app


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
