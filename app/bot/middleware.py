from aiogram import BaseMiddleware
from aiogram.types import (
    TelegramObject,
    Message,
    CallbackQuery,
)
from typing import Any, Awaitable, Callable

from app.config.settings import get_settings


class AuthenticationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[
            [TelegramObject, dict[str, Any]],
            Awaitable[Any]
        ],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:

        settings = get_settings()
        allowed_id = settings.allowed_telegram_user_id

        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user

            if user is None:
                return None

            if allowed_id is None or user.id != allowed_id:
                if isinstance(event, Message):
                    await event.answer("Unauthorized access.")

                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "Unauthorized access.",
                        show_alert=True,
                    )

                return None

        return await handler(event, data)
