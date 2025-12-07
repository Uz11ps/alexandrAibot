"""Сервис для управления настройками сотрудников"""
import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

EMPLOYEE_SETTINGS_FILE = Path("config/employee_settings.json")

DEFAULT_SETTINGS = {
    "response_timeout_hours": 24,  # Таймаут для эскалации (часы)
    "reminder_interval_hours": 4   # Интервал напоминаний (часы)
}


class EmployeeSettingsService:
    """Сервис для управления настройками таймаутов сотрудников"""
    
    def __init__(self):
        self.settings = self._load_settings()
    
    def _load_settings(self) -> Dict:
        """Загружает настройки из файла"""
        try:
            if EMPLOYEE_SETTINGS_FILE.exists():
                with open(EMPLOYEE_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # Объединяем с дефолтными значениями для новых полей
                    for key, value in DEFAULT_SETTINGS.items():
                        if key not in settings:
                            settings[key] = value
                    return settings
        except Exception as e:
            logger.warning(f"Ошибка при загрузке настроек сотрудников: {e}")
        
        # Возвращаем дефолтные значения
        return DEFAULT_SETTINGS.copy()
    
    def _save_settings(self):
        """Сохраняет настройки в файл"""
        try:
            EMPLOYEE_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(EMPLOYEE_SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            logger.info("Настройки сотрудников сохранены")
        except Exception as e:
            logger.error(f"Ошибка при сохранении настроек сотрудников: {e}")
    
    def get_response_timeout(self) -> int:
        """Получает таймаут для эскалации (в часах)"""
        return self.settings.get("response_timeout_hours", 24)
    
    def get_reminder_interval(self) -> int:
        """Получает интервал напоминаний (в часах)"""
        return self.settings.get("reminder_interval_hours", 4)
    
    def set_response_timeout(self, hours: int) -> bool:
        """
        Устанавливает таймаут для эскалации
        
        Args:
            hours: Количество часов до эскалации
            
        Returns:
            True если успешно
        """
        if hours < 1:
            return False
        
        self.settings["response_timeout_hours"] = hours
        self._save_settings()
        logger.info(f"Таймаут эскалации установлен: {hours} часов")
        return True
    
    def set_reminder_interval(self, hours: int) -> bool:
        """
        Устанавливает интервал напоминаний
        
        Args:
            hours: Интервал между напоминаниями (в часах)
            
        Returns:
            True если успешно
        """
        if hours < 1:
            return False
        
        self.settings["reminder_interval_hours"] = hours
        self._save_settings()
        logger.info(f"Интервал напоминаний установлен: {hours} часов")
        return True
    
    def get_all_settings(self) -> Dict:
        """Получает все настройки"""
        return self.settings.copy()

