"""Обработчики управления сотрудниками для администратора"""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from handlers.utils import safe_answer_callback, safe_edit_message, safe_clear_state
from services import dependencies
from config.settings import settings
from handlers.admin_handlers import is_admin
from aiogram.fsm.state import State, StatesGroup


class EmployeeManagementStates(StatesGroup):
    """Состояния для управления сотрудниками"""
    waiting_for_employee_id = State()
    waiting_for_employee_name = State()
    waiting_for_employee_role = State()
    waiting_for_request_text = State()
    waiting_for_request_type = State()
    waiting_for_reminder_interval = State()
    waiting_for_response_timeout = State()
    waiting_for_content_manager_selection = State()

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "employees_list")
async def employees_list(callback: CallbackQuery):
    """Показывает список сотрудников"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    employees = dependencies.employee_service.get_all_employees()
    
    if not employees:
        employees_text = "👥 <b>Список сотрудников</b>\n\nСотрудники не добавлены."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить сотрудника", callback_data="employee_add")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_employees")]
        ])
    else:
        employees_list_text = "\n".join([
            f"{i+1}. <b>{emp.name}</b> ({emp.role})\n   🆔 ID: {emp.telegram_id}"
            for i, emp in enumerate(employees)
        ])
        
        employees_text = (
            f"👥 <b>Список сотрудников</b>\n\n"
            f"{employees_list_text}"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить сотрудника", callback_data="employee_add")],
            [InlineKeyboardButton(text="🗑️ Удалить сотрудника", callback_data="employee_remove")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_employees")]
        ])
    
    await safe_edit_message(callback, employees_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "employee_add")
async def employee_add_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс добавления сотрудника"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await state.set_state(EmployeeManagementStates.waiting_for_employee_id)
    
    await safe_edit_message(
        callback,
        "➕ <b>Добавление сотрудника</b>\n\n"
        "Отправьте Telegram ID сотрудника (число):\n\n"
        "Или отправьте 'отмена' для отмены:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_employees")]
        ])
    )
    await safe_answer_callback(callback)


@router.message(EmployeeManagementStates.waiting_for_employee_id)
async def employee_process_id(message: Message, state: FSMContext):
    """Обрабатывает ID сотрудника"""
    logger.info(f"Получено сообщение в состоянии waiting_for_employee_id: {message.text}")
    
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    if message.text and message.text.lower() == 'отмена':
        await safe_clear_state(state)
        await message.answer("Отменено.")
        return
    
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте текст с ID сотрудника.")
        return
    
    try:
        employee_id = int(message.text.strip())
        await state.update_data(employee_id=employee_id)
        await state.set_state(EmployeeManagementStates.waiting_for_employee_name)
        
        logger.info(f"ID сотрудника обработан: {employee_id}, переход к вводу имени")
        
        await message.answer(
            f"✅ ID: {employee_id}\n\n"
            "Теперь отправьте имя сотрудника:"
        )
    except ValueError:
        logger.warning(f"Неверный формат ID: {message.text}")
        await message.answer("❌ Неверный формат. Отправьте число (Telegram ID):")
    except Exception as e:
        logger.error(f"Ошибка при обработке ID сотрудника: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


@router.message(EmployeeManagementStates.waiting_for_employee_name)
async def employee_process_name(message: Message, state: FSMContext):
    """Обрабатывает имя сотрудника"""
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте имя сотрудника.")
        return
    
    name = message.text.strip()
    await state.update_data(employee_name=name)
    await state.set_state(EmployeeManagementStates.waiting_for_employee_role)
    
    await message.answer(
        f"✅ Имя: {name}\n\n"
        "Теперь отправьте роль сотрудника (например: Менеджер, Строитель, Дизайнер):"
    )


@router.message(EmployeeManagementStates.waiting_for_employee_role)
async def employee_process_role(message: Message, state: FSMContext):
    """Обрабатывает роль сотрудника и добавляет его"""
    if not dependencies.employee_service:
        await message.answer("Сервис недоступен")
        await safe_clear_state(state)
        return
    
    role = message.text.strip()
    data = await state.get_data()
    employee_id = data.get('employee_id')
    employee_name = data.get('employee_name')
    
    if dependencies.employee_service.add_employee(employee_id, employee_name, role):
        await message.answer(
            f"✅ <b>Сотрудник добавлен!</b>\n\n"
            f"👤 Имя: {employee_name}\n"
            f"🆔 ID: {employee_id}\n"
            f"💼 Роль: {role}"
        )
    else:
        await message.answer(
            f"❌ Ошибка: Сотрудник с ID {employee_id} уже существует."
        )
    
    await safe_clear_state(state)


@router.callback_query(F.data == "employee_remove")
async def employee_remove_start(callback: CallbackQuery):
    """Начинает процесс удаления сотрудника"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    employees = dependencies.employee_service.get_all_employees()
    
    if not employees:
        await safe_answer_callback(callback, "Нет сотрудников для удаления", show_alert=True)
        return
    
    # Создаем кнопки для каждого сотрудника
    buttons = []
    for emp in employees[:10]:  # Максимум 10 кнопок
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑️ {emp.name}",
                callback_data=f"employee_remove_{emp.telegram_id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="employees_list")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await safe_edit_message(
        callback,
        "🗑️ <b>Удаление сотрудника</b>\n\n"
        "Выберите сотрудника для удаления:",
        reply_markup=keyboard
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("employee_remove_"))
async def employee_remove_confirm(callback: CallbackQuery):
    """Удаляет сотрудника"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    employee_id = int(callback.data.replace("employee_remove_", ""))
    employee = dependencies.employee_service.get_employee(employee_id)
    
    if employee and dependencies.employee_service.remove_employee(employee_id):
        await safe_answer_callback(callback, f"✅ Сотрудник {employee.name} удален", show_alert=True)
        await employees_list(callback)
    else:
        await safe_answer_callback(callback, "❌ Ошибка при удалении", show_alert=True)


@router.callback_query(F.data == "employee_request")
async def employee_request_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс отправки запроса сотруднику"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    employees = dependencies.employee_service.get_all_employees()
    
    if not employees:
        await safe_answer_callback(callback, "Нет сотрудников. Добавьте сотрудника сначала.", show_alert=True)
        return
    
    # Создаем кнопки для выбора сотрудника
    buttons = []
    for emp in employees[:10]:
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 {emp.name}",
                callback_data=f"employee_request_select_{emp.telegram_id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_employees")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await safe_edit_message(
        callback,
        "📤 <b>Отправка запроса сотруднику</b>\n\n"
        "Выберите сотрудника:",
        reply_markup=keyboard
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("employee_request_select_"))
async def employee_request_select_type(callback: CallbackQuery, state: FSMContext):
    """Выбирает тип запроса"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    employee_id = int(callback.data.replace("employee_request_select_", ""))
    employee = dependencies.employee_service.get_employee(employee_id)
    
    if not employee:
        await safe_answer_callback(callback, "Сотрудник не найден", show_alert=True)
        return
    
    await state.update_data(employee_id=employee_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📸 Фото", callback_data="request_type_photo"),
            InlineKeyboardButton(text="📄 Документ", callback_data="request_type_document")
        ],
        [
            InlineKeyboardButton(text="💬 Информация", callback_data="request_type_info"),
            InlineKeyboardButton(text="📋 Общий", callback_data="request_type_general")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="employee_request")]
    ])
    
    await safe_edit_message(
        callback,
        f"📤 <b>Отправка запроса</b>\n\n"
        f"Сотрудник: <b>{employee.name}</b>\n\n"
        f"Выберите тип запроса:",
        reply_markup=keyboard
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("request_type_"))
async def employee_request_text(callback: CallbackQuery, state: FSMContext):
    """Запрашивает текст запроса"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    request_type = callback.data.replace("request_type_", "")
    await state.update_data(request_type=request_type)
    await state.set_state(EmployeeManagementStates.waiting_for_request_text)
    
    type_names = {
        "photo": "фотографию",
        "document": "документ",
        "info": "информацию",
        "general": "материалы"
    }
    
    await safe_edit_message(
        callback,
        f"📤 <b>Отправка запроса</b>\n\n"
        f"Тип запроса: <b>{type_names.get(request_type, request_type)}</b>\n\n"
        f"Отправьте текст запроса:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_employees")]
        ])
    )
    await safe_answer_callback(callback)


@router.message(EmployeeManagementStates.waiting_for_request_text)
async def employee_request_send(message: Message, state: FSMContext):
    """Отправляет запрос сотруднику"""
    if not dependencies.employee_service:
        await message.answer("Сервис недоступен")
        await safe_clear_state(state)
        return
    
    # Проверяем наличие текста
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте текст запроса.")
        return
    
    data = await state.get_data()
    employee_id = data.get('employee_id')
    request_type = data.get('request_type', 'general')
    request_text = message.text.strip()
    
    logger.info(f"Отправка запроса сотруднику. Employee ID: {employee_id}, тип: {request_type}, текст: {request_text[:50]}...")
    
    if not employee_id:
        await message.answer("❌ Ошибка: не найден ID сотрудника. Попробуйте создать запрос заново.")
        await safe_clear_state(state)
        return
    
    employee = dependencies.employee_service.get_employee(employee_id)
    
    if not employee:
        await message.answer(
            f"❌ Сотрудник с ID {employee_id} не найден.\n\n"
            f"Проверьте список сотрудников и попробуйте снова."
        )
        await safe_clear_state(state)
        return
    
    # Отправляем запрос
    message_id = await dependencies.employee_service.send_request_to_employee(
        employee_id,
        request_text,
        request_type
    )
    
    if message_id:
        type_names = {
            "photo": "📸 Фотографию",
            "document": "📄 Документ",
            "info": "💬 Информацию",
            "general": "📋 Материалы"
        }
        
        await message.answer(
            f"✅ <b>Запрос отправлен!</b>\n\n"
            f"👤 <b>Сотрудник:</b> {employee.name} (ID: {employee_id})\n"
            f"💼 <b>Роль:</b> {employee.role}\n"
            f"📝 <b>Тип запроса:</b> {type_names.get(request_type, request_type)}\n"
            f"💬 <b>Текст:</b> {request_text[:200]}"
        )
    else:
        await message.answer(
            f"❌ Ошибка при отправке запроса.\n\n"
            f"Проверьте, что сотрудник {employee.name} (ID: {employee_id}) доступен в Telegram."
        )
    
    await safe_clear_state(state)


@router.callback_query(F.data == "employees_pending")
async def employees_pending_requests(callback: CallbackQuery):
    """Показывает активные запросы"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    pending = dependencies.employee_service.get_pending_requests()
    
    if not pending:
        requests_text = "⏳ <b>Активные запросы</b>\n\nНет активных запросов."
    else:
        requests_list = []
        for req in pending:
            employee = dependencies.employee_service.get_employee(req.employee_id)
            employee_name = employee.name if employee else f"ID: {req.employee_id}"
            created_at = datetime.fromisoformat(req.created_at)
            time_passed = datetime.now() - created_at
            
            requests_list.append(
                f"👤 <b>{employee_name}</b>\n"
                f"📝 {req.request_text[:50]}...\n"
                f"⏱️ Прошло: {int(time_passed.total_seconds() / 3600)} часов"
            )
        
        requests_text = (
            f"⏳ <b>Активные запросы</b>\n\n"
            f"{chr(10).join(requests_list)}"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_employees")]
    ])
    
    await safe_edit_message(callback, requests_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "employees_history")
async def employees_history(callback: CallbackQuery):
    """Показывает историю запросов"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    history = dependencies.employee_service.request_history[-10:]  # Последние 10
    
    if not history:
        history_text = "📜 <b>История запросов</b>\n\nИстория пуста."
    else:
        history_list = []
        for req in reversed(history):
            employee = dependencies.employee_service.get_employee(req.employee_id)
            employee_name = employee.name if employee else f"ID: {req.employee_id}"
            created_at = datetime.fromisoformat(req.created_at)
            status = "✅ Ответ получен" if req.answered else "⏳ Ожидает"
            
            history_list.append(
                f"{status} | {employee_name}\n"
                f"📝 {req.request_text[:40]}...\n"
                f"🕐 {created_at.strftime('%d.%m %H:%M')}"
            )
        
        history_text = (
            f"📜 <b>История запросов</b> (последние {len(history)})\n\n"
            f"{chr(10).join(history_list)}"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_employees")]
    ])
    
    await safe_edit_message(callback, history_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "employee_settings")
async def employee_settings_menu(callback: CallbackQuery):
    """Меню настроек таймаутов сотрудников"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    settings_service = dependencies.employee_service.settings_service
    reminder_interval = settings_service.get_reminder_interval()
    response_timeout = settings_service.get_response_timeout()
    
    settings_text = (
        "⚙️ <b>Настройки таймаутов сотрудников</b>\n\n"
        f"⏰ <b>Интервал напоминаний:</b> {reminder_interval} часов\n"
        f"   (Как часто отправлять напоминания сотрудникам)\n\n"
        f"⏱️ <b>Таймаут эскалации:</b> {response_timeout} часов\n"
        f"   (Через сколько часов отправлять уведомление администратору)\n\n"
        f"Выберите параметр для изменения:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"⏰ Интервал напоминаний ({reminder_interval}ч)",
                callback_data="employee_set_reminder_interval"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"⏱️ Таймаут эскалации ({response_timeout}ч)",
                callback_data="employee_set_response_timeout"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_employees")
        ]
    ])
    
    await safe_edit_message(callback, settings_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "employee_set_reminder_interval")
async def employee_set_reminder_interval_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс установки интервала напоминаний"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    current_interval = dependencies.employee_service.settings_service.get_reminder_interval()
    
    await state.set_state(EmployeeManagementStates.waiting_for_reminder_interval)
    
    await safe_edit_message(
        callback,
        f"⏰ <b>Установка интервала напоминаний</b>\n\n"
        f"Текущее значение: <b>{current_interval} часов</b>\n\n"
        f"Отправьте новое значение (число от 1 до 48 часов):\n\n"
        f"Или отправьте 'отмена' для отмены:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="employee_settings")]
        ])
    )
    await safe_answer_callback(callback)


@router.message(EmployeeManagementStates.waiting_for_reminder_interval)
async def employee_process_reminder_interval(message: Message, state: FSMContext):
    """Обрабатывает новое значение интервала напоминаний"""
    if not dependencies.employee_service:
        await message.answer("Сервис недоступен")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте число от 1 до 48.")
        return
    
    if message.text.lower() == 'отмена':
        await safe_clear_state(state)
        await message.answer("Отменено.")
        return
    
    try:
        hours = int(message.text.strip())
        
        if hours < 1 or hours > 48:
            await message.answer("❌ Значение должно быть от 1 до 48 часов.")
            return
        
        if dependencies.employee_service.settings_service.set_reminder_interval(hours):
            await message.answer(
                f"✅ <b>Интервал напоминаний установлен!</b>\n\n"
                f"Новое значение: <b>{hours} часов</b>\n\n"
                f"Напоминания будут отправляться каждые {hours} часов."
            )
        else:
            await message.answer("❌ Ошибка при установке значения.")
    
    except ValueError:
        await message.answer("❌ Неверный формат. Отправьте число от 1 до 48:")
    
    await safe_clear_state(state)


@router.callback_query(F.data == "employee_set_response_timeout")
async def employee_set_response_timeout_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс установки таймаута эскалации"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    current_timeout = dependencies.employee_service.settings_service.get_response_timeout()
    
    await state.set_state(EmployeeManagementStates.waiting_for_response_timeout)
    
    await safe_edit_message(
        callback,
        f"⏱️ <b>Установка таймаута эскалации</b>\n\n"
        f"Текущее значение: <b>{current_timeout} часов</b>\n\n"
        f"Отправьте новое значение (число от 1 до 168 часов / 7 дней):\n\n"
        f"Или отправьте 'отмена' для отмены:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="employee_settings")]
        ])
    )
    await safe_answer_callback(callback)


@router.message(EmployeeManagementStates.waiting_for_response_timeout)
async def employee_process_response_timeout(message: Message, state: FSMContext):
    """Обрабатывает новое значение таймаута эскалации"""
    if not dependencies.employee_service:
        await message.answer("Сервис недоступен")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте число от 1 до 168.")
        return
    
    if message.text.lower() == 'отмена':
        await safe_clear_state(state)
        await message.answer("Отменено.")
        return
    
    try:
        hours = int(message.text.strip())
        
        if hours < 1 or hours > 168:
            await message.answer("❌ Значение должно быть от 1 до 168 часов (7 дней).")
            return
        
        if dependencies.employee_service.settings_service.set_response_timeout(hours):
            await message.answer(
                f"✅ <b>Таймаут эскалации установлен!</b>\n\n"
                f"Новое значение: <b>{hours} часов</b>\n\n"
                f"Эскалация будет отправляться через {hours} часов после запроса."
            )
        else:
            await message.answer("❌ Ошибка при установке значения.")
    
    except ValueError:
        await message.answer("❌ Неверный формат. Отправьте число от 1 до 168:")
    
    await safe_clear_state(state)


@router.callback_query(F.data == "employee_content_manager")
async def employee_content_manager_menu(callback: CallbackQuery):
    """Меню управления ответственным за контент"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    content_manager = dependencies.employee_service.get_content_manager()
    
    if content_manager:
        manager_text = (
            f"👤 <b>Ответственный за контент</b>\n\n"
            f"<b>Текущий ответственный:</b>\n"
            f"• Имя: <b>{content_manager.name}</b>\n"
            f"• Роль: {content_manager.role}\n"
            f"• ID: {content_manager.telegram_id}\n\n"
            f"Ответственный за контент получает уведомления об отсутствии фотографий для постов."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить", callback_data="employee_content_manager_set")],
            [InlineKeyboardButton(text="🗑️ Удалить", callback_data="employee_content_manager_remove")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_employees")]
        ])
    else:
        manager_text = (
            f"👤 <b>Ответственный за контент</b>\n\n"
            f"Ответственный за контент не назначен.\n\n"
            f"Ответственный за контент получает уведомления об отсутствии фотографий для постов."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Назначить", callback_data="employee_content_manager_set")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_employees")]
        ])
    
    await safe_edit_message(callback, manager_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "employee_content_manager_set")
async def employee_content_manager_set_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс назначения ответственного за контент"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    employees = dependencies.employee_service.get_all_employees()
    
    if not employees:
        await safe_answer_callback(callback, "Нет сотрудников для назначения", show_alert=True)
        return
    
    buttons = []
    for emp in employees:
        button_text = f"{emp.name} ({emp.role})"
        if len(button_text) > 30:
            button_text = button_text[:27] + "..."
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"employee_content_manager_select_{emp.telegram_id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="employee_content_manager")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await safe_edit_message(
        callback,
        "👤 <b>Назначение ответственного за контент</b>\n\n"
        "Выберите сотрудника:",
        reply_markup=keyboard
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("employee_content_manager_select_"))
async def employee_content_manager_set_confirm(callback: CallbackQuery):
    """Подтверждает назначение ответственного за контент"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    employee_id = int(callback.data.replace("employee_content_manager_select_", ""))
    employee = dependencies.employee_service.get_employee(employee_id)
    
    if not employee:
        await safe_answer_callback(callback, "Сотрудник не найден", show_alert=True)
        return
    
    success = dependencies.employee_service.set_content_manager(employee_id)
    
    if success:
        await safe_edit_message(
            callback,
            f"✅ <b>Ответственный за контент назначен!</b>\n\n"
            f"<b>Сотрудник:</b> {employee.name}\n"
            f"<b>Роль:</b> {employee.role}\n"
            f"<b>ID:</b> {employee.telegram_id}\n\n"
            f"Теперь этот сотрудник будет получать уведомления об отсутствии фотографий для постов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="employee_content_manager")]
            ])
        )
    else:
        await safe_answer_callback(callback, "Ошибка при назначении", show_alert=True)
    
    await safe_answer_callback(callback)


@router.callback_query(F.data == "employee_content_manager_remove")
async def employee_content_manager_remove(callback: CallbackQuery):
    """Удаляет назначение ответственного за контент"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    dependencies.employee_service.remove_content_manager()
    
    await safe_edit_message(
        callback,
        "✅ <b>Ответственный за контент удален</b>\n\n"
        "Уведомления об отсутствии фотографий будут отправляться только администраторам.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="employee_content_manager")]
        ])
    )
    await safe_answer_callback(callback)

