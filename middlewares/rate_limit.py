# middlewares/rate_limit.py
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from database import UserDB
from config import config


class RateLimitMiddleware(BaseMiddleware):
    """Middleware для проверки лимитов free-пользователей"""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем telegram_id
        if isinstance(event, Message):
            telegram_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id
        else:
            return await handler(event, data)

        # Загружаем пользователя и передаём в data
        user = await UserDB.get_or_create(
            telegram_id=telegram_id,
            username=event.from_user.username,
            full_name=event.from_user.full_name
        )
        data["db_user"] = user

        return await handler(event, data)