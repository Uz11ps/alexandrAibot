"""Обработчики управления источниками для администратора"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from handlers.utils import safe_answer_callback, safe_edit_message, safe_clear_state
from services import dependencies
from handlers.admin_handlers import is_admin

logger = logging.getLogger(__name__)
router = Router()


class SourceManagementStates(StatesGroup):
    """Состояния для управления источниками"""
    waiting_for_source_type = State()
    waiting_for_source_url = State()
    waiting_for_source_name = State()


@router.callback_query(F.data == "menu_sources")
async def menu_sources(callback: CallbackQuery):
    """Меню управления источниками"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.source_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    sources = dependencies.source_service.get_all_sources()
    
    if not sources:
        sources_text = (
            "🔗 <b>Управление источниками</b>\n\n"
            "Источники не добавлены.\n\n"
            "Добавьте Telegram каналы или VK группы для анализа и генерации постов."
        )
    else:
        sources_list = []
        for i, source in enumerate(sources, 1):
            status = "✅" if source.enabled else "❌"
            name_part = f" ({source.name})" if source.name else ""
            sources_list.append(
                f"{i}. {status} <b>{source.type.upper()}</b>{name_part}\n"
                f"   🔗 {source.url}"
            )
        
        sources_text = (
            f"🔗 <b>Управление источниками</b>\n\n"
            f"Всего источников: {len(sources)}\n\n"
            f"{chr(10).join(sources_list)}"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить источник", callback_data="source_add")],
        [InlineKeyboardButton(text="📋 Список источников", callback_data="source_list")],
        [InlineKeyboardButton(text="🗑️ Удалить источник", callback_data="source_remove")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
    ])
    
    await safe_edit_message(callback, sources_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "source_list")
async def source_list(callback: CallbackQuery):
    """Показывает список источников"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.source_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    sources = dependencies.source_service.get_all_sources()
    
    if not sources:
        sources_text = "📋 <b>Список источников</b>\n\nИсточники не добавлены."
    else:
        sources_list = []
        for i, source in enumerate(sources, 1):
            status = "✅" if source.enabled else "❌"
            name_part = f" ({source.name})" if source.name else ""
            sources_list.append(
                f"{i}. {status} <b>{source.type.upper()}</b>{name_part}\n"
                f"   🔗 {source.url}"
            )
        
        sources_text = (
            f"📋 <b>Список источников</b>\n\n"
            f"{chr(10).join(sources_list)}"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить источник", callback_data="source_add")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_sources")]
    ])
    
    await safe_edit_message(callback, sources_text, reply_markup=keyboard)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "source_add")
async def source_add_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс добавления источника"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    await state.set_state(SourceManagementStates.waiting_for_source_type)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 Telegram", callback_data="source_type_telegram"),
            InlineKeyboardButton(text="🔵 VK", callback_data="source_type_vk")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_sources")]
    ])
    
    await safe_edit_message(
        callback,
        "➕ <b>Добавление источника</b>\n\n"
        "Выберите тип источника:",
        reply_markup=keyboard
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("source_type_"))
async def source_process_type(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор типа источника"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    source_type = callback.data.split("_")[-1]  # "telegram" или "vk"
    
    await state.update_data(source_type=source_type)
    await state.set_state(SourceManagementStates.waiting_for_source_url)
    
    type_name = "Telegram канал" if source_type == "telegram" else "VK группа"
    example_url = "https://t.me/channel_name" if source_type == "telegram" else "https://vk.com/group_name"
    
    await safe_edit_message(
        callback,
        f"➕ <b>Добавление источника</b>\n\n"
        f"Тип: <b>{type_name}</b>\n\n"
        f"Отправьте URL источника:\n"
        f"Пример: {example_url}\n\n"
        f"Или отправьте 'отмена' для отмены:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_sources")]
        ])
    )
    await safe_answer_callback(callback)


@router.message(SourceManagementStates.waiting_for_source_url)
async def source_process_url(message: Message, state: FSMContext):
    """Обрабатывает URL источника"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с URL.")
        return
    
    if message.text.lower() in ['отмена', 'назад', 'cancel', 'back']:
        await state.clear()
        await message.answer("❌ Добавление источника отменено.", reply_markup=get_sources_menu_keyboard())
        return
    
    url = message.text.strip()
    data = await state.get_data()
    source_type = data.get('source_type')
    
    # Валидация URL
    if source_type == "telegram" and not url.startswith(("https://t.me/", "http://t.me/")):
        await message.answer(
            "❌ Неверный формат URL для Telegram!\n\n"
            "Используйте формат: https://t.me/channel_name\n\n"
            "Попробуйте снова или отправьте 'отмена':"
        )
        return
    
    if source_type == "vk" and not url.startswith(("https://vk.com/", "http://vk.com/")):
        await message.answer(
            "❌ Неверный формат URL для VK!\n\n"
            "Используйте формат: https://vk.com/group_name\n\n"
            "Попробуйте снова или отправьте 'отмена':"
        )
        return
    
    await state.update_data(source_url=url)
    await state.set_state(SourceManagementStates.waiting_for_source_name)
    
    await message.answer(
        f"✅ URL сохранен: <b>{url}</b>\n\n"
        "Теперь отправьте имя источника (опционально, для удобства):\n\n"
        "Или отправьте 'пропустить' для пропуска:",
        parse_mode="HTML"
    )


@router.message(SourceManagementStates.waiting_for_source_name)
async def source_process_name(message: Message, state: FSMContext):
    """Обрабатывает имя источника"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        await safe_clear_state(state)
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        return
    
    name = message.text.strip() if message.text.lower() not in ['пропустить', 'skip', ''] else None
    
    data = await state.get_data()
    source_type = data.get('source_type')
    source_url = data.get('source_url')
    
    if not dependencies.source_service:
        await message.answer("Сервис недоступен")
        await safe_clear_state(state)
        return
    
    success = dependencies.source_service.add_source(source_type, source_url, name)
    
    if success:
        name_text = f" ({name})" if name else ""
        await message.answer(
            f"✅ Источник успешно добавлен!\n\n"
            f"Тип: <b>{source_type.upper()}</b>{name_text}\n"
            f"URL: {source_url}",
            reply_markup=get_sources_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Ошибка при добавлении источника.\n"
            "Возможно, источник с таким URL уже существует.\n\n"
            "Попробуйте снова или отправьте 'отмена':",
            reply_markup=get_sources_menu_keyboard()
        )
    
    await safe_clear_state(state)


@router.callback_query(F.data == "source_remove")
async def source_remove_start(callback: CallbackQuery):
    """Начинает процесс удаления источника"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.source_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    sources = dependencies.source_service.get_all_sources()
    
    if not sources:
        await safe_answer_callback(callback, "Нет источников для удаления", show_alert=True)
        return
    
    keyboard_buttons = []
    for source in sources:
        name_part = f" ({source.name})" if source.name else ""
        button_text = f"{source.type.upper()}{name_part}"
        if len(button_text) > 30:
            button_text = button_text[:27] + "..."
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"source_delete_{source.url}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_sources")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await safe_edit_message(
        callback,
        "🗑️ <b>Удаление источника</b>\n\n"
        "Выберите источник для удаления:",
        reply_markup=keyboard
    )
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("source_delete_"))
async def source_remove_confirm(callback: CallbackQuery):
    """Удаляет источник"""
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "У вас нет доступа.", show_alert=True)
        return
    
    if not dependencies.source_service:
        await safe_answer_callback(callback, "Сервис недоступен", show_alert=True)
        return
    
    # Извлекаем URL из callback_data (source_delete_https://t.me/...)
    url = callback.data.replace("source_delete_", "", 1)
    
    success = dependencies.source_service.remove_source(url)
    
    if success:
        await safe_edit_message(
            callback,
            f"✅ Источник успешно удален!\n\n"
            f"URL: {url}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_sources")]
            ])
        )
    else:
        await safe_answer_callback(callback, "Ошибка при удалении источника", show_alert=True)
    
    await safe_answer_callback(callback)


def get_sources_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру меню источников"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="menu_back")]
    ])

