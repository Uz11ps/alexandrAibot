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
        self._draft_photos = {}  # Словарь для хранения путей к фотографиям черновиков
    
    async def send_draft_for_approval(
        self,
        draft_text: str,
        photos: Optional[List[str]] = None,
        day_of_week: Optional[str] = None
    ) -> int:
        """
        Отправляет черновик поста руководителю на согласование
        
        Args:
            draft_text: Текст черновика
            photos: Список путей к фотографиям (опционально)
            day_of_week: День недели для планирования ("monday", "tuesday", etc.) или None для немедленной публикации
            
        Returns:
            ID сообщения для отслеживания
        """
        try:
            # Формируем callback_data для кнопки "Принять" с указанием дня недели
            approve_callback = f"approve_post_{day_of_week}" if day_of_week else "approve_post"
            publish_now_callback = f"publish_now_{day_of_week}" if day_of_week else "publish_now"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять", callback_data=approve_callback),
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post")
                ],
                [
                    InlineKeyboardButton(text="🚀 Отправить сейчас", callback_data=publish_now_callback)
                ]
            ])
            
            # Telegram ограничивает caption до 1024 символов
            MAX_CAPTION_LENGTH = 1024
            header = "<b>Черновик поста для согласования:</b>\n\n"
            header_length = len(header.replace("<b>", "").replace("</b>", ""))  # Примерная длина без HTML
            
            if photos and len(photos) > 0:
                # Если текст с заголовком помещается в caption
                full_text = f"{header}{draft_text}"
                if len(full_text) <= MAX_CAPTION_LENGTH:
                    photo_file = FSInputFile(photos[0])
                    message = await self.bot.send_photo(
                        chat_id=self.admin_id,
                        photo=photo_file,
                        caption=full_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                else:
                    # Если текст слишком длинный, отправляем фото с коротким caption
                    # и полный текст отдельным сообщением
                    short_caption = f"{header}📝 Полный текст ниже ⬇️"
                    photo_file = FSInputFile(photos[0])
                    photo_message = await self.bot.send_photo(
                        chat_id=self.admin_id,
                        photo=photo_file,
                        caption=short_caption,
                        parse_mode="HTML"
                    )
                    
                    # Отправляем полный текст отдельным сообщением с кнопками
                    message = await self.bot.send_message(
                        chat_id=self.admin_id,
                        text=full_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    
                    # Сохраняем фотографии для текстового сообщения (оно содержит кнопки)
                    self._draft_photos[message.message_id] = photos.copy()
                    logger.info(f"Сохранены пути к фотографиям для текстового сообщения {message.message_id}: {photos}")
            else:
                message_text = f"{header}{draft_text}"
                message = await self.bot.send_message(
                    chat_id=self.admin_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            
            logger.info(f"Черновик отправлен руководителю: {message.message_id}, фото: {len(photos) if photos else 0}")
            
            # Сохраняем пути к фотографиям для последующей публикации
            # Используем message_id как ключ для хранения фотографий
            if photos and len(photos) > 0:
                # Сохраняем в атрибуте класса для доступа из обработчиков
                self._draft_photos[message.message_id] = photos.copy()
                logger.info(f"Сохранены пути к фотографиям для сообщения {message.message_id}: {photos}")
            
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
            
            # Telegram ограничивает caption до 1024 символов
            MAX_CAPTION_LENGTH = 1024
            
            if photos and len(photos) > 0:
                # Отправляем с фотографиями
                photo_files = [FSInputFile(photo) for photo in photos]
                
                if len(photo_files) == 1:
                    # Если текст помещается в caption
                    if len(post_text) <= MAX_CAPTION_LENGTH:
                        message = await self.bot.send_photo(
                            chat_id=self.channel_id,
                            photo=photo_files[0],
                            caption=post_text,
                            parse_mode="HTML"
                        )
                    else:
                        # Если текст слишком длинный, отправляем фото с коротким caption и текст отдельно
                        # Отправляем фото первым, потом текст
                        photo_message = await self.bot.send_photo(
                            chat_id=self.channel_id,
                            photo=photo_files[0],
                            caption="📝 Полный текст ниже ⬇️"
                        )
                        text_message = await self.bot.send_message(
                            chat_id=self.channel_id,
                            text=post_text,
                            parse_mode="HTML"
                        )
                        message = photo_message  # Возвращаем ID фото сообщения
                else:
                    # Для нескольких фото используем медиагруппу
                    media = []
                    for i, photo_file in enumerate(photo_files):
                        # Для первого фото добавляем caption, если текст короткий
                        caption = post_text if i == 0 and len(post_text) <= MAX_CAPTION_LENGTH else None
                        media.append({
                            "type": "photo",
                            "media": photo_file,
                            "caption": caption
                        })
                    
                    messages = await self.bot.send_media_group(
                        chat_id=self.channel_id,
                        media=media
                    )
                    message = messages[0]
                    
                    # Если текст не поместился в caption, отправляем отдельным сообщением
                    if len(post_text) > MAX_CAPTION_LENGTH:
                        await self.bot.send_message(
                            chat_id=self.channel_id,
                            text=post_text,
                            parse_mode="HTML"
                        )
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
    
    def get_draft_photos(self, message_id: int) -> List[str]:
        """
        Получает пути к фотографиям черновика по ID сообщения
        
        Args:
            message_id: ID сообщения с черновиком
            
        Returns:
            Список путей к фотографиям
        """
        if hasattr(self, '_draft_photos'):
            photos = self._draft_photos.get(message_id, [])
            logger.info(f"Получены фотографии для сообщения {message_id}: {len(photos)} файлов")
            return photos
        logger.warning(f"Словарь _draft_photos не найден для сообщения {message_id}")
        return []

