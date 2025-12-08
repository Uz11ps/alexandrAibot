"""Управление зависимостями и глобальными сервисами"""
from typing import Optional
from services.ai_service import AIService
from services.file_service import FileService
from services.telegram_service import TelegramService
from services.vk_service import VKService
from services.post_service import PostService
from services.scheduler_service import SchedulerService
from services.google_drive_service import GoogleDriveService
from services.employee_service import EmployeeService
from services.source_service import SourceService
from services.source_parser_service import SourceParserService
from services.scheduled_posts_service import ScheduledPostsService
from services.prompt_config_service import PromptConfigService

# Глобальные экземпляры сервисов
ai_service: Optional[AIService] = None
file_service: Optional[FileService] = None
telegram_service: Optional[TelegramService] = None
vk_service: Optional[VKService] = None
post_service: Optional[PostService] = None
scheduler_service: Optional[SchedulerService] = None
employee_service: Optional[EmployeeService] = None
google_drive_service: Optional[GoogleDriveService] = None
source_service: Optional[SourceService] = None
source_parser_service: Optional[SourceParserService] = None
scheduled_posts_service: Optional[ScheduledPostsService] = None
prompt_config_service: Optional[PromptConfigService] = None


def init_services(bot, telegram_service_instance: TelegramService):
    """Инициализирует все сервисы"""
    global ai_service, file_service, telegram_service, vk_service
    global post_service, scheduler_service, employee_service, google_drive_service
    global source_service, source_parser_service, scheduled_posts_service, prompt_config_service
    
    # Инициализируем сервис промптов первым
    prompt_config_service = PromptConfigService()
    
    ai_service = AIService(prompt_config_service=prompt_config_service)
    
    # Инициализируем Google Drive сервис
    google_drive_service = GoogleDriveService()
    
    # Инициализируем FileService с Google Drive
    file_service = FileService(google_drive_service=google_drive_service)
    
    telegram_service = telegram_service_instance
    vk_service = VKService(google_drive_service=google_drive_service)
    post_service = PostService(
        ai_service=ai_service,
        file_service=file_service,
        telegram_service=telegram_service,
        vk_service=vk_service
    )
    scheduler_service = SchedulerService(post_service=post_service)
    employee_service = EmployeeService(telegram_service)
    source_service = SourceService()
    source_parser_service = SourceParserService(vk_service=vk_service)
    scheduled_posts_service = ScheduledPostsService()

