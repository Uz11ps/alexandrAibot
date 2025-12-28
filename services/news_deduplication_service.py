"""Сервис для предотвращения дублирования новостей"""
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Set, Dict

logger = logging.getLogger(__name__)

class NewsDeduplicationService:
    """Сервис для хранения хешей использованных новостей"""
    
    def __init__(self):
        self.storage_path = Path("storage/deduplication")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.history_file = self.storage_path / "news_hashes.json"
        
        # Храним хеши: {hash: iso_timestamp}
        self.hashes: Dict[str, str] = {}
        self._load_hashes()
        self._cleanup_old_hashes()
    
    def _load_hashes(self):
        """Загружает хеши из файла"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.hashes = json.load(f)
                logger.info(f"Загружено {len(self.hashes)} хешей новостей")
        except Exception as e:
            logger.error(f"Ошибка при загрузке хешей: {e}")
            self.hashes = {}
            
    def _save_hashes(self):
        """Сохраняет хеши в файл"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.hashes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении хешей: {e}")
            
    def _cleanup_old_hashes(self, days: int = 30):
        """Удаляет хеши старше N дней"""
        cutoff = datetime.now() - timedelta(days=days)
        initial_count = len(self.hashes)
        
        self.hashes = {
            h: ts for h, ts in self.hashes.items() 
            if datetime.fromisoformat(ts) > cutoff
        }
        
        if len(self.hashes) < initial_count:
            logger.info(f"Очищено {initial_count - len(self.hashes)} старых хешей")
            self._save_hashes()
            
    def get_content_hash(self, text: str) -> str:
        """Генерирует хеш для текста новости"""
        # Очищаем текст от лишних пробелов для более точного сравнения
        clean_text = " ".join(text.lower().split())
        return hashlib.md5(clean_text.encode('utf-8')).hexdigest()
        
    def is_duplicate(self, text: str, url: str = None) -> bool:
        """Проверяет, является ли новость дубликатом"""
        if url and url in self.hashes:
            return True
            
        h = self.get_content_hash(text)
        return h in self.hashes
        
    def mark_as_used(self, text: str, url: str = None):
        """Помечает новость как использованную"""
        timestamp = datetime.now().isoformat()
        if url:
            self.hashes[url] = timestamp
        
        h = self.get_content_hash(text)
        self.hashes[h] = timestamp
        self._save_hashes()

