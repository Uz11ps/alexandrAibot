"""Сервис для работы с конфигурацией расписания"""
import os
import re
import logging
from pathlib import Path
from config.settings import settings

logger = logging.getLogger(__name__)


class ScheduleConfigService:
    """Сервис для управления конфигурацией расписания"""
    
    def __init__(self):
        self.env_file = Path(".env")
    
    def update_schedule_time(self, day: str, time_str: str) -> bool:
        """
        Обновляет время публикации для указанного дня
        
        Args:
            day: День недели (monday, tuesday, wednesday, thursday, friday, saturday, sunday)
            time_str: Время в формате HH:MM
            
        Returns:
            True если успешно, False при ошибке
        """
        # Проверяем формат времени
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
            logger.error(f"Неверный формат времени: {time_str}")
            return False
        
        day_map = {
            'monday': 'SCHEDULE_MONDAY_TIME',
            'tuesday': 'SCHEDULE_TUESDAY_TIME',
            'wednesday': 'SCHEDULE_WEDNESDAY_TIME',
            'thursday': 'SCHEDULE_THURSDAY_TIME',
            'friday': 'SCHEDULE_FRIDAY_TIME',
            'saturday': 'SCHEDULE_SATURDAY_TIME',
            'sunday': 'SCHEDULE_SUNDAY_REMINDER_TIME'
        }
        
        env_key = day_map.get(day.lower())
        if not env_key:
            logger.error(f"Неизвестный день: {day}")
            return False
        
        try:
            # Читаем файл .env
            if not self.env_file.exists():
                logger.error("Файл .env не найден")
                return False
            
            lines = []
            updated = False
            
            with open(self.env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith(f'{env_key}='):
                        lines.append(f'{env_key}={time_str}\n')
                        updated = True
                    else:
                        lines.append(line)
            
            # Если параметр не найден, добавляем его
            if not updated:
                lines.append(f'{env_key}={time_str}\n')
            
            # Записываем обратно
            with open(self.env_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            logger.info(f"Расписание обновлено: {day} = {time_str}")
            return True
        
        except Exception as e:
            logger.error(f"Ошибка при обновлении расписания: {e}")
            return False
    
    def get_schedule_time(self, day: str) -> str:
        """
        Получает время публикации для указанного дня
        
        Args:
            day: День недели (monday, tuesday, и т.д.)
            
        Returns:
            Время в формате HH:MM
        """
        day_map = {
            'monday': settings.SCHEDULE_MONDAY_TIME,
            'tuesday': settings.SCHEDULE_TUESDAY_TIME,
            'wednesday': settings.SCHEDULE_WEDNESDAY_TIME,
            'thursday': settings.SCHEDULE_THURSDAY_TIME,
            'friday': settings.SCHEDULE_FRIDAY_TIME,
            'saturday': settings.SCHEDULE_SATURDAY_TIME,
            'sunday': settings.SCHEDULE_SUNDAY_REMINDER_TIME
        }
        
        return day_map.get(day.lower(), "09:00")

