"""Сервис для работы с Telegram API"""
import logging
from typing import Optional, List
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from config.settings import settings

logger = logging.getLogger(__name__)


class TelegramService:
    """Сервис для публикации и отправки сообщений в Telegram"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.admin_id = settings.TELEGRAM_ADMIN_ID
        self.channel_id = settings.TELEGRAM_CHANNEL_ID
    
    async def send_draft_for_approval(
        self,
        draft_text: str,
        photos: Optional[List[str]] = None
    ) -> int:
        """
        Отправляет черновик поста руководителю на согласование
        
        Args:
            draft_text: Текст черновика
            photos: Список путей к фотографиям (опционально)
            
        Returns:
            ID сообщения для отслеживания
        """
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять", callback_data="approve_post"),
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post")
                ]
            ])
            
            message_text = f"<b>Черновик поста для согласования:</b>\n\n{draft_text}"
            
            if photos and len(photos) > 0:
                # Отправляем с первой фотографией
                photo_file = FSInputFile(photos[0])
                message = await self.bot.send_photo(
                    chat_id=self.admin_id,
                    photo=photo_file,
                    caption=message_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                message = await self.bot.send_message(
                    chat_id=self.admin_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            
            logger.info(f"Черновик отправлен руководителю: {message.message_id}")
            return message.message_id
        
        except Exception as e:
            logger.error(f"Ошибка при отправке черновика: {e}")
            raise
    
    async def publish_to_channel(
        self,
        post_text: str,
        photos: Optional[List[str]] = None
    ) -> int:
        """
        Публикует пост в Telegram канал
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям (опционально)
            
        Returns:
            ID опубликованного сообщения
        """
        try:
            if not self.channel_id:
                logger.warning("ID канала не указан, публикация пропущена")
                return 0
            
            if photos and len(photos) > 0:
                # Отправляем с фотографиями
                photo_files = [FSInputFile(photo) for photo in photos]
                
                if len(photo_files) == 1:
                    message = await self.bot.send_photo(
                        chat_id=self.channel_id,
                        photo=photo_files[0],
                        caption=post_text,
                        parse_mode="HTML"
                    )
                else:
                    # Для нескольких фото используем медиагруппу
                    media = []
                    for i, photo_file in enumerate(photo_files):
                        media.append({
                            "type": "photo",
                            "media": photo_file,
                            "caption": post_text if i == 0 else None
                        })
                    
                    messages = await self.bot.send_media_group(
                        chat_id=self.channel_id,
                        media=media
                    )
                    message = messages[0]
            else:
                message = await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=post_text,
                    parse_mode="HTML"
                )
            
            logger.info(f"Пост опубликован в канал: {message.message_id}")
            return message.message_id
        
        except Exception as e:
            logger.error(f"Ошибка при публикации в канал: {e}")
            raise
    
    async def send_message_to_employee(
        self,
        employee_id: int,
        message_text: str
    ) -> int:
        """
        Отправляет сообщение сотруднику
        
        Args:
            employee_id: Telegram ID сотрудника
            message_text: Текст сообщения
            
        Returns:
            ID отправленного сообщения
        """
        try:
            message = await self.bot.send_message(
                chat_id=employee_id,
                text=message_text,
                parse_mode="HTML"
            )
            
            logger.info(f"Сообщение отправлено сотруднику {employee_id}: {message.message_id}")
            return message.message_id
        
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения сотруднику: {e}")
            raise
    
    async def send_notification_to_admin(
        self,
        notification_text: str
    ) -> int:
        """
        Отправляет уведомление администратору
        
        Args:
            notification_text: Текст уведомления
            
        Returns:
            ID отправленного сообщения
        """
        try:
            message = await self.bot.send_message(
                chat_id=self.admin_id,
                text=notification_text,
                parse_mode="HTML"
            )
            
            logger.info(f"Уведомление отправлено администратору: {message.message_id}")
            return message.message_id
        
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")
            raise
    
    async def request_edit_text(self, draft_message_id: int) -> None:
        """
        Запрашивает текст правок у руководителя
        
        Args:
            draft_message_id: ID сообщения с черновиком
        """
        try:
            await self.bot.send_message(
                chat_id=self.admin_id,
                text="Пожалуйста, отправьте текст правок для этого поста:",
                reply_to_message_id=draft_message_id,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при запросе правок: {e}")
            raise

