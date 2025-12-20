"""Сервис для работы с Telegram API"""
import logging
from typing import Optional, List
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from config.settings import settings
from services.text_utils import truncate_text_by_sentences

logger = logging.getLogger(__name__)


class TelegramService:
    """Сервис для публикации и отправки сообщений в Telegram"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.admin_id = settings.TELEGRAM_ADMIN_ID
        self.channel_id = settings.TELEGRAM_CHANNEL_ID
        self._draft_photos = {}  # Словарь для хранения путей к фотографиям черновиков
        
        # Собираем список всех администраторов
        self.admin_ids = [settings.TELEGRAM_ADMIN_ID]
        if settings.TELEGRAM_ADMIN_IDS:
            admin_ids_list = [int(id.strip()) for id in settings.TELEGRAM_ADMIN_IDS.split(',') if id.strip()]
            self.admin_ids.extend(admin_ids_list)
        
        logger.info(f"Инициализирован TelegramService с {len(self.admin_ids)} администраторами: {self.admin_ids}")
    
    async def send_draft_for_approval(
        self,
        draft_text: str,
        photos: Optional[List[str]] = None,
        day_of_week: Optional[str] = None
    ) -> int:
        """
        Отправляет черновик поста всем администраторам на согласование
        
        Args:
            draft_text: Текст черновика
            photos: Список путей к фотографиям (опционально)
            day_of_week: День недели для планирования ("monday", "tuesday", etc.) или None для немедленной публикации
            
        Returns:
            ID первого отправленного сообщения для отслеживания
        """
        # Проверяем настройки уведомлений
        from services import dependencies
        if dependencies.notification_settings_service:
            if not dependencies.notification_settings_service.is_draft_notifications_enabled():
                logger.info("Уведомления о черновиках отключены в настройках")
                return 0
        
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
            
            first_message_id = None
            
            # Отправляем черновик всем администраторам
            for admin_id in self.admin_ids:
                try:
                    if photos and len(photos) > 0:
                        # Если текст с заголовком помещается в caption
                        full_text = f"{header}{draft_text}"
                        if len(full_text) <= MAX_CAPTION_LENGTH:
                            photo_file = FSInputFile(photos[0])
                            message = await self.bot.send_photo(
                                chat_id=admin_id,
                                photo=photo_file,
                                caption=full_text,
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                            # Сохраняем фотографии для этого сообщения
                            self._draft_photos[message.message_id] = photos.copy()
                            if first_message_id is None:
                                first_message_id = message.message_id
                            logger.info(f"Черновик отправлен администратору {admin_id}: {message.message_id}, фото: {len(photos)}")
                        else:
                            # Если текст слишком длинный, отправляем фото с коротким caption
                            # и полный текст отдельным сообщением
                            short_caption = f"{header}📝 Полный текст ниже ⬇️"
                            photo_file = FSInputFile(photos[0])
                            photo_message = await self.bot.send_photo(
                                chat_id=admin_id,
                                photo=photo_file,
                                caption=short_caption,
                                parse_mode="HTML"
                            )
                            
                            # Отправляем полный текст отдельным сообщением с кнопками
                            message = await self.bot.send_message(
                                chat_id=admin_id,
                                text=full_text,
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                            
                            # Сохраняем фотографии для текстового сообщения (оно содержит кнопки)
                            self._draft_photos[message.message_id] = photos.copy()
                            if first_message_id is None:
                                first_message_id = message.message_id
                            logger.info(f"Черновик отправлен администратору {admin_id}: {message.message_id}, фото: {len(photos)}")
                    else:
                        message_text = f"{header}{draft_text}"
                        message = await self.bot.send_message(
                            chat_id=admin_id,
                            text=message_text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                        if first_message_id is None:
                            first_message_id = message.message_id
                        logger.info(f"Черновик отправлен администратору {admin_id}: {message.message_id}, без фото")
                
                except Exception as e:
                    logger.error(f"Ошибка при отправке черновика администратору {admin_id}: {e}")
                    # Продолжаем отправку другим администраторам даже если один не получил
            
            if first_message_id is None:
                raise Exception("Не удалось отправить черновик ни одному администратору")
            
            logger.info(f"Черновик отправлен {len(self.admin_ids)} администраторам, первый message_id: {first_message_id}")
            return first_message_id
        
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
            
            # Очищаем текст от технических заголовков перед публикацией
            import re
            # Удаляем HTML-теги из заголовков
            post_text = re.sub(r'<b>📝\s*Черновик поста для согласования[^<]*</b>', '', post_text, flags=re.IGNORECASE)
            post_text = re.sub(r'<b>Черновик поста для согласования[^<]*</b>', '', post_text, flags=re.IGNORECASE)
            
            # Удаляем обычные заголовки (с эмодзи и без)
            header_patterns = [
                r'📝\s*Черновик поста для согласования[^:]*:?\s*\n*',
                r'📝\s*Полный текст ниже ⬇️\s*\n*',
                r'Черновик поста для согласования[^:]*:?\s*\n*',
                r'📝\s*Черновик поста для согласования \(после правок\):?\s*\n*',
                r'Черновик поста для согласования \(после правок\):?\s*\n*',
            ]
            for pattern in header_patterns:
                post_text = re.sub(pattern, '', post_text, flags=re.IGNORECASE | re.MULTILINE)
            
            # Удаляем множественные переносы строк после удаления заголовков
            post_text = re.sub(r'\n{3,}', '\n\n', post_text)
            post_text = post_text.strip()
            
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
                        # Обрезаем текст по предложениям, чтобы не обрывать мысль (лимит Telegram для сообщений - 4096)
                        truncated_text = truncate_text_by_sentences(post_text, 4096)
                        photo_message = await self.bot.send_photo(
                            chat_id=self.channel_id,
                            photo=photo_files[0],
                            caption="📝 Полный текст ниже ⬇️"
                        )
                        text_message = await self.bot.send_message(
                            chat_id=self.channel_id,
                            text=truncated_text,
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
                    # Обрезаем текст по предложениям, чтобы не обрывать мысль
                    if len(post_text) > MAX_CAPTION_LENGTH:
                        truncated_text = truncate_text_by_sentences(post_text, 4096)
                        await self.bot.send_message(
                            chat_id=self.channel_id,
                            text=truncated_text,
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

