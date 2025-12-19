"""Сервис для хранения истории запросов на генерацию и редактирование постов"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class PostRequest:
    """Запрос на генерацию или редактирование поста"""
    request_id: str
    admin_id: int
    request_type: str  # "generate", "edit", "publish_now"
    prompt: str
    original_post: Optional[str] = None  # Для редактирования
    generated_post: Optional[str] = None
    photos_count: int = 0
    created_at: str = ""
    status: str = "pending"  # "pending", "completed", "failed"
    error: Optional[str] = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class PostHistoryService:
    """Сервис для управления историей запросов постов"""
    
    def __init__(self):
        self.storage_path = Path("storage/post_history")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.history_file = self.storage_path / "history.json"
        self.history: List[PostRequest] = []
        self._load_history()
    
    def _load_history(self):
        """Загружает историю из файла"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.history = [PostRequest(**req) for req in data]
                logger.info(f"Загружено {len(self.history)} запросов в истории постов")
        except Exception as e:
            logger.error(f"Ошибка при загрузке истории постов: {e}")
            self.history = []
    
    def _save_history(self):
        """Сохраняет историю в файл"""
        try:
            # Сохраняем последние 1000 запросов
            data = [asdict(req) for req in self.history[-1000:]]
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении истории постов: {e}")
    
    def add_request(
        self,
        admin_id: int,
        request_type: str,
        prompt: str,
        original_post: Optional[str] = None,
        photos_count: int = 0
    ) -> str:
        """
        Добавляет новый запрос в историю
        
        Args:
            admin_id: ID администратора
            request_type: Тип запроса ("generate", "edit", "publish_now")
            prompt: Текст запроса/промпта
            original_post: Исходный текст поста (для редактирования)
            photos_count: Количество фотографий
            
        Returns:
            ID запроса
        """
        request_id = f"{request_type}_{datetime.now().timestamp()}"
        request = PostRequest(
            request_id=request_id,
            admin_id=admin_id,
            request_type=request_type,
            prompt=prompt,
            original_post=original_post,
            photos_count=photos_count
        )
        self.history.append(request)
        self._save_history()
        logger.info(f"Добавлен запрос в историю: {request_id}")
        return request_id
    
    def update_request(
        self,
        request_id: str,
        generated_post: Optional[str] = None,
        status: str = "completed",
        error: Optional[str] = None
    ):
        """
        Обновляет запрос в истории
        
        Args:
            request_id: ID запроса
            generated_post: Сгенерированный текст поста
            status: Статус запроса
            error: Текст ошибки (если есть)
        """
        for req in self.history:
            if req.request_id == request_id:
                if generated_post:
                    req.generated_post = generated_post
                req.status = status
                if error:
                    req.error = error
                self._save_history()
                logger.info(f"Обновлен запрос в истории: {request_id}, статус: {status}")
                return
        
        logger.warning(f"Запрос {request_id} не найден в истории")
    
    def get_history(self, limit: int = 50) -> List[PostRequest]:
        """
        Возвращает историю запросов
        
        Args:
            limit: Максимальное количество запросов
            
        Returns:
            Список запросов
        """
        return self.history[-limit:]
    
    def get_history_by_admin(self, admin_id: int, limit: int = 50) -> List[PostRequest]:
        """
        Возвращает историю запросов конкретного администратора
        
        Args:
            admin_id: ID администратора
            limit: Максимальное количество запросов
            
        Returns:
            Список запросов
        """
        admin_requests = [req for req in self.history if req.admin_id == admin_id]
        return admin_requests[-limit:]

