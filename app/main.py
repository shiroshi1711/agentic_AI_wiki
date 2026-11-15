import asyncio

from aiogram import Bot, Dispatcher

from app.bot.handlers import router
from app.bot.middleware import AuthenticationMiddleware
from app.config.settings import get_settings


async def main():
    settings = get_settings()

    if settings.telegram_bot_token is None:
        raise RuntimeError("Telegram bot token is missing!")

    if settings.allowed_telegram_user_id is None:
        raise RuntimeError("Authorized Telegram user ID is missing!")

    bot = Bot(token=settings.telegram_bot_token.get_secret_value())

    dp = Dispatcher()
    dp.message.middleware(AuthenticationMiddleware())
    dp.callback_query.middleware(AuthenticationMiddleware())
    dp.include_router(router)

    print("Elarion AI Wiki is starting...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
