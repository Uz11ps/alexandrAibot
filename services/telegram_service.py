"""Сервис для работы с Telegram API"""
import logging
from typing import List, Optional, Dict
from pathlib import Path
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from config.settings import settings

logger = logging.getLogger(__name__)


class TelegramService:
    """Сервис для работы с Telegram API"""
    
    def __init__(self, bot: Bot):
        """
        Инициализация Telegram сервиса
        
        Args:
            bot: Экземпляр бота aiogram
        """
        self.bot = bot
        self._draft_photos: Dict[int, List[str]] = {}  # Хранение фото черновиков по message_id
        
        # Получаем список ID администраторов
        self.admin_ids = [settings.TELEGRAM_ADMIN_ID]
        if settings.TELEGRAM_ADMIN_IDS:
            admin_ids_list = [int(id.strip()) for id in settings.TELEGRAM_ADMIN_IDS.split(',') if id.strip()]
            self.admin_ids.extend(admin_ids_list)
        
        logger.info(f"TelegramService инициализирован. Администраторов: {len(self.admin_ids)}")
    
    def get_draft_photos(self, message_id: int) -> List[str]:
        """
        Получает список путей к фотографиям черновика по message_id
        
        Args:
            message_id: ID сообщения с черновиком
            
        Returns:
            Список путей к фотографиям или пустой список
        """
        return self._draft_photos.get(message_id, [])
    
    async def send_message_to_employee(self, employee_id: int, text: str) -> Optional[int]:
        """
        Отправляет сообщение сотруднику
        
        Args:
            employee_id: Telegram ID сотрудника
            text: Текст сообщения
            
        Returns:
            ID отправленного сообщения или None при ошибке
        """
        try:
            message = await self.bot.send_message(
                chat_id=employee_id,
                text=text,
                parse_mode="HTML"
            )
            logger.info(f"Сообщение отправлено сотруднику {employee_id}")
            return message.message_id
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения сотруднику {employee_id}: {e}")
            return None
    
    async def send_notification_to_admin(self, text: str):
        """
        Отправляет уведомление всем администраторам
        
        Args:
            text: Текст уведомления
        """
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="HTML"
                )
                logger.info(f"Уведомление отправлено администратору {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")
    
    async def send_for_approval(
        self,
        post_text: str,
        photos: List[str],
        day_of_week: Optional[str] = None
    ):
        """
        Отправляет пост на согласование администраторам
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям
            day_of_week: День недели для запланированного поста (опционально)
        """
        # Формируем заголовок
        header = "📝 <b>Черновик поста для согласования:</b>\n\n"
        full_text = f"{header}{post_text}"
        
        # Формируем callback_data для кнопок
        if day_of_week:
            approve_callback = f"approve_post_{day_of_week}"
        else:
            approve_callback = "approve_post"
        
        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=approve_callback),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post")
            ]
        ])
        
        MAX_CAPTION_LENGTH = 1024
        
        # Отправляем пост каждому администратору
        for admin_id in self.admin_ids:
            try:
                if photos:
                    # Отправляем с фото
                    if len(photos) == 1:
                        # Одно фото
                        photo_path = Path(photos[0])
                        if photo_path.exists():
                            if len(full_text) <= MAX_CAPTION_LENGTH:
                                sent_message = await self.bot.send_photo(
                                    chat_id=admin_id,
                                    photo=FSInputFile(photos[0]),
                                    caption=full_text,
                                    reply_markup=keyboard,
                                    parse_mode="HTML"
                                )
                                # Сохраняем фото для черновика
                                self._draft_photos[sent_message.message_id] = photos.copy()
                            else:
                                # Текст слишком длинный, отправляем отдельно
                                photo_message = await self.bot.send_photo(
                                    chat_id=admin_id,
                                    photo=FSInputFile(photos[0]),
                                    caption=f"{header}📝 Полный текст ниже ⬇️",
                                    parse_mode="HTML"
                                )
                                text_message = await self.bot.send_message(
                                    chat_id=admin_id,
                                    text=full_text,
                                    reply_markup=keyboard,
                                    parse_mode="HTML"
                                )
                                # Сохраняем фото для черновика
                                self._draft_photos[text_message.message_id] = photos.copy()
                    else:
                        # Несколько фото - отправляем медиагруппу
                        from aiogram.types import InputMediaPhoto
                        media_group = []
                        for i, photo_path in enumerate(photos):
                            path = Path(photo_path)
                            if path.exists():
                                if i == 0:
                                    # Первое фото с подписью
                                    if len(full_text) <= MAX_CAPTION_LENGTH:
                                        media_group.append(
                                            InputMediaPhoto(
                                                media=FSInputFile(photo_path),
                                                caption=full_text,
                                                parse_mode="HTML"
                                            )
                                        )
                                    else:
                                        media_group.append(
                                            InputMediaPhoto(
                                                media=FSInputFile(photo_path),
                                                caption=f"{header}📝 Полный текст ниже ⬇️",
                                                parse_mode="HTML"
                                            )
                                        )
                                else:
                                    media_group.append(
                                        InputMediaPhoto(media=FSInputFile(photo_path))
                                    )
                        
                        if media_group:
                            sent_messages = await self.bot.send_media_group(
                                chat_id=admin_id,
                                media=media_group
                            )
                            # Отправляем текст отдельно если он длинный
                            if len(full_text) > MAX_CAPTION_LENGTH:
                                text_message = await self.bot.send_message(
                                    chat_id=admin_id,
                                    text=full_text,
                                    reply_markup=keyboard,
                                    parse_mode="HTML"
                                )
                                # Сохраняем фото для черновика
                                self._draft_photos[text_message.message_id] = photos.copy()
                            else:
                                # Сохраняем фото для черновика
                                self._draft_photos[sent_messages[0].message_id] = photos.copy()
                    else:
                        # Отправляем только текст
                        sent_message = await self.bot.send_message(
                            chat_id=admin_id,
                            text=full_text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                
                logger.info(f"Пост отправлен на согласование администратору {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке поста на согласование администратору {admin_id}: {e}")
    
    async def publish_post(self, post_text: str, photos: List[str]) -> Optional[str]:
        """
        Публикует пост в Telegram канал
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям
            
        Returns:
            Результат публикации или None при ошибке
        """
        if not settings.TELEGRAM_CHANNEL_ID:
            logger.error("TELEGRAM_CHANNEL_ID не указан в настройках")
            return None
        
        try:
            channel_id = settings.TELEGRAM_CHANNEL_ID
            
            if photos:
                # Отправляем с фото
                if len(photos) == 1:
                    # Одно фото
                    photo_path = Path(photos[0])
                    if photo_path.exists():
                        await self.bot.send_photo(
                            chat_id=channel_id,
                            photo=FSInputFile(photos[0]),
                            caption=post_text,
                            parse_mode="HTML"
                        )
                else:
                    # Несколько фото - отправляем медиагруппу
                    from aiogram.types import InputMediaPhoto
                    media_group = []
                    for i, photo_path in enumerate(photos):
                        path = Path(photo_path)
                        if path.exists():
                            if i == 0:
                                # Первое фото с подписью
                                media_group.append(
                                    InputMediaPhoto(
                                        media=FSInputFile(photo_path),
                                        caption=post_text,
                                        parse_mode="HTML"
                                    )
                                )
                            else:
                                media_group.append(
                                    InputMediaPhoto(media=FSInputFile(photo_path))
                                )
                    
                    if media_group:
                        await self.bot.send_media_group(
                            chat_id=channel_id,
                            media=media_group
                        )
            else:
                # Отправляем только текст
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=post_text,
                    parse_mode="HTML"
                )
            
            logger.info(f"Пост опубликован в канал {channel_id}")
            return "Опубликовано"
        except Exception as e:
            logger.error(f"Ошибка при публикации поста в канал: {e}")
            return None
