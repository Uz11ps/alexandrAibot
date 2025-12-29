"""Модуль для управления зависимостями и инициализации сервисов"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Глобальные переменные для сервисов
telegram_service: Optional = None
ai_service: Optional = None
post_service: Optional = None
file_service: Optional = None
employee_service: Optional = None
scheduler_service: Optional = None
scheduled_posts_service: Optional = None
prompt_config_service: Optional = None
source_service: Optional = None
source_parser_service: Optional = None
vk_service: Optional = None
post_history_service: Optional = None
news_deduplication_service: Optional = None
tavily_service: Optional = None


def init_services(bot, telegram_service_instance):
    """Инициализирует все сервисы"""
    global telegram_service, ai_service, post_service, file_service
    global employee_service, scheduler_service, scheduled_posts_service
    global prompt_config_service, source_service, source_parser_service
    global vk_service, post_history_service, news_deduplication_service
    global tavily_service
    
    logger.info("Инициализация сервисов...")
    
    # Базовые сервисы без зависимостей
    from services.prompt_config_service import PromptConfigService
    from services.file_service import FileService
    from services.google_drive_service import GoogleDriveService
    from services.scheduled_posts_service import ScheduledPostsService
    from services.source_service import SourceService
    from services.post_history_service import PostHistoryService
    from services.news_deduplication_service import NewsDeduplicationService
    from services.tavily_service import TavilyService
    
    prompt_config_service = PromptConfigService()
    logger.info("PromptConfigService инициализирован")
    
    # Google Drive (опционально)
    google_drive_service = None
    try:
        google_drive_service = GoogleDriveService()
        logger.info("GoogleDriveService инициализирован")
    except Exception as e:
        logger.warning(f"GoogleDriveService не инициализирован: {e}")
    
    file_service = FileService(google_drive_service=google_drive_service)
    logger.info("FileService инициализирован")
    
    scheduled_posts_service = ScheduledPostsService()
    logger.info("ScheduledPostsService инициализирован")
    
    source_service = SourceService()
    logger.info("SourceService инициализирован")
    
    post_history_service = PostHistoryService()
    logger.info("PostHistoryService инициализирован")
    
    news_deduplication_service = NewsDeduplicationService()
    logger.info("NewsDeduplicationService инициализирован")
    
    tavily_service = TavilyService()
    logger.info("TavilyService инициализирован")
    
    # Сервисы с зависимостями
    from services.ai_service import AIService
    from services.vk_service import VKService
    from services.employee_service import EmployeeService
    from services.source_parser_service import SourceParserService
    
    ai_service = AIService(prompt_config_service=prompt_config_service)
    logger.info("AIService инициализирован")
    
    vk_service = VKService(google_drive_service=google_drive_service)
    logger.info("VKService инициализирован")
    
    telegram_service = telegram_service_instance
    logger.info("TelegramService установлен")
    
    employee_service = EmployeeService(telegram_service=telegram_service)
    logger.info("EmployeeService инициализирован")
    
    source_parser_service = SourceParserService(vk_service=vk_service)
    logger.info("SourceParserService инициализирован")
    
    # PostService требует ai_service, telegram_service, vk_service, file_service, post_history_service
    from services.post_service import PostService
    post_service = PostService(
        ai_service=ai_service,
        telegram_service=telegram_service,
        vk_service=vk_service,
        file_service=file_service,
        post_history_service=post_history_service
    )
    logger.info("PostService инициализирован")
    
    # SchedulerService требует post_service
    from services.scheduler_service import SchedulerService
    scheduler_service = SchedulerService(post_service=post_service)
    logger.info("SchedulerService инициализирован")
    
    logger.info("Все сервисы успешно инициализированы")
