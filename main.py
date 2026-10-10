import asyncio
import sys

# Redirected output on Windows defaults to the ANSI code page (cp1251), where the
# emoji in our log lines and warnings raise UnicodeEncodeError. Must run before
# config/logger are imported, since they print and log at import time.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

# Import configuration and logging first
from config import Config
from logger import logger

# Import modules
import handlers
import database as db
import scheduler


async def on_error(event: ErrorEvent) -> bool:
    """Log unhandled handler errors and tell the user instead of leaving them hanging"""
    logger.error(f"Unhandled error while processing update: {event.exception}", exc_info=event.exception)
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer("❌ Произошла ошибка. Попробуйте ещё раз.", show_alert=True)
        elif update.message:
            await update.message.answer("❌ Произошла ошибка. Попробуйте ещё раз или нажмите /cancel")
    except Exception:
        pass  # the notification is best effort; the error is already logged
    return True


async def on_startup(bot: Bot):
    """Actions to perform on bot startup"""
    logger.info("=" * 60)
    logger.info("Bot is starting up...")
    logger.info(f"Allowed users: {Config.ALLOWED_USERS if Config.ALLOWED_USERS else 'All users (no restrictions)'}")
    logger.info(f"Check time: {Config.CHECK_TIME_HOUR:02d}:{Config.CHECK_TIME_MINUTE:02d}")
    logger.info(f"Advance notification: {Config.ADVANCE_NOTIFICATION_DAYS} days")
    logger.info("=" * 60)
    
    # Initialize database
    try:
        await db.init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Setup scheduler
    try:
        scheduler.setup_scheduler(bot)
        logger.info("Scheduler setup completed")
    except Exception as e:
        logger.error(f"Failed to setup scheduler: {e}")
        raise
    
    # Get bot info
    try:
        bot_info = await bot.get_me()
        logger.info(f"Bot started: @{bot_info.username} ({bot_info.first_name})")
        logger.info(f"Bot ID: {bot_info.id}")
    except Exception as e:
        logger.warning(f"Could not get bot info: {e}")
    
    logger.info("✅ Bot startup completed successfully")


async def on_shutdown(bot: Bot):
    """Actions to perform on bot shutdown"""
    logger.info("=" * 60)
    logger.info("Bot is shutting down...")
    
    # Stop scheduler
    try:
        scheduler.stop_scheduler()
        logger.info("Scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
    
    # Close bot session
    try:
        await bot.session.close()
        logger.info("Bot session closed")
    except Exception as e:
        logger.error(f"Error closing bot session: {e}")
    
    logger.info("✅ Bot shutdown completed")
    logger.info("=" * 60)


async def main():
    """Main function to run the bot"""
    try:
        # Validate configuration
        if not Config.BOT_TOKEN:
            logger.error("BOT_TOKEN not found in .env file")
            print("\n❌ Ошибка: BOT_TOKEN не найден в файле .env")
            print("Пожалуйста, создайте файл .env на основе .env.example")
            print("и добавьте ваш токен от @BotFather\n")
            return
        
        # Initialize bot with default properties
        bot = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML
            )
        )
        
        # Initialize dispatcher
        dp = Dispatcher()
        
        # Register routers
        dp.include_router(handlers.router)
        
        dp.errors.register(on_error)
        
        # Register startup and shutdown handlers
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        # Start polling
        logger.info("Starting bot polling...")
        print("\n✅ Бот запущен и работает!")
        print(f"⏰ Проверка платежей: каждый день в {Config.CHECK_TIME_HOUR:02d}:{Config.CHECK_TIME_MINUTE:02d}")
        print("📝 Логи сохраняются в:", Config.LOG_FILE)
        print("\nНажмите Ctrl+C для остановки бота\n")
        
        try:
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types()
            )
        finally:
            # The sqlite worker thread is non-daemon: left open, it keeps the
            # process alive after a crash.
            await db.close_db()
        
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        print(f"\n❌ Критическая ошибка: {e}\n")
        raise


if __name__ == "__main__":
    try:
        # Set event loop policy for Windows
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            logger.info("Windows event loop policy set")
        
        # Run the bot
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
        print("\n✅ Бот остановлен пользователем\n")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"\n❌ Необработанная ошибка: {e}\n")
        sys.exit(1)
