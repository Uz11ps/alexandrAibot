"""Сервис для работы с Google Drive API"""
import logging
import os
import json
from pathlib import Path
from typing import List, Optional, Dict
import io

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

from config.settings import settings

logger = logging.getLogger(__name__)

# Права доступа для Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive']

# Файл для хранения ID папок
FOLDERS_CONFIG_FILE = Path("config/drive_folders.json")


class GoogleDriveService:
    """Сервис для работы с Google Drive"""
    
    def __init__(self):
        self.credentials_file = Path(settings.GOOGLE_DRIVE_CREDENTIALS_FILE or "credentials/google-credentials.json")
        self.token_file = Path(settings.GOOGLE_DRIVE_TOKEN_FILE or "credentials/google-token.json")
        self.service = None
        self.enabled = settings.GOOGLE_DRIVE_ENABLED
        self.folders_config = self._load_folders_config()
        
        if self.enabled:
            self._authenticate()
            if self.service:
                self._ensure_folders_exist()
    
    def _authenticate(self):
        """Аутентификация в Google Drive API"""
        try:
            creds = None
            
            # Загружаем сохраненные токены если есть
            if self.token_file.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            
            # Если нет валидных токенов, запрашиваем авторизацию
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not self.credentials_file.exists():
                        logger.error(f"Файл credentials не найден: {self.credentials_file}")
                        logger.error("Скачайте credentials.json из Google Cloud Console")
                        return
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_file), SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Сохраняем токены для следующего использования
                self.token_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
            
            self.service = build('drive', 'v3', credentials=creds)
            logger.info("Успешная аутентификация в Google Drive")
        
        except Exception as e:
            logger.error(f"Ошибка при аутентификации Google Drive: {e}")
            self.enabled = False
    
    def _load_folders_config(self) -> Dict[str, Optional[str]]:
        """Загружает конфигурацию папок из файла"""
        try:
            if FOLDERS_CONFIG_FILE.exists():
                with open(FOLDERS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Добавляем root_folder_id если его нет
                    if 'root_folder_id' not in config:
                        config['root_folder_id'] = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
                    return config
        except Exception as e:
            logger.warning(f"Ошибка при загрузке конфигурации папок: {e}")
        
        # Возвращаем значения из .env если файл не существует
        config = {
            'root_folder_id': settings.GOOGLE_DRIVE_ROOT_FOLDER_ID,
            'photos': settings.GOOGLE_DRIVE_PHOTOS_FOLDER_ID,
            'drafts': settings.GOOGLE_DRIVE_DRAFTS_FOLDER_ID,
            'laws': settings.GOOGLE_DRIVE_LAWS_FOLDER_ID,
            'memes': settings.GOOGLE_DRIVE_MEMES_FOLDER_ID,
            'services': settings.GOOGLE_DRIVE_SERVICES_FOLDER_ID,
            'archive': settings.GOOGLE_DRIVE_ARCHIVE_FOLDER_ID
        }
        return config
    
    def _save_folders_config(self):
        """Сохраняет конфигурацию папок в файл"""
        try:
            FOLDERS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(FOLDERS_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.folders_config, f, indent=2, ensure_ascii=False)
            logger.info("Конфигурация папок сохранена")
        except Exception as e:
            logger.error(f"Ошибка при сохранении конфигурации папок: {e}")
    
    def _ensure_folders_exist(self):
        """Создает необходимые папки в Google Drive если их нет"""
        if not self.service:
            return
        
        # Получаем ID родительской папки
        root_folder_id = self.folders_config.get('root_folder_id') or settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
        
        # Если указана родительская папка в .env, обновляем конфигурацию
        if settings.GOOGLE_DRIVE_ROOT_FOLDER_ID and not self.folders_config.get('root_folder_id'):
            self.folders_config['root_folder_id'] = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
            root_folder_id = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
        
        folder_names = {
            'photos': '📸 Фотографии объектов',
            'drafts': '📝 Черновики',
            'laws': '📚 Документы с законами',
            'memes': '😄 Мемы и визуальный контент',
            'services': '💼 Материалы об услугах',
            'archive': '📦 Архив публикаций'
        }
        
        created_any = False
        
        for folder_key, folder_name in folder_names.items():
            # Проверяем, есть ли уже ID папки
            if self.folders_config.get(folder_key):
                # Проверяем, существует ли папка
                try:
                    folder_info = self.service.files().get(
                        fileId=self.folders_config[folder_key],
                        fields='id,name,parents'
                    ).execute()
                    
                    # Проверяем, находится ли папка в правильной родительской папке
                    parents = folder_info.get('parents', [])
                    if root_folder_id and root_folder_id not in parents:
                        logger.warning(f"Папка '{folder_name}' находится не в нужной родительской папке, создаем новую")
                        self.folders_config[folder_key] = None
                    else:
                        logger.info(f"Папка '{folder_name}' уже существует (ID: {self.folders_config[folder_key]})")
                        continue
                except HttpError:
                    # Папка не найдена, создадим новую
                    logger.warning(f"Папка '{folder_name}' не найдена, создаем новую")
                    self.folders_config[folder_key] = None
            
            # Создаем папку если её нет
            if not self.folders_config.get(folder_key):
                folder_id = self.create_folder(folder_name, parent_folder_id=root_folder_id)
                if folder_id:
                    self.folders_config[folder_key] = folder_id
                    created_any = True
                    location = f"в папке (ID: {root_folder_id})" if root_folder_id else "в корне Drive"
                    logger.info(f"✅ Создана папка '{folder_name}' {location} (ID: {folder_id})")
        
        # Сохраняем конфигурацию если были созданы новые папки или обновлен root_folder_id
        if created_any or (root_folder_id and not self.folders_config.get('root_folder_id')):
            if root_folder_id:
                self.folders_config['root_folder_id'] = root_folder_id
            self._save_folders_config()
            logger.info("Все папки в Google Drive готовы к работе")
    
    def get_folder_id(self, folder_type: str) -> Optional[str]:
        """
        Возвращает ID папки по типу
        
        Args:
            folder_type: Тип папки (photos, drafts, laws, memes, services, archive)
            
        Returns:
            ID папки или None
        """
        return self.folders_config.get(folder_type)
    
    def create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> Optional[str]:
        """
        Создает папку в Google Drive
        
        Args:
            folder_name: Имя папки
            parent_folder_id: ID родительской папки (опционально)
            
        Returns:
            ID созданной папки или None при ошибке
        """
        if not self.enabled or not self.service:
            return None
        
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            logger.info(f"Папка создана: {folder_name} (ID: {folder.get('id')})")
            return folder.get('id')
        
        except HttpError as e:
            logger.error(f"Ошибка при создании папки: {e}")
            return None
    
    def upload_file(
        self,
        file_path: str,
        folder_id: Optional[str] = None,
        file_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Загружает файл в Google Drive
        
        Args:
            file_path: Путь к файлу на локальном диске
            folder_id: ID папки в Google Drive (опционально)
            file_name: Имя файла в Drive (если отличается от локального)
            
        Returns:
            ID загруженного файла или None при ошибке
        """
        if not self.enabled or not self.service:
            return None
        
        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"Файл не найден: {file_path}")
                return None
            
            file_name = file_name or path.name
            
            file_metadata = {'name': file_name}
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            media = MediaFileUpload(
                str(file_path),
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logger.info(f"Файл загружен: {file_name} (ID: {file.get('id')})")
            return file.get('id')
        
        except HttpError as e:
            logger.error(f"Ошибка при загрузке файла: {e}")
            return None
    
    def download_file(self, file_id: str, destination_path: str) -> bool:
        """
        Скачивает файл из Google Drive
        
        Args:
            file_id: ID файла в Google Drive
            destination_path: Путь для сохранения файла
            
        Returns:
            True если успешно, False при ошибке
        """
        if not self.enabled or not self.service:
            return False
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_data = io.BytesIO()
            downloader = MediaIoBaseDownload(file_data, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            # Сохраняем файл
            Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
            with open(destination_path, 'wb') as f:
                f.write(file_data.getvalue())
            
            logger.info(f"Файл скачан: {destination_path}")
            return True
        
        except HttpError as e:
            logger.error(f"Ошибка при скачивании файла: {e}")
            return False
    
    def list_files(
        self,
        folder_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Получает список файлов из Google Drive
        
        Args:
            folder_id: ID папки для поиска (опционально)
            mime_type: Фильтр по типу файла (например, 'image/jpeg'). Если None, возвращает все файлы
            limit: Максимальное количество файлов
            
        Returns:
            Список словарей с информацией о файлах
        """
        if not self.enabled or not self.service:
            logger.warning("Google Drive не включен или сервис не инициализирован")
            return []
        
        try:
            query = "trashed=false"
            
            if folder_id:
                query += f" and '{folder_id}' in parents"
                logger.debug(f"Поиск файлов в папке: {folder_id}")
            else:
                logger.debug("Поиск файлов без указания папки")
            
            if mime_type:
                query += f" and mimeType='{mime_type}'"
                logger.debug(f"Фильтр по MIME типу: {mime_type}")
            
            # Исключаем папки из результатов
            query += " and mimeType!='application/vnd.google-apps.folder'"
            
            results = self.service.files().list(
                q=query,
                pageSize=limit,
                fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, parents)"
            ).execute()
            
            files = results.get('files', [])
            logger.info(f"Найдено файлов в Google Drive: {len(files)} (запрос: {query})")
            
            # Логируем информацию о найденных файлах для отладки
            if files:
                for file_info in files[:5]:  # Показываем первые 5 файлов
                    logger.debug(f"  - {file_info.get('name')} (ID: {file_info.get('id')}, MIME: {file_info.get('mimeType')})")
            elif folder_id:
                # Если файлов не найдено, проверяем существование папки
                try:
                    folder_info = self.service.files().get(
                        fileId=folder_id,
                        fields='id,name,parents'
                    ).execute()
                    logger.info(f"Папка существует: {folder_info.get('name')} (ID: {folder_id})")
                except HttpError as e:
                    logger.error(f"Папка не найдена или нет доступа: {e}")
            
            return files
        
        except HttpError as e:
            logger.error(f"Ошибка при получении списка файлов из Google Drive: {e}")
            return []
        except Exception as e:
            logger.error(f"Неожиданная ошибка при получении списка файлов: {e}")
            return []
    
    def get_file_by_name(
        self,
        file_name: str,
        folder_id: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Находит файл по имени
        
        Args:
            file_name: Имя файла
            folder_id: ID папки для поиска (опционально)
            
        Returns:
            Словарь с информацией о файле или None
        """
        files = self.list_files(folder_id=folder_id, limit=1000)
        for file in files:
            if file['name'] == file_name:
                return file
        return None
    
    def delete_file(self, file_id: str) -> bool:
        """
        Удаляет файл из Google Drive
        
        Args:
            file_id: ID файла
            
        Returns:
            True если успешно, False при ошибке
        """
        if not self.enabled or not self.service:
            return False
        
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"Файл удален: {file_id}")
            return True
        
        except HttpError as e:
            logger.error(f"Ошибка при удалении файла: {e}")
            return False

