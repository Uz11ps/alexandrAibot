"""Конфигурация приложения"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Настройки бота"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_ADMIN_ID: int
    TELEGRAM_ADMIN_IDS: Optional[str] = None  # Дополнительные администраторы через запятую (например: "123456,789012")
    TELEGRAM_CHANNEL_ID: Optional[str] = None
    
    # VK
    VK_GROUP_ID: int
    VK_ACCESS_TOKEN: str  # Токен группы (для публикации постов)
    VK_USER_TOKEN: Optional[str] = None  # Пользовательский токен (для загрузки фото, если токен группы не поддерживает)
    
    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_API_KEYS: Optional[str] = None  # Дополнительные ключи через запятую для ротации
    OPENAI_MODEL: str = "gpt-5"
    OPENAI_PROXY_ENABLED: bool = False
    OPENAI_PROXY_URL: Optional[str] = None  # Формат: https://user:pass@host:port или список через запятую
    
    # Пути к папкам
    PHOTOS_FOLDER: str = "storage/photos"
    DRAFTS_FOLDER: str = "storage/drafts"
    LAWS_FOLDER: str = "storage/laws"
    MEMES_FOLDER: str = "storage/memes"
    SERVICES_FOLDER: str = "storage/services"
    ARCHIVE_FOLDER: str = "storage/archive"
    
    # Расписание публикаций (время в формате HH:MM)
    SCHEDULE_MONDAY_TIME: str = "09:00"
    SCHEDULE_TUESDAY_TIME: str = "09:00"
    SCHEDULE_WEDNESDAY_TIME: str = "09:00"
    SCHEDULE_THURSDAY_TIME: str = "09:00"
    SCHEDULE_FRIDAY_TIME: str = "09:00"
    SCHEDULE_SATURDAY_TIME: str = "09:00"
    SCHEDULE_SUNDAY_REMINDER_TIME: str = "10:00"
    
    # Таймауты для сотрудников (в часах)
    EMPLOYEE_RESPONSE_TIMEOUT: int = 24
    EMPLOYEE_REMINDER_INTERVAL: int = 4
    
    # Google Drive настройки
    GOOGLE_DRIVE_ENABLED: bool = False
    GOOGLE_DRIVE_CREDENTIALS_FILE: Optional[str] = "credentials/google-credentials.json"
    GOOGLE_DRIVE_TOKEN_FILE: Optional[str] = "credentials/google-token.json"
    GOOGLE_DRIVE_ROOT_FOLDER_ID: Optional[str] = None  # Родительская папка для всех папок бота
    GOOGLE_DRIVE_PHOTOS_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_DRAFTS_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_LAWS_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_MEMES_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_SERVICES_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_ARCHIVE_FOLDER_ID: Optional[str] = None
    
    # Анализ источников
    SOURCE_ANALYSIS_ENABLED: bool = True
    SOURCE_ANALYSIS_TIME: str = "12:00"  # Время ежедневного анализа источников
    TELEGRAM_API_ID: Optional[int] = None  # API ID для Telethon (получить на my.telegram.org)
    TELEGRAM_API_HASH: Optional[str] = None  # API Hash для Telethon
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

