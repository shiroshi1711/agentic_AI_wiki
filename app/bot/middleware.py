from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
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

        if not isinstance(event, Message):
            return await handler(event, data)

        user = event.from_user

        if user is None:
            return None

        allowed_id = settings.allowed_telegram_user_id

        allowed_id = settings.allowed_telegram_user_id

        print(
            f"DEBUG AUTH | "
            f"Received ID: {user.id} ({type(user.id).__name__}) | "
            f"Allowed ID: {allowed_id} ({type(allowed_id).__name__}) | "
            f"Chat: {event.chat.type}"
        )

        if allowed_id is None or user.id != allowed_id:
            await event.answer("Unauthorized access.")
            return None

        return await handler(event, data)
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
