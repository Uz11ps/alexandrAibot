"""Сервис для работы с файловой системой"""
import os
import logging
from pathlib import Path
from typing import List, Optional
import aiofiles
from config.settings import settings

logger = logging.getLogger(__name__)


class FileService:
    """Сервис для работы с файлами и папками"""
    
    def __init__(self, google_drive_service=None):
        self.photos_folder = Path(settings.PHOTOS_FOLDER)
        self.drafts_folder = Path(settings.DRAFTS_FOLDER)
        self.laws_folder = Path(settings.LAWS_FOLDER)
        self.memes_folder = Path(settings.MEMES_FOLDER)
        self.services_folder = Path(settings.SERVICES_FOLDER)
        self.archive_folder = Path(settings.ARCHIVE_FOLDER)
        
        # Google Drive сервис (опционально)
        self.google_drive = google_drive_service
        
        # Создаем папки если их нет
        self._ensure_folders_exist()
        
        # Хранилище использованных файлов
        self._used_files: set = set()
    
    def _ensure_folders_exist(self):
        """Создает необходимые папки если их нет"""
        folders = [
            self.photos_folder,
            self.drafts_folder,
            self.laws_folder,
            self.memes_folder,
            self.services_folder,
            self.archive_folder
        ]
        
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Папка {folder} готова")
    
    async def get_unused_photos(self, limit: int = 10) -> List[Path]:
        """
        Возвращает список неиспользованных фотографий
        
        Args:
            limit: Максимальное количество фотографий
            
        Returns:
            Список путей к фотографиям
        """
        photos = []
        logger.info(f"Поиск неиспользованных фотографий (лимит: {limit})")
        
        # Если используется Google Drive, получаем файлы оттуда
        if self.google_drive and self.google_drive.enabled:
            logger.info("Google Drive включен, получаем фотографии из Drive")
            folder_id = self.google_drive.get_folder_id('photos')
            if folder_id:
                logger.info(f"Получение фотографий из Google Drive, папка ID: {folder_id}")
                
                # Получаем все изображения из папки (без фильтра по MIME типу, чтобы получить все форматы)
                drive_files = self.google_drive.list_files(
                    folder_id=folder_id,
                    mime_type=None,  # Не фильтруем по типу, получим все файлы
                    limit=limit * 3  # Получаем больше для фильтрации
                )
                
                logger.info(f"Найдено файлов в Google Drive: {len(drive_files)}")
                
                # Фильтруем только изображения по расширению и MIME типу
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
                image_mime_types = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'}
                
                image_files = []
                for file_info in drive_files:
                    file_name = file_info.get('name', '')
                    mime_type = file_info.get('mimeType', '')
                    
                    # Проверяем по расширению или MIME типу
                    file_ext = Path(file_name).suffix.lower()
                    if file_ext in image_extensions or mime_type in image_mime_types:
                        image_files.append(file_info)
                
                logger.info(f"Отфильтровано изображений: {len(image_files)}")
                
                # Скачиваем неиспользованные файлы
                for file_info in image_files:
                    file_id = file_info['id']
                    file_name = file_info['name']
                    
                    # Используем file_id для отслеживания использованных файлов
                    if file_id not in self._used_files:
                        # Скачиваем во временную папку
                        temp_path = self.photos_folder / file_name
                        if self.google_drive.download_file(file_id, str(temp_path)):
                            photos.append(temp_path)
                            # Помечаем file_id как использованный
                            self._used_files.add(file_id)
                            logger.info(f"Скачана фотография: {file_name}")
                            if len(photos) >= limit:
                                break
                
                logger.info(f"Всего скачано фотографий: {len(photos)}")
            else:
                logger.warning("ID папки для фотографий не указан в Google Drive")
        
        # Также проверяем локальные файлы (если Google Drive не дал результатов)
        if not photos:
            logger.info("Проверка локальных файлов...")
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
            
            local_count = 0
            for file_path in self.photos_folder.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                    if str(file_path) not in self._used_files:
                        photos.append(file_path)
                        local_count += 1
                        if len(photos) >= limit:
                            break
            
            logger.info(f"Найдено локальных фотографий: {local_count}")
        
        logger.info(f"Итого доступно фотографий: {len(photos)}")
        return photos
    
    async def mark_file_as_used(self, file_path: Path, file_id: Optional[str] = None):
        """
        Помечает файл как использованный
        
        Args:
            file_path: Путь к файлу
            file_id: ID файла в Google Drive (если есть)
        """
        self._used_files.add(str(file_path))
        if file_id:
            self._used_files.add(file_id)
    
    async def upload_photo_to_drive(self, file_path: str, folder_type: str = 'photos') -> Optional[str]:
        """
        Загружает фотографию в Google Drive
        
        Args:
            file_path: Путь к файлу
            folder_type: Тип папки (photos, drafts, laws, memes, services, archive)
            
        Returns:
            ID файла в Google Drive или None
        """
        if not self.google_drive or not self.google_drive.enabled:
            return None
        
        folder_id = self.google_drive.get_folder_id(folder_type)
        if not folder_id:
            logger.warning(f"ID папки для {folder_type} не указан")
            return None
        
        # Используем синхронный метод в async функции (можно обернуть в executor если нужно)
        return self.google_drive.upload_file(file_path, folder_id=folder_id)
    
    async def get_draft_files(self) -> List[Path]:
        """
        Возвращает список файлов черновиков
        
        Returns:
            Список путей к файлам черновиков
        """
        drafts = []
        
        for file_path in self.drafts_folder.rglob('*'):
            if file_path.is_file():
                drafts.append(file_path)
        
        return drafts
    
    async def get_law_documents(self) -> List[Path]:
        """
        Возвращает список документов из папки "Законы"
        
        Returns:
            Список путей к документам
        """
        documents = []
        
        document_extensions = {'.pdf', '.doc', '.docx', '.txt'}
        
        for file_path in self.laws_folder.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in document_extensions:
                documents.append(file_path)
        
        return documents
    
    async def save_draft(self, content: str, filename: str) -> Path:
        """
        Сохраняет черновик поста
        
        Args:
            content: Содержимое черновика
            filename: Имя файла
            
        Returns:
            Путь к сохраненному файлу
        """
        file_path = self.drafts_folder / filename
        
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(content)
        
        logger.info(f"Черновик сохранен: {file_path}")
        return file_path
    
    async def archive_post(self, post_content: str, post_date: str) -> Path:
        """
        Архивирует опубликованный пост
        
        Args:
            post_content: Содержимое поста
            post_date: Дата публикации
            
        Returns:
            Путь к архивированному файлу
        """
        filename = f"post_{post_date.replace(':', '-')}.txt"
        file_path = self.archive_folder / filename
        
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(post_content)
        
        logger.info(f"Пост архивирован: {file_path}")
        return file_path
    
    async def read_file_content(self, file_path: Path) -> str:
        """
        Читает содержимое текстового файла
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Содержимое файла
        """
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            return await f.read()
    
    async def get_archived_posts(self, days: int = 7) -> List[dict]:
        """
        Получает список архивированных постов за указанный период
        
        Args:
            days: Количество дней для выборки
            
        Returns:
            Список словарей с информацией о постах: {'date': str, 'filename': str, 'path': Path}
        """
        from datetime import datetime, timedelta
        
        posts = []
        cutoff_date = datetime.now() - timedelta(days=days)
        
        try:
            if not self.archive_folder.exists():
                return posts
            
            for file_path in self.archive_folder.glob("post_*.txt"):
                try:
                    # Извлекаем дату из имени файла: post_2025-12-06_17-30-45.txt
                    filename = file_path.stem  # post_2025-12-06_17-30-45
                    date_str = filename.replace("post_", "").replace("-", ":", 2)  # 2025:12:06_17-30-45
                    date_str = date_str.replace("_", ":", 1).replace("-", ":")  # 2025:12:06:17:30:45
                    
                    # Парсим дату
                    post_date = datetime.strptime(date_str, "%Y:%m:%d:%H:%M:%S")
                    
                    if post_date >= cutoff_date:
                        posts.append({
                            'date': post_date,
                            'date_str': post_date.strftime("%d.%m.%Y %H:%M"),
                            'filename': file_path.name,
                            'path': file_path
                        })
                except Exception as e:
                    logger.warning(f"Не удалось обработать файл {file_path}: {e}")
                    continue
            
            # Сортируем по дате (новые первыми)
            posts.sort(key=lambda x: x['date'], reverse=True)
            return posts
        
        except Exception as e:
            logger.error(f"Ошибка при получении архивированных постов: {e}")
            return posts
    
    async def get_post_content(self, filename: str) -> Optional[str]:
        """
        Получает содержимое конкретного поста по имени файла
        
        Args:
            filename: Имя файла поста
            
        Returns:
            Содержимое поста или None
        """
        try:
            file_path = self.archive_folder / filename
            if file_path.exists():
                return await self.read_file_content(file_path)
            return None
        except Exception as e:
            logger.error(f"Ошибка при чтении поста {filename}: {e}")
            return None
    
    def get_folder_path(self, folder_type: str) -> Path:
        """
        Возвращает путь к папке по типу
        
        Args:
            folder_type: Тип папки (photos, drafts, laws, memes, services, archive)
            
        Returns:
            Путь к папке
        """
        folder_map = {
            'photos': self.photos_folder,
            'drafts': self.drafts_folder,
            'laws': self.laws_folder,
            'memes': self.memes_folder,
            'services': self.services_folder,
            'archive': self.archive_folder
        }
        
        return folder_map.get(folder_type, self.archive_folder)

