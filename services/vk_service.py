"""Сервис для работы с VK API"""
import logging
from typing import Optional, List
import vk_api
from vk_api.upload import VkUpload
from config.settings import settings

logger = logging.getLogger(__name__)


class VKService:
    """Сервис для публикации постов в VK"""
    
    def __init__(self):
        self.group_id = settings.VK_GROUP_ID
        self.access_token = settings.VK_ACCESS_TOKEN
        
        # Инициализация VK API
        self.session = vk_api.VkApi(token=self.access_token)
        self.vk = self.session.get_api()
        self.upload = VkUpload(self.session)
    
    def publish_post(
        self,
        post_text: str,
        photos: Optional[List[str]] = None
    ) -> int:
        """
        Публикует пост на стене группы VK
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям (опционально)
            
        Returns:
            ID опубликованного поста
        """
        try:
            attachments = []
            
            # Загружаем фотографии если есть
            if photos:
                uploaded_photos = []
                for photo_path in photos:
                    try:
                        # Загружаем фото на сервер VK
                        photo_info = self.upload.photo_wall(
                            photos=[photo_path],
                            group_id=abs(self.group_id)
                        )
                        if photo_info:
                            photo = photo_info[0]
                            attachments.append(
                                f"photo{photo['owner_id']}_{photo['id']}"
                            )
                    except Exception as e:
                        logger.error(f"Ошибка при загрузке фото {photo_path}: {e}")
                        continue
            
            # Публикуем пост
            post_id = self.vk.wall.post(
                owner_id=self.group_id,
                message=post_text,
                attachments=",".join(attachments) if attachments else None,
                from_group=1  # От имени группы
            )
            
            logger.info(f"Пост опубликован в VK: {post_id}")
            return post_id
        
        except Exception as e:
            logger.error(f"Ошибка при публикации в VK: {e}")
            raise
    
    def get_group_info(self) -> dict:
        """
        Получает информацию о группе
        
        Returns:
            Словарь с информацией о группе
        """
        try:
            group_info = self.vk.groups.getById(group_id=abs(self.group_id))[0]
            return group_info
        except Exception as e:
            logger.error(f"Ошибка при получении информации о группе: {e}")
            raise

