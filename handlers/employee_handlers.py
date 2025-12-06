"""Обработчики для взаимодействия с сотрудниками"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from aiogram import Router, F
from aiogram.types import Message, PhotoSize
from aiogram.filters import Command

from services.telegram_service import TelegramService
from config.settings import settings

logger = logging.getLogger(__name__)
router = Router()


class EmployeeRequest:
    """Класс для хранения информации о запросе к сотруднику"""
    def __init__(self, employee_id: int, request_text: str, request_type: str):
        self.employee_id = employee_id
        self.request_text = request_text
        self.request_type = request_type
        self.created_at = datetime.now()
        self.last_reminder = None
        self.answered = False
        self.response = None


class EmployeeService:
    """Сервис для управления запросами к сотрудникам"""
    
    def __init__(self, telegram_service: TelegramService):
        self.telegram_service = telegram_service
        self.active_requests: Dict[int, EmployeeRequest] = {}
        self.employee_roles: Dict[int, str] = {}  # employee_id -> role
    
    async def send_request_to_employee(
        self,
        employee_id: int,
        request_text: str,
        request_type: str = "general"
    ) -> int:
        """
        Отправляет запрос сотруднику
        
        Args:
            employee_id: Telegram ID сотрудника
            request_text: Текст запроса
            request_type: Тип запроса (general, photo, info)
            
        Returns:
            ID сообщения
        """
        try:
            message_id = await self.telegram_service.send_message_to_employee(
                employee_id,
                f"📋 <b>Запрос от бота:</b>\n\n{request_text}"
            )
            
            # Сохраняем запрос
            request = EmployeeRequest(employee_id, request_text, request_type)
            self.active_requests[employee_id] = request
            
            logger.info(f"Запрос отправлен сотруднику {employee_id}")
            return message_id
        
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса сотруднику: {e}")
            raise
    
    async def check_timeouts(self):
        """Проверяет таймауты запросов и отправляет напоминания"""
        timeout_hours = settings.EMPLOYEE_RESPONSE_TIMEOUT
        reminder_interval = settings.EMPLOYEE_REMINDER_INTERVAL
        
        now = datetime.now()
        
        for employee_id, request in list(self.active_requests.items()):
            if request.answered:
                continue
            
            time_since_request = now - request.created_at
            
            # Проверяем таймаут
            if time_since_request >= timedelta(hours=timeout_hours):
                # Отправляем уведомление администратору
                await self._notify_admin_about_timeout(request)
                # Удаляем запрос из активных
                del self.active_requests[employee_id]
                continue
            
            # Проверяем необходимость напоминания
            if request.last_reminder is None:
                time_for_reminder = timedelta(hours=reminder_interval)
            else:
                time_for_reminder = now - request.last_reminder
            
            if time_for_reminder >= timedelta(hours=reminder_interval):
                await self._send_reminder(request)
                request.last_reminder = now
    
    async def _send_reminder(self, request: EmployeeRequest):
        """Отправляет напоминание сотруднику"""
        try:
            reminder_text = (
                f"⏰ <b>Напоминание:</b>\n\n"
                f"{request.request_text}\n\n"
                f"Пожалуйста, предоставьте запрошенную информацию."
            )
            
            await self.telegram_service.send_message_to_employee(
                request.employee_id,
                reminder_text
            )
            
            logger.info(f"Напоминание отправлено сотруднику {request.employee_id}")
        
        except Exception as e:
            logger.error(f"Ошибка при отправке напоминания: {e}")
    
    async def _notify_admin_about_timeout(self, request: EmployeeRequest):
        """Уведомляет администратора о таймауте"""
        try:
            notification_text = (
                f"⚠️ <b>Таймаут запроса к сотруднику</b>\n\n"
                f"Сотрудник: {request.employee_id}\n"
                f"Запрос: {request.request_text}\n"
                f"Тип: {request.request_type}\n"
                f"Время запроса: {request.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Сотрудник не ответил в течение {settings.EMPLOYEE_RESPONSE_TIMEOUT} часов."
            )
            
            await self.telegram_service.send_notification_to_admin(notification_text)
            logger.info(f"Администратор уведомлен о таймауте запроса {request.employee_id}")
        
        except Exception as e:
            logger.error(f"Ошибка при уведомлении администратора: {e}")
    
    def mark_request_answered(self, employee_id: int, response: str):
        """Помечает запрос как отвеченный"""
        if employee_id in self.active_requests:
            request = self.active_requests[employee_id]
            request.answered = True
            request.response = response
            logger.info(f"Запрос сотрудника {employee_id} помечен как отвеченный")


# Глобальный экземпляр сервиса (будет инициализирован в main.py)
# Используется через dependencies модуль


@router.message(F.photo)
async def handle_photo_from_employee(message: Message):
    """Обрабатывает фотографии от сотрудников"""
    from services import dependencies
    
    if (dependencies.employee_service and 
        message.from_user.id in dependencies.employee_service.active_requests):
        request = dependencies.employee_service.active_requests[message.from_user.id]
        if request.request_type == "photo" and not request.answered:
            # Помечаем запрос как отвеченный
            dependencies.employee_service.mark_request_answered(
                message.from_user.id,
                f"Получена фотография: {message.photo[-1].file_id}"
            )
            
            await message.answer(
                "✅ Спасибо! Фотография получена и будет использована для поста."
            )
            logger.info(f"Фотография получена от сотрудника {message.from_user.id}")


@router.message()
async def handle_text_from_employee(message: Message):
    """Обрабатывает текстовые сообщения от сотрудников"""
    from services import dependencies
    
    if (dependencies.employee_service and 
        message.from_user.id in dependencies.employee_service.active_requests):
        request = dependencies.employee_service.active_requests[message.from_user.id]
        if not request.answered:
            # Помечаем запрос как отвеченный
            dependencies.employee_service.mark_request_answered(
                message.from_user.id,
                message.text
            )
            
            await message.answer(
                "✅ Спасибо! Ваш ответ получен и будет использован."
            )
            logger.info(f"Ответ получен от сотрудника {message.from_user.id}")

