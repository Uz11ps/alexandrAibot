"""Сервис для управления историей постов и самообучения"""
import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class PostHistoryEntry:
    """Запись в истории постов"""
    request_id: str
    admin_id: int
    request_type: str  # publish_now, scheduled, edit, etc.
    prompt: str
    original_post: Optional[str] = None
    generated_post: Optional[str] = None
    final_post: Optional[str] = None
    photos_count: int = 0
    status: str = "pending"  # pending, approved, rejected, edited, published
    edits: Optional[str] = None  # Правки администратора
    edit_count: int = 0  # Количество редактирований
    created_at: str = ""
    updated_at: str = ""
    published_at: Optional[str] = None
    day_of_week: Optional[str] = None  # Для запланированных постов
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()


class PostHistoryService:
    """Сервис для управления историей постов и самообучения"""
    
    def __init__(self):
        self.storage_path = Path("storage/post_history")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.history_file = self.storage_path / "history.json"
        self.stats_file = self.storage_path / "stats.json"
        
        self.history: List[PostHistoryEntry] = []
        self.stats: Dict = {
            "total_posts": 0,
            "approved_posts": 0,
            "rejected_posts": 0,
            "edited_posts": 0,
            "published_posts": 0,
            "avg_edit_count": 0.0,
            "successful_patterns": [],
            "common_edits": {}
        }
        
        self._load_history()
        self._load_stats()
    
    def _load_history(self):
        """Загружает историю постов из файла"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.history = [PostHistoryEntry(**entry) for entry in data]
                logger.info(f"Загружено {len(self.history)} запросов в истории постов")
            else:
                self.history = []
        except Exception as e:
            logger.error(f"Ошибка при загрузке истории постов: {e}")
            self.history = []
    
    def _save_history(self):
        """Сохраняет историю постов в файл"""
        try:
            # Сохраняем последние 10000 записей
            data = [asdict(entry) for entry in self.history[-10000:]]
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении истории постов: {e}")
    
    def _load_stats(self):
        """Загружает статистику"""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    self.stats = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка при загрузке статистики: {e}")
            self.stats = {
                "total_posts": 0,
                "approved_posts": 0,
                "rejected_posts": 0,
                "edited_posts": 0,
                "published_posts": 0,
                "avg_edit_count": 0.0,
                "successful_patterns": [],
                "common_edits": {}
            }
    
    def _save_stats(self):
        """Сохраняет статистику"""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении статистики: {e}")
    
    def _update_stats(self):
        """Обновляет статистику на основе истории"""
        if not self.history:
            return
        
        total = len(self.history)
        approved = sum(1 for entry in self.history if entry.status == "approved")
        rejected = sum(1 for entry in self.history if entry.status == "rejected")
        edited = sum(1 for entry in self.history if entry.edit_count > 0)
        published = sum(1 for entry in self.history if entry.status == "published")
        
        avg_edit_count = sum(entry.edit_count for entry in self.history) / total if total > 0 else 0.0
        
        # Анализируем успешные паттерны (посты, которые были одобрены без правок или с минимальными правками)
        successful_patterns = []
        for entry in self.history:
            if entry.status in ["approved", "published"] and entry.edit_count <= 1:
                successful_patterns.append({
                    "prompt": entry.prompt[:200],  # Первые 200 символов промпта
                    "post_length": len(entry.final_post or entry.generated_post or ""),
                    "photos_count": entry.photos_count,
                    "edit_count": entry.edit_count
                })
        
        # Анализируем частые правки
        common_edits = defaultdict(int)
        for entry in self.history:
            if entry.edits:
                # Простые ключевые слова из правок
                edits_lower = entry.edits.lower()
                if "сократи" in edits_lower or "короче" in edits_lower:
                    common_edits["shorten"] += 1
                if "добавь" in edits_lower and "эмодзи" in edits_lower:
                    common_edits["add_emoji"] += 1
                if "приветствие" in edits_lower or "привет" in edits_lower:
                    common_edits["add_greeting"] += 1
                if "прощание" in edits_lower or "прощай" in edits_lower:
                    common_edits["add_farewell"] += 1
                if "стиль" in edits_lower:
                    common_edits["change_style"] += 1
        
        self.stats = {
            "total_posts": total,
            "approved_posts": approved,
            "rejected_posts": rejected,
            "edited_posts": edited,
            "published_posts": published,
            "avg_edit_count": round(avg_edit_count, 2),
            "successful_patterns": successful_patterns[-50:],  # Последние 50 успешных паттернов
            "common_edits": dict(common_edits)
        }
        self._save_stats()
    
    def add_request(
        self,
        request_id: str,
        admin_id: int,
        request_type: str,
        prompt: str,
        original_post: Optional[str] = None,
        photos_count: int = 0,
        day_of_week: Optional[str] = None
    ) -> PostHistoryEntry:
        """
        Добавляет новый запрос в историю
        
        Args:
            request_id: Уникальный ID запроса
            admin_id: ID администратора
            request_type: Тип запроса (publish_now, scheduled, edit, etc.)
            prompt: Промпт пользователя
            original_post: Исходный текст поста (для редактирования)
            photos_count: Количество фотографий
            day_of_week: День недели (для запланированных постов)
            
        Returns:
            Созданная запись истории
        """
        entry = PostHistoryEntry(
            request_id=request_id,
            admin_id=admin_id,
            request_type=request_type,
            prompt=prompt,
            original_post=original_post,
            photos_count=photos_count,
            day_of_week=day_of_week
        )
        
        self.history.append(entry)
        self._save_history()
        self._update_stats()
        
        logger.info(f"Добавлен запрос в историю: {request_id}")
        return entry
    
    def update_request(
        self,
        request_id: str,
        generated_post: Optional[str] = None,
        final_post: Optional[str] = None,
        status: Optional[str] = None,
        edits: Optional[str] = None,
        published_at: Optional[str] = None
    ) -> bool:
        """
        Обновляет запрос в истории
        
        Args:
            request_id: ID запроса
            generated_post: Сгенерированный текст поста
            final_post: Финальный текст поста (после правок)
            status: Статус (pending, approved, rejected, edited, published)
            edits: Текст правок
            published_at: Время публикации
            
        Returns:
            True если запрос найден и обновлен
        """
        for entry in self.history:
            if entry.request_id == request_id:
                if generated_post is not None:
                    entry.generated_post = generated_post
                if final_post is not None:
                    entry.final_post = final_post
                if status is not None:
                    entry.status = status
                if edits is not None:
                    entry.edits = edits
                    entry.edit_count += 1
                if published_at is not None:
                    entry.published_at = published_at
                
                entry.updated_at = datetime.now().isoformat()
                
                self._save_history()
                self._update_stats()
                
                logger.info(f"Обновлен запрос в истории: {request_id}, статус: {status}")
                return True
        
        logger.warning(f"Запрос не найден в истории: {request_id}")
        return False
    
    def get_recent_successful_posts(self, limit: int = 10) -> List[PostHistoryEntry]:
        """
        Получает последние успешные посты (одобренные без правок или с минимальными правками)
        
        Args:
            limit: Количество постов
            
        Returns:
            Список успешных постов
        """
        successful = [
            entry for entry in self.history
            if entry.status in ["approved", "published"] and entry.edit_count <= 1
        ]
        return successful[-limit:]
    
    def get_similar_posts(self, prompt: str, limit: int = 5) -> List[PostHistoryEntry]:
        """
        Находит похожие посты по промпту
        
        Args:
            prompt: Промпт для поиска похожих
            limit: Количество результатов
            
        Returns:
            Список похожих постов
        """
        prompt_words = set(prompt.lower().split())
        
        scored_posts = []
        for entry in self.history:
            if not entry.prompt:
                continue
            
            entry_words = set(entry.prompt.lower().split())
            common_words = prompt_words & entry_words
            
            if common_words:
                # Простой подсчет схожести по количеству общих слов
                similarity = len(common_words) / max(len(prompt_words), len(entry_words))
                scored_posts.append((similarity, entry))
        
        # Сортируем по схожести и возвращаем лучшие
        scored_posts.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored_posts[:limit]]
    
    def get_context_for_generation(self, prompt: str, max_context_length: int = 2000) -> str:
        """
        Получает контекст из истории для улучшения генерации
        
        Args:
            prompt: Текущий промпт
            max_context_length: Максимальная длина контекста
            
        Returns:
            Контекст из истории в виде текста
        """
        # Находим похожие успешные посты
        similar_posts = self.get_similar_posts(prompt, limit=5)
        successful_posts = self.get_recent_successful_posts(limit=5)
        
        # Объединяем и убираем дубликаты
        all_posts = {}
        for entry in similar_posts + successful_posts:
            if entry.request_id not in all_posts:
                all_posts[entry.request_id] = entry
        
        # Формируем контекст
        context_parts = []
        context_length = 0
        
        for entry in list(all_posts.values())[:5]:  # Берем до 5 постов
            if entry.final_post:
                post_text = entry.final_post
            elif entry.generated_post:
                post_text = entry.generated_post
            else:
                continue
            
            # Добавляем информацию о посте
            post_info = f"Промпт: {entry.prompt[:100]}\nПост: {post_text[:300]}\n---\n"
            
            if context_length + len(post_info) > max_context_length:
                break
            
            context_parts.append(post_info)
            context_length += len(post_info)
        
        return "\n".join(context_parts) if context_parts else ""
    
    def get_learning_insights(self) -> Dict:
        """
        Получает инсайты для самообучения на основе истории
        
        Returns:
            Словарь с инсайтами
        """
        self._update_stats()
        
        insights = {
            "stats": self.stats.copy(),
            "recommendations": []
        }
        
        # Рекомендации на основе статистики
        if self.stats["avg_edit_count"] > 2:
            insights["recommendations"].append(
                "Высокое среднее количество правок. Рекомендуется улучшить промпты для генерации постов."
            )
        
        if self.stats["rejected_posts"] > self.stats["approved_posts"] * 0.3:
            insights["recommendations"].append(
                "Высокий процент отклоненных постов. Рекомендуется проанализировать причины отклонения."
            )
        
        # Анализ частых правок
        if "shorten" in self.stats.get("common_edits", {}):
            if self.stats["common_edits"]["shorten"] > 10:
                insights["recommendations"].append(
                    "Часто требуется сокращение текста. Рекомендуется генерировать более короткие посты."
                )
        
        if "add_emoji" in self.stats.get("common_edits", {}):
            if self.stats["common_edits"]["add_emoji"] > 10:
                insights["recommendations"].append(
                    "Часто требуется добавление эмодзи. Рекомендуется добавлять больше эмодзи при генерации."
                )
        
        return insights
