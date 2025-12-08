"""Сервис для управления конфигурацией типов постов"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# Файл для хранения конфигурации типов постов
POST_TYPES_CONFIG_FILE = Path("config/post_types.json")

# Типы постов по умолчанию (старый формат для обратной совместимости)
DEFAULT_POST_TYPES_OLD = {
    "monday": {
        "name": "Отчет по объектам",
        "description": "Отчетные посты по текущим объектам с фотографиями",
        "enabled": True
    },
    "tuesday": {
        "name": "Экспертная статья",
        "description": "Экспертная статья по земельным вопросам",
        "enabled": True
    },
    "wednesday": {
        "name": "Отчет или мемы",
        "description": "Отчет по стройке или приколы, мемы, визуальный контент",
        "enabled": True
    },
    "thursday": {
        "name": "Ответы на вопросы",
        "description": "Пост на основе частых вопросов клиентов",
        "enabled": True
    },
    "friday": {
        "name": "Обзор проектов",
        "description": "Обзор текущих проектов с подборкой фото",
        "enabled": True
    },
    "saturday": {
        "name": "Услуги компании",
        "description": "Пост об услугах компании",
        "enabled": True
    }
}

# Новый формат: массив постов для каждого дня с указанием времени
DEFAULT_POST_TYPES = {
    "monday": [
        {"time": "09:00", "name": "Отчет по объектам", "description": "Отчетные посты по текущим объектам с фотографиями", "enabled": True}
    ],
    "tuesday": [
        {"time": "09:00", "name": "Экспертная статья", "description": "Экспертная статья по земельным вопросам", "enabled": True}
    ],
    "wednesday": [
        {"time": "09:00", "name": "Отчет или мемы", "description": "Отчет по стройке или приколы, мемы, визуальный контент", "enabled": True}
    ],
    "thursday": [
        {"time": "09:00", "name": "Ответы на вопросы", "description": "Пост на основе частых вопросов клиентов", "enabled": True}
    ],
    "friday": [
        {"time": "09:00", "name": "Обзор проектов", "description": "Обзор текущих проектов с подборкой фото", "enabled": True}
    ],
    "saturday": [
        {"time": "09:00", "name": "Услуги компании", "description": "Пост об услугах компании", "enabled": True}
    ]
}


class PostTypesConfigService:
    """Сервис для управления типами постов"""
    
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Загружает конфигурацию типов постов из файла"""
        try:
            if POST_TYPES_CONFIG_FILE.exists():
                with open(POST_TYPES_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Конвертируем старый формат в новый, если нужно
                    config = self._migrate_old_format(config)
                    # Объединяем с дефолтными значениями для новых полей
                    for day, default_posts in DEFAULT_POST_TYPES.items():
                        if day not in config:
                            config[day] = default_posts.copy()
                        else:
                            # Убеждаемся, что это массив
                            if not isinstance(config[day], list):
                                config[day] = self._convert_to_list(config[day])
                    return config
        except Exception as e:
            logger.warning(f"Ошибка при загрузке конфигурации типов постов: {e}")
        
        # Возвращаем дефолтные значения
        return DEFAULT_POST_TYPES.copy()
    
    def _migrate_old_format(self, config: Dict) -> Dict:
        """Конвертирует старый формат (один объект) в новый (массив)"""
        migrated = {}
        for day, value in config.items():
            if isinstance(value, dict) and "time" not in value:
                # Старый формат - конвертируем в массив
                migrated[day] = [{"time": "09:00", **value}]
            elif isinstance(value, list):
                # Уже новый формат
                migrated[day] = value
            else:
                migrated[day] = value
        return migrated
    
    def _convert_to_list(self, post_data: Dict) -> List[Dict]:
        """Конвертирует один объект поста в массив"""
        if "time" not in post_data:
            return [{"time": "09:00", **post_data}]
        return [post_data]
    
    def _save_config(self):
        """Сохраняет конфигурацию типов постов в файл"""
        try:
            POST_TYPES_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(POST_TYPES_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info("Конфигурация типов постов сохранена")
        except Exception as e:
            logger.error(f"Ошибка при сохранении конфигурации типов постов: {e}")
    
    def get_post_type(self, day: str) -> Dict:
        """
        Получает первый тип поста для указанного дня (для обратной совместимости)
        
        Args:
            day: День недели (monday, tuesday, и т.д.)
            
        Returns:
            Словарь с информацией о типе поста
        """
        posts = self.get_post_types(day)
        if posts:
            return posts[0]
        return {}
    
    def get_post_types(self, day: str) -> List[Dict]:
        """
        Получает все типы постов для указанного дня
        
        Args:
            day: День недели (monday, tuesday, и т.д.)
            
        Returns:
            Список словарей с информацией о типах постов
        """
        return self.config.get(day, DEFAULT_POST_TYPES.get(day, []))
    
    def get_all_post_types(self) -> Dict:
        """Возвращает все типы постов"""
        return self.config.copy()
    
    def update_post_type(self, day: str, name: str, description: str = None, enabled: bool = True) -> bool:
        """
        Обновляет первый тип поста для указанного дня (для обратной совместимости)
        
        Args:
            day: День недели (monday, tuesday, и т.д.)
            name: Название типа поста
            description: Описание типа поста
            enabled: Включен ли тип поста
            
        Returns:
            True если успешно, False при ошибке
        """
        if day not in DEFAULT_POST_TYPES:
            logger.error(f"Неизвестный день: {day}")
            return False
        
        try:
            posts = self.get_post_types(day)
            if not posts:
                # Если постов нет, создаем новый
                default_time = DEFAULT_POST_TYPES[day][0]["time"] if DEFAULT_POST_TYPES[day] else "09:00"
                posts = [{"time": default_time, "name": name, "description": description or "", "enabled": enabled}]
            else:
                # Обновляем первый пост
                posts[0]["name"] = name
                if description is not None:
                    posts[0]["description"] = description
                posts[0]["enabled"] = enabled
            
            self.config[day] = posts
            self._save_config()
            logger.info(f"Тип поста обновлен: {day} = {name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении типа поста: {e}")
            return False
    
    def toggle_post_type(self, day: str, post_index: int = 0) -> bool:
        """
        Переключает состояние типа поста (включен/выключен)
        
        Args:
            day: День недели
            post_index: Индекс поста в массиве (по умолчанию 0)
            
        Returns:
            True если успешно, False при ошибке
        """
        if day not in self.config:
            logger.error(f"Неизвестный день: {day}")
            return False
        
        posts = self.get_post_types(day)
        if post_index >= len(posts):
            logger.error(f"Индекс поста {post_index} выходит за границы для дня {day}")
            return False
        
        try:
            posts[post_index]["enabled"] = not posts[post_index].get("enabled", True)
            self.config[day] = posts
            self._save_config()
            logger.info(f"Тип поста переключен: {day}[{post_index}] = {posts[post_index]['enabled']}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при переключении типа поста: {e}")
            return False
    
    def add_post(self, day: str, time: str, name: str, description: str = "", enabled: bool = True) -> bool:
        """
        Добавляет новый пост в расписание дня
        
        Args:
            day: День недели
            time: Время публикации в формате HH:MM
            name: Название поста
            description: Описание поста
            enabled: Включен ли пост
            
        Returns:
            True если успешно, False при ошибке
        """
        if day not in DEFAULT_POST_TYPES:
            logger.error(f"Неизвестный день: {day}")
            return False
        
        try:
            if day not in self.config:
                self.config[day] = []
            
            new_post = {
                "time": time,
                "name": name,
                "description": description,
                "enabled": enabled
            }
            
            self.config[day].append(new_post)
            self._save_config()
            logger.info(f"Пост добавлен: {day} в {time} - {name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении поста: {e}")
            return False
    
    def update_post(self, day: str, post_index: int, time: str = None, name: str = None, 
                    description: str = None, enabled: Optional[bool] = None) -> bool:
        """
        Обновляет существующий пост в расписании
        
        Args:
            day: День недели
            post_index: Индекс поста в массиве
            time: Новое время публикации (опционально)
            name: Новое название (опционально)
            description: Новое описание (опционально)
            enabled: Новое состояние (опционально)
            
        Returns:
            True если успешно, False при ошибке
        """
        posts = self.get_post_types(day)
        if post_index >= len(posts):
            logger.error(f"Индекс поста {post_index} выходит за границы для дня {day}")
            return False
        
        try:
            if time is not None:
                posts[post_index]["time"] = time
            if name is not None:
                posts[post_index]["name"] = name
            if description is not None:
                posts[post_index]["description"] = description
            if enabled is not None:
                posts[post_index]["enabled"] = enabled
            
            self.config[day] = posts
            self._save_config()
            logger.info(f"Пост обновлен: {day}[{post_index}]")
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении поста: {e}")
            return False
    
    def remove_post(self, day: str, post_index: int) -> bool:
        """
        Удаляет пост из расписания
        
        Args:
            day: День недели
            post_index: Индекс поста в массиве
            
        Returns:
            True если успешно, False при ошибке
        """
        posts = self.get_post_types(day)
        if post_index >= len(posts):
            logger.error(f"Индекс поста {post_index} выходит за границы для дня {day}")
            return False
        
        try:
            removed_post = posts.pop(post_index)
            self.config[day] = posts
            self._save_config()
            logger.info(f"Пост удален: {day}[{post_index}] - {removed_post.get('name', '')}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении поста: {e}")
            return False
