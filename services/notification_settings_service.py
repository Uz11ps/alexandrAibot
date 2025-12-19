"""Сервис для управления настройками уведомлений"""
import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class NotificationSettingsService:
    """Сервис для управления настройками уведомлений"""
    
    def __init__(self):
        self.storage_path = Path("storage/settings")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.storage_path / "notifications.json"
        self.settings: Dict[str, bool] = {
            "draft_notifications": True  # Уведомления о черновиках по умолчанию включены
        }
        self._load_settings()
    
    def _load_settings(self):
        """Загружает настройки из файла"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
                logger.info("Настройки уведомлений загружены")
        except Exception as e:
            logger.error(f"Ошибка при загрузке настроек уведомлений: {e}")
            self.settings = {"draft_notifications": True}
    
    def _save_settings(self):
        """Сохраняет настройки в файл"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении настроек уведомлений: {e}")
    
    def is_draft_notifications_enabled(self) -> bool:
        """Проверяет, включены ли уведомления о черновиках"""
        return self.settings.get("draft_notifications", True)
    
    def set_draft_notifications(self, enabled: bool):
        """Включает или отключает уведомления о черновиках"""
        self.settings["draft_notifications"] = enabled
        self._save_settings()
        logger.info(f"Уведомления о черновиках {'включены' if enabled else 'отключены'}")

