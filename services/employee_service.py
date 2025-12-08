"""Сервис для управления сотрудниками и запросами"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from aiogram import Bot

from services.telegram_service import TelegramService
from services.employee_settings_service import EmployeeSettingsService
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class Employee:
    """Информация о сотруднике"""
    telegram_id: int
    name: str
    role: str
    added_at: str
    is_active: bool = True


@dataclass
class EmployeeRequest:
    """Запрос к сотруднику"""
    request_id: str
    employee_id: int
    request_text: str
    request_type: str  # general, photo, info, document
    created_at: str
    last_reminder: Optional[str] = None
    answered: bool = False
    response: Optional[str] = None
    response_at: Optional[str] = None
    conversation_history: List[Dict[str, str]] = None  # История диалога
    
    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []


class EmployeeService:
    """Сервис для управления сотрудниками и запросами"""
    
    def __init__(self, telegram_service: TelegramService):
        self.telegram_service = telegram_service
        self.settings_service = EmployeeSettingsService()
        self.storage_path = Path("storage/employees")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.employees_file = self.storage_path / "employees.json"
        self.requests_file = self.storage_path / "requests.json"
        self.history_file = self.storage_path / "history.json"
        self.content_manager_file = self.storage_path / "content_manager.json"
        
        self.employees: Dict[int, Employee] = {}
        self.active_requests: Dict[int, EmployeeRequest] = {}
        self.request_history: List[EmployeeRequest] = {}
        self.content_manager_id: Optional[int] = None
        
        self._load_employees()
        self._load_requests()
        self._load_history()
        self._load_content_manager()
    
    def _load_employees(self):
        """Загружает список сотрудников из файла"""
        try:
            if self.employees_file.exists():
                with open(self.employees_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.employees = {
                        int(eid): Employee(**emp) 
                        for eid, emp in data.items()
                    }
                logger.info(f"Загружено {len(self.employees)} сотрудников")
        except Exception as e:
            logger.error(f"Ошибка при загрузке сотрудников: {e}")
            self.employees = {}
    
    def _save_employees(self):
        """Сохраняет список сотрудников в файл"""
        try:
            data = {
                str(eid): asdict(emp) 
                for eid, emp in self.employees.items()
            }
            with open(self.employees_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Сохранено {len(self.employees)} сотрудников")
        except Exception as e:
            logger.error(f"Ошибка при сохранении сотрудников: {e}")
    
    def _load_requests(self):
        """Загружает активные запросы из файла"""
        try:
            if self.requests_file.exists():
                with open(self.requests_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.active_requests = {
                        int(eid): EmployeeRequest(**req) 
                        for eid, req in data.items()
                    }
                logger.info(f"Загружено {len(self.active_requests)} активных запросов")
        except Exception as e:
            logger.error(f"Ошибка при загрузке запросов: {e}")
            self.active_requests = {}
    
    def _save_requests(self):
        """Сохраняет активные запросы в файл"""
        try:
            data = {
                str(eid): asdict(req) 
                for eid, req in self.active_requests.items()
            }
            with open(self.requests_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении запросов: {e}")
    
    def _load_history(self):
        """Загружает историю запросов"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.request_history = [EmployeeRequest(**req) for req in data]
                logger.info(f"Загружено {len(self.request_history)} запросов в истории")
        except Exception as e:
            logger.error(f"Ошибка при загрузке истории: {e}")
            self.request_history = []
    
    def _save_history(self):
        """Сохраняет историю запросов"""
        try:
            data = [asdict(req) for req in self.request_history[-1000:]]  # Последние 1000 запросов
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении истории: {e}")
    
    def add_employee(self, telegram_id: int, name: str, role: str) -> bool:
        """
        Добавляет сотрудника
        
        Args:
            telegram_id: Telegram ID сотрудника
            name: Имя сотрудника
            role: Роль сотрудника
            
        Returns:
            True если успешно добавлен
        """
        if telegram_id in self.employees:
            logger.warning(f"Сотрудник {telegram_id} уже существует")
            return False
        
        employee = Employee(
            telegram_id=telegram_id,
            name=name,
            role=role,
            added_at=datetime.now().isoformat(),
            is_active=True
        )
        self.employees[telegram_id] = employee
        self._save_employees()
        logger.info(f"Добавлен сотрудник: {name} ({telegram_id}), роль: {role}")
        return True
    
    def remove_employee(self, telegram_id: int) -> bool:
        """Удаляет сотрудника"""
        if telegram_id not in self.employees:
            return False
        
        del self.employees[telegram_id]
        self._save_employees()
        logger.info(f"Удален сотрудник {telegram_id}")
        return True
    
    def get_employee(self, telegram_id: int) -> Optional[Employee]:
        """Получает информацию о сотруднике"""
        return self.employees.get(telegram_id)
    
    def get_all_employees(self) -> List[Employee]:
        """Получает список всех активных сотрудников"""
        return [emp for emp in self.employees.values() if emp.is_active]
    
    async def send_request_to_employee(
        self,
        employee_id: int,
        request_text: str,
        request_type: str = "general"
    ) -> Optional[int]:
        """
        Отправляет запрос сотруднику
        
        Args:
            employee_id: Telegram ID сотрудника
            request_text: Текст запроса
            request_type: Тип запроса (general, photo, info, document)
            
        Returns:
            ID сообщения или None при ошибке
        """
        if employee_id not in self.employees:
            logger.warning(f"Сотрудник {employee_id} не найден")
            return None
        
        try:
            message_id = await self.telegram_service.send_message_to_employee(
                employee_id,
                f"📋 <b>Запрос от бота:</b>\n\n{request_text}"
            )
            
            # Создаем запрос
            request_id = f"{employee_id}_{datetime.now().timestamp()}"
            request = EmployeeRequest(
                request_id=request_id,
                employee_id=employee_id,
                request_text=request_text,
                request_type=request_type,
                created_at=datetime.now().isoformat(),
                conversation_history=[{
                    "role": "bot",
                    "text": request_text,
                    "timestamp": datetime.now().isoformat()
                }]
            )
            
            self.active_requests[employee_id] = request
            self._save_requests()
            
            logger.info(f"Запрос отправлен сотруднику {employee_id}: {request_text[:50]}...")
            return message_id
        
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса сотруднику: {e}")
            return None
    
    def add_to_conversation(self, employee_id: int, role: str, text: str):
        """Добавляет сообщение в историю диалога"""
        if employee_id in self.active_requests:
            request = self.active_requests[employee_id]
            request.conversation_history.append({
                "role": role,
                "text": text,
                "timestamp": datetime.now().isoformat()
            })
            self._save_requests()
    
    def mark_request_answered(self, employee_id: int, response: str):
        """Помечает запрос как отвеченный"""
        if employee_id in self.active_requests:
            request = self.active_requests[employee_id]
            request.answered = True
            request.response = response
            request.response_at = datetime.now().isoformat()
            
            # Добавляем ответ в историю
            self.add_to_conversation(employee_id, "employee", response)
            
            # Перемещаем в историю
            self.request_history.append(request)
            del self.active_requests[employee_id]
            
            self._save_requests()
            self._save_history()
            
            logger.info(f"Запрос сотрудника {employee_id} помечен как отвеченный")
    
    async def check_timeouts(self):
        """Проверяет таймауты запросов и отправляет напоминания"""
        timeout_hours = self.settings_service.get_response_timeout()
        reminder_interval = self.settings_service.get_reminder_interval()
        
        now = datetime.now()
        
        for employee_id, request in list(self.active_requests.items()):
            if request.answered:
                continue
            
            created_at = datetime.fromisoformat(request.created_at)
            time_since_request = now - created_at
            
            # Проверяем таймаут (24 часа по умолчанию)
            if time_since_request >= timedelta(hours=timeout_hours):
                # Отправляем эскалацию администратору с историей диалога
                await self._escalate_to_admin(request)
                # Перемещаем в историю
                self.request_history.append(request)
                del self.active_requests[employee_id]
                self._save_requests()
                self._save_history()
                continue
            
            # Проверяем необходимость напоминания
            last_reminder = None
            if request.last_reminder:
                last_reminder = datetime.fromisoformat(request.last_reminder)
            
            if last_reminder is None:
                time_for_reminder = time_since_request
            else:
                time_for_reminder = now - last_reminder
            
            if time_for_reminder >= timedelta(hours=reminder_interval):
                await self._send_reminder(request)
                request.last_reminder = now.isoformat()
                self._save_requests()
    
    async def _send_reminder(self, request: EmployeeRequest):
        """Отправляет напоминание сотруднику"""
        try:
            employee = self.get_employee(request.employee_id)
            employee_name = employee.name if employee else f"ID: {request.employee_id}"
            
            reminder_text = (
                f"⏰ <b>Напоминание:</b>\n\n"
                f"{request.request_text}\n\n"
                f"Пожалуйста, предоставьте запрошенную информацию."
            )
            
            await self.telegram_service.send_message_to_employee(
                request.employee_id,
                reminder_text
            )
            
            # Добавляем напоминание в историю
            self.add_to_conversation(request.employee_id, "bot", f"Напоминание: {request.request_text}")
            
            logger.info(f"Напоминание отправлено сотруднику {request.employee_id}")
        
        except Exception as e:
            logger.error(f"Ошибка при отправке напоминания: {e}")
    
    async def _escalate_to_admin(self, request: EmployeeRequest):
        """Эскалирует запрос администратору с полной историей диалога"""
        try:
            employee = self.get_employee(request.employee_id)
            employee_name = employee.name if employee else f"ID: {request.employee_id}"
            employee_role = employee.role if employee else "Не указана"
            
            # Формируем историю диалога
            conversation_text = "\n".join([
                f"{msg['timestamp'][:16]} [{msg['role']}]: {msg['text']}"
                for msg in request.conversation_history
            ])
            
            timeout_hours = self.settings_service.get_response_timeout()
            notification_text = (
                f"⚠️ <b>ЭСКАЛАЦИЯ: Таймаут запроса к сотруднику</b>\n\n"
                f"👤 <b>Сотрудник:</b> {employee_name}\n"
                f"🆔 <b>Telegram ID:</b> {request.employee_id}\n"
                f"💼 <b>Роль:</b> {employee_role}\n\n"
                f"📋 <b>Запрос:</b> {request.request_text}\n"
                f"📝 <b>Тип:</b> {request.request_type}\n"
                f"🕐 <b>Время запроса:</b> {request.created_at[:16]}\n"
                f"⏱️ <b>Прошло времени:</b> {timeout_hours} часов\n\n"
                f"💬 <b>История диалога:</b>\n"
                f"<code>{conversation_text}</code>"
            )
            
            await self.telegram_service.send_notification_to_admin(notification_text)
            logger.info(f"Эскалация отправлена администратору для сотрудника {request.employee_id}")
        
        except Exception as e:
            logger.error(f"Ошибка при эскалации администратору: {e}")
    
    def get_pending_requests(self) -> List[EmployeeRequest]:
        """Получает список ожидающих ответа запросов"""
        return [req for req in self.active_requests.values() if not req.answered]
    
    def get_request_history_for_employee(self, employee_id: int) -> List[EmployeeRequest]:
        """Получает историю запросов для сотрудника"""
        return [req for req in self.request_history if req.employee_id == employee_id]
    
    def get_weekly_statistics(self) -> dict:
        """
        Получает статистику за последние 7 дней
        
        Returns:
            Словарь со статистикой
        """
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        
        # Статистика по запросам
        recent_requests = [
            req for req in self.request_history
            if datetime.fromisoformat(req.created_at) >= week_ago
        ]
        
        pending_count = len(self.active_requests)
        answered_count = len([r for r in recent_requests if r.answered])
        total_requests = len(recent_requests) + pending_count
        
        # Статистика по сотрудникам
        active_employees = [e for e in self.employees.values() if e.is_active]
        employees_with_requests = set()
        for req in list(self.active_requests.values()) + recent_requests:
            employees_with_requests.add(req.employee_id)
        
        # Статистика по типам запросов
        request_types = {}
        for req in list(self.active_requests.values()) + recent_requests:
            req_type = req.request_type
            request_types[req_type] = request_types.get(req_type, 0) + 1
        
        return {
            'total_requests': total_requests,
            'pending_requests': pending_count,
            'answered_requests': answered_count,
            'total_employees': len(active_employees),
            'employees_with_requests': len(employees_with_requests),
            'request_types': request_types,
            'recent_requests': recent_requests[:10]  # Последние 10 запросов
        }
    
    def get_all_conversations(self) -> List[dict]:
        """
        Получает все переписки с сотрудниками
        
        Returns:
            Список словарей с информацией о переписках
        """
        conversations = []
        
        # Активные запросы
        for request in self.active_requests.values():
            employee = self.get_employee(request.employee_id)
            conversations.append({
                'employee_id': request.employee_id,
                'employee_name': employee.name if employee else f"ID: {request.employee_id}",
                'employee_role': employee.role if employee else "Не указана",
                'request': request,
                'is_active': True,
                'conversation_history': request.conversation_history
            })
        
        # Завершенные запросы (последние 50)
        for request in self.request_history[-50:]:
            employee = self.get_employee(request.employee_id)
            conversations.append({
                'employee_id': request.employee_id,
                'employee_name': employee.name if employee else f"ID: {request.employee_id}",
                'employee_role': employee.role if employee else "Не указана",
                'request': request,
                'is_active': False,
                'conversation_history': request.conversation_history
            })
        
        # Группируем по сотрудникам
        grouped = {}
        for conv in conversations:
            emp_id = conv['employee_id']
            if emp_id not in grouped:
                grouped[emp_id] = {
                    'employee_id': emp_id,
                    'employee_name': conv['employee_name'],
                    'employee_role': conv['employee_role'],
                    'requests': []
                }
            grouped[emp_id]['requests'].append(conv['request'])
        
        return list(grouped.values())
    
    def _load_content_manager(self):
        """Загружает ID ответственного за контент"""
        try:
            if self.content_manager_file.exists():
                with open(self.content_manager_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.content_manager_id = data.get('content_manager_id')
                    if self.content_manager_id:
                        logger.info(f"Загружен ответственный за контент: {self.content_manager_id}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке ответственного за контент: {e}")
            self.content_manager_id = None
    
    def _save_content_manager(self):
        """Сохраняет ID ответственного за контент"""
        try:
            data = {'content_manager_id': self.content_manager_id}
            with open(self.content_manager_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Сохранен ответственный за контент: {self.content_manager_id}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении ответственного за контент: {e}")
    
    def set_content_manager(self, employee_id: int) -> bool:
        """
        Назначает сотрудника ответственным за контент
        
        Args:
            employee_id: Telegram ID сотрудника
            
        Returns:
            True если успешно, False если сотрудник не найден
        """
        if employee_id not in self.employees:
            logger.warning(f"Сотрудник {employee_id} не найден")
            return False
        
        self.content_manager_id = employee_id
        self._save_content_manager()
        logger.info(f"Назначен ответственный за контент: {employee_id}")
        return True
    
    def remove_content_manager(self):
        """Удаляет назначение ответственного за контент"""
        self.content_manager_id = None
        self._save_content_manager()
        logger.info("Ответственный за контент удален")
    
    def get_content_manager_id(self) -> Optional[int]:
        """
        Возвращает ID ответственного за контент
        
        Returns:
            Telegram ID ответственного за контент или None
        """
        return self.content_manager_id
    
    def get_content_manager(self) -> Optional[Employee]:
        """
        Возвращает информацию об ответственном за контент
        
        Returns:
            Employee объект или None
        """
        if self.content_manager_id and self.content_manager_id in self.employees:
            return self.employees[self.content_manager_id]
        return None

