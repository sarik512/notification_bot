import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Centralized configuration for the bot"""
    
    # Bot Configuration
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    
    # Security
    ALLOWED_USERS: List[int] = [
        int(uid.strip()) 
        for uid in os.getenv("ALLOWED_USERS", "").split(",") 
        if uid.strip().isdigit()
    ]
    
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
        
        if not cls.ALLOWED_USERS:
            print("⚠️ Предупреждение: ALLOWED_USERS не настроен. Бот доступен всем!")
        
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
