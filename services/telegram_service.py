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
                await self.send_long_message(
                    chat_id=admin_id,
                    text=text
                )
                logger.info(f"Уведомление отправлено администратору {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")
    
    async def send_long_message(self, chat_id: int, text: str, reply_markup=None, parse_mode="HTML", **kwargs):
        """
        Отправляет длинное сообщение, разбивая его на части если нужно
        """
        MAX_LENGTH = 4090 # Оставляем запас
        
        if len(text) <= MAX_LENGTH:
            return await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs
            )
        
        # Разбиваем текст на части
        parts = []
        for i in range(0, len(text), MAX_LENGTH):
            parts.append(text[i:i+MAX_LENGTH])
        
        sent_message = None
        for i, part in enumerate(parts):
            # Клавиатуру прикрепляем только к последней части
            current_markup = reply_markup if i == len(parts) - 1 else None
            sent_message = await self.bot.send_message(
                chat_id=chat_id,
                text=part,
                reply_markup=current_markup,
                parse_mode=parse_mode,
                **kwargs
            )
        return sent_message

    def _get_photo_input(self, photo_path: str):
        """Возвращает FSInputFile для локальных файлов или строку для URL"""
        if photo_path.startswith(('http://', 'https://')):
            return photo_path
        return FSInputFile(photo_path)

    async def send_for_approval(
        self,
        post_text: str,
        photos: List[str],
        day_of_week: Optional[str] = None,
        triggered_by: Optional[str] = None
    ):
        """
        Отправляет пост на согласование администраторам
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям или URL
            day_of_week: День недели для запланированного поста (опционально)
            triggered_by: Имя пользователя, инициировавшего генерацию (опционально)
        """
        # Формируем заголовок
        user_tag = f"👤 <b>Автор:</b> {triggered_by}\n" if triggered_by else ""
        header = f"{user_tag}📝 <b>Черновик поста для согласования:</b>\n\n"
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
                        photo_input = self._get_photo_input(photos[0])
                        
                        if len(full_text) <= MAX_CAPTION_LENGTH:
                            sent_message = await self.bot.send_photo(
                                chat_id=admin_id,
                                photo=photo_input,
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
                                photo=photo_input,
                                caption=f"{header}📝 Полный текст ниже ⬇️",
                                parse_mode="HTML"
                            )
                            text_message = await self.send_long_message(
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
                        for i, p in enumerate(photos):
                            photo_input = self._get_photo_input(p)
                            if i == 0:
                                # Первое фото с подписью
                                if len(full_text) <= MAX_CAPTION_LENGTH:
                                    media_group.append(
                                        InputMediaPhoto(
                                            media=photo_input,
                                            caption=full_text,
                                            parse_mode="HTML"
                                        )
                                    )
                                else:
                                    media_group.append(
                                        InputMediaPhoto(
                                            media=photo_input,
                                            caption=f"{header}📝 Полный текст ниже ⬇️",
                                            parse_mode="HTML"
                                        )
                                    )
                            else:
                                media_group.append(
                                    InputMediaPhoto(media=photo_input)
                                )
                        
                        if media_group:
                            sent_messages = await self.bot.send_media_group(
                                chat_id=admin_id,
                                media=media_group
                            )
                            # Отправляем текст отдельно если он длинный
                            if len(full_text) > MAX_CAPTION_LENGTH:
                                text_message = await self.send_long_message(
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
                    sent_message = await self.send_long_message(
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
            photos: Список путей к фотографиям или URL
            
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
                MAX_CAPTION_LENGTH = 1024
                
                if len(photos) == 1:
                    # Одно фото
                    photo_input = self._get_photo_input(photos[0])
                    
                    if len(post_text) <= MAX_CAPTION_LENGTH:
                        await self.bot.send_photo(
                            chat_id=channel_id,
                            photo=photo_input,
                            caption=post_text,
                            parse_mode="HTML"
                        )
                    else:
                        # Текст слишком длинный для подписи - отправляем фото и текст отдельно
                        await self.bot.send_photo(
                            chat_id=channel_id,
                            photo=photo_input,
                            parse_mode="HTML"
                        )
                        await self.send_long_message(
                            chat_id=channel_id,
                            text=post_text,
                            parse_mode="HTML"
                        )
                else:
                    # Несколько фото - отправляем медиагруппу
                    from aiogram.types import InputMediaPhoto
                    media_group = []
                    
                    # Если текст длинный, отправим его отдельным сообщением после группы
                    send_text_separately = len(post_text) > MAX_CAPTION_LENGTH
                    
                    for i, p in enumerate(photos):
                        photo_input = self._get_photo_input(p)
                        if i == 0 and not send_text_separately:
                            # Первое фото с подписью (только если текст не длинный)
                            media_group.append(
                                InputMediaPhoto(
                                    media=photo_input,
                                    caption=post_text,
                                    parse_mode="HTML"
                                )
                            )
                        else:
                            media_group.append(
                                InputMediaPhoto(media=photo_input)
                            )
                    
                    if media_group:
                        await self.bot.send_media_group(
                            chat_id=channel_id,
                            media=media_group
                        )
                        
                        if send_text_separately:
                            await self.send_long_message(
                                chat_id=channel_id,
                                text=post_text,
                                parse_mode="HTML"
                            )
            else:
                # Отправляем только текст
                await self.send_long_message(
                    chat_id=channel_id,
                    text=post_text,
                    parse_mode="HTML"
                )
            
            logger.info(f"Пост опубликован в канал {channel_id}")
            return "Опубликовано"
        except Exception as e:
            logger.error(f"Ошибка при публикации поста в канал: {e}")
            return None
