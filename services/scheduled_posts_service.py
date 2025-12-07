"""Сервис для управления запланированными постами"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

SCHEDULED_POSTS_FILE = Path("storage/scheduled_posts.json")


@dataclass
class ScheduledPost:
    """Запланированный пост"""
    day_of_week: str  # "monday", "tuesday", etc.
    post_text: str
    photos: List[str]
    created_at: Optional[str] = None
    created_by_admin_id: Optional[int] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class ScheduledPostsService:
    """Сервис для управления запланированными постами"""
    
    def __init__(self):
        self.scheduled_posts_file = SCHEDULED_POSTS_FILE
        self.scheduled_posts_file.parent.mkdir(parents=True, exist_ok=True)
        self.scheduled_posts: List[ScheduledPost] = []
        self._load_scheduled_posts()
    
    def _load_scheduled_posts(self):
        """Загружает список запланированных постов из файла"""
        try:
            if self.scheduled_posts_file.exists():
                with open(self.scheduled_posts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.scheduled_posts = [ScheduledPost(**post) for post in data]
                logger.info(f"Загружено {len(self.scheduled_posts)} запланированных постов")
            else:
                self.scheduled_posts = []
                logger.info("Файл запланированных постов не найден, создан пустой список")
        except Exception as e:
            logger.error(f"Ошибка при загрузке запланированных постов: {e}")
            self.scheduled_posts = []
    
    def _save_scheduled_posts(self):
        """Сохраняет список запланированных постов в файл"""
        try:
            data = [asdict(post) for post in self.scheduled_posts]
            with open(self.scheduled_posts_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Сохранено {len(self.scheduled_posts)} запланированных постов")
        except Exception as e:
            logger.error(f"Ошибка при сохранении запланированных постов: {e}")
    
    def add_scheduled_post(
        self,
        day_of_week: str,
        post_text: str,
        photos: List[str],
        admin_id: Optional[int] = None
    ) -> bool:
        """
        Добавляет запланированный пост
        
        Args:
            day_of_week: День недели ("monday", "tuesday", etc.)
            post_text: Текст поста
            photos: Список путей к фотографиям
            admin_id: ID администратора, создавшего пост
            
        Returns:
            True если успешно добавлен
        """
        # Удаляем старый пост для этого дня, если есть
        self.scheduled_posts = [p for p in self.scheduled_posts if p.day_of_week != day_of_week]
        
        scheduled_post = ScheduledPost(
            day_of_week=day_of_week,
            post_text=post_text,
            photos=photos,
            created_by_admin_id=admin_id
        )
        
        self.scheduled_posts.append(scheduled_post)
        self._save_scheduled_posts()
        logger.info(f"Добавлен запланированный пост для {day_of_week}")
        return True
    
    def get_scheduled_post(self, day_of_week: str) -> Optional[ScheduledPost]:
        """
        Получает запланированный пост для указанного дня
        
        Args:
            day_of_week: День недели ("monday", "tuesday", etc.)
            
        Returns:
            ScheduledPost или None если не найден
        """
        for post in self.scheduled_posts:
            if post.day_of_week == day_of_week:
                return post
        return None
    
    def remove_scheduled_post(self, day_of_week: str) -> bool:
        """
        Удаляет запланированный пост для указанного дня
        
        Args:
            day_of_week: День недели
            
        Returns:
            True если успешно удален
        """
        initial_count = len(self.scheduled_posts)
        self.scheduled_posts = [p for p in self.scheduled_posts if p.day_of_week != day_of_week]
        
        if len(self.scheduled_posts) < initial_count:
            self._save_scheduled_posts()
            logger.info(f"Удален запланированный пост для {day_of_week}")
            return True
        return False
    
    def get_all_scheduled_posts(self) -> List[ScheduledPost]:
        """Возвращает список всех запланированных постов"""
        return self.scheduled_posts.copy()

