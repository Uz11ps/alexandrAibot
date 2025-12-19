"""Обработчики команд администратора"""
import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config.settings import settings
from services import dependencies
from services.schedule_config import ScheduleConfigService
from services.post_types_config import PostTypesConfigService
from handlers.utils import safe_answer_callback, safe_edit_message, safe_clear_state

logger = logging.getLogger(__name__)
router = Router()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру главного меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статус бота", callback_data="menu_status"),
            InlineKeyboardButton(text="📤 Загрузить файл", callback_data="menu_upload")
        ],
        [
            InlineKeyboardButton(text="📅 Расписание", callback_data="menu_schedule"),
            InlineKeyboardButton(text="👥 Сотрудники", callback_data="menu_employees")
        ],
        [
            InlineKeyboardButton(text="📝 Сгенерировать пост", callback_data="menu_generate"),
            InlineKeyboardButton(text="📋 Отчеты", callback_data="menu_reports")
        ],
        [
            InlineKeyboardButton(text="🔗 Управление источниками", callback_data="menu_sources"),
            InlineKeyboardButton(text="📅 Запланированные посты", callback_data="menu_scheduled_posts")
        ],
        [
            InlineKeyboardButton(text="✏️ Редактировать промпты", callback_data="menu_prompts")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки уведомлений", callback_data="menu_notifications")
        ],
        [
            InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data="post_now")
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить меню", callback_data="menu_refresh")
        ]
    ])
    return keyboard


def get_upload_folder_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора папки для загрузки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📸 Фотографии", callback_data="upload_photos"),
            InlineKeyboardButton(text="📝 Черновики", callback_data="upload_drafts")
        ],
        [
            InlineKeyboardButton(text="📚 Законы", callback_data="upload_laws"),
            InlineKeyboardButton(text="😄 Мемы", callback_data="upload_memes")
        ],
        [
            InlineKeyboardButton(text="💼 Услуги", callback_data="upload_services"),
            InlineKeyboardButton(text="📦 Архив", callback_data="upload_archive")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")
        ]
    ])
    return keyboard


def get_generate_post_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора типа поста для генерации"""
    post_types_config = PostTypesConfigService()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Понедельник ({post_types_config.get_post_type('monday')['name']})",
                callback_data="generate_monday"
            ),
            InlineKeyboardButton(
                text=f"Вторник ({post_types_config.get_post_type('tuesday')['name']})",
                callback_data="generate_tuesday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Среда ({post_types_config.get_post_type('wednesday')['name']})",
                callback_data="generate_wednesday"
            ),
            InlineKeyboardButton(
                text=f"Четверг ({post_types_config.get_post_type('thursday')['name']})",
                callback_data="generate_thursday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Пятница ({post_types_config.get_post_type('friday')['name']})",
                callback_data="generate_friday"
            ),
            InlineKeyboardButton(
                text=f"Суббота ({post_types_config.get_post_type('saturday')['name']})",
                callback_data="generate_saturday"
            )
        ],
        [
            InlineKeyboardButton(text="⚙️ Настроить типы постов", callback_data="post_types_edit")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")
        ]
    ])
    return keyboard


class PostApprovalStates(StatesGroup):
    """Состояния для процесса согласования поста"""
    waiting_for_edits = State()


class FileUploadStates(StatesGroup):
    """Состояния для загрузки файлов"""
    waiting_for_folder_type = State()
    waiting_for_file = State()


class ScheduleEditStates(StatesGroup):
    """Состояния для редактирования расписания"""
    waiting_for_day = State()
    waiting_for_time = State()


class PostTypeEditStates(StatesGroup):
    """Состояния для редактирования типов постов"""
    waiting_for_day = State()
    waiting_for_name = State()
    waiting_for_description = State()


class EmployeeManagementStates(StatesGroup):
    """Состояния для управления сотрудниками"""
    waiting_for_employee_id = State()
    waiting_for_employee_name = State()
    waiting_for_employee_role = State()
    waiting_for_request_text = State()
    waiting_for_request_type = State()


class PromptEditStates(StatesGroup):
    """Состояния для редактирования промптов"""
    waiting_for_prompt_selection = State()
    waiting_for_prompt_text = State()


class SchedulePostStates(StatesGroup):
    """Состояния для управления постами в расписании"""
    waiting_for_day = State()
    waiting_for_time = State()
    waiting_for_post_name = State()
    waiting_for_post_description = State()
    waiting_for_post_index = State()


class PostNowStates(StatesGroup):
    """Состояния для функции 'Опубликовать сейчас'"""
    waiting_for_photo = State()
    waiting_for_prompt = State()
    waiting_for_sources = State()  # Ожидание источников (опционально)
    waiting_for_approval = State()  # Ожидание одобрения сгенерированного поста


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    # Проверяем основной ID администратора
    if user_id == settings.TELEGRAM_ADMIN_ID:
        return True
    
    # Проверяем дополнительные ID администраторов
    if settings.TELEGRAM_ADMIN_IDS:
        admin_ids = [int(id.strip()) for id in settings.TELEGRAM_ADMIN_IDS.split(',') if id.strip()]
        if user_id in admin_ids:
            return True
    
    return False


def is_employee(user_id: int) -> bool:
    """Проверяет, является ли пользователь сотрудником"""
    if not dependencies.employee_service:
        return False
    
    employee = dependencies.employee_service.get_employee(user_id)
    return employee is not None and employee.is_active


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором или сотрудником
    if not is_admin(user_id) and not is_employee(user_id):
        await message.answer("У вас нет доступа к этому боту.")
        return
    
    # Администраторы получают полное меню
    if is_admin(user_id):
        await message.answer(
            "👋 <b>Добро пожаловать в панель управления ботом!</b>\n\n"
            "Используйте кнопки ниже для навигации по меню.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        # Сотрудники получают ограниченное меню (только для отправки материалов)
        await message.answer(
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Вы можете отправлять фотографии, документы и текстовые сообщения. "
            "Администратор получит ваши материалы.",
            parse_mode="HTML"
        )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Показывает главное меню администратора"""
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором или сотрудником
    if not is_admin(user_id) and not is_employee(user_id):
        await message.answer("У вас нет доступа.")
        return
    
    # Только администраторы получают полное меню
    if not is_admin(user_id):
        await message.answer(
            "📋 <b>Меню</b>\n\n"
            "Вы можете отправлять фотографии, документы и текстовые сообщения. "
            "Администратор получит ваши материалы.",
            parse_mode="HTML"
        )
        return
    
    await message.answer(
        "📋 <b>Главное меню</b>\n\n"
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu_back")
async def menu_back(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await safe_clear_state(state, callback)
    await safe_edit_message(
        callback,
        "📋 <b>Главное меню</b>\n\n"
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard()
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data == "menu_refresh")
async def menu_refresh(callback: CallbackQuery):
    """Обновление меню"""
    await safe_edit_message(
        callback,
        "📋 <b>Главное меню</b>\n\n"
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard()
    )
    await safe_answer_callback(callback, "Меню обновлено")


@router.callback_query(F.data == "menu_status")
async def menu_status(callback: CallbackQuery):
    """Показывает статус бота через меню"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.scheduler_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    # Проверяем количество файлов в Google Drive
    photos_count = 0
    if dependencies.file_service and dependencies.file_service.google_drive and dependencies.file_service.google_drive.enabled:
        folder_id = dependencies.file_service.google_drive.get_folder_id('photos')
        if folder_id:
            files = dependencies.file_service.google_drive.list_files(
                folder_id=folder_id,
                mime_type=None,
                limit=100
            )
            # Фильтруем только изображения
            image_mime_types = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'}
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
            photos_count = sum(1 for f in files if 
                f.get('mimeType', '') in image_mime_types or 
                Path(f.get('name', '')).suffix.lower() in image_extensions)
    
    # Получаем список всех администраторов
    admin_ids = [settings.TELEGRAM_ADMIN_ID]
    if settings.TELEGRAM_ADMIN_IDS:
        admin_ids_list = [int(id.strip()) for id in settings.TELEGRAM_ADMIN_IDS.split(',') if id.strip()]
        admin_ids.extend(admin_ids_list)
    
    admin_list = "\n".join([f"  • <code>{admin_id}</code>" for admin_id in admin_ids])
    
    status_text = (
        f"📊 <b>Статус бота</b>\n\n"
        f"Планировщик: {'✅ Включен' if dependencies.scheduler_service.is_enabled else '❌ Выключен'}\n"
        f"Задач в расписании: {len(dependencies.scheduler_service.scheduler.get_jobs())}\n"
        f"Google Drive: {'✅ Включен' if (dependencies.file_service and dependencies.file_service.google_drive and dependencies.file_service.google_drive.enabled) else '❌ Выключен'}\n"
        f"Фотографий в Drive: <b>{photos_count}</b>\n\n"
        f"👥 <b>Администраторы ({len(admin_ids)}):</b>\n{admin_list}\n\n"
        f"Бот работает и готов к работе!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Тест уведомлений", callback_data="test_notifications")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
    ])
    
    await safe_edit_message(callback, status_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "test_notifications")
async def test_notifications(callback: CallbackQuery):
    """Тестовая отправка уведомлений всем администраторам"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await safe_answer_callback(callback, "Отправляю тестовые уведомления...")
    
    # Получаем список всех администраторов
    admin_ids = [settings.TELEGRAM_ADMIN_ID]
    if settings.TELEGRAM_ADMIN_IDS:
        admin_ids_list = [int(id.strip()) for id in settings.TELEGRAM_ADMIN_IDS.split(',') if id.strip()]
        admin_ids.extend(admin_ids_list)
    
    # Отправляем тестовое уведомление каждому администратору
    success_count = 0
    failed_ids = []
    
    test_message = (
        "🧪 <b>Тестовое уведомление</b>\n\n"
        "Это тестовое сообщение для проверки отправки уведомлений всем администраторам.\n\n"
        "Если вы получили это сообщение, значит система уведомлений работает корректно! ✅"
    )
    
    for admin_id in admin_ids:
        try:
            await callback.message.bot.send_message(
                chat_id=admin_id,
                text=test_message,
                parse_mode="HTML"
            )
            success_count += 1
            logger.info(f"Тестовое уведомление отправлено администратору {admin_id}")
        except Exception as e:
            failed_ids.append((admin_id, str(e)))
            logger.error(f"Ошибка при отправке тестового уведомления администратору {admin_id}: {e}")
    
    # Отправляем отчет о результатах
    result_text = (
        f"📊 <b>Результаты теста уведомлений</b>\n\n"
        f"✅ Успешно отправлено: <b>{success_count}</b> из {len(admin_ids)}\n"
    )
    
    if failed_ids:
        result_text += f"\n❌ Ошибки:\n"
        for admin_id, error in failed_ids:
            result_text += f"  • <code>{admin_id}</code>: {error[:50]}...\n"
    else:
        result_text += "\n✅ Все уведомления успешно доставлены!"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к статусу", callback_data="menu_status")]
    ])
    
    await callback.message.answer(result_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "menu_notifications")
async def menu_notifications(callback: CallbackQuery):
    """Меню настроек уведомлений"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.notification_settings_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    draft_enabled = dependencies.notification_settings_service.is_draft_notifications_enabled()
    status_icon = "✅" if draft_enabled else "❌"
    status_text = "включены" if draft_enabled else "отключены"
    
    text = (
        f"⚙️ <b>Настройки уведомлений</b>\n\n"
        f"📝 Уведомления о черновиках: {status_icon} {status_text.capitalize()}\n\n"
        f"Выберите действие:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"{'❌ Отключить' if draft_enabled else '✅ Включить'} уведомления о черновиках",
                callback_data="toggle_draft_notifications"
            )
        ],
        [
            InlineKeyboardButton(text="📜 История запросов", callback_data="menu_post_history")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")
        ]
    ])
    
    await safe_edit_message(callback, text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "toggle_draft_notifications")
async def toggle_draft_notifications(callback: CallbackQuery):
    """Переключает уведомления о черновиках"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.notification_settings_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    current_status = dependencies.notification_settings_service.is_draft_notifications_enabled()
    new_status = not current_status
    dependencies.notification_settings_service.set_draft_notifications(new_status)
    
    status_text = "включены" if new_status else "отключены"
    await safe_answer_callback(callback, f"Уведомления о черновиках {status_text}")
    
    # Обновляем меню
    await menu_notifications(callback)


@router.callback_query(F.data == "menu_post_history")
async def menu_post_history(callback: CallbackQuery):
    """Показывает историю запросов постов"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.post_history_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    history = dependencies.post_history_service.get_history(limit=20)
    
    if not history:
        history_text = "📜 <b>История запросов постов</b>\n\nИстория пуста."
    else:
        history_list = []
        for req in reversed(history[-10:]):  # Последние 10
            created_at = datetime.fromisoformat(req.created_at)
            status_icon = "✅" if req.status == "completed" else "⏳" if req.status == "pending" else "❌"
            type_name = {
                "generate": "Генерация",
                "edit": "Редактирование",
                "publish_now": "Опубликовать сейчас"
            }.get(req.request_type, req.request_type)
            
            prompt_preview = req.prompt[:50] + "..." if len(req.prompt) > 50 else req.prompt
            
            history_list.append(
                f"{status_icon} <b>{type_name}</b>\n"
                f"📝 {prompt_preview}\n"
                f"🕐 {created_at.strftime('%d.%m %H:%M')}"
            )
        
        history_text = (
            f"📜 <b>История запросов постов</b> (последние {len(history_list)})\n\n"
            f"{chr(10).join(history_list)}"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_notifications")]
    ])
    
    await safe_edit_message(callback, history_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "menu_upload")
async def menu_upload(callback: CallbackQuery):
    """Меню загрузки файлов"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.file_service or not dependencies.file_service.google_drive or not dependencies.file_service.google_drive.enabled:
        await safe_answer_callback(
            callback,
            "❌ Google Drive не настроен",
            show_alert=True
        )
        return
    
    await safe_edit_message(
        callback,
        "📤 <b>Загрузка файла в Google Drive</b>\n\n"
        "Выберите папку для загрузки:",
        reply_markup=get_upload_folder_keyboard()
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("upload_"))
async def handle_upload_folder(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора папки для загрузки"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    folder_type = callback.data.replace("upload_", "")
    
    await state.update_data(folder_type=folder_type)
    await state.set_state(FileUploadStates.waiting_for_file)
    
    folder_names = {
        'photos': '📸 Фотографии объектов',
        'drafts': '📝 Черновики',
        'laws': '📚 Документы с законами',
        'memes': '😄 Мемы и визуальный контент',
        'services': '💼 Материалы об услугах',
        'archive': '📦 Архив'
    }
    
    await safe_edit_message(
        callback,
        f"✅ Выбрана папка: <b>{folder_names.get(folder_type, folder_type)}</b>\n\n"
        "Теперь отправьте файл (фото или документ):"
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data == "menu_generate")
async def menu_generate(callback: CallbackQuery):
    """Меню генерации постов"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    post_types_config = PostTypesConfigService()
    
    types_text = "📝 <b>Генерация поста</b>\n\n"
    types_text += "<b>Текущие типы постов:</b>\n"
    day_names_ru = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    for day, day_name in day_names_ru.items():
        # Используем get_post_type для получения первого поста (словарь)
        post_type = post_types_config.get_post_type(day)
        types_text += f"• {day_name}: <b>{post_type.get('name', 'Не указан')}</b>\n"
    
    types_text += "\n\nВыберите тип поста для генерации или настройте типы:"
    
    await safe_edit_message(
        callback,
        types_text,
        reply_markup=get_generate_post_keyboard()
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("generate_"))
async def handle_generate_post(callback: CallbackQuery):
    """Обработчик генерации поста"""
    try:
        logger.info(f"Получен callback для генерации поста: {callback.data} от пользователя {callback.from_user.id}")
        
        if not is_admin(callback.from_user.id):
            logger.warning(f"Попытка доступа не администратора: {callback.from_user.id}")
            await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
            return
        
        if not dependencies.post_service:
            logger.error("PostService недоступен")
            await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
            return
        
        post_type = callback.data.replace("generate_", "")
        logger.info(f"Тип поста: {post_type}")
        
        post_generators = {
            'monday': ('Понедельник', dependencies.post_service.generate_monday_post),
            'tuesday': ('Вторник', dependencies.post_service.generate_tuesday_post),
            'wednesday': ('Среда', dependencies.post_service.generate_wednesday_post),
            'thursday': ('Четверг', dependencies.post_service.generate_thursday_post),
            'friday': ('Пятница', dependencies.post_service.generate_friday_post),
            'saturday': ('Суббота', dependencies.post_service.generate_saturday_post)
        }
        
        if post_type not in post_generators:
            logger.error(f"Неизвестный тип поста: {post_type}")
            await safe_answer_callback(callback, "Неизвестный тип поста", show_alert=True)
            return
        
        day_name, generator = post_generators[post_type]
        logger.info(f"Выбран генератор для {day_name}")
        
        # ВАЖНО: Отвечаем на callback СРАЗУ, до начала длительной операции
        await safe_answer_callback(callback, "Генерация поста...")
        logger.info("Ответ на callback отправлен")
        
        # Показываем индикатор загрузки
        await safe_edit_message(
            callback,
            f"⏳ <b>Генерирую пост для {day_name}...</b>\n\n"
            f"Пожалуйста, подождите. Это может занять некоторое время.\n\n"
            f"📝 Анализирую материалы...\n"
            f"🤖 Генерирую текст...",
            reply_markup=None
        )
        logger.info("Сообщение о загрузке отправлено")
        
        logger.info(f"Начало генерации поста для {day_name} (тип: {post_type})")
        
        post_text, photos = await generator()
        
        logger.info(f"Пост для {day_name} сгенерирован успешно. Текст: {len(post_text)} символов, фото: {len(photos)}")
        
        # Отправляем на согласование с указанием дня недели
        logger.info(f"Отправка поста на согласование для дня: {post_type}")
        await dependencies.post_service.send_for_approval(post_text, photos, day_of_week=post_type)
        logger.info(f"Пост отправлен на согласование")
        
        await safe_edit_message(
            callback,
            f"✅ <b>Пост для {day_name} сгенерирован!</b>\n\n"
            f"Черновик отправлен на согласование.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
            ])
        )
        logger.info("Сообщение об успехе отправлено")
        
    except Exception as e:
        logger.error(f"Ошибка при генерации поста: {e}", exc_info=True)
        try:
            await safe_answer_callback(callback, f"Ошибка: {str(e)[:100]}", show_alert=True)
            await safe_edit_message(
                callback,
                f"❌ <b>Ошибка при генерации поста</b>\n\n"
                f"{str(e)}\n\n"
                f"Попробуйте еще раз или проверьте логи.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
                ])
            )
        except Exception as e2:
            logger.error(f"Ошибка при отправке сообщения об ошибке: {e2}", exc_info=True)


def get_schedule_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора дня недели"""
    schedule_config = ScheduleConfigService()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Понедельник ({schedule_config.get_schedule_time('monday')})",
                callback_data="schedule_edit_monday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Вторник ({schedule_config.get_schedule_time('tuesday')})",
                callback_data="schedule_edit_tuesday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Среда ({schedule_config.get_schedule_time('wednesday')})",
                callback_data="schedule_edit_wednesday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Четверг ({schedule_config.get_schedule_time('thursday')})",
                callback_data="schedule_edit_thursday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Пятница ({schedule_config.get_schedule_time('friday')})",
                callback_data="schedule_edit_friday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Суббота ({schedule_config.get_schedule_time('saturday')})",
                callback_data="schedule_edit_saturday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Воскресенье ({schedule_config.get_schedule_time('sunday')})",
                callback_data="schedule_edit_sunday"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")
        ]
    ])
    return keyboard


@router.callback_query(F.data == "menu_schedule")
async def menu_schedule(callback: CallbackQuery):
    """Меню расписания публикаций"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    post_types_config = PostTypesConfigService()
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    schedule_lines = []
    for day_key, day_name in day_names.items():
        posts = post_types_config.get_post_types(day_key)
        if posts:
            post_list = []
            for i, post in enumerate(posts):
                status = "✅" if post.get('enabled', True) else "❌"
                post_list.append(f"  {status} {post.get('time', '09:00')} - {post.get('name', 'Без названия')}")
            schedule_lines.append(f"<b>{day_name}:</b>\n" + "\n".join(post_list))
        else:
            schedule_lines.append(f"<b>{day_name}:</b> Нет постов")
    
    schedule_text = (
        "📅 <b>Расписание публикаций</b>\n\n"
        + "\n\n".join(schedule_lines) +
        "\n\nВыберите действие:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить пост", callback_data="schedule_add_post")],
        [InlineKeyboardButton(text="✏️ Редактировать пост", callback_data="schedule_edit_post_list")],
        [InlineKeyboardButton(text="🗑️ Удалить пост", callback_data="schedule_delete_post_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
    ])
    
    await safe_edit_message(callback, schedule_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("schedule_edit_"))
async def schedule_edit_day(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора дня для редактирования"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    day = callback.data.replace("schedule_edit_", "")
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота',
        'sunday': 'Воскресенье'
    }
    
    day_name = day_names.get(day)
    if not day_name:
        await safe_answer_callback(callback, "Неизвестный день", show_alert=True)
        return
    
    schedule_config = ScheduleConfigService()
    current_time = schedule_config.get_schedule_time(day)
    
    await state.update_data(day=day)
    await state.set_state(ScheduleEditStates.waiting_for_time)
    
    await safe_edit_message(
        callback,
        f"📅 <b>Изменение расписания</b>\n\n"
        f"День: <b>{day_name}</b>\n"
        f"Текущее время: <b>{current_time}</b>\n\n"
        "Введите новое время в формате <b>HH:MM</b>\n"
        "Например: 09:00, 14:30, 18:15\n\n"
        "Или отправьте 'отмена' для отмены:"
    )
    await safe_answer_callback(callback)


@router.message(ScheduleEditStates.waiting_for_time)
async def schedule_process_time(message: Message, state: FSMContext):
    """Обрабатывает ввод нового времени"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await state.clear()
        return
    
    time_str = message.text.strip()
    
    # Проверка на отмену
    if time_str.lower() in ['отмена', 'cancel', 'назад']:
        await state.clear()
        await message.answer("❌ Изменение расписания отменено.", reply_markup=get_main_menu_keyboard())
        return
    
    # Проверка формата времени
    import re
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        await message.answer(
            "❌ Неверный формат времени!\n\n"
            "Используйте формат <b>HH:MM</b>\n"
            "Например: 09:00, 14:30, 18:15\n\n"
            "Попробуйте снова или отправьте 'отмена':",
            parse_mode="HTML"
        )
        return
    
    data = await state.get_data()
    day = data.get('day')
    
    if not day:
        await message.answer("Ошибка: день не указан")
        await state.clear()
        return
    
    schedule_config = ScheduleConfigService()
    
    # Обновляем время в .env
    if schedule_config.update_schedule_time(day, time_str):
        day_names = {
            'monday': 'Понедельник',
            'tuesday': 'Вторник',
            'wednesday': 'Среда',
            'thursday': 'Четверг',
            'friday': 'Пятница',
            'saturday': 'Суббота',
            'sunday': 'Воскресенье'
        }
        
        day_name = day_names.get(day, day)
        
        # Обновляем планировщик
        try:
            # Обновляем планировщик с перезагрузкой настроек
            if dependencies.scheduler_service:
                dependencies.scheduler_service.setup_schedule(reload_settings=True)
            
            await message.answer(
                f"✅ <b>Расписание обновлено!</b>\n\n"
                f"День: <b>{day_name}</b>\n"
                f"Новое время: <b>{time_str}</b>\n\n"
                "Изменения применены. Планировщик обновлен.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении планировщика: {e}")
            await message.answer(
                f"✅ Время сохранено в .env файл.\n\n"
                f"⚠️ Для применения изменений перезапустите бота.\n\n"
                f"День: <b>{day_name}</b>\n"
                f"Новое время: <b>{time_str}</b>",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="HTML"
            )
    else:
        await message.answer(
            "❌ Ошибка при сохранении расписания.\n"
            "Проверьте логи для подробностей.",
            reply_markup=get_main_menu_keyboard()
        )
    
    await state.clear()


@router.callback_query(F.data == "menu_employees")
async def menu_employees(callback: CallbackQuery):
    """Меню сотрудников"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    employees = dependencies.employee_service.get_all_employees()
    pending_requests = dependencies.employee_service.get_pending_requests()
    settings_service = dependencies.employee_service.settings_service
    
    reminder_interval = settings_service.get_reminder_interval()
    response_timeout = settings_service.get_response_timeout()
    
    # Получаем информацию об ответственном за контент
    content_manager = dependencies.employee_service.get_content_manager()
    content_manager_text = "Не назначен"
    if content_manager:
        content_manager_text = f"{content_manager.name} ({content_manager.role})"
    
    employees_text = (
        "👥 <b>Управление сотрудниками</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего сотрудников: {len(employees)}\n"
        f"• Активных запросов: {len(pending_requests)}\n"
        f"• Ответственный за контент: <b>{content_manager_text}</b>\n\n"
        f"⚙️ <b>Настройки таймаутов:</b>\n"
        f"• Интервал напоминаний: <b>{reminder_interval} часов</b>\n"
        f"• Таймаут эскалации: <b>{response_timeout} часов</b>\n\n"
        f"<b>Функции:</b>\n"
        f"• Запрос материалов у сотрудников\n"
        f"• Автоматические напоминания\n"
        f"• Эскалация при отсутствии ответа"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Список сотрудников", callback_data="employees_list"),
            InlineKeyboardButton(text="➕ Добавить сотрудника", callback_data="employee_add")
        ],
        [
            InlineKeyboardButton(text="📤 Отправить запрос", callback_data="employee_request"),
            InlineKeyboardButton(text="⏳ Активные запросы", callback_data="employees_pending")
        ],
        [
            InlineKeyboardButton(text="📜 История запросов", callback_data="employees_history")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки таймаутов", callback_data="employee_settings")
        ],
        [
            InlineKeyboardButton(text="👤 Ответственный за контент", callback_data="employee_content_manager")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")
        ]
    ])
    
    await safe_edit_message(callback, employees_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "menu_reports")
async def menu_reports(callback: CallbackQuery):
    """Меню отчетов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    reports_text = (
        "📋 <b>Отчеты</b>\n\n"
        "Доступные отчеты:\n"
        "• Отчеты за неделю\n"
        "• История публикаций\n"
        "• Переписка с сотрудниками"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Отчеты за неделю", callback_data="reports_weekly")
        ],
        [
            InlineKeyboardButton(text="📚 История публикаций", callback_data="reports_history")
        ],
        [
            InlineKeyboardButton(text="💬 Переписка с сотрудниками", callback_data="reports_conversations")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")
        ]
    ])
    
    await safe_edit_message(callback, reports_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "menu_scheduled_posts")
async def menu_scheduled_posts(callback: CallbackQuery):
    """Меню запланированных постов"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.scheduled_posts_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    scheduled_posts = dependencies.scheduled_posts_service.get_all_scheduled_posts()
    
    if not scheduled_posts:
        posts_text = (
            "📅 <b>Запланированные посты</b>\n\n"
            "Нет запланированных постов.\n\n"
            "Посты будут появляться здесь после того, как вы нажмете 'Принять' при генерации поста."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
        ])
    else:
        day_names = {
            'monday': 'Понедельник',
            'tuesday': 'Вторник',
            'wednesday': 'Среда',
            'thursday': 'Четверг',
            'friday': 'Пятница',
            'saturday': 'Суббота'
        }
        
        posts_list = []
        for post in scheduled_posts:
            day_name = day_names.get(post.day_of_week, post.day_of_week)
            created_date = datetime.fromisoformat(post.created_at).strftime("%d.%m %H:%M")
            text_preview = post.post_text[:100].replace('\n', ' ') + "..." if len(post.post_text) > 100 else post.post_text.replace('\n', ' ')
            photos_count = len(post.photos)
            
            posts_list.append(
                f"📅 <b>{day_name}</b>\n"
                f"📝 {text_preview}\n"
                f"📸 Фото: {photos_count}\n"
                f"🕐 Создан: {created_date}"
            )
        
        posts_text = (
            f"📅 <b>Запланированные посты</b>\n\n"
            f"Всего запланировано: {len(scheduled_posts)}\n\n"
            f"{chr(10).join(posts_list)}"
        )
        
        keyboard_buttons = []
        for post in scheduled_posts:
            day_name = day_names.get(post.day_of_week, post.day_of_week)
            button_text = f"📅 {day_name}"
            if len(button_text) > 30:
                button_text = button_text[:27] + "..."
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_scheduled_post_{post.day_of_week}"
                )
            ])
        
        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await safe_edit_message(callback, posts_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("view_scheduled_post_"))
async def view_scheduled_post(callback: CallbackQuery, state: FSMContext):
    """Просмотр конкретного запланированного поста"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.scheduled_posts_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    # Очищаем состояние FSM если было установлено (например, при отмене редактирования)
    current_state = await state.get_state()
    if current_state:
        await safe_clear_state(state)
    
    day_of_week = callback.data.replace("view_scheduled_post_", "")
    scheduled_post = dependencies.scheduled_posts_service.get_scheduled_post(day_of_week)
    
    if not scheduled_post:
        await safe_answer_callback(callback, "Запланированный пост не найден", show_alert=True)
        return
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    day_name = day_names.get(day_of_week, day_of_week)
    created_date = datetime.fromisoformat(scheduled_post.created_at).strftime("%d.%m.%Y %H:%M")
    
    # Обрезаем текст если слишком длинный для отображения
    display_text = scheduled_post.post_text
    if len(display_text) > 3000:
        display_text = display_text[:3000] + "\n\n... (текст обрезан)"
    
    post_text = (
        f"📅 <b>Запланированный пост</b>\n\n"
        f"📆 День: <b>{day_name}</b>\n"
        f"🕐 Создан: {created_date}\n"
        f"📸 Фото: {len(scheduled_post.photos)}\n\n"
        f"<b>Текст поста:</b>\n\n{display_text}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_scheduled_post_{day_of_week}"),
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_scheduled_post_{day_of_week}")
        ],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="menu_scheduled_posts")]
    ])
    
    await safe_edit_message(callback, post_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("delete_scheduled_post_"))
async def delete_scheduled_post(callback: CallbackQuery):
    """Удаляет запланированный пост"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.scheduled_posts_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    day_of_week = callback.data.replace("delete_scheduled_post_", "")
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    day_name = day_names.get(day_of_week, day_of_week)
    
    success = dependencies.scheduled_posts_service.remove_scheduled_post(day_of_week)
    
    if success:
        await safe_answer_callback(callback, f"Пост для {day_name} удален", show_alert=True)
        await menu_scheduled_posts(callback)  # Возвращаемся к списку
    else:
        await safe_answer_callback(callback, "Ошибка при удалении поста", show_alert=True)


@router.callback_query(F.data.startswith("edit_scheduled_post_"))
async def edit_scheduled_post_start(callback: CallbackQuery, state: FSMContext):
    """Начинает редактирование запланированного поста"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.scheduled_posts_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    day_of_week = callback.data.replace("edit_scheduled_post_", "")
    scheduled_post = dependencies.scheduled_posts_service.get_scheduled_post(day_of_week)
    
    if not scheduled_post:
        await safe_answer_callback(callback, "Запланированный пост не найден", show_alert=True)
        return
    
    # Сохраняем данные в состояние для редактирования
    await state.update_data(
        scheduled_post_day=day_of_week,
        original_post_text=scheduled_post.post_text,
        original_photos=scheduled_post.photos
    )
    await state.set_state(PostApprovalStates.waiting_for_edits)
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    day_name = day_names.get(day_of_week, day_of_week)
    
    await safe_edit_message(
        callback,
        f"✏️ <b>Редактирование запланированного поста</b>\n\n"
        f"📅 День: <b>{day_name}</b>\n\n"
        f"Отправьте новый текст поста или правки:\n\n"
        f"Текущий текст:\n{scheduled_post.post_text[:500]}...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_scheduled_post_{day_of_week}")]
        ])
    )
    await safe_answer_callback(callback)




@router.callback_query(F.data == "reports_weekly")
async def reports_weekly(callback: CallbackQuery):
    """Отчеты за неделю"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service or not dependencies.file_service:
        await safe_answer_callback(callback, "Сервисы недоступны", show_alert=True)
        return
    
    # Получаем статистику
    stats = dependencies.employee_service.get_weekly_statistics()
    archived_posts = await dependencies.file_service.get_archived_posts(days=7)
    
    # Формируем отчет
    type_names = {
        "photo": "📸 Фотографии",
        "document": "📄 Документы",
        "info": "💬 Информация",
        "general": "📋 Общие"
    }
    
    request_types_text = "\n".join([
        f"• {type_names.get(t, t)}: {count}"
        for t, count in stats['request_types'].items()
    ]) if stats['request_types'] else "• Нет запросов"
    
    report_text = (
        f"📊 <b>Отчет за неделю</b>\n\n"
        f"📅 <b>Период:</b> {datetime.now().strftime('%d.%m.%Y')}\n\n"
        f"📝 <b>Публикации:</b>\n"
        f"• Опубликовано постов: <b>{len(archived_posts)}</b>\n\n"
        f"👥 <b>Сотрудники:</b>\n"
        f"• Всего сотрудников: <b>{stats['total_employees']}</b>\n"
        f"• С активными запросами: <b>{stats['employees_with_requests']}</b>\n\n"
        f"📋 <b>Запросы:</b>\n"
        f"• Всего запросов: <b>{stats['total_requests']}</b>\n"
        f"• Ожидают ответа: <b>{stats['pending_requests']}</b>\n"
        f"• Получено ответов: <b>{stats['answered_requests']}</b>\n\n"
        f"📊 <b>По типам:</b>\n{request_types_text}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к отчетам", callback_data="menu_reports")]
    ])
    
    await safe_edit_message(callback, report_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "reports_history")
async def reports_history(callback: CallbackQuery):
    """История публикаций"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.file_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    archived_posts = await dependencies.file_service.get_archived_posts(days=30)
    
    if not archived_posts:
        report_text = (
            "📚 <b>История публикаций</b>\n\n"
            "За последние 30 дней публикаций не найдено."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к отчетам", callback_data="menu_reports")]
        ])
        await safe_edit_message(callback, report_text, reply_markup=keyboard)
        await safe_answer_callback(callback)
        return
    
    # Показываем первые 10 постов
    posts_list = "\n".join([
        f"{i+1}. {post['date_str']}"
        for i, post in enumerate(archived_posts[:10])
    ])
    
    report_text = (
        f"📚 <b>История публикаций</b>\n\n"
        f"Всего найдено: <b>{len(archived_posts)}</b> постов\n\n"
        f"<b>Последние публикации:</b>\n{posts_list}"
    )
    
    # Создаем кнопки для просмотра постов
    keyboard_buttons = []
    for i, post in enumerate(archived_posts[:5]):  # Показываем первые 5
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"📄 {post['date_str']}",
                callback_data=f"view_post_{post['filename']}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="◀️ Назад к отчетам", callback_data="menu_reports")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await safe_edit_message(callback, report_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("view_post_"))
async def view_post(callback: CallbackQuery):
    """Просмотр конкретного поста"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.file_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    filename = callback.data.replace("view_post_", "")
    post_content = await dependencies.file_service.get_post_content(filename)
    
    if not post_content:
        await safe_answer_callback(callback, "Пост не найден", show_alert=True)
        return
    
    # Обрезаем текст если слишком длинный (Telegram лимит ~4096 символов)
    if len(post_content) > 4000:
        post_content = post_content[:4000] + "\n\n... (текст обрезан)"
    
    # Извлекаем дату из имени файла
    try:
        date_str = filename.replace("post_", "").replace(".txt", "")
        date_str = date_str.replace("-", ":", 2).replace("_", ":", 1)
        date_obj = datetime.strptime(date_str, "%Y:%m:%d:%H:%M:%S")
        formatted_date = date_obj.strftime("%d.%m.%Y %H:%M")
    except:
        formatted_date = "Дата неизвестна"
    
    report_text = (
        f"📄 <b>Публикация от {formatted_date}</b>\n\n"
        f"{post_content}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к истории", callback_data="reports_history")]
    ])
    
    await safe_edit_message(callback, report_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "reports_conversations")
async def reports_conversations(callback: CallbackQuery):
    """Переписка с сотрудниками"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    conversations = dependencies.employee_service.get_all_conversations()
    
    if not conversations:
        report_text = (
            "💬 <b>Переписка с сотрудниками</b>\n\n"
            "Переписки не найдены."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к отчетам", callback_data="menu_reports")]
        ])
        await safe_edit_message(callback, report_text, reply_markup=keyboard)
        await safe_answer_callback(callback)
        return
    
    # Формируем список переписок
    conversations_list = []
    for conv in conversations[:10]:  # Показываем первые 10
        active_count = len([r for r in conv['requests'] if not r.answered])
        total_count = len(conv['requests'])
        
        status = "🟢" if active_count > 0 else "⚪"
        conversations_list.append(
            f"{status} {conv['employee_name']} ({conv['employee_role']})\n"
            f"   Запросов: {total_count} (активных: {active_count})"
        )
    
    conversations_text = "\n\n".join(conversations_list)
    
    report_text = (
        f"💬 <b>Переписка с сотрудниками</b>\n\n"
        f"Всего сотрудников с переписками: <b>{len(conversations)}</b>\n\n"
        f"{conversations_text}"
    )
    
    # Создаем кнопки для просмотра переписок
    keyboard_buttons = []
    for conv in conversations[:5]:  # Показываем первые 5
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"👤 {conv['employee_name']}",
                callback_data=f"view_conversation_{conv['employee_id']}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="◀️ Назад к отчетам", callback_data="menu_reports")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await safe_edit_message(callback, report_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("view_conversation_"))
async def view_conversation(callback: CallbackQuery):
    """Просмотр переписки с конкретным сотрудником"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.employee_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    try:
        employee_id = int(callback.data.replace("view_conversation_", ""))
    except ValueError:
        await safe_answer_callback(callback, "Неверный ID сотрудника", show_alert=True)
        return
    
    employee = dependencies.employee_service.get_employee(employee_id)
    if not employee:
        await safe_answer_callback(callback, "Сотрудник не найден", show_alert=True)
        return
    
    # Получаем все запросы для сотрудника
    active_requests = [
        req for req in dependencies.employee_service.active_requests.values()
        if req.employee_id == employee_id
    ]
    history_requests = dependencies.employee_service.get_request_history_for_employee(employee_id)
    all_requests = active_requests + history_requests
    
    if not all_requests:
        report_text = (
            f"💬 <b>Переписка с {employee.name}</b>\n\n"
            f"Переписки не найдены."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к перепискам", callback_data="reports_conversations")]
        ])
        await safe_edit_message(callback, report_text, reply_markup=keyboard)
        await safe_answer_callback(callback)
        return
    
    # Формируем историю переписки
    conversation_lines = []
    for req in sorted(all_requests, key=lambda x: x.created_at, reverse=True)[:5]:  # Последние 5
        status = "🟢 Активен" if not req.answered else "✅ Завершен"
        created = datetime.fromisoformat(req.created_at).strftime("%d.%m %H:%M")
        
        conversation_lines.append(
            f"<b>{status}</b> - {created}\n"
            f"Тип: {req.request_type}\n"
            f"Запрос: {req.request_text[:100]}..."
        )
        
        if req.answered and req.response:
            response_time = datetime.fromisoformat(req.response_at).strftime("%d.%m %H:%M")
            conversation_lines.append(f"Ответ ({response_time}): {req.response[:100]}...")
        
        conversation_lines.append("")  # Пустая строка между запросами
    
    conversation_text = "\n".join(conversation_lines)
    
    report_text = (
        f"💬 <b>Переписка с {employee.name}</b>\n"
        f"💼 Роль: {employee.role}\n"
        f"🆔 ID: {employee_id}\n\n"
        f"<b>Последние запросы:</b>\n\n{conversation_text}"
    )
    
    # Обрезаем если слишком длинно
    if len(report_text) > 4000:
        report_text = report_text[:4000] + "\n\n... (текст обрезан)"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к перепискам", callback_data="reports_conversations")]
    ])
    
    await safe_edit_message(callback, report_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


def get_post_types_edit_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для редактирования типов постов"""
    post_types_config = PostTypesConfigService()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Понедельник ({post_types_config.get_post_type('monday')['name']})",
                callback_data="post_type_edit_monday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Вторник ({post_types_config.get_post_type('tuesday')['name']})",
                callback_data="post_type_edit_tuesday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Среда ({post_types_config.get_post_type('wednesday')['name']})",
                callback_data="post_type_edit_wednesday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Четверг ({post_types_config.get_post_type('thursday')['name']})",
                callback_data="post_type_edit_thursday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Пятница ({post_types_config.get_post_type('friday')['name']})",
                callback_data="post_type_edit_friday"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Суббота ({post_types_config.get_post_type('saturday')['name']})",
                callback_data="post_type_edit_saturday"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_generate")
        ]
    ])
    return keyboard


@router.callback_query(F.data == "post_types_edit")
async def post_types_edit_menu(callback: CallbackQuery):
    """Меню редактирования типов постов"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    post_types_config = PostTypesConfigService()
    all_types = post_types_config.get_all_post_types()
    
    types_text = "⚙️ <b>Настройка типов постов</b>\n\n"
    types_text += "<b>Текущие типы постов:</b>\n"
    day_names_ru = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    for day, day_name in day_names_ru.items():
        post_type = all_types.get(day, {})
        status = "✅" if post_type.get('enabled', True) else "❌"
        types_text += f"{status} {day_name}: <b>{post_type.get('name', 'Не указан')}</b>\n"
        if post_type.get('description'):
            types_text += f"   └ {post_type['description']}\n"
    
    types_text += "\nВыберите день для изменения типа поста:"
    
    await safe_edit_message(
        callback,
        types_text,
        reply_markup=get_post_types_edit_keyboard()
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("post_type_edit_"))
async def post_type_edit_day(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора дня для редактирования типа поста"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    day = callback.data.replace("post_type_edit_", "")
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    day_name = day_names.get(day)
    if not day_name:
        await safe_answer_callback(callback, "Неизвестный день", show_alert=True)
        return
    
    post_types_config = PostTypesConfigService()
    current_type = post_types_config.get_post_type(day)
    
    await state.update_data(day=day)
    await state.set_state(PostTypeEditStates.waiting_for_name)
    
    await safe_edit_message(
        callback,
        f"⚙️ <b>Изменение типа поста</b>\n\n"
        f"День: <b>{day_name}</b>\n"
        f"Текущее название: <b>{current_type.get('name', 'Не указано')}</b>\n"
        f"Текущее описание: {current_type.get('description', 'Не указано')}\n\n"
        "Введите новое название типа поста:\n\n"
        "Или отправьте 'отмена' для отмены:"
    )
    await safe_answer_callback(callback)


@router.message(PostTypeEditStates.waiting_for_name)
async def post_type_process_name(message: Message, state: FSMContext):
    """Обрабатывает ввод нового названия типа поста"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    name = message.text.strip()
    
    # Проверка на отмену
    if name.lower() in ['отмена', 'cancel', 'назад']:
        await safe_clear_state(state)
        await message.answer("❌ Изменение типа поста отменено.", reply_markup=get_main_menu_keyboard())
        return
    
    if len(name) < 3:
        await message.answer(
            "❌ Название слишком короткое!\n\n"
            "Введите название длиной не менее 3 символов.\n\n"
            "Попробуйте снова или отправьте 'отмена':"
        )
        return
    
    await state.update_data(name=name)
    await state.set_state(PostTypeEditStates.waiting_for_description)
    
    await message.answer(
        f"✅ Название сохранено: <b>{name}</b>\n\n"
        "Теперь введите описание типа поста (или отправьте 'пропустить' для пропуска):",
        parse_mode="HTML"
    )


@router.message(PostTypeEditStates.waiting_for_description)
async def post_type_process_description(message: Message, state: FSMContext):
    """Обрабатывает ввод описания типа поста"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    description = message.text.strip()
    
    # Проверка на пропуск
    if description.lower() in ['пропустить', 'skip', 'нет']:
        description = None
    
    data = await state.get_data()
    day = data.get('day')
    name = data.get('name')
    
    if not day or not name:
        await message.answer("Ошибка: данные не найдены")
        await safe_clear_state(state)
        return
    
    post_types_config = PostTypesConfigService()
    
    # Обновляем тип поста
    if post_types_config.update_post_type(day, name, description):
        day_names = {
            'monday': 'Понедельник',
            'tuesday': 'Вторник',
            'wednesday': 'Среда',
            'thursday': 'Четверг',
            'friday': 'Пятница',
            'saturday': 'Суббота'
        }
        
        day_name = day_names.get(day, day)
        
        await message.answer(
            f"✅ <b>Тип поста обновлен!</b>\n\n"
            f"День: <b>{day_name}</b>\n"
            f"Название: <b>{name}</b>\n"
            f"Описание: {description or 'Не указано'}\n\n"
            "Изменения сохранены.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении типа поста.\n"
            "Проверьте логи для подробностей.",
            reply_markup=get_main_menu_keyboard()
        )
    
    await safe_clear_state(state)


@router.callback_query(F.data.startswith("approve_post"))
async def approve_post(callback: CallbackQuery):
    """Обработчик кнопки 'Принять' пост"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.post_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    # Извлекаем день недели из callback_data (approve_post_monday -> monday)
    day_of_week = None
    if callback.data == "approve_post":
        # Старый формат без дня недели - оставляем None для обратной совместимости
        day_of_week = None
        logger.info("Получен callback approve_post без указания дня недели (старый формат)")
    elif callback.data.startswith("approve_post_"):
        day_of_week = callback.data.replace("approve_post_", "")
        logger.info(f"Извлечен день недели из callback_data: {day_of_week}")
    
    try:
        # Получаем текст поста из сообщения
        post_text = callback.message.text or callback.message.caption
        if post_text:
            # Убираем заголовок "Черновик поста для согласования:"
            if "Черновик поста для согласования:" in post_text:
                post_text = post_text.split("\n\n", 1)[1] if "\n\n" in post_text else post_text
        
        # Получаем фотографии из сохраненных путей
        photos = dependencies.telegram_service.get_draft_photos(callback.message.message_id)
        logger.info(f"Получены фотографии из draft_photos: {photos}")
        
        # Если фотографии не найдены в сохраненных путях, пытаемся скачать из сообщения
        if not photos and callback.message.photo:
            try:
                logger.info("Фотографии не найдены в draft_photos, скачиваем из сообщения")
                # Скачиваем фото из сообщения
                photo = callback.message.photo[-1]  # Берем фото наибольшего размера
                file_info = await callback.message.bot.get_file(photo.file_id)
                
                # Сохраняем во временную папку
                temp_path = dependencies.file_service.get_folder_path('photos') / f"{photo.file_id}.jpg"
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                await callback.message.bot.download_file(file_info.file_path, destination=str(temp_path))
                photos = [str(temp_path.absolute())]  # Используем абсолютный путь
                logger.info(f"Скачана фотография из сообщения: {temp_path.absolute()}")
            except Exception as e:
                logger.error(f"Ошибка при скачивании фотографии: {e}", exc_info=True)
        
        # Проверяем существование файлов
        if photos:
            existing_photos = []
            for photo_path in photos:
                from pathlib import Path
                photo_path_obj = Path(photo_path)
                if photo_path_obj.exists():
                    existing_photos.append(str(photo_path_obj.absolute()))
                    logger.info(f"Фото существует: {photo_path_obj.absolute()}")
                else:
                    logger.warning(f"Фото не найдено: {photo_path}")
            photos = existing_photos
        
        # Если указан день недели, сохраняем пост для планирования
        if day_of_week:
            if not dependencies.scheduled_posts_service:
                logger.error("scheduled_posts_service не инициализирован, публикуем немедленно")
                # Fallback: публикуем немедленно если сервис не доступен
                results = await dependencies.post_service.publish_approved_post(post_text, photos or [])
                await safe_answer_callback(callback, "Пост опубликован!", show_alert=True)
                await safe_edit_message(
                    callback,
                    f"✅ <b>Пост опубликован!</b>\n\n"
                    f"Telegram: {results.get('telegram', 'N/A')}\n"
                    f"VK: {results.get('vk', 'N/A')}"
                )
                return
            
            logger.info(f"Сохраняем пост для планирования на день: {day_of_week}")
            dependencies.scheduled_posts_service.add_scheduled_post(
                day_of_week=day_of_week,
                post_text=post_text,
                photos=photos or [],
                admin_id=callback.from_user.id
            )
            
            day_names = {
                'monday': 'Понедельник',
                'tuesday': 'Вторник',
                'wednesday': 'Среда',
                'thursday': 'Четверг',
                'friday': 'Пятница',
                'saturday': 'Суббота'
            }
            day_name = day_names.get(day_of_week, day_of_week)
            
            await safe_answer_callback(callback, f"Пост запланирован на {day_name}!", show_alert=True)
            await safe_edit_message(
                callback,
                f"✅ <b>Пост запланирован!</b>\n\n"
                f"📅 День: <b>{day_name}</b>\n"
                f"⏰ Время публикации: согласно расписанию\n\n"
                f"Пост будет автоматически опубликован в указанное время."
            )
        else:
            # Если день недели не указан, публикуем немедленно (старое поведение или fallback)
            logger.info(f"День недели не указан, публикуем пост немедленно. Callback data: {callback.data}")
            logger.info(f"Публикация поста с {len(photos) if photos else 0} фотографиями")
            results = await dependencies.post_service.publish_approved_post(post_text, photos or [])
            
            await safe_answer_callback(callback, "Пост опубликован!", show_alert=True)
            await safe_edit_message(
                callback,
                f"✅ <b>Пост опубликован!</b>\n\n"
                f"Telegram: {results.get('telegram', 'N/A')}\n"
                f"VK: {results.get('vk', 'N/A')}"
            )
    
    except Exception as e:
        logger.error(f"Ошибка при обработке поста: {e}")
        await safe_answer_callback(callback, "Ошибка при обработке поста", show_alert=True)


@router.callback_query(F.data.startswith("publish_now"))
async def publish_now(callback: CallbackQuery):
    """Обработчик кнопки 'Отправить сейчас' - публикует пост немедленно"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.post_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    try:
        await safe_answer_callback(callback, "Публикую пост...")
        
        # Получаем текст поста из сообщения
        post_text = callback.message.text or callback.message.caption or ""
        if post_text:
            # Убираем заголовок "Черновик поста для согласования:" и другие префиксы
            if "Черновик поста для согласования:" in post_text:
                post_text = post_text.split("\n\n", 1)[1] if "\n\n" in post_text else post_text.replace("Черновик поста для согласования:", "").strip()
            # Убираем HTML теги из заголовка
            post_text = post_text.replace("<b>Черновик поста для согласования:</b>", "").replace("📝 Полный текст ниже ⬇️", "").strip()
        
        if not post_text:
            await safe_answer_callback(callback, "Не удалось найти текст поста", show_alert=True)
            return
        
        # Получаем фотографии из сохраненных путей
        photos = dependencies.telegram_service.get_draft_photos(callback.message.message_id)
        logger.info(f"Получены фотографии из draft_photos: {photos}")
        
        # Если фотографии не найдены в сохраненных путях, пытаемся скачать из сообщения
        if not photos and callback.message.photo:
            try:
                logger.info("Фотографии не найдены в draft_photos, скачиваем из сообщения")
                # Скачиваем фото из сообщения
                photo = callback.message.photo[-1]  # Берем фото наибольшего размера
                file_info = await callback.message.bot.get_file(photo.file_id)
                
                # Сохраняем во временную папку
                temp_path = dependencies.file_service.get_folder_path('photos') / f"{photo.file_id}.jpg"
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                await callback.message.bot.download_file(file_info.file_path, destination=str(temp_path))
                photos = [str(temp_path.absolute())]  # Используем абсолютный путь
                logger.info(f"Скачана фотография из сообщения: {temp_path.absolute()}")
            except Exception as e:
                logger.error(f"Ошибка при скачивании фотографии: {e}", exc_info=True)
        
        # Проверяем существование файлов перед публикацией
        if photos:
            existing_photos = []
            for photo_path in photos:
                from pathlib import Path
                photo_path_obj = Path(photo_path)
                if photo_path_obj.exists():
                    existing_photos.append(str(photo_path_obj.absolute()))
                    logger.info(f"Фото существует: {photo_path_obj.absolute()}")
                else:
                    logger.warning(f"Фото не найдено: {photo_path}")
            photos = existing_photos
        
        logger.info(f"Публикация поста с {len(photos)} фотографиями: {photos}")
        
        # Публикуем пост сразу
        results = await dependencies.post_service.publish_approved_post(post_text, photos)
        
        await safe_edit_message(
            callback,
            f"🚀 <b>Пост опубликован сразу!</b>\n\n"
            f"Telegram: {results.get('telegram', 'N/A')}\n"
            f"VK: {results.get('vk', 'N/A')}"
        )
    
    except Exception as e:
        logger.error(f"Ошибка при публикации поста: {e}")
        await safe_answer_callback(callback, f"Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data == "edit_post")
async def request_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Редактировать' пост"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await safe_answer_callback(callback)
    await state.set_state(PostApprovalStates.waiting_for_edits)
    
    # Получаем текст поста из сообщения
    post_text = callback.message.text or callback.message.caption or ""
    if post_text:
        # Убираем заголовок "Черновик поста для согласования:" и другие префиксы
        if "Черновик поста для согласования:" in post_text:
            post_text = post_text.split("\n\n", 1)[1] if "\n\n" in post_text else post_text.replace("Черновик поста для согласования:", "").strip()
        # Убираем HTML теги из заголовка
        post_text = post_text.replace("<b>Черновик поста для согласования:</b>", "").replace("📝 Полный текст ниже ⬇️", "").strip()
    
    # Сохраняем исходный текст и ID сообщения с черновиком
    await state.update_data(
        draft_message_id=callback.message.message_id,
        original_post_text=post_text,
        original_photos=[]  # TODO: сохранить пути к фотографиям если есть
    )
    
    await callback.message.answer(
        "Пожалуйста, отправьте текст правок для этого поста:\n\n"
        "Например: 'сократи текст в 3 раза', 'добавь больше эмодзи', 'измени стиль на более дружелюбный'"
    )


@router.message(PostApprovalStates.waiting_for_edits)
async def process_edits(message: Message, state: FSMContext):
    """Обрабатывает правки от администратора (для обычных черновиков и запланированных постов)"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с правками.")
        return
    
    if not dependencies.post_service:
        await message.answer("Сервис недоступен")
        await safe_clear_state(state)
        return
    
    edits = message.text.strip()
    
    if not edits:
        await message.answer("Пожалуйста, отправьте текст правок.")
        return
    
    data = await state.get_data()
    day_of_week = data.get('scheduled_post_day')  # Проверяем, редактируется ли запланированный пост
    original_post_text = data.get('original_post_text', '')
    original_photos = data.get('original_photos', [])
    
    if not original_post_text:
        await message.answer("Не удалось найти исходный текст поста. Попробуйте создать пост заново.")
        await safe_clear_state(state)
        return
    
    # Сохраняем запрос на редактирование в историю
    request_id = None
    if dependencies.post_history_service:
        request_id = dependencies.post_history_service.add_request(
            admin_id=message.from_user.id,
            request_type="edit",
            prompt=edits,
            original_post=original_post_text,
            photos_count=len(original_photos) + len(original_photo_paths)
        )
    
    try:
        await message.answer("⏳ Перерабатываю пост с учетом ваших правок...")
        
        # Перерабатываем пост через AI
        logger.info(f"Переработка поста. Исходный текст: {len(original_post_text)} символов. Правки: {edits}")
        refined_post = await dependencies.post_service.refine_post(original_post_text, edits)
        logger.info(f"Пост переработан. Новый текст: {len(refined_post)} символов")
        
        # Обновляем историю с успешным результатом
        if dependencies.post_history_service and request_id:
            dependencies.post_history_service.update_request(
                request_id=request_id,
                generated_post=refined_post,
                status="completed"
            )
        
        # Если это запланированный пост, обновляем его
        if day_of_week and dependencies.scheduled_posts_service:
            dependencies.scheduled_posts_service.add_scheduled_post(
                day_of_week=day_of_week,
                post_text=refined_post,
                photos=original_photos,
                admin_id=message.from_user.id
            )
            
            day_names = {
                'monday': 'Понедельник',
                'tuesday': 'Вторник',
                'wednesday': 'Среда',
                'thursday': 'Четверг',
                'friday': 'Пятница',
                'saturday': 'Суббота'
            }
            day_name = day_names.get(day_of_week, day_of_week)
            
            await message.answer(
                f"✅ <b>Запланированный пост обновлен!</b>\n\n"
                f"📅 День: <b>{day_name}</b>\n\n"
                f"Пост будет опубликован в запланированное время.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            # Обычный черновик - отправляем на согласование
            await dependencies.post_service.send_for_approval(refined_post, original_photos)
            
            await message.answer(
                "✅ <b>Пост переработан и отправлен на согласование!</b>\n\n"
                f"Новая длина: {len(refined_post)} символов",
                parse_mode="HTML"
            )
        
        await safe_clear_state(state)
    
    except Exception as e:
        logger.error(f"Ошибка при обработке правок: {e}")
        await message.answer(f"❌ Ошибка при обработке правок: {str(e)}")
        await safe_clear_state(state)


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Показывает статус бота"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        return
    
    if not dependencies.scheduler_service:
        await message.answer("Сервис недоступен")
        return
    
    status_text = (
        f"📊 <b>Статус бота</b>\n\n"
        f"Планировщик: {'✅ Включен' if dependencies.scheduler_service.is_enabled else '❌ Выключен'}\n"
        f"Задач в расписании: {len(dependencies.scheduler_service.scheduler.get_jobs())}\n"
        f"Google Drive: {'✅ Включен' if (dependencies.file_service and dependencies.file_service.google_drive and dependencies.file_service.google_drive.enabled) else '❌ Выключен'}"
    )
    
    await message.answer(status_text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")


@router.message(Command("upload"))
async def cmd_upload(message: Message):
    """Обработчик команды загрузки файла"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        return
    
    if not dependencies.file_service or not dependencies.file_service.google_drive or not dependencies.file_service.google_drive.enabled:
        await message.answer(
            "❌ Google Drive не настроен.\n\n"
            "Для настройки:\n"
            "1. Включите GOOGLE_DRIVE_ENABLED=true в .env\n"
            "2. Добавьте credentials файл в credentials/google-credentials.json\n"
            "3. Укажите ID папок в Google Drive",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    await message.answer(
        "📤 <b>Загрузка файла в Google Drive</b>\n\n"
        "Выберите папку для загрузки:",
        reply_markup=get_upload_folder_keyboard(),
        parse_mode="HTML"
    )


@router.message(FileUploadStates.waiting_for_folder_type)
async def process_folder_type(message: Message, state: FSMContext):
    """Обрабатывает выбор типа папки"""
    folder_map = {
        '1': 'photos',
        '2': 'drafts',
        '3': 'laws',
        '4': 'memes',
        '5': 'services',
        '6': 'archive',
        'photos': 'photos',
        'drafts': 'drafts',
        'laws': 'laws',
        'memes': 'memes',
        'services': 'services',
        'archive': 'archive'
    }
    
    folder_type = folder_map.get(message.text.lower().strip())
    
    if not folder_type:
        await message.answer("❌ Неверный тип папки. Попробуйте снова.")
        return
    
    await state.update_data(folder_type=folder_type)
    await state.set_state(FileUploadStates.waiting_for_file)
    
    await message.answer(
        f"✅ Выбрана папка: <b>{folder_type}</b>\n\n"
        "Теперь отправьте файл (фото или документ):",
        parse_mode="HTML"
    )


@router.message(FileUploadStates.waiting_for_file, F.photo)
async def process_photo_upload(message: Message, state: FSMContext):
    """Обрабатывает загрузку фотографии"""
    if not dependencies.file_service:
        await message.answer("Сервис недоступен")
        await state.clear()
        return
    
    data = await state.get_data()
    folder_type = data.get('folder_type', 'photos')
    
    try:
        # Скачиваем фото
        photo = message.photo[-1]  # Берем фото наибольшего размера
        file_info = await message.bot.get_file(photo.file_id)
        
        # Сохраняем во временную папку
        temp_path = dependencies.file_service.get_folder_path(folder_type) / f"{photo.file_id}.jpg"
        await message.bot.download_file(file_info.file_path, destination=str(temp_path))
        
        # Загружаем в Google Drive
        drive_file_id = await dependencies.file_service.upload_photo_to_drive(
            str(temp_path),
            folder_type
        )
        
        if drive_file_id:
            logger.info(f"Фото успешно загружено в Google Drive, ID: {drive_file_id}, папка: {folder_type}")
            await message.answer(
                f"✅ Фото успешно загружено в Google Drive!\n\n"
                f"Папка: <b>{folder_type}</b>\n"
                f"ID файла: <code>{drive_file_id}</code>",
                parse_mode="HTML"
            )
        else:
            logger.warning(f"Не удалось загрузить фото в Google Drive: {temp_path}, папка: {folder_type}")
            await message.answer("❌ Ошибка при загрузке в Google Drive")
        
        # Удаляем временный файл
        if temp_path.exists():
            temp_path.unlink()
        
        await state.clear()
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке фото: {e}")
        await message.answer(f"❌ Ошибка при загрузке: {str(e)}")
        await state.clear()


@router.message(FileUploadStates.waiting_for_file, F.document)
async def process_document_upload(message: Message, state: FSMContext):
    """Обрабатывает загрузку документа"""
    if not dependencies.file_service:
        await message.answer("Сервис недоступен")
        await state.clear()
        return
    
    data = await state.get_data()
    folder_type = data.get('folder_type', 'drafts')
    
    try:
        # Скачиваем документ
        document = message.document
        file_info = await message.bot.get_file(document.file_id)
        
        # Сохраняем во временную папку
        temp_path = dependencies.file_service.get_folder_path(folder_type) / document.file_name
        await message.bot.download_file(file_info.file_path, destination=str(temp_path))
        
        # Загружаем в Google Drive
        drive_file_id = await dependencies.file_service.upload_photo_to_drive(
            str(temp_path),
            folder_type
        )
        
        if drive_file_id:
            await message.answer(
                f"✅ Документ успешно загружен в Google Drive!\n\n"
                f"Файл: <b>{document.file_name}</b>\n"
                f"Папка: <b>{folder_type}</b>\n"
                f"ID файла: <code>{drive_file_id}</code>",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка при загрузке в Google Drive")
        
        # Удаляем временный файл
        if temp_path.exists():
            temp_path.unlink()
        
        await state.clear()
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке документа: {e}")
        await message.answer(f"❌ Ошибка при загрузке: {str(e)}")
        await state.clear()


@router.message(FileUploadStates.waiting_for_file)
async def process_invalid_file(message: Message, state: FSMContext):
    """Обрабатывает некорректный тип файла"""
    # Если пользователь отправил текст "отмена" или "назад", отменяем операцию
    if message.text and message.text.lower() in ['отмена', 'назад', 'cancel', 'back']:
        await state.clear()
        await message.answer(
            "❌ Операция отменена.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_back")]
    ])
    await message.answer(
        "❌ Пожалуйста, отправьте фото или документ.\n\n"
        "Или нажмите кнопку для отмены:",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "menu_prompts")
async def menu_prompts(callback: CallbackQuery):
    """Меню редактирования промптов"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.prompt_config_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    prompts = dependencies.prompt_config_service.get_all_prompts()
    
    prompts_text = (
        "✏️ <b>Редактирование промптов</b>\n\n"
        "Промпты - это инструкции для AI, которые определяют как генерируются посты.\n\n"
        "Выберите промпт для редактирования:"
    )
    
    keyboard_buttons = []
    for prompt_key, prompt_info in prompts.items():
        name = prompt_info.get('name', prompt_key)
        description = prompt_info.get('description', '')
        button_text = f"✏️ {name}"
        if len(button_text) > 30:
            button_text = button_text[:27] + "..."
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"edit_prompt_{prompt_key}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await safe_edit_message(callback, prompts_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("edit_prompt_"))
async def edit_prompt_start(callback: CallbackQuery, state: FSMContext):
    """Начинает редактирование промпта"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.prompt_config_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    prompt_key = callback.data.replace("edit_prompt_", "")
    prompt_info = dependencies.prompt_config_service.get_prompt_info(prompt_key)
    
    if not prompt_info:
        await safe_answer_callback(callback, "Промпт не найден", show_alert=True)
        return
    
    # Определяем тип промпта (system_prompt или user_prompt)
    prompt_type = "system_prompt" if "system_prompt" in prompt_info else "user_prompt"
    current_prompt = prompt_info.get(prompt_type, "")
    
    # Сохраняем данные в состояние
    await state.update_data(
        prompt_key=prompt_key,
        prompt_type=prompt_type
    )
    await state.set_state(PromptEditStates.waiting_for_prompt_text)
    
    prompt_name = prompt_info.get('name', prompt_key)
    prompt_description = prompt_info.get('description', '')
    
    # Обрезаем текущий промпт для отображения если слишком длинный
    display_prompt = current_prompt
    if len(display_prompt) > 2000:
        display_prompt = display_prompt[:2000] + "\n\n... (текст обрезан, полный текст будет заменен)"
    
    await safe_edit_message(
        callback,
        f"✏️ <b>Редактирование промпта</b>\n\n"
        f"<b>Название:</b> {prompt_name}\n"
        f"<b>Описание:</b> {prompt_description}\n"
        f"<b>Тип:</b> {prompt_type}\n\n"
        f"<b>Текущий промпт:</b>\n\n"
        f"<code>{display_prompt}</code>\n\n"
        f"Отправьте новый текст промпта:\n\n"
        f"Или отправьте 'отмена' для отмены:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_prompts")]
        ])
    )
    await safe_answer_callback(callback)


@router.message(PromptEditStates.waiting_for_prompt_text)
async def process_prompt_text(message: Message, state: FSMContext):
    """Обрабатывает новый текст промпта"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с промптом.")
        return
    
    if not dependencies.prompt_config_service:
        await message.answer("Сервис недоступен")
        await safe_clear_state(state)
        return
    
    # Проверка на отмену
    if message.text.lower().strip() in ['отмена', 'cancel', 'назад']:
        await safe_clear_state(state)
        await message.answer("❌ Редактирование промпта отменено.", reply_markup=get_main_menu_keyboard())
        return
    
    data = await state.get_data()
    prompt_key = data.get('prompt_key')
    prompt_type = data.get('prompt_type')
    
    if not prompt_key or not prompt_type:
        await message.answer("Ошибка: не найдены данные промпта для редактирования")
        await safe_clear_state(state)
        return
    
    new_prompt_text = message.text.strip()
    
    try:
        # Сохраняем новый промпт
        dependencies.prompt_config_service.set_prompt(prompt_key, prompt_type, new_prompt_text)
        
        prompt_info = dependencies.prompt_config_service.get_prompt_info(prompt_key)
        prompt_name = prompt_info.get('name', prompt_key) if prompt_info else prompt_key
        
        await message.answer(
            f"✅ <b>Промпт успешно обновлен!</b>\n\n"
            f"<b>Промпт:</b> {prompt_name}\n"
            f"<b>Тип:</b> {prompt_type}\n\n"
            f"Изменения вступят в силу при следующей генерации поста.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
        
        await safe_clear_state(state)
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении промпта: {e}")
        await message.answer(
            f"❌ Ошибка при сохранении промпта: {str(e)}\n\n"
            f"Попробуйте снова или отправьте 'отмена'."
        )


# ========== Обработчики управления расписанием ==========

@router.callback_query(F.data == "schedule_add_post")
async def schedule_add_post_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс добавления поста в расписание"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"schedule_add_day_{key}")] for key, name in day_names.items()]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_schedule")])
    
    await safe_edit_message(
        callback,
        "➕ <b>Добавление поста в расписание</b>\n\nВыберите день недели:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("schedule_add_day_"))
async def schedule_add_post_day(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор дня для добавления поста"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    day = callback.data.replace("schedule_add_day_", "")
    await state.update_data(day=day)
    await state.set_state(SchedulePostStates.waiting_for_time)
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    await safe_edit_message(
        callback,
        f"➕ <b>Добавление поста</b>\n\n"
        f"День: <b>{day_names.get(day, day)}</b>\n\n"
        f"Введите время публикации в формате <b>HH:MM</b>\n"
        f"Например: 09:00, 14:30, 18:15\n\n"
        f"Или отправьте 'отмена' для отмены:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_schedule")]
        ])
    )
    await safe_answer_callback(callback)


@router.message(SchedulePostStates.waiting_for_time)
async def schedule_add_post_time(message: Message, state: FSMContext):
    """Обрабатывает ввод времени для нового поста или редактирования"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с временем.")
        return
    
    time_str = message.text.strip()
    
    if time_str.lower() in ['отмена', 'cancel', 'назад']:
        await safe_clear_state(state)
        await message.answer("❌ Операция отменена.", reply_markup=get_main_menu_keyboard())
        return
    
    if time_str.lower() == 'пропустить':
        # Пропускаем изменение времени, переходим к названию
        data = await state.get_data()
        post_index = data.get('post_index')
        if post_index is not None:
            # Редактирование - пропускаем время
            await state.set_state(SchedulePostStates.waiting_for_post_name)
            await message.answer(
                "⏭️ Время не изменено.\n\n"
                "Введите новое название поста (или отправьте 'пропустить'):\n\n"
                "Или отправьте 'отмена' для отмены:"
            )
            return
    
    import re
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        await message.answer(
            "❌ Неверный формат времени!\n\n"
            "Используйте формат <b>HH:MM</b>\n"
            "Например: 09:00, 14:30, 18:15\n\n"
            "Или отправьте 'пропустить' чтобы не менять время (при редактировании)\n\n"
            "Попробуйте снова или отправьте 'отмена':",
            parse_mode="HTML"
        )
        return
    
    await state.update_data(time=time_str)
    await state.set_state(SchedulePostStates.waiting_for_post_name)
    
    data = await state.get_data()
    post_index = data.get('post_index')
    
    if post_index is not None:
        # Редактирование
        await message.answer(
            f"✅ Время обновлено: <b>{time_str}</b>\n\n"
            f"Введите новое название поста (или отправьте 'пропустить'):\n\n"
            f"Или отправьте 'отмена' для отмены:",
            parse_mode="HTML"
        )
    else:
        # Добавление нового поста
        await message.answer(
            f"✅ Время установлено: <b>{time_str}</b>\n\n"
            f"Теперь введите название поста:\n\n"
            f"Или отправьте 'отмена' для отмены:",
            parse_mode="HTML"
        )


@router.message(SchedulePostStates.waiting_for_post_name)
async def schedule_add_post_name(message: Message, state: FSMContext):
    """Обрабатывает ввод названия поста"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с названием.")
        return
    
    if message.text.lower().strip() in ['отмена', 'cancel', 'назад']:
        await safe_clear_state(state)
        await message.answer("❌ Операция отменена.", reply_markup=get_main_menu_keyboard())
        return
    
    if message.text.lower().strip() == 'пропустить':
        # Пропускаем изменение названия, переходим к описанию
        data = await state.get_data()
        post_index = data.get('post_index')
        if post_index is not None:
            # Редактирование - пропускаем название
            await state.set_state(SchedulePostStates.waiting_for_post_description)
            await message.answer(
                "⏭️ Название не изменено.\n\n"
                "Введите новое описание поста (или отправьте 'пропустить'):\n\n"
                "Или отправьте 'отмена' для отмены:"
            )
            return
    
    await state.update_data(name=message.text.strip())
    await state.set_state(SchedulePostStates.waiting_for_post_description)
    
    await message.answer(
        f"✅ Название установлено: <b>{message.text.strip()}</b>\n\n"
        f"Теперь введите описание поста (или отправьте 'пропустить'):\n\n"
        f"Или отправьте 'отмена' для отмены:",
        parse_mode="HTML"
    )


@router.message(SchedulePostStates.waiting_for_post_description)
async def schedule_add_post_description(message: Message, state: FSMContext):
    """Обрабатывает ввод описания поста и сохраняет его"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        return
    
    description = message.text.strip()
    if description.lower() in ['отмена', 'cancel', 'назад']:
        await safe_clear_state(state)
        await message.answer("❌ Добавление поста отменено.", reply_markup=get_main_menu_keyboard())
        return
    
    if description.lower() == 'пропустить':
        description = ""
    
    data = await state.get_data()
    day = data.get('day')
    time = data.get('time')
    name = data.get('name')
    post_index = data.get('post_index')
    
    post_types_config = PostTypesConfigService()
    
    if post_index is not None:
        # Редактирование существующего поста
        posts = post_types_config.get_post_types(day)
        if post_index >= len(posts):
            await message.answer("❌ Ошибка: пост не найден.")
            await safe_clear_state(state)
            return
        
        old_post = posts[post_index]
        # Обновляем только указанные поля
        update_time = time if time else old_post.get('time', '09:00')
        update_name = name if name else old_post.get('name', 'Без названия')
        update_description = description if description != "" else old_post.get('description', '')
        
        success = post_types_config.update_post(
            day, post_index,
            time=update_time,
            name=update_name,
            description=update_description
        )
        
        if success:
            if dependencies.scheduler_service:
                dependencies.scheduler_service.setup_schedule()
            
            await message.answer(
                f"✅ <b>Пост обновлен!</b>\n\n"
                f"День: <b>{day}</b>\n"
                f"Время: <b>{update_time}</b>\n"
                f"Название: <b>{update_name}</b>\n\n"
                f"Планировщик обновлен.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка при обновлении поста.")
    else:
        # Добавление нового поста
        if not all([day, time, name]):
            await message.answer("❌ Ошибка: не все данные заполнены. Попробуйте снова.")
            await safe_clear_state(state)
            return
        
        success = post_types_config.add_post(day, time, name, description, enabled=True)
        
        if success:
            if dependencies.scheduler_service:
                dependencies.scheduler_service.setup_schedule()
            
            await message.answer(
                f"✅ <b>Пост добавлен в расписание!</b>\n\n"
                f"День: <b>{day}</b>\n"
                f"Время: <b>{time}</b>\n"
                f"Название: <b>{name}</b>\n\n"
                f"Планировщик обновлен.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка при добавлении поста.")
    
    await safe_clear_state(state)


# ========== Обработчики функции "Опубликовать сейчас" ==========

@router.callback_query(F.data == "post_now")
async def post_now_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс публикации поста сейчас"""
    logger.info(f"🔴 Кнопка 'Опубликовать сейчас' нажата пользователем {callback.from_user.id}")
    
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    # Проверяем текущее состояние перед установкой нового
    old_state = await state.get_state()
    logger.info(f"🔴 Текущее состояние перед установкой: {old_state}")
    
    # Устанавливаем состояние ожидания фото
    await state.set_state(PostNowStates.waiting_for_photo)
    new_state = await state.get_state()
    logger.info(f"🔴 Установлено состояние PostNowStates.waiting_for_photo для пользователя {callback.from_user.id}. Новое состояние: {new_state}")
    
    # Дополнительная проверка состояния
    if new_state != PostNowStates.waiting_for_photo:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Состояние не установлено правильно! Ожидалось: PostNowStates.waiting_for_photo, получено: {new_state}")
    
    await safe_answer_callback(callback)
    
    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
    ])
    
    await callback.message.answer(
        "🚀 <b>Опубликовать сейчас</b>\n\n"
        "<b>Шаг 1:</b> Прикрепите одну или несколько фотографий или видео к сообщению\n\n"
        "💡 <i>Совет: Вы можете отправить альбом из нескольких фото для более полного описания объекта. Видео будет проанализировано через AI.</i>",
        reply_markup=cancel_keyboard,
        parse_mode="HTML"
    )
    logger.info(f"🔴 Сообщение с запросом фото отправлено пользователю {callback.from_user.id}")


@router.message(PostNowStates.waiting_for_photo)
async def post_now_process_photo(message: Message, state: FSMContext):
    """Обрабатывает фото и переходит к вводу промпта"""
    logger.info(f"🔵 Обработчик post_now_process_photo вызван для пользователя {message.from_user.id}")
    current_state = await state.get_state()
    logger.info(f"🔵 Текущее состояние FSM: {current_state}")
    
    # Дополнительная проверка состояния
    if current_state != PostNowStates.waiting_for_photo:
        logger.warning(f"⚠️ Состояние не соответствует ожидаемому! Ожидалось: PostNowStates.waiting_for_photo, получено: {current_state}")
        return
    
    if not is_admin(message.from_user.id):
        logger.warning(f"Пользователь {message.from_user.id} не является администратором")
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    # Проверка на отмену
    if message.text and message.text.lower().strip() in ['отмена', 'cancel', 'назад']:
        logger.info("Пользователь отменил публикацию")
        await safe_clear_state(state)
        await message.answer("❌ Публикация отменена.", reply_markup=get_main_menu_keyboard())
        return
    
    # Проверяем наличие фото или видео
    if not message.photo and not message.video:
        logger.warning("Сообщение не содержит фото или видео")
        cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
        ])
        await message.answer(
            "❌ <b>Фотография или видео обязательны!</b>\n\n"
            "Пожалуйста, прикрепите фотографию или видео к сообщению.",
            reply_markup=cancel_keyboard,
            parse_mode="HTML"
        )
        return
    
    # Обрабатываем видео
    if message.video:
        try:
            logger.info("Начинаем обработку видео")
            video = message.video
            file_info = await message.bot.get_file(video.file_id)
            video_path = dependencies.file_service.get_folder_path('photos') / f"{video.file_id}.mp4"
            video_path.parent.mkdir(parents=True, exist_ok=True)
            await message.bot.download_file(file_info.file_path, destination=str(video_path))
            logger.info(f"Видео скачано: {video_path.absolute()}")
            
            # Сохраняем путь к видео в состоянии
            await state.update_data(
                video_path=str(video_path.absolute()),
                video_paths=[str(video_path.absolute())],
                has_video=True
            )
            logger.info(f"Путь к видео сохранен в состоянии: {video_path.absolute()}")
            
            # Устанавливаем состояние ожидания промпта
            await state.set_state(PostNowStates.waiting_for_prompt)
            
            cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
            ])
            
            await message.answer(
                "✅ <b>Видео получено!</b>\n\n"
                "<b>Шаг 2:</b> Отправьте промпт (описание того, какой пост нужно создать)\n\n"
                "Например:\n"
                "• \"Создай отчетный пост о текущих объектах\"\n"
                "• \"Напиши экспертную статью о земельных вопросах\"\n"
                "• \"Сделай пост об услугах компании\"",
                reply_markup=cancel_keyboard,
                parse_mode="HTML"
            )
            logger.info("Сообщение с запросом промпта отправлено пользователю")
            return
        except Exception as e:
            logger.error(f"Ошибка при обработке видео: {e}", exc_info=True)
            await message.answer(f"❌ Ошибка при обработке видео: {str(e)}")
            await safe_clear_state(state)
            return
    
    try:
        logger.info("Начинаем обработку фото")
        
        # Проверяем, является ли это частью альбома
        media_group_id = message.media_group_id
        if media_group_id:
            # Глобальные словари для хранения данных альбомов и задач обработки
            # Ключ: (user_id, media_group_id)
            if not hasattr(post_now_process_photo, '_album_tasks'):
                post_now_process_photo._album_tasks = {}
            if not hasattr(post_now_process_photo, '_album_data'):
                post_now_process_photo._album_data = {}
            if not hasattr(post_now_process_photo, '_album_message_sent'):
                post_now_process_photo._album_message_sent = set()
            
            task_key = (message.from_user.id, media_group_id)
            
            # Инициализируем данные альбома, если это новый альбом
            if task_key not in post_now_process_photo._album_data:
                post_now_process_photo._album_data[task_key] = {
                    'photos': [],
                    'state': state
                }
            
            # Скачиваем текущее фото
            photo = message.photo[-1]
            file_info = await message.bot.get_file(photo.file_id)
            photo_path = dependencies.file_service.get_folder_path('photos') / f"{photo.file_id}.jpg"
            photo_path.parent.mkdir(parents=True, exist_ok=True)
            await message.bot.download_file(file_info.file_path, destination=str(photo_path))
            logger.info(f"Фото из альбома скачано: {photo_path.absolute()}")
            
            # Добавляем фото в глобальный словарь альбома
            post_now_process_photo._album_data[task_key]['photos'].append(str(photo_path.absolute()))
            album_photos = post_now_process_photo._album_data[task_key]['photos']
            
            logger.info(f"Фото добавлено в альбом. Всего фото в альбоме: {len(album_photos)}")
            
            # Отправляем подтверждение получения фото (только один раз для каждого альбома)
            if task_key not in post_now_process_photo._album_message_sent:
                await message.answer(f"✅ Получено фото 1 из альбома. Ожидаю остальные фото...")
                post_now_process_photo._album_message_sent.add(task_key)
            
            # Сохраняем количество фото на момент создания задачи для сравнения
            photos_count_at_task_creation = len(album_photos)
            
            # Создаем задачу, которая через 2 секунды проверит, не пришло ли новое фото
            async def process_album_after_delay():
                import asyncio
                await asyncio.sleep(2.0)  # Ждем 2 секунды
                
                # Проверяем данные альбома из глобального словаря
                if task_key not in post_now_process_photo._album_data:
                    return
                
                current_album_photos = post_now_process_photo._album_data[task_key]['photos']
                album_state = post_now_process_photo._album_data[task_key]['state']
                
                # Если альбом не изменился (то же количество фото), завершаем обработку
                if len(current_album_photos) == photos_count_at_task_creation:
                    
                    logger.info(f"Альбом завершен. Всего фото: {len(current_album_photos)}")
                    
                    # Удаляем задачу и данные альбома из словарей
                    if task_key in post_now_process_photo._album_tasks:
                        del post_now_process_photo._album_tasks[task_key]
                    if task_key in post_now_process_photo._album_data:
                        del post_now_process_photo._album_data[task_key]
                    if task_key in post_now_process_photo._album_message_sent:
                        post_now_process_photo._album_message_sent.remove(task_key)
                    
                    # Сохраняем все фото как список в состоянии
                    await album_state.update_data(
                        photo_paths=current_album_photos.copy(),
                        photo_path=current_album_photos[0] if current_album_photos else None
                    )
                    
                    # Устанавливаем состояние ожидания промпта
                    await album_state.set_state(PostNowStates.waiting_for_prompt)
                    
                    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
                    ])
                    
                    photo_text = "фотографий" if len(current_album_photos) > 1 else "фотография"
                    await message.answer(
                        f"✅ <b>{len(current_album_photos)} {photo_text} получено!</b>\n\n"
                        "<b>Шаг 2:</b> Отправьте промпт (описание того, какой пост нужно создать)\n\n"
                        "Например:\n"
                        "• \"Создай отчетный пост о текущих объектах\"\n"
                        "• \"Напиши экспертную статью о земельных вопросах\"\n"
                        "• \"Сделай пост об услугах компании\"",
                        reply_markup=cancel_keyboard,
                        parse_mode="HTML"
                    )
                    logger.info("Сообщение с запросом промпта отправлено пользователю")
            
            # Отменяем предыдущую задачу для этого альбома, если она есть
            if task_key in post_now_process_photo._album_tasks:
                try:
                    post_now_process_photo._album_tasks[task_key].cancel()
                except:
                    pass
            
            # Создаем и сохраняем задачу обработки альбома
            import asyncio
            task = asyncio.create_task(process_album_after_delay())
            post_now_process_photo._album_tasks[task_key] = task
            
            return
        
        # Одиночное фото или последнее фото в альбоме
        data = await state.get_data()
        album_photos = data.get('album_photos', [])
        
        if album_photos:
            # Если были фото из альбома, добавляем текущее
            photo = message.photo[-1]
            file_info = await message.bot.get_file(photo.file_id)
            photo_path = dependencies.file_service.get_folder_path('photos') / f"{photo.file_id}.jpg"
            photo_path.parent.mkdir(parents=True, exist_ok=True)
            await message.bot.download_file(file_info.file_path, destination=str(photo_path))
            album_photos.append(str(photo_path.absolute()))
            
            # Сохраняем все фото как список
            await state.update_data(photo_paths=album_photos)
            logger.info(f"Альбом завершен. Всего фото: {len(album_photos)}")
        else:
            # Одиночное фото
            photo = message.photo[-1]
            file_info = await message.bot.get_file(photo.file_id)
            photo_path = dependencies.file_service.get_folder_path('photos') / f"{photo.file_id}.jpg"
            photo_path.parent.mkdir(parents=True, exist_ok=True)
            await message.bot.download_file(file_info.file_path, destination=str(photo_path))
            logger.info(f"Фото скачано: {photo_path.absolute()}")
            
            # Сохраняем путь к фото в состоянии (для обратной совместимости)
            await state.update_data(photo_path=str(photo_path.absolute()), photo_paths=[str(photo_path.absolute())])
            logger.info(f"Путь к фото сохранен в состоянии: {photo_path.absolute()}")
        
        # Устанавливаем состояние ожидания промпта
        await state.set_state(PostNowStates.waiting_for_prompt)
        new_state = await state.get_state()
        logger.info(f"Состояние изменено на: {new_state}")
        
        cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
        ])
        
        # Определяем количество фото для сообщения
        data = await state.get_data()
        photo_paths = data.get('photo_paths', [])
        photo_count = len(photo_paths) if photo_paths else 1
        
        photo_text = "фотография" if photo_count == 1 else f"{photo_count} фотографий"
        await message.answer(
            f"✅ <b>{photo_text.capitalize()} получена!</b>\n\n"
            "<b>Шаг 2:</b> Отправьте промпт (описание того, какой пост нужно создать)\n\n"
            "Например:\n"
            "• \"Создай отчетный пост о текущих объектах\"\n"
            "• \"Напиши экспертную статью о земельных вопросах\"\n"
            "• \"Сделай пост об услугах компании\"",
            reply_markup=cancel_keyboard,
            parse_mode="HTML"
        )
        logger.info("Сообщение с запросом промпта отправлено пользователю")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка при обработке фото: {str(e)}")
        await safe_clear_state(state)


@router.message(PostNowStates.waiting_for_prompt)
async def post_now_process_prompt(message: Message, state: FSMContext):
    """Обрабатывает промпт и генерирует пост"""
    logger.info(f"🟡 Обработчик post_now_process_prompt вызван для пользователя {message.from_user.id}")
    current_state = await state.get_state()
    logger.info(f"🟡 Текущее состояние FSM: {current_state}")
    
    # Если пользователь отправил фото вместо текста, переключаемся на обработку фото
    if message.photo:
        logger.warning(f"⚠️ Пользователь отправил фото в состоянии waiting_for_prompt, переключаемся на обработку фото")
        await state.set_state(PostNowStates.waiting_for_photo)
        # Рекурсивно вызываем обработчик фото
        from handlers.admin_handlers import post_now_process_photo
        await post_now_process_photo(message, state)
        return
    
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    # Проверка на отмену
    if message.text and message.text.lower().strip() in ['отмена', 'cancel', 'назад']:
        await safe_clear_state(state)
        await message.answer("❌ Публикация отменена.", reply_markup=get_main_menu_keyboard())
        return
    
    if not message.text:
        cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
        ])
        await message.answer(
            "❌ <b>Промпт обязателен!</b>\n\n"
            "Пожалуйста, отправьте текстовое описание того, какой пост нужно создать.",
            reply_markup=cancel_keyboard,
            parse_mode="HTML"
        )
        return
    
    try:
        data = await state.get_data()
        # Поддерживаем как старый формат (одно фото), так и новый (несколько фото)
        photo_paths = data.get('photo_paths', [])
        photo_path = data.get('photo_path')  # Для обратной совместимости
        video_paths = data.get('video_paths', [])
        video_path = data.get('video_path')  # Для видео
        has_video = data.get('has_video', False)
        
        # Если есть список фото, используем его, иначе используем одно фото
        if not photo_paths and photo_path:
            photo_paths = [photo_path]
        
        # Если есть видео, добавляем его в список медиа
        if video_paths:
            pass  # Видео уже в списке
        elif video_path:
            video_paths = [video_path]
        
        if not photo_paths and not video_paths:
            await message.answer("❌ Ошибка: медиафайлы не найдены. Начните заново.")
            await safe_clear_state(state)
            return
        
        prompt = message.text.strip()
        
        # Сохраняем промпт в состоянии
        await state.update_data(user_prompt=prompt)
        
        # Спрашиваем, хочет ли пользователь добавить источники
        cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, добавить источники", callback_data="post_now_add_sources"),
                InlineKeyboardButton(text="➡️ Пропустить", callback_data="post_now_skip_sources")
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
        ])
        
        await message.answer(
            "🔗 <b>Добавить источники?</b>\n\n"
            "Вы можете прикрепить ссылки на сайты, Telegram каналы или VK группы для дополнительного контекста.\n\n"
            "Источники будут проанализированы через AI и использованы при генерации поста.",
            reply_markup=cancel_keyboard,
            parse_mode="HTML"
        )
        await state.set_state(PostNowStates.waiting_for_sources)
        return
        
        # Генерируем пост на основе медиа и промпта
        if has_video:
            # Есть видео - анализируем его через AI
            video_description = None
            if video_paths:
                try:
                    logger.info(f"Анализ видео через AI: {video_paths[0]}")
                    video_description = await dependencies.ai_service.analyze_video(video_paths[0])
                    logger.info(f"Описание видео получено: {video_description[:100]}...")
                except Exception as e:
                    logger.error(f"Ошибка при анализе видео: {e}", exc_info=True)
                    video_description = f"Видео со строительного объекта. [Ошибка при анализе: {str(e)}]"
            
            # Если есть и фото, и видео - анализируем оба
            if photo_paths:
                # Анализируем фото
                if len(photo_paths) == 1:
                    photo_description = await dependencies.ai_service.analyze_photo(photo_paths[0])
                else:
                    photo_description = await dependencies.ai_service.analyze_multiple_photos(photo_paths)
                
                # Объединяем описания
                combined_description = f"{photo_description}\n\n{video_description}" if video_description else photo_description
                
                # Генерируем пост на основе фото и видео
                prompt_with_media = f"""{prompt}

КРИТИЧЕСКИ ВАЖНО: Используй ТОЛЬКО информацию из описания фотографий и видео ниже.
НЕ придумывай информацию о других объектах или работах, которых нет в описании.
НЕ используй шаблонные тексты о торговых центрах, солнечных панелях или других объектах, если их нет в описании.
Пост должен точно отражать то, что изображено на предоставленных медиафайлах."""
                post_text = await dependencies.ai_service.generate_post_text(
                    prompt=prompt_with_media,
                    photos_description=combined_description,
                    use_post_now_prompt=True
                )
            else:
                # Только видео - генерируем пост на основе анализа видео
                prompt_with_video = f"""{prompt}

КРИТИЧЕСКИ ВАЖНО: Используй ТОЛЬКО информацию из описания видео ниже.
НЕ придумывай информацию о других объектах или работах, которых нет в описании.
НЕ используй шаблонные тексты о торговых центрах, солнечных панелях или других объектах, если их нет в описании.
Пост должен точно отражать то, что показано в предоставленном видео."""
                post_text = await dependencies.ai_service.generate_post_text(
                    prompt=prompt_with_video,
                    photos_description=video_description,
                    use_post_now_prompt=True
                )
            
            # Применяем очистку и форматирование
            from services.ai_service import clean_ai_response, markdown_to_html
            post_text = clean_ai_response(post_text)
            post_text = markdown_to_html(post_text)
            # Для "Опубликовать сейчас" НЕ обрезаем до 900 символов - структура из 4 абзацев важнее
            # Проверяем только критическую длину для Telegram (2000 символов)
            if len(post_text) > 2000:
                logger.warning(f"Пост превышает 2000 символов ({len(post_text)}), обрезаем")
                post_text = post_text[:2000] + "..."
            
            photos = []  # Видео будет обработано отдельно при публикации
        else:
            # Есть только фото - используем обычную генерацию
            post_text, photos = await dependencies.post_service._generate_post_from_photo_and_prompt(
                photo_paths, prompt
            )
        
        # Удаляем сообщение о загрузке
        try:
            await loading_msg.delete()
        except:
            pass
        
        if not post_text or "Ошибка" in post_text or post_text.startswith("Ошибка"):
            await message.answer(
                f"❌ <b>Ошибка при генерации поста</b>\n\n"
                f"{post_text}\n\n"
                f"Попробуйте снова или проверьте логи на сервере.",
                parse_mode="HTML"
            )
            await safe_clear_state(state)
            return
        
        # Сохраняем сгенерированный пост в состоянии для одобрения
        await state.update_data(
            generated_post_text=post_text,
            generated_photo_paths=photos,  # Сохраняем список фото
            generated_photo_path=photos[0] if photos else None  # Для обратной совместимости
        )
        await state.set_state(PostNowStates.waiting_for_approval)
        
        # Отправляем пост на согласование
        # Сохраняем фото для черновика
        dependencies.telegram_service._draft_photos[message.message_id] = photos.copy()
        
        # Отправляем пост с кнопками одобрения/редактирования
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять и опубликовать", callback_data="post_now_approve"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_now_edit")
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")
            ]
        ])
        
        # Отправляем фото с текстом поста
        try:
            from pathlib import Path
            from aiogram.types import InputMediaPhoto
            
            MAX_CAPTION_LENGTH = 1024
            header = "📝 <b>Черновик поста для согласования:</b>\n\n"
            full_text = f"{header}{post_text}"
            
            if len(photos) == 1:
                # Одно фото
                photo_file = Path(photos[0])
                if photo_file.exists():
                    with open(photos[0], 'rb') as photo:
                        if len(full_text) <= MAX_CAPTION_LENGTH:
                            sent_message = await message.answer_photo(
                                photo=photo,
                                caption=full_text,
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                        else:
                            # Текст слишком длинный - отправляем фото с коротким caption и текст отдельно
                            photo.seek(0)
                            photo_message = await message.answer_photo(
                                photo=photo,
                                caption=f"{header}📝 Полный текст ниже ⬇️",
                                parse_mode="HTML"
                            )
                            sent_message = await message.answer(
                                text=full_text,
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                            dependencies.telegram_service._draft_photos[sent_message.message_id] = photos.copy()
                        dependencies.telegram_service._draft_photos[sent_message.message_id] = photos.copy()
                else:
                    # Если фото не найдено, отправляем только текст
                    sent_message = await message.answer(
                        f"📝 <b>Черновик поста для согласования:</b>\n\n{post_text}",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
            else:
                # Несколько фото - используем медиагруппу
                media = []
                for i, photo_path in enumerate(photos):
                    photo_file = Path(photo_path)
                    if photo_file.exists():
                        with open(photo_path, 'rb') as photo_data:
                            if i == 0 and len(full_text) <= MAX_CAPTION_LENGTH:
                                # Первое фото с полным текстом в caption
                                media.append(InputMediaPhoto(
                                    media=photo_data,
                                    caption=full_text,
                                    parse_mode="HTML"
                                ))
                            else:
                                # Остальные фото без caption или с коротким
                                photo_data.seek(0)
                                media.append(InputMediaPhoto(media=photo_data))
                
                if media:
                    sent_messages = await message.answer_media_group(media=media)
                    # Отправляем текст отдельным сообщением с кнопками, если он не поместился в caption
                    if len(full_text) > MAX_CAPTION_LENGTH:
                        sent_message = await message.answer(
                            text=full_text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                        dependencies.telegram_service._draft_photos[sent_message.message_id] = photos.copy()
                    else:
                        # Если текст поместился в caption первого фото, отправляем кнопки отдельным сообщением
                        sent_message = await message.answer(
                            text="Выберите действие:",
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                        dependencies.telegram_service._draft_photos[sent_message.message_id] = photos.copy()
                else:
                    # Если ни одно фото не найдено, отправляем только текст
                    sent_message = await message.answer(
                        f"📝 <b>Черновик поста для согласования:</b>\n\n{post_text}",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}", exc_info=True)
            # Fallback: отправляем только текст
            sent_message = await message.answer(
                f"📝 <b>Черновик поста для согласования:</b>\n\n{post_text}",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Ошибка при публикации поста: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка при публикации: {str(e)}")
        await safe_clear_state(state)


# ========== Обработчики одобрения/редактирования для "Опубликовать сейчас" ==========

@router.callback_query(F.data == "post_now_approve")
async def post_now_approve(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Принять и опубликовать' для функции 'Опубликовать сейчас'"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    try:
        data = await state.get_data()
        post_text = data.get('generated_post_text')
        photo_paths = data.get('generated_photo_paths', [])
        photo_path = data.get('generated_photo_path')  # Для обратной совместимости
        
        if not post_text:
            # Пытаемся получить текст из сообщения
            post_text = callback.message.text or callback.message.caption or ""
            if post_text:
                # Убираем заголовок
                if "Черновик поста для согласования:" in post_text:
                    post_text = post_text.split("\n\n", 1)[1] if "\n\n" in post_text else post_text.replace("Черновик поста для согласования:", "").strip()
                post_text = post_text.replace("<b>Черновик поста для согласования:</b>", "").strip()
        
        if not post_text:
            await safe_answer_callback(callback, "Не удалось найти текст поста", show_alert=True)
            return
        
        # Получаем фото из сохраненных путей или из состояния
        photos = dependencies.telegram_service.get_draft_photos(callback.message.message_id)
        if not photos:
            # Используем фото из состояния
            if photo_paths:
                photos = photo_paths
            elif photo_path:
                photos = [photo_path]
        
        if not photos:
            # Пытаемся скачать из сообщения
            if callback.message.photo:
                try:
                    photo = callback.message.photo[-1]
                    file_info = await callback.message.bot.get_file(photo.file_id)
                    temp_path = dependencies.file_service.get_folder_path('photos') / f"{photo.file_id}.jpg"
                    temp_path.parent.mkdir(parents=True, exist_ok=True)
                    await callback.message.bot.download_file(file_info.file_path, destination=str(temp_path))
                    photos = [str(temp_path.absolute())]
                except Exception as e:
                    logger.error(f"Ошибка при скачивании фотографии: {e}", exc_info=True)
        
        await safe_answer_callback(callback, "Публикую пост...")
        
        # Публикуем пост
        results = await dependencies.post_service.publish_approved_post(post_text, photos or [])
        
        await safe_edit_message(
            callback,
            f"✅ <b>Пост опубликован!</b>\n\n"
            f"Telegram: {results.get('telegram', 'N/A')}\n"
            f"VK: {results.get('vk', 'N/A')}",
            reply_markup=None
        )
        
        await safe_clear_state(state)
        
    except Exception as e:
        logger.error(f"Ошибка при публикации поста: {e}", exc_info=True)
        await safe_answer_callback(callback, f"Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data == "post_now_edit")
async def post_now_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Редактировать' для функции 'Опубликовать сейчас'"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await safe_answer_callback(callback)
    
    # Получаем текст поста из сообщения
    post_text = callback.message.text or callback.message.caption or ""
    if post_text:
        # Убираем заголовок
        if "Черновик поста для согласования:" in post_text:
            post_text = post_text.split("\n\n", 1)[1] if "\n\n" in post_text else post_text.replace("Черновик поста для согласования:", "").strip()
        post_text = post_text.replace("<b>Черновик поста для согласования:</b>", "").strip()
    
    # Сохраняем исходный текст и фото в состоянии
    data = await state.get_data()
    photo_path = data.get('generated_photo_path')
    photo_paths = data.get('generated_photo_paths', [])
    
    # Если нет списка фото, используем одно фото
    if not photo_paths and photo_path:
        photo_paths = [photo_path]
    
    await state.update_data(
        original_post_text=post_text,
        original_photo_path=photo_path,
        original_photo_paths=photo_paths  # Сохраняем список фото для функции "Опубликовать сейчас"
    )
    
    # Переходим в состояние ожидания правок (используем существующее состояние)
    await state.set_state(PostApprovalStates.waiting_for_edits)
    
    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
    ])
    
    await callback.message.answer(
        "✏️ <b>Редактирование поста</b>\n\n"
        "Пожалуйста, отправьте текст правок для этого поста:\n\n"
        "Например:\n"
        "• \"сократи текст в 3 раза\"\n"
        "• \"добавь больше эмодзи\"\n"
        "• \"измени стиль на более дружелюбный\"",
        reply_markup=cancel_keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "post_now_add_sources")
async def post_now_add_sources(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Добавить источники'"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await safe_answer_callback(callback)
    
    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Готово", callback_data="post_now_sources_done"),
            InlineKeyboardButton(text="➡️ Пропустить", callback_data="post_now_skip_sources")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
    ])
    
    await callback.message.answer(
        "🔗 <b>Добавление источников</b>\n\n"
        "Отправьте ссылки на источники (по одной ссылке в сообщении):\n\n"
        "• Сайты: https://example.com\n"
        "• Telegram каналы: https://t.me/channel_name\n"
        "• VK группы: https://vk.com/group_name\n\n"
        "Можно добавить несколько ссылок. После каждой ссылки нажмите 'Готово' или 'Пропустить'.",
        reply_markup=cancel_keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "post_now_skip_sources")
async def post_now_skip_sources(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Пропустить источники' - переходит к генерации поста"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await safe_answer_callback(callback)
    await _generate_post_from_state(callback.message, state)


@router.callback_query(F.data == "post_now_sources_done")
async def post_now_sources_done(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Готово' для источников - переходит к генерации поста"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await safe_answer_callback(callback)
    await _generate_post_from_state(callback.message, state)


@router.message(PostNowStates.waiting_for_sources)
async def post_now_process_sources(message: Message, state: FSMContext):
    """Обрабатывает источники (ссылки) от пользователя"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    # Проверка на отмену
    if message.text and message.text.lower().strip() in ['отмена', 'cancel', 'назад']:
        await safe_clear_state(state)
        await message.answer("❌ Публикация отменена.", reply_markup=get_main_menu_keyboard())
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте ссылку на источник.")
        return
    
    url = message.text.strip()
    
    # Базовая валидация URL
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer(
            "❌ Неверный формат ссылки!\n\n"
            "Используйте формат:\n"
            "• https://example.com\n"
            "• https://t.me/channel_name\n"
            "• https://vk.com/group_name"
        )
        return
    
    # Сохраняем ссылку в состоянии
    data = await state.get_data()
    sources = data.get('sources', [])
    sources.append(url)
    await state.update_data(sources=sources)
    
    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Готово", callback_data="post_now_sources_done"),
            InlineKeyboardButton(text="➡️ Пропустить", callback_data="post_now_skip_sources")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")]
    ])
    
    await message.answer(
        f"✅ Ссылка добавлена: {url}\n\n"
        f"Всего источников: {len(sources)}\n\n"
        "Отправьте еще одну ссылку или нажмите 'Готово' для продолжения.",
        reply_markup=cancel_keyboard
    )


async def _generate_post_from_state(message: Message, state: FSMContext):
    """Генерирует пост на основе данных из состояния"""
    try:
        data = await state.get_data()
        prompt = data.get('user_prompt', '')
        photo_paths = data.get('photo_paths', [])
        photo_path = data.get('photo_path')
        video_paths = data.get('video_paths', [])
        video_path = data.get('video_path')
        has_video = data.get('has_video', False)
        sources = data.get('sources', [])
        
        if not prompt:
            await message.answer("❌ Ошибка: промпт не найден. Начните заново.")
            await safe_clear_state(state)
            return
        
        # Если есть список фото, используем его, иначе используем одно фото
        if not photo_paths and photo_path:
            photo_paths = [photo_path]
        
        # Если есть видео, добавляем его в список медиа
        if video_paths:
            pass
        elif video_path:
            video_paths = [video_path]
        
        if not photo_paths and not video_paths:
            await message.answer("❌ Ошибка: медиафайлы не найдены. Начните заново.")
            await safe_clear_state(state)
            return
        
        # Отправляем сообщение о генерации
        if has_video:
            media_text = f"{len(video_paths)} видео" if len(video_paths) > 1 else "видео"
            if photo_paths:
                media_text += f" и {len(photo_paths)} фото" if len(photo_paths) > 1 else " и фото"
        else:
            media_text = f"{len(photo_paths)} фотографий" if len(photo_paths) > 1 else "фото"
        
        sources_text = f" и {len(sources)} источников" if sources else ""
        loading_msg = await message.answer(f"⏳ Генерирую пост на основе {media_text}{sources_text} и промпта...")
        
        # Анализируем источники, если они есть
        sources_context = ""
        if sources:
            try:
                sources_context = await dependencies.ai_service.analyze_sources(sources)
                logger.info(f"Источники проанализированы: {len(sources_context)} символов")
            except Exception as e:
                logger.error(f"Ошибка при анализе источников: {e}", exc_info=True)
                sources_context = f"\n\nДополнительные источники для контекста:\n" + "\n".join([f"- {url}" for url in sources])
        
        # Сохраняем запрос в историю
        request_id = None
        if dependencies.post_history_service:
            request_id = dependencies.post_history_service.add_request(
                admin_id=message.from_user.id,
                request_type="publish_now",
                prompt=prompt,
                photos_count=len(photo_paths) + len(video_paths)
            )
            # Сохраняем request_id в состоянии для обработки ошибок
            await state.update_data(_current_request_id=request_id)
        
        # Генерируем пост на основе медиа, промпта и источников
        if has_video:
            video_description = None
            if video_paths:
                try:
                    logger.info(f"Анализ видео через AI: {video_paths[0]}")
                    video_description = await dependencies.ai_service.analyze_video(video_paths[0])
                    logger.info(f"Описание видео получено: {video_description[:100]}...")
                except Exception as e:
                    logger.error(f"Ошибка при анализе видео: {e}", exc_info=True)
                    video_description = f"Видео со строительного объекта. [Ошибка при анализе: {str(e)}]"
            
            if photo_paths:
                if len(photo_paths) == 1:
                    photo_description = await dependencies.ai_service.analyze_photo(photo_paths[0])
                else:
                    photo_description = await dependencies.ai_service.analyze_multiple_photos(photo_paths)
                
                combined_description = f"{photo_description}\n\n{video_description}" if video_description else photo_description
                
                prompt_with_media = f"""{prompt}

КРИТИЧЕСКИ ВАЖНО: Используй ТОЛЬКО информацию из описания фотографий и видео ниже.
НЕ придумывай информацию о других объектах или работах, которых нет в описании.
Пост должен точно отражать то, что изображено на предоставленных медиафайлах."""
                
                if sources_context:
                    prompt_with_media += f"\n\nДополнительный контекст из источников:\n{sources_context}"
                
                post_text = await dependencies.ai_service.generate_post_text(
                    prompt=prompt_with_media,
                    photos_description=combined_description,
                    use_post_now_prompt=True
                )
            else:
                prompt_with_video = f"""{prompt}

КРИТИЧЕСКИ ВАЖНО: Используй ТОЛЬКО информацию из описания видео ниже.
Пост должен точно отражать то, что показано в предоставленном видео."""
                
                if sources_context:
                    prompt_with_video += f"\n\nДополнительный контекст из источников:\n{sources_context}"
                
                post_text = await dependencies.ai_service.generate_post_text(
                    prompt=prompt_with_video,
                    photos_description=video_description,
                    use_post_now_prompt=True
                )
            
            from services.ai_service import clean_ai_response, markdown_to_html
            post_text = clean_ai_response(post_text)
            post_text = markdown_to_html(post_text)
            # Для "Опубликовать сейчас" НЕ обрезаем до 900 символов - структура из 4 абзацев важнее
            # Проверяем только критическую длину для Telegram (2000 символов)
            if len(post_text) > 2000:
                logger.warning(f"Пост превышает 2000 символов ({len(post_text)}), обрезаем")
                post_text = post_text[:2000] + "..."
            
            photos = []
        else:
            # Есть только фото - используем обычную генерацию с учетом источников
            if sources_context:
                prompt = f"{prompt}\n\nДополнительный контекст из источников:\n{sources_context}"
            
            post_text, photos = await dependencies.post_service._generate_post_from_photo_and_prompt(
                photo_paths, prompt
            )
        
        # Удаляем сообщение о загрузке
        try:
            await loading_msg.delete()
        except:
            pass
        
        if not post_text or "Ошибка" in post_text or post_text.startswith("Ошибка"):
            await message.answer(
                f"❌ <b>Ошибка при генерации поста</b>\n\n"
                f"{post_text}\n\n"
                f"Попробуйте снова или проверьте логи на сервере.",
                parse_mode="HTML"
            )
            await safe_clear_state(state)
            return
        
        # Сохраняем сгенерированный пост в состоянии для одобрения
        await state.update_data(
            generated_post_text=post_text,
            generated_photo_paths=photos,
            generated_photo_path=photos[0] if photos else None
        )
        await state.set_state(PostNowStates.waiting_for_approval)
        
        # Отправляем пост на согласование (код из оригинального post_now_process_prompt)
        dependencies.telegram_service._draft_photos[message.message_id] = photos.copy()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять и опубликовать", callback_data="post_now_approve"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_now_edit")
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")
            ]
        ])
        
        try:
            from pathlib import Path
            from aiogram.types import InputMediaPhoto
            
            MAX_CAPTION_LENGTH = 1024
            header = "📝 <b>Черновик поста для согласования:</b>\n\n"
            full_text = f"{header}{post_text}"
            
            if len(photos) == 1:
                photo_file = Path(photos[0])
                if photo_file.exists():
                    with open(photos[0], 'rb') as photo:
                        if len(full_text) <= MAX_CAPTION_LENGTH:
                            sent_message = await message.answer_photo(
                                photo=photo,
                                caption=full_text,
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                        else:
                            photo.seek(0)
                            photo_message = await message.answer_photo(
                                photo=photo,
                                caption=f"{header}📝 Полный текст ниже ⬇️",
                                parse_mode="HTML"
                            )
                            sent_message = await message.answer(
                                text=full_text,
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                            dependencies.telegram_service._draft_photos[sent_message.message_id] = photos.copy()
                        dependencies.telegram_service._draft_photos[sent_message.message_id] = photos.copy()
                else:
                    sent_message = await message.answer(
                        f"📝 <b>Черновик поста для согласования:</b>\n\n{post_text}",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
            else:
                media = []
                for i, photo_path in enumerate(photos):
                    photo_file = Path(photo_path)
                    if photo_file.exists():
                        with open(photo_path, 'rb') as photo_data:
                            if i == 0 and len(full_text) <= MAX_CAPTION_LENGTH:
                                media.append(InputMediaPhoto(
                                    media=photo_data,
                                    caption=full_text,
                                    parse_mode="HTML"
                                ))
                            else:
                                photo_data.seek(0)
                                media.append(InputMediaPhoto(media=photo_data))
                
                if media:
                    sent_messages = await message.answer_media_group(media=media)
                    if len(full_text) > MAX_CAPTION_LENGTH:
                        sent_message = await message.answer(
                            text=full_text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                        dependencies.telegram_service._draft_photos[sent_message.message_id] = photos.copy()
                    else:
                        sent_message = await message.answer(
                            text="Выберите действие:",
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                        dependencies.telegram_service._draft_photos[sent_message.message_id] = photos.copy()
                else:
                    sent_message = await message.answer(
                        f"📝 <b>Черновик поста для согласования:</b>\n\n{post_text}",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}", exc_info=True)
            sent_message = await message.answer(
                f"📝 <b>Черновик поста для согласования:</b>\n\n{post_text}",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Ошибка при генерации поста: {e}", exc_info=True)
        # Обновляем историю с ошибкой, если request_id был создан
        try:
            data = await state.get_data()
            request_id = data.get('_current_request_id')
            if dependencies.post_history_service and request_id:
                dependencies.post_history_service.update_request(
                    request_id=request_id,
                    status="failed",
                    error=str(e)[:500]
                )
        except:
            pass  # Игнорируем ошибки при обновлении истории
        await message.answer(f"❌ Ошибка при генерации поста: {str(e)}")
        await safe_clear_state(state)


@router.callback_query(F.data == "post_now_cancel")
async def post_now_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Отмена' для функции 'Опубликовать сейчас'"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await safe_answer_callback(callback, "Публикация отменена", show_alert=True)
    await safe_edit_message(
        callback,
        "❌ <b>Публикация отменена</b>",
        reply_markup=None
    )
    await safe_clear_state(state)


# Модифицируем обработчик process_edits для поддержки функции "Опубликовать сейчас"
@router.message(PostApprovalStates.waiting_for_edits)
async def process_edits(message: Message, state: FSMContext):
    """Обрабатывает правки от администратора (для обычных черновиков, запланированных постов и 'Опубликовать сейчас')"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    # Проверка на отмену
    if message.text and message.text.lower().strip() in ['отмена', 'cancel', 'назад']:
        await safe_clear_state(state)
        await message.answer("❌ Редактирование отменено.", reply_markup=get_main_menu_keyboard())
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с правками.")
        return
    
    if not dependencies.post_service:
        await message.answer("Сервис недоступен")
        await safe_clear_state(state)
        return
    
    edits = message.text.strip()
    
    if not edits:
        await message.answer("Пожалуйста, отправьте текст правок.")
        return
    
    data = await state.get_data()
    day_of_week = data.get('scheduled_post_day')  # Проверяем, редактируется ли запланированный пост
    original_post_text = data.get('original_post_text', '')
    original_photos = data.get('original_photos', [])
    original_photo_paths = data.get('original_photo_paths', [])  # Для функции "Опубликовать сейчас"
    original_photo_path = data.get('original_photo_path')  # Для обратной совместимости
    
    # Если нет списка фото, используем одно фото
    if not original_photo_paths and original_photo_path:
        original_photo_paths = [original_photo_path]
    
    if not original_post_text:
        await message.answer("Не удалось найти исходный текст поста. Попробуйте создать пост заново.")
        await safe_clear_state(state)
        return
    
    # Сохраняем запрос на редактирование в историю
    request_id = None
    if dependencies.post_history_service:
        request_id = dependencies.post_history_service.add_request(
            admin_id=message.from_user.id,
            request_type="edit",
            prompt=edits,
            original_post=original_post_text,
            photos_count=len(original_photos) + len(original_photo_paths)
        )
    
    try:
        await message.answer("⏳ Перерабатываю пост с учетом ваших правок...")
        
        # Перерабатываем пост через AI
        logger.info(f"Переработка поста. Исходный текст: {len(original_post_text)} символов. Правки: {edits}")
        refined_post = await dependencies.post_service.refine_post(original_post_text, edits)
        logger.info(f"Пост переработан. Новый текст: {len(refined_post)} символов")
        
        # Если это запланированный пост, обновляем его
        if day_of_week and dependencies.scheduled_posts_service:
            dependencies.scheduled_posts_service.add_scheduled_post(
                day_of_week=day_of_week,
                post_text=refined_post,
                photos=original_photos,
                admin_id=message.from_user.id
            )
            
            day_names = {
                'monday': 'Понедельник',
                'tuesday': 'Вторник',
                'wednesday': 'Среда',
                'thursday': 'Четверг',
                'friday': 'Пятница',
                'saturday': 'Суббота'
            }
            day_name = day_names.get(day_of_week, day_of_week)
            
            await message.answer(
                f"✅ <b>Запланированный пост обновлен!</b>\n\n"
                f"📅 День: <b>{day_name}</b>\n\n"
                f"Пост будет опубликован в запланированное время.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="HTML"
            )
        elif original_photo_paths:
            # Это функция "Опубликовать сейчас" - используем специальный метод редактирования
            logger.info("Используем специальный метод редактирования для 'Опубликовать сейчас'")
            refined_post = await dependencies.post_service.refine_post_now(original_post_text, edits)
            logger.info(f"Пост 'Опубликовать сейчас' переработан. Новый текст: {len(refined_post)} символов")
            
            # Обновляем историю с успешным результатом
            if dependencies.post_history_service and request_id:
                dependencies.post_history_service.update_request(
                    request_id=request_id,
                    generated_post=refined_post,
                    status="completed"
                )
            
            await state.update_data(
                generated_post_text=refined_post,
                generated_photo_paths=original_photo_paths,
                generated_photo_path=original_photo_paths[0] if original_photo_paths else None
            )
            await state.set_state(PostNowStates.waiting_for_approval)
            
            # Сохраняем фото для черновика
            dependencies.telegram_service._draft_photos[message.message_id] = original_photo_paths.copy()
            
            # Отправляем переработанный пост на согласование
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять и опубликовать", callback_data="post_now_approve"),
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_now_edit")
                ],
                [
                    InlineKeyboardButton(text="❌ Отмена", callback_data="post_now_cancel")
                ]
            ])
            
            try:
                from pathlib import Path
                from aiogram.types import InputMediaPhoto
                
                MAX_CAPTION_LENGTH = 1024
                header = "📝 <b>Черновик поста для согласования (после правок):</b>\n\n"
                full_text = f"{header}{refined_post}"
                
                if len(original_photo_paths) == 1:
                    # Одно фото
                    photo_file = Path(original_photo_paths[0])
                    if photo_file.exists():
                        with open(original_photo_paths[0], 'rb') as photo:
                            if len(full_text) <= MAX_CAPTION_LENGTH:
                                sent_message = await message.answer_photo(
                                    photo=photo,
                                    caption=full_text,
                                    reply_markup=keyboard,
                                    parse_mode="HTML"
                                )
                            else:
                                photo.seek(0)
                                photo_message = await message.answer_photo(
                                    photo=photo,
                                    caption=f"{header}📝 Полный текст ниже ⬇️",
                                    parse_mode="HTML"
                                )
                                sent_message = await message.answer(
                                    text=full_text,
                                    reply_markup=keyboard,
                                    parse_mode="HTML"
                                )
                                dependencies.telegram_service._draft_photos[sent_message.message_id] = original_photo_paths.copy()
                            dependencies.telegram_service._draft_photos[sent_message.message_id] = original_photo_paths.copy()
                    else:
                        await message.answer(
                            f"📝 <b>Черновик поста для согласования (после правок):</b>\n\n{refined_post}",
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                else:
                    # Несколько фото - используем медиагруппу
                    media = []
                    for i, photo_path in enumerate(original_photo_paths):
                        photo_file = Path(photo_path)
                        if photo_file.exists():
                            with open(photo_path, 'rb') as photo_data:
                                if i == 0 and len(full_text) <= MAX_CAPTION_LENGTH:
                                    media.append(InputMediaPhoto(
                                        media=photo_data,
                                        caption=full_text,
                                        parse_mode="HTML"
                                    ))
                                else:
                                    photo_data.seek(0)
                                    media.append(InputMediaPhoto(media=photo_data))
                    
                    if media:
                        sent_messages = await message.answer_media_group(media=media)
                        if len(full_text) > MAX_CAPTION_LENGTH:
                            sent_message = await message.answer(
                                text=full_text,
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                            dependencies.telegram_service._draft_photos[sent_message.message_id] = original_photo_paths.copy()
                        else:
                            sent_message = await message.answer(
                                text="Выберите действие:",
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                            dependencies.telegram_service._draft_photos[sent_message.message_id] = original_photo_paths.copy()
                    else:
                        await message.answer(
                            f"📝 <b>Черновик поста для согласования (после правок):</b>\n\n{refined_post}",
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
            except Exception as e:
                logger.error(f"Ошибка при отправке фото: {e}", exc_info=True)
                await message.answer(
                    f"📝 <b>Черновик поста для согласования (после правок):</b>\n\n{refined_post}",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        else:
            # Обычный черновик - отправляем на согласование
            await dependencies.post_service.send_for_approval(refined_post, original_photos)
            
            await message.answer(
                "✅ <b>Пост переработан и отправлен на согласование!</b>\n\n"
                f"Новая длина: {len(refined_post)} символов",
                parse_mode="HTML"
            )
        
        await safe_clear_state(state)
    
    except Exception as e:
        logger.error(f"Ошибка при переработке поста: {e}", exc_info=True)
        # Обновляем историю с ошибкой
        if dependencies.post_history_service and request_id:
            dependencies.post_history_service.update_request(
                request_id=request_id,
                status="failed",
                error=str(e)[:500]  # Ограничиваем длину ошибки
            )
        await message.answer(f"❌ Ошибка при переработке поста: {str(e)}")
        await safe_clear_state(state)


@router.callback_query(F.data == "schedule_edit_post_list")
async def schedule_edit_post_list(callback: CallbackQuery):
    """Показывает список постов для редактирования"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    post_types_config = PostTypesConfigService()
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    buttons = []
    for day_key, day_name in day_names.items():
        posts = post_types_config.get_post_types(day_key)
        if posts:
            for i, post in enumerate(posts):
                button_text = f"{day_name} - {post.get('time', '09:00')} - {post.get('name', 'Без названия')}"
                if len(button_text) > 40:
                    button_text = button_text[:37] + "..."
                buttons.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"schedule_edit_post_{day_key}_{i}"
                    )
                ])
    
    if not buttons:
        await safe_answer_callback(callback, "Нет постов для редактирования", show_alert=True)
        return
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_schedule")])
    
    await safe_edit_message(
        callback,
        "✏️ <b>Редактирование поста</b>\n\nВыберите пост для редактирования:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("schedule_edit_post_"))
async def schedule_edit_post_start(callback: CallbackQuery, state: FSMContext):
    """Начинает редактирование поста"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    parts = callback.data.replace("schedule_edit_post_", "").split("_")
    if len(parts) != 2:
        await safe_answer_callback(callback, "Ошибка формата", show_alert=True)
        return
    
    day = parts[0]
    post_index = int(parts[1])
    
    post_types_config = PostTypesConfigService()
    posts = post_types_config.get_post_types(day)
    
    if post_index >= len(posts):
        await safe_answer_callback(callback, "Пост не найден", show_alert=True)
        return
    
    post = posts[post_index]
    await state.update_data(day=day, post_index=post_index)
    await state.set_state(SchedulePostStates.waiting_for_time)
    
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    await safe_edit_message(
        callback,
        f"✏️ <b>Редактирование поста</b>\n\n"
        f"День: <b>{day_names.get(day, day)}</b>\n"
        f"Текущее время: <b>{post.get('time', '09:00')}</b>\n"
        f"Текущее название: <b>{post.get('name', 'Без названия')}</b>\n\n"
        f"Введите новое время в формате <b>HH:MM</b> (или отправьте 'пропустить'):\n\n"
        f"Или отправьте 'отмена' для отмены:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_schedule")]
        ])
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data == "schedule_delete_post_list")
async def schedule_delete_post_list(callback: CallbackQuery):
    """Показывает список постов для удаления"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    post_types_config = PostTypesConfigService()
    day_names = {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота'
    }
    
    buttons = []
    for day_key, day_name in day_names.items():
        posts = post_types_config.get_post_types(day_key)
        if posts:
            for i, post in enumerate(posts):
                button_text = f"{day_name} - {post.get('time', '09:00')} - {post.get('name', 'Без названия')}"
                if len(button_text) > 40:
                    button_text = button_text[:37] + "..."
                buttons.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"schedule_delete_post_{day_key}_{i}"
                    )
                ])
    
    if not buttons:
        await safe_answer_callback(callback, "Нет постов для удаления", show_alert=True)
        return
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_schedule")])
    
    await safe_edit_message(
        callback,
        "🗑️ <b>Удаление поста</b>\n\nВыберите пост для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("schedule_delete_post_"))
async def schedule_delete_post_confirm(callback: CallbackQuery):
    """Подтверждает и удаляет пост"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    parts = callback.data.replace("schedule_delete_post_", "").split("_")
    if len(parts) != 2:
        await safe_answer_callback(callback, "Ошибка формата", show_alert=True)
        return
    
    day = parts[0]
    post_index = int(parts[1])
    
    post_types_config = PostTypesConfigService()
    success = post_types_config.remove_post(day, post_index)
    
    if success:
        # Обновляем планировщик
        if dependencies.scheduler_service:
            dependencies.scheduler_service.setup_schedule()
        
        await safe_answer_callback(callback, "Пост удален", show_alert=True)
        await menu_schedule(callback)
    else:
        await safe_answer_callback(callback, "Ошибка при удалении поста", show_alert=True)



