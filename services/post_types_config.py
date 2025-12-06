"""Сервис для управления конфигурацией типов постов"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Файл для хранения конфигурации типов постов
POST_TYPES_CONFIG_FILE = Path("config/post_types.json")

# Типы постов по умолчанию
DEFAULT_POST_TYPES = {
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
                    # Объединяем с дефолтными значениями для новых полей
                    for day, default_data in DEFAULT_POST_TYPES.items():
                        if day not in config:
                            config[day] = default_data.copy()
                        else:
                            # Обновляем недостающие поля
                            for key, value in default_data.items():
                                if key not in config[day]:
                                    config[day][key] = value
                    return config
        except Exception as e:
            logger.warning(f"Ошибка при загрузке конфигурации типов постов: {e}")
        
        # Возвращаем дефолтные значения
        return DEFAULT_POST_TYPES.copy()
    
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
        Получает тип поста для указанного дня
        
        Args:
            day: День недели (monday, tuesday, и т.д.)
            
        Returns:
            Словарь с информацией о типе поста
        """
        return self.config.get(day, DEFAULT_POST_TYPES.get(day, {}))
    
    def get_all_post_types(self) -> Dict:
        """Возвращает все типы постов"""
        return self.config.copy()
    
    def update_post_type(self, day: str, name: str, description: str = None, enabled: bool = True) -> bool:
        """
        Обновляет тип поста для указанного дня
        
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
            self.config[day] = {
                "name": name,
                "description": description or self.config.get(day, {}).get("description", ""),
                "enabled": enabled
            }
            self._save_config()
            logger.info(f"Тип поста обновлен: {day} = {name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении типа поста: {e}")
            return False
    
    def toggle_post_type(self, day: str) -> bool:
        """
        Переключает состояние типа поста (включен/выключен)
        
        Args:
            day: День недели
            
        Returns:
            True если успешно, False при ошибке
        """
        if day not in self.config:
            logger.error(f"Неизвестный день: {day}")
            return False
        
        try:
            self.config[day]["enabled"] = not self.config[day].get("enabled", True)
            self._save_config()
            logger.info(f"Тип поста переключен: {day} = {self.config[day]['enabled']}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при переключении типа поста: {e}")
            return False
