"""Сервис для публикации постов в VK"""
import logging
import os
import requests
from pathlib import Path
from typing import Optional, List

import vk_api
from vk_api.upload import VkUpload

from config.settings import settings
from services.google_drive_service import GoogleDriveService

logger = logging.getLogger(__name__)


class VKService:
    """Сервис для публикации постов в VK"""
    
    def __init__(self, google_drive_service: Optional[GoogleDriveService] = None):
        self.group_id = settings.VK_GROUP_ID
        self.google_drive = google_drive_service
        
        # Инициализация VK API с токеном группы
        vk_session = vk_api.VkApi(token=settings.VK_ACCESS_TOKEN)
        self.vk = vk_session.get_api()
        self.upload = VkUpload(vk_session)
        
        # Инициализация пользовательского токена если доступен
        self.user_vk = None
        self.user_upload = None
        if settings.VK_USER_TOKEN:
            try:
                user_session = vk_api.VkApi(token=settings.VK_USER_TOKEN)
                self.user_vk = user_session.get_api()
                self.user_upload = VkUpload(user_session)
                logger.info("Пользовательский токен VK инициализирован для загрузки файлов")
            except Exception as e:
                logger.warning(f"Не удалось инициализировать пользовательский токен VK: {e}")
        
        logger.info("VK API инициализирован успешно (токен группы)")
    
    def _prepare_photo_path(self, photo_path: str) -> Optional[str]:
        """
        Подготавливает путь к фотографии для загрузки в VK
        
        Если это file_id из Google Drive, скачивает файл локально.
        Если это локальный путь, проверяет существование.
        
        Args:
            photo_path: Путь к файлу или file_id из Google Drive
            
        Returns:
            Локальный путь к файлу или None если не удалось подготовить
        """
        # Проверяем, является ли это file_id из Google Drive
        # file_id обычно длинная строка без расширения и без путей
        is_likely_file_id = (
            len(photo_path) > 20 and 
            '/' not in photo_path and 
            '\\' not in photo_path and
            '.' not in photo_path[-5:]  # Нет расширения в конце
        )
        
        # Если это похоже на file_id и включен Google Drive, пытаемся скачать
        if is_likely_file_id and self.google_drive and self.google_drive.enabled:
            try:
                temp_folder = Path("storage/temp")
                temp_folder.mkdir(parents=True, exist_ok=True)
                temp_path = temp_folder / f"{photo_path}.jpg"
                
                if self.google_drive.download_file(photo_path, str(temp_path)):
                    logger.info(f"Фото скачано из Google Drive: {temp_path}")
                    return str(temp_path)
                else:
                    logger.warning(f"Не удалось скачать фото из Google Drive: {photo_path}")
            except Exception as e:
                logger.error(f"Ошибка при скачивании фото из Google Drive: {e}")
        else:
            # Проверяем локальный путь
            photo_path_obj = Path(photo_path)
            if photo_path_obj.exists():
                return str(photo_path_obj.absolute())
            
            # Если файл не найден локально и включен Google Drive, 
            # все равно попробуем скачать из Google Drive (на случай если это file_id)
            if self.google_drive and self.google_drive.enabled:
                try:
                    temp_folder = Path("storage/temp")
                    temp_folder.mkdir(parents=True, exist_ok=True)
                    # Заменяем слэши на подчеркивания для имени файла
                    safe_filename = photo_path.replace('/', '_').replace('\\', '_')
                    temp_path = temp_folder / f"{safe_filename}.jpg"
                    
                    if self.google_drive.download_file(photo_path, str(temp_path)):
                        logger.info(f"Фото скачано из Google Drive (fallback): {temp_path}")
                        return str(temp_path)
                except Exception as e:
                    logger.debug(f"Не удалось скачать из Google Drive (fallback): {e}")
        
        logger.warning(f"Файл не найден и не удалось скачать из Google Drive: {photo_path}")
        return None
    
    def publish_post(
        self,
        post_text: str,
        photos: Optional[List[str]] = None
    ) -> Optional[int]:
        """
        Публикует пост на стене группы VK
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям или file_id из Google Drive (опционально)
            
        Returns:
            ID опубликованного поста или None при ошибке
        """
        try:
            attachments = []
            temp_files = []  # Для удаления временных файлов после публикации
            
            # Загружаем фотографии если есть
            if photos:
                logger.info(f"Начинаем загрузку {len(photos)} фотографий в VK")
                for photo_path in photos:
                    try:
                        logger.info(f"Обработка фотографии: {photo_path}")
                        # Подготавливаем путь к фото (скачиваем из Google Drive если нужно)
                        local_path = self._prepare_photo_path(photo_path)
                        
                        if not local_path:
                            logger.warning(f"Пропущена фотография: {photo_path} (не удалось подготовить путь)")
                            continue
                        
                        logger.info(f"Локальный путь к фото: {local_path}")
                        
                        # Проверяем существование файла перед загрузкой
                        if not os.path.exists(local_path):
                            logger.error(f"Файл не существует: {local_path}")
                            continue
                        
                        logger.info(f"Загрузка фото в VK: {local_path}")
                        
                        photo_uploaded = False
                        
                        # Пробуем сначала пользовательский токен если доступен
                        if self.user_vk:
                            logger.info("Используем пользовательский токен для загрузки фото")
                            try:
                                photo_info = self.user_upload.photo_wall(
                                    photos=[local_path],
                                    group_id=abs(self.group_id)
                                )
                                
                                if photo_info:
                                    photo = photo_info[0]
                                    attachment_str = f"photo{photo['owner_id']}_{photo['id']}"
                                    attachments.append(attachment_str)
                                    logger.info(f"Фото успешно загружено через пользовательский токен: {attachment_str}")
                                    photo_uploaded = True
                                else:
                                    logger.warning("VK API не вернул информацию о загруженном фото")
                            except vk_api.exceptions.ApiError as ip_error:
                                error_str = str(ip_error).lower()
                                if 'ip address' in error_str or 'another ip' in error_str:
                                    logger.warning(f"⚠️ Пользовательский токен привязан к другому IP адресу.")
                                    logger.warning(f"⚠️ Пробуем использовать метод messages как fallback...")
                                else:
                                    logger.warning(f"Ошибка пользовательского токена: {ip_error}")
                        
                        # Если пользовательский токен не сработал, пробуем метод messages
                        if not photo_uploaded:
                            logger.info("Используем токен группы, пробуем загрузить через messages")
                            try:
                                # Метод getMessagesUploadServer работает с токеном группы
                                upload_url = self.vk.photos.getMessagesUploadServer(peer_id=self.group_id)
                                
                                # Загружаем фото
                                with open(local_path, 'rb') as photo_file:
                                    files = {'photo': photo_file}
                                    upload_response = requests.post(upload_url['upload_url'], files=files).json()
                                
                                # Сохраняем фото через saveMessagesPhoto
                                save_result = self.vk.photos.saveMessagesPhoto(
                                    photo=upload_response['photo'],
                                    server=upload_response['server'],
                                    hash=upload_response['hash']
                                )
                                
                                if save_result:
                                    photo = save_result[0] if isinstance(save_result, list) else save_result
                                    attachment_str = f"photo{photo['owner_id']}_{photo['id']}"
                                    attachments.append(attachment_str)
                                    logger.info(f"Фото успешно загружено через messages: {attachment_str}")
                                    photo_uploaded = True
                                else:
                                    raise Exception("Не удалось сохранить фото")
                            
                            except Exception as messages_error:
                                logger.warning(f"Метод messages не сработал: {messages_error}")
                                # Пробуем через альбом
                                try:
                                    logger.info("Пробуем загрузить через альбом группы")
                                    # Получаем альбом группы
                                    albums = self.vk.photos.getAlbums(owner_id=self.group_id)
                                    
                                    if albums and albums.get('items'):
                                        album_id = albums['items'][0]['id']
                                        logger.info(f"Найден альбом группы: {album_id}")
                                        
                                        # Получаем URL для загрузки (без group_id в getUploadServer)
                                        upload_url = self.vk.photos.getUploadServer(album_id=album_id)
                                        
                                        # Загружаем фото
                                        with open(local_path, 'rb') as photo_file:
                                            files = {'file1': photo_file}
                                            upload_response = requests.post(upload_url['upload_url'], files=files).json()
                                        
                                        # Сохраняем фото в альбом группы
                                        save_result = self.vk.photos.save(
                                            album_id=album_id,
                                            group_id=abs(self.group_id),
                                            server=upload_response['server'],
                                            photos_list=upload_response['photos_list'],
                                            hash=upload_response['hash']
                                        )
                                        
                                        if save_result and len(save_result) > 0:
                                            photo = save_result[0]
                                            attachment_str = f"photo{photo['owner_id']}_{photo['id']}"
                                            attachments.append(attachment_str)
                                            logger.info(f"Фото успешно загружено в альбом: {attachment_str}")
                                            photo_uploaded = True
                                        else:
                                            raise Exception("Не удалось сохранить фото в альбом")
                                    else:
                                        raise Exception("Альбомы группы не найдены")
                                except Exception as album_error:
                                    logger.warning(f"Метод альбома не сработал: {album_error}")
                                    # Пробуем через документы как последний вариант
                                    try:
                                        logger.info("Пробуем загрузить через документы")
                                        upload_url = self.vk.docs.getUploadServer(group_id=abs(self.group_id))
                                        
                                        with open(local_path, 'rb') as doc_file:
                                            files = {'file': doc_file}
                                            upload_response = requests.post(upload_url['upload_url'], files=files).json()
                                        
                                        save_result = self.vk.docs.save(
                                            file=upload_response['file'],
                                            title=f"photo_{Path(local_path).stem}.jpg"
                                        )
                                        
                                        if save_result:
                                            doc = save_result if isinstance(save_result, dict) else save_result[0]
                                            attachment_str = f"doc{doc['owner_id']}_{doc['id']}"
                                            attachments.append(attachment_str)
                                            logger.info(f"Фото успешно загружено как документ: {attachment_str}")
                                            photo_uploaded = True
                                        else:
                                            raise Exception("Не удалось сохранить документ")
                                    except Exception as doc_error:
                                        logger.error(f"Все методы загрузки не сработали. Messages: {messages_error}, Album: {album_error}, Docs: {doc_error}")
                                        logger.warning(f"Пропускаем фото {photo_path} из-за ошибок загрузки")
                        
                        if not photo_uploaded:
                            logger.warning(f"⚠️ Не удалось загрузить фото {photo_path} ни одним из методов")
                        
                        # Если это временный файл из Google Drive, помечаем для удаления
                        if local_path.startswith("storage/temp") or "temp" in local_path:
                            temp_files.append(local_path)
                    
                    except Exception as e:
                        logger.error(f"Ошибка при загрузке фото {photo_path} в VK: {e}", exc_info=True)
                        continue
                
                logger.info(f"Всего подготовлено {len(attachments)} фотографий для публикации")
            else:
                logger.info("Фотографии не предоставлены для публикации в VK")
            
            # Публикуем пост
            post_params = {
                'owner_id': self.group_id,
                'message': post_text,
                'from_group': 1  # От имени группы
            }
            
            if attachments:
                post_params['attachments'] = ",".join(attachments)
                logger.info(f"Публикуем пост с {len(attachments)} вложениями: {post_params['attachments']}")
            else:
                logger.warning("⚠️ Пост публикуется БЕЗ фотографий! Проверьте логи выше для диагностики.")
            
            post_id = self.vk.wall.post(**post_params)
            
            # Удаляем временные файлы
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.debug(f"Временный файл удален: {temp_file}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить временный файл {temp_file}: {e}")
            
            logger.info(f"Пост опубликован в VK. Post ID: {post_id.get('post_id') if isinstance(post_id, dict) else post_id}")
            
            # VK API возвращает словарь с post_id или просто число
            if isinstance(post_id, dict):
                return post_id.get('post_id')
            return post_id
        
        except vk_api.exceptions.ApiError as e:
            logger.error(f"Ошибка VK API при публикации поста: {e}")
            raise
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
    
    def get_group_posts(self, group_screen_name: str, count: int = 10) -> List[dict]:
        """
        Получает посты из VK группы
        
        Args:
            group_screen_name: Короткое имя группы (например, "club123456" или "group_name")
            count: Количество постов для получения
            
        Returns:
            Список словарей с информацией о постах: [{'id': post_id, 'text': post_text}, ...]
        """
        try:
            # Получаем посты из группы
            posts = self.vk.wall.get(
                domain=group_screen_name.replace('https://vk.com/', '').replace('vk.com/', ''),
                count=count,
                filter='owner'
            )
            
            result = []
            for post in posts.get('items', []):
                if 'text' in post and post['text']:
                    result.append({
                        'id': post['id'],
                        'text': post['text']
                    })
            
            logger.info(f"Получено {len(result)} постов из группы {group_screen_name}")
            return result
        
        except Exception as e:
            logger.error(f"Ошибка при получении постов из группы {group_screen_name}: {e}")
            return []
