import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _parse_user_ids(raw: str) -> List[int]:
    """Parse a comma-separated list of Telegram IDs.

    A malformed entry is an error rather than being skipped: dropping it would
    silently shrink the allow-list, and an empty list means "open to everyone".
    """
    ids: List[int] = []
    invalid: List[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part.isdigit():
            ids.append(int(part))
        else:
            invalid.append(part)
    if invalid:
        raise ValueError(
            f"ALLOWED_USERS содержит некорректные значения: {invalid}. "
            "Ожидаются числовые Telegram ID через запятую, например: 123456789,987654321"
        )
    return ids


class Config:
    """Centralized configuration for the bot"""

    # Bot Configuration
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # Security
    ALLOWED_USERS: List[int] = _parse_user_ids(os.getenv("ALLOWED_USERS", ""))

    # Scheduler
    CHECK_TIME_HOUR: int = int(os.getenv("CHECK_TIME_HOUR", "10"))
    CHECK_TIME_MINUTE: int = int(os.getenv("CHECK_TIME_MINUTE", "0"))
    ADVANCE_NOTIFICATION_DAYS: int = int(os.getenv("ADVANCE_NOTIFICATION_DAYS", "3"))

    # Database
    DB_NAME: str = os.getenv("DB_NAME", "bot_database.db")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/bot.log")

    @classmethod
    def validate(cls) -> bool:
        """Validate critical configuration"""
        if not cls.BOT_TOKEN:
            print("❌ Ошибка: BOT_TOKEN не найден в файле .env")
            return False

        if not 0 <= cls.CHECK_TIME_HOUR <= 23 or not 0 <= cls.CHECK_TIME_MINUTE <= 59:
            print("❌ Ошибка: CHECK_TIME_HOUR должен быть 0-23, CHECK_TIME_MINUTE — 0-59")
            return False

        if cls.ADVANCE_NOTIFICATION_DAYS < 0:
            print("❌ Ошибка: ADVANCE_NOTIFICATION_DAYS не может быть отрицательным")
            return False

        if not cls.ALLOWED_USERS:
            print("⚠️ Предупреждение: ALLOWED_USERS не настроен. Бот доступен всем!")
            if os.getenv("ADMIN_ID"):
                print("⚠️ В .env найден ADMIN_ID, но бот его не использует. "
                      "Переименуйте его в ALLOWED_USERS, чтобы ограничить доступ.")

        return True

    @classmethod
    def is_user_allowed(cls, user_id: int) -> bool:
        """Check if user is allowed to use the bot"""
        # If no users specified, allow all (backward compatibility)
        if not cls.ALLOWED_USERS:
            return True
        return user_id in cls.ALLOWED_USERS


# Validate config on import
if not Config.validate():
    raise ValueError("Invalid configuration. Please check your .env file.")
