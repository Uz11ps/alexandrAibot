"""Сервис для управления источниками (Telegram каналы и VK группы)"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

SOURCES_FILE = Path("storage/sources.json")


@dataclass
class Source:
    """Информация об источнике"""
    type: str  # "telegram", "vk" или "website"
    url: str
    name: Optional[str] = None  # Опциональное имя для удобства
    added_at: Optional[str] = None
    enabled: bool = True
    
    def __post_init__(self):
        if self.added_at is None:
            self.added_at = datetime.now().isoformat()


class SourceService:
    """Сервис для управления источниками"""
    
    def __init__(self):
        self.sources_file = SOURCES_FILE
        self.sources_file.parent.mkdir(parents=True, exist_ok=True)
        self.sources: List[Source] = []
        self._load_sources()
    
    def _load_sources(self):
        """Загружает список источников из файла"""
        try:
            if self.sources_file.exists():
                with open(self.sources_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.sources = [Source(**source) for source in data]
                logger.info(f"Загружено {len(self.sources)} источников")
            else:
                self.sources = []
                logger.info("Файл источников не найден, создан пустой список")
        except Exception as e:
            logger.error(f"Ошибка при загрузке источников: {e}")
            self.sources = []
    
    def _save_sources(self):
        """Сохраняет список источников в файл"""
        try:
            data = [asdict(source) for source in self.sources]
            with open(self.sources_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Сохранено {len(self.sources)} источников")
        except Exception as e:
            logger.error(f"Ошибка при сохранении источников: {e}")
    
    def add_source(self, source_type: str, url: str, name: Optional[str] = None) -> bool:
        """
        Добавляет новый источник
        
        Args:
            source_type: Тип источника ("telegram", "vk" или "website")
            url: URL источника
            name: Опциональное имя источника
            
        Returns:
            True если успешно добавлен, False если уже существует
        """
        # Проверяем, не существует ли уже такой источник
        if any(s.url == url for s in self.sources):
            logger.warning(f"Источник с URL {url} уже существует")
            return False
        
        # Валидация типа
        if source_type not in ["telegram", "vk", "website"]:
            logger.error(f"Неверный тип источника: {source_type}")
            return False
        
        # Валидация URL
        if source_type == "telegram" and not url.startswith(("https://t.me/", "http://t.me/")):
            logger.error(f"Неверный формат Telegram URL: {url}")
            return False
        
        if source_type == "vk" and not url.startswith(("https://vk.com/", "http://vk.com/")):
            logger.error(f"Неверный формат VK URL: {url}")
            return False
        
        if source_type == "website" and not url.startswith(("https://", "http://")):
            logger.error(f"Неверный формат Website URL: {url}")
            return False
        
        source = Source(
            type=source_type,
            url=url,
            name=name,
            enabled=True
        )
        
        self.sources.append(source)
        self._save_sources()
        logger.info(f"Добавлен источник: {source_type} - {url}")
        return True
    
    def remove_source(self, url: str) -> bool:
        """
        Удаляет источник по URL
        
        Args:
            url: URL источника для удаления
            
        Returns:
            True если успешно удален, False если не найден
        """
        initial_count = len(self.sources)
        self.sources = [s for s in self.sources if s.url != url]
        
        if len(self.sources) < initial_count:
            self._save_sources()
            logger.info(f"Удален источник: {url}")
            return True
        else:
            logger.warning(f"Источник с URL {url} не найден")
            return False
    
    def get_all_sources(self) -> List[Source]:
        """Возвращает список всех источников"""
        return self.sources.copy()
    
    def get_enabled_sources(self) -> List[Source]:
        """Возвращает список только включенных источников"""
        return [s for s in self.sources if s.enabled]
    
    def get_sources_by_type(self, source_type: str) -> List[Source]:
        """Возвращает источники определенного типа"""
        return [s for s in self.sources if s.type == source_type and s.enabled]
    
    def toggle_source(self, url: str) -> bool:
        """
        Включает/выключает источник
        
        Args:
            url: URL источника
            
        Returns:
            True если успешно изменен, False если не найден
        """
        for source in self.sources:
            if source.url == url:
                source.enabled = not source.enabled
                self._save_sources()
                logger.info(f"Источник {url} {'включен' if source.enabled else 'выключен'}")
                return True
        
        logger.warning(f"Источник с URL {url} не найден")
        return False
    
    def get_source_by_url(self, url: str) -> Optional[Source]:
        """Возвращает источник по URL"""
        for source in self.sources:
            if source.url == url:
                return source
        return None

