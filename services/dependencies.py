"""Управление зависимостями и глобальными сервисами"""
from typing import Optional
from services.ai_service import AIService
from services.file_service import FileService
from services.telegram_service import TelegramService
from services.vk_service import VKService
from services.post_service import PostService
from services.scheduler_service import SchedulerService
from services.google_drive_service import GoogleDriveService
from handlers.employee_handlers import EmployeeService

# Глобальные экземпляры сервисов
ai_service: Optional[AIService] = None
file_service: Optional[FileService] = None
telegram_service: Optional[TelegramService] = None
vk_service: Optional[VKService] = None
post_service: Optional[PostService] = None
scheduler_service: Optional[SchedulerService] = None
employee_service: Optional[EmployeeService] = None
google_drive_service: Optional[GoogleDriveService] = None


def init_services(bot, telegram_service_instance: TelegramService):
    """Инициализирует все сервисы"""
    global ai_service, file_service, telegram_service, vk_service
    global post_service, scheduler_service, employee_service, google_drive_service
    
    ai_service = AIService()
    
    # Инициализируем Google Drive сервис
    google_drive_service = GoogleDriveService()
    
    # Инициализируем FileService с Google Drive
    file_service = FileService(google_drive_service=google_drive_service)
    
    telegram_service = telegram_service_instance
    vk_service = VKService()
    post_service = PostService(
        ai_service=ai_service,
        file_service=file_service,
        telegram_service=telegram_service,
        vk_service=vk_service
    )
    scheduler_service = SchedulerService(post_service=post_service)
    employee_service = EmployeeService(telegram_service)

