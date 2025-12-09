"""Обработчики для взаимодействия с сотрудниками"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from services.employee_service import EmployeeService

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.photo)
async def handle_photo_from_employee(message: Message, state: FSMContext):
    """Обрабатывает фотографии от сотрудников"""
    from services import dependencies
    from handlers.admin_handlers import is_admin
    
    # ВСЕГДА пропускаем сообщения от администратора (они обрабатываются в admin_handlers)
    # Это критически важно для работы FSM обработчиков из admin_handlers
    if is_admin(message.from_user.id):
        current_state = await state.get_state()
        logger.info(f"⚠️ ПРОПУСКАЕМ фото от администратора {message.from_user.id}. Текущее состояние FSM: {current_state}")
        # Возвращаемся БЕЗ обработки, чтобы FSM обработчики из admin_handlers могли обработать сообщение
        return
    
    if not dependencies.employee_service:
        return
    
    employee_id = message.from_user.id
    
    # Проверяем, есть ли активный запрос к этому сотруднику
    if employee_id in dependencies.employee_service.active_requests:
        request = dependencies.employee_service.active_requests[employee_id]
        
        if not request.answered:
            # Сохраняем фото (можно добавить сохранение файла)
            photo_info = f"Получена фотография: {message.photo[-1].file_id}"
            
            # Добавляем в историю диалога
            dependencies.employee_service.add_to_conversation(
                employee_id,
                "employee",
                photo_info
            )
            
            # Помечаем запрос как отвеченный
            dependencies.employee_service.mark_request_answered(
                employee_id,
                photo_info
            )
            
            await message.answer(
                "✅ Спасибо! Фотография получена и будет использована для поста."
            )
            
            # Уведомляем администратора
            employee = dependencies.employee_service.get_employee(employee_id)
            employee_name = employee.name if employee else f"ID: {employee_id}"
            await dependencies.telegram_service.send_notification_to_admin(
                f"✅ <b>Сотрудник ответил</b>\n\n"
                f"👤 Сотрудник: {employee_name}\n"
                f"📸 Получена фотография\n"
                f"🆔 File ID: {message.photo[-1].file_id}"
            )
            
            logger.info(f"Фотография получена от сотрудника {employee_id}")


@router.message(F.document)
async def handle_document_from_employee(message: Message, state: FSMContext):
    """Обрабатывает документы от сотрудников"""
    from services import dependencies
    from handlers.admin_handlers import is_admin
    
    # Пропускаем сообщения от администратора (они обрабатываются в admin_handlers)
    if is_admin(message.from_user.id):
        current_state = await state.get_state()
        # Если администратор находится в каком-либо FSM состоянии, пропускаем обработку
        if current_state:
            return
    
    if not dependencies.employee_service:
        return
    
    employee_id = message.from_user.id
    
    if employee_id in dependencies.employee_service.active_requests:
        request = dependencies.employee_service.active_requests[employee_id]
        
        if not request.answered:
            doc_info = f"Получен документ: {message.document.file_name} ({message.document.file_id})"
            
            dependencies.employee_service.add_to_conversation(
                employee_id,
                "employee",
                doc_info
            )
            
            dependencies.employee_service.mark_request_answered(
                employee_id,
                doc_info
            )
            
            await message.answer(
                "✅ Спасибо! Документ получен и будет использован."
            )
            
            employee = dependencies.employee_service.get_employee(employee_id)
            employee_name = employee.name if employee else f"ID: {employee_id}"
            await dependencies.telegram_service.send_notification_to_admin(
                f"✅ <b>Сотрудник ответил</b>\n\n"
                f"👤 Сотрудник: {employee_name}\n"
                f"📄 Получен документ: {message.document.file_name}"
            )
            
            logger.info(f"Документ получен от сотрудника {employee_id}")


@router.message()
async def handle_text_from_employee(message: Message, state: FSMContext):
    """Обрабатывает текстовые сообщения от сотрудников"""
    from services import dependencies
    from config.settings import settings
    
    # Пропускаем сообщения от администратора (они обрабатываются в employee_admin_handlers)
    if message.from_user.id == settings.TELEGRAM_ADMIN_ID:
        # Проверяем, есть ли активное FSM состояние
        current_state = await state.get_state()
        if current_state:
            # Если админ в FSM состоянии, не обрабатываем здесь
            return
    
    if not dependencies.employee_service:
        return
    
    employee_id = message.from_user.id
    
    # Проверяем, есть ли активный запрос
    if employee_id in dependencies.employee_service.active_requests:
        request = dependencies.employee_service.active_requests[employee_id]
        
        if not request.answered:
            # Добавляем в историю диалога
            dependencies.employee_service.add_to_conversation(
                employee_id,
                "employee",
                message.text
            )
            
            # Помечаем запрос как отвеченный
            dependencies.employee_service.mark_request_answered(
                employee_id,
                message.text
            )
            
            await message.answer(
                "✅ Спасибо! Ваш ответ получен и будет использован."
            )
            
            # Уведомляем администратора
            employee = dependencies.employee_service.get_employee(employee_id)
            employee_name = employee.name if employee else f"ID: {employee_id}"
            await dependencies.telegram_service.send_notification_to_admin(
                f"✅ <b>Сотрудник ответил</b>\n\n"
                f"👤 Сотрудник: {employee_name}\n"
                f"💬 Ответ: {message.text[:200]}"
            )
            
            logger.info(f"Ответ получен от сотрудника {employee_id}")

