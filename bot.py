# bot.py
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import init_db, UserDB
from handlers import setup_routers
from middlewares import RateLimitMiddleware
from payment_service import payment_service

# ─── Логирование ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# ─── Обработчик вебхуков ЮKassa ───
async def yukassa_webhook_handler(request: web.Request) -> web.Response:
    """Обработка уведомлений от ЮKassa"""
    try:
        event_json = await request.json()
        logger.info(f"YooKassa webhook: {event_json.get('event', 'unknown')}")

        result = await payment_service.process_webhook(event_json)

        # Уведомляем пользователя если оплата прошла
        if result.get("status") == "succeeded" and result.get("telegram_id"):
            bot = request.app.get("bot")
            if bot:
                try:
                    await bot.send_message(
                        chat_id=result["telegram_id"],
                        text=(
                            "🎉 <b>Оплата подтверждена!</b>\n\n"
                            "⭐️ Premium активирован!\n"
                            "Наслаждайся безлимитными рецептами! 🍽"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user: {e}")

        return web.Response(status=200, text="OK")
    except Exception as e:
        logger.error(f"YooKassa webhook error: {e}")
        return web.Response(status=200, text="OK")  # Всегда 200, иначе ЮKassa будет ретраить


# ─── Периодические задачи ───
async def periodic_tasks():
    """Фоновые задачи"""
    while True:
        try:
            await UserDB.check_expired_premiums()
        except Exception as e:
            logger.error(f"Periodic task error: {e}")
        await asyncio.sleep(3600)  # Каждый час


# ─── Запуск через Webhook (для Railway) ───
async def on_startup(bot: Bot):
    logger.info("Initializing database...")
    await init_db()

    # Устанавливаем webhook
    webhook_url = config.webhook_url
    logger.info(f"Setting webhook: {webhook_url}")
    await bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )

    # Запускаем периодические задачи
    asyncio.create_task(periodic_tasks())

    logger.info("Bot started!")


async def on_shutdown(bot: Bot):
    logger.info("Shutting down...")
    await bot.delete_webhook()


def create_app() -> web.Application:
    """Создание приложения для Railway"""
    bot = Bot(token=config.BOT_TOKEN, default={"parse_mode": ParseMode.HTML})
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрируем middleware
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    # Регистрируем роутеры
    main_router = setup_routers()
    dp.include_router(main_router)

    # Startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Создаём aiohttp-приложение
    app = web.Application()
    app["bot"] = bot

    # Telegram webhook handler
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=config.WEBHOOK_PATH)

    # ЮKassa webhook handler
    app.router.add_post(config.PAYMENT_CALLBACK_PATH, yukassa_webhook_handler)

    # Health check для Railway
    async def health_check(request):
        return web.Response(text="OK")

    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)

    setup_application(app, dp, bot=bot)
    return app


# ─── Альтернативный запуск через polling (для разработки) ───
async def run_polling():
    """Запуск через long polling (для локальной разработки)"""
    bot = Bot(token=config.BOT_TOKEN, default={"parse_mode": ParseMode.HTML})
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    main_router = setup_routers()
    dp.include_router(main_router)

    await init_db()
    logger.info("Starting polling...")

    # Запускаем периодические задачи
    asyncio.create_task(periodic_tasks())

    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    import sys

    if "--polling" in sys.argv:
        # Локальная разработка
        asyncio.run(run_polling())
    else:
        # Production (Railway)
        app = create_app()
        web.run_app(app, host=config.WEBAPP_HOST, port=config.WEBAPP_PORT)