from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from database import UserDB


class RateLimitMiddleware(BaseMiddleware):
    """Middleware — загружает пользователя из БД и передаёт в хэндлеры"""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем user из event
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user:
            db_user = await UserDB.get_or_create(
                telegram_id=user.id,
                username=user.username,
                full_name=user.full_name
            )
            data["db_user"] = db_user

        return await handler(event, data)
