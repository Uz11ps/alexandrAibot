"""Обработчики команд администратора"""
import logging
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


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id == settings.TELEGRAM_ADMIN_ID


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к этому боту.")
        return
    
    await message.answer(
        "👋 <b>Добро пожаловать в панель управления ботом!</b>\n\n"
        "Используйте кнопки ниже для навигации по меню.",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Показывает главное меню администратора"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
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
    
    status_text = (
        f"📊 <b>Статус бота</b>\n\n"
        f"Планировщик: {'✅ Включен' if dependencies.scheduler_service.is_enabled else '❌ Выключен'}\n"
        f"Задач в расписании: {len(dependencies.scheduler_service.scheduler.get_jobs())}\n"
        f"Google Drive: {'✅ Включен' if (dependencies.file_service and dependencies.file_service.google_drive and dependencies.file_service.google_drive.enabled) else '❌ Выключен'}\n"
        f"Фотографий в Drive: <b>{photos_count}</b>\n\n"
        f"Бот работает и готов к работе!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
    ])
    
    await safe_edit_message(callback, status_text, reply_markup=keyboard)
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
    all_types = post_types_config.get_all_post_types()
    
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
        post_type = all_types.get(day, {})
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
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.post_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    post_type = callback.data.replace("generate_", "")
    
    post_generators = {
        'monday': ('Понедельник', dependencies.post_service.generate_monday_post),
        'tuesday': ('Вторник', dependencies.post_service.generate_tuesday_post),
        'wednesday': ('Среда', dependencies.post_service.generate_wednesday_post),
        'thursday': ('Четверг', dependencies.post_service.generate_thursday_post),
        'friday': ('Пятница', dependencies.post_service.generate_friday_post),
        'saturday': ('Суббота', dependencies.post_service.generate_saturday_post)
    }
    
    if post_type not in post_generators:
        await safe_answer_callback(callback, "Неизвестный тип поста", show_alert=True)
        return
    
    await safe_answer_callback(callback, "Генерация поста...")
    
    try:
        day_name, generator = post_generators[post_type]
        logger.info(f"Начало генерации поста для {day_name} (тип: {post_type})")
        
        post_text, photos = await generator()
        
        logger.info(f"Пост для {day_name} сгенерирован успешно. Текст: {len(post_text)} символов, фото: {len(photos)}")
        
        # Отправляем на согласование
        logger.info(f"Отправка поста на согласование...")
        await dependencies.post_service.send_for_approval(post_text, photos)
        logger.info(f"Пост отправлен на согласование")
        
        await safe_edit_message(
            callback,
            f"✅ <b>Пост для {day_name} сгенерирован!</b>\n\n"
            f"Черновик отправлен на согласование.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка при генерации поста: {e}")
        await safe_answer_callback(callback, f"Ошибка: {str(e)}", show_alert=True)


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
    """Меню расписания"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    schedule_config = ScheduleConfigService()
    
    schedule_text = (
        "📅 <b>Расписание публикаций</b>\n\n"
        f"Понедельник: {schedule_config.get_schedule_time('monday')} - Отчет по объектам\n"
        f"Вторник: {schedule_config.get_schedule_time('tuesday')} - Экспертная статья\n"
        f"Среда: {schedule_config.get_schedule_time('wednesday')} - Отчет или мемы\n"
        f"Четверг: {schedule_config.get_schedule_time('thursday')} - Ответы на вопросы\n"
        f"Пятница: {schedule_config.get_schedule_time('friday')} - Обзор проектов\n"
        f"Суббота: {schedule_config.get_schedule_time('saturday')} - Услуги компании\n"
        f"Воскресенье: {schedule_config.get_schedule_time('sunday')} - Напоминания сотрудникам\n\n"
        "Выберите день для изменения времени:"
    )
    
    await safe_edit_message(
        callback,
        schedule_text,
        reply_markup=get_schedule_keyboard()
    )
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
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    employees_text = (
        "👥 <b>Управление сотрудниками</b>\n\n"
        "Функции:\n"
        "• Запрос материалов у сотрудников\n"
        "• Автоматические напоминания\n"
        "• Эскалация при отсутствии ответа\n\n"
        "Функция будет доработана."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
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
        "• Переписка с сотрудниками\n\n"
        "Функция будет доработана."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
    ])
    
    await safe_edit_message(callback, reports_text, reply_markup=keyboard)
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


@router.callback_query(F.data == "approve_post")
async def approve_post(callback: CallbackQuery):
    """Обработчик кнопки 'Принять' пост"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.post_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    try:
        # Получаем текст поста из сообщения
        post_text = callback.message.text or callback.message.caption
        if post_text:
            # Убираем заголовок "Черновик поста для согласования:"
            if "Черновик поста для согласования:" in post_text:
                post_text = post_text.split("\n\n", 1)[1] if "\n\n" in post_text else post_text
        
        # Получаем фотографии если есть
        photos = []
        if callback.message.photo:
            # TODO: Сохранить фото и получить путь
            pass
        
        # Публикуем пост
        results = await dependencies.post_service.publish_approved_post(post_text, photos)
        
        await safe_answer_callback(callback, "Пост опубликован!", show_alert=True)
        await safe_edit_message(
            callback,
            f"✅ <b>Пост опубликован!</b>\n\n"
            f"Telegram: {results.get('telegram', 'N/A')}\n"
            f"VK: {results.get('vk', 'N/A')}"
        )
    
    except Exception as e:
        logger.error(f"Ошибка при публикации поста: {e}")
        await safe_answer_callback(callback, "Ошибка при публикации", show_alert=True)


@router.callback_query(F.data == "edit_post")
async def request_edit(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Редактировать' пост"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await safe_answer_callback(callback)
    await state.set_state(PostApprovalStates.waiting_for_edits)
    
    # Сохраняем ID сообщения с черновиком
    await state.update_data(draft_message_id=callback.message.message_id)
    
    await callback.message.answer(
        "Пожалуйста, отправьте текст правок для этого поста:"
    )


@router.message(PostApprovalStates.waiting_for_edits)
async def process_edits(message: Message, state: FSMContext):
    """Обрабатывает правки от администратора"""
    if not dependencies.post_service:
        await message.answer("Сервис недоступен")
        await state.clear()
        return
    
    edits = message.text
    
    data = await state.get_data()
    draft_message_id = data.get('draft_message_id')
    
    try:
        # Получаем исходный текст поста
        # TODO: Получить исходный текст из сохраненного черновика
        
        # Перерабатываем пост
        # refined_post = await dependencies.post_service.refine_post(original_post, edits)
        
        await message.answer(
            "Пост переработан. Функция редактирования будет доработана."
        )
        
        await state.clear()
    
    except Exception as e:
        logger.error(f"Ошибка при обработке правок: {e}")
        await message.answer("Ошибка при обработке правок.")
        await state.clear()


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



