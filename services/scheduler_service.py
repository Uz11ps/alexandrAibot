"""Сервис для планирования публикаций"""
import logging
import importlib
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import settings as settings_module

logger = logging.getLogger(__name__)

# Получаем settings объект
settings = settings_module.settings


class SchedulerService:
    """Сервис для управления расписанием публикаций"""
    
    def __init__(self, post_service):
        self.scheduler = AsyncIOScheduler()
        self.post_service = post_service
        self.is_enabled = True
    
    def _parse_time(self, time_str: str) -> tuple[int, int]:
        """Парсит время из строки формата HH:MM"""
        hour, minute = map(int, time_str.split(':'))
        return hour, minute
    
    def setup_schedule(self, reload_settings: bool = False):
        """Настраивает расписание публикаций"""
        if not self.is_enabled:
            logger.info("Планировщик отключен")
            return
        
        # Перезагружаем настройки если нужно
        if reload_settings:
            global settings
            importlib.reload(settings_module)
            settings = settings_module.settings
            logger.info("Настройки перезагружены")
        
        # Понедельник - отчет по объектам
        mon_hour, mon_min = self._parse_time(settings.SCHEDULE_MONDAY_TIME)
        try:
            self.scheduler.remove_job('monday_post')
        except:
            pass
        self.scheduler.add_job(
            self._generate_and_send_monday_post,
            CronTrigger(day_of_week='mon', hour=mon_hour, minute=mon_min),
            id='monday_post'
        )
        
        # Вторник - экспертная статья
        tue_hour, tue_min = self._parse_time(settings.SCHEDULE_TUESDAY_TIME)
        try:
            self.scheduler.remove_job('tuesday_post')
        except:
            pass
        self.scheduler.add_job(
            self._generate_and_send_tuesday_post,
            CronTrigger(day_of_week='tue', hour=tue_hour, minute=tue_min),
            id='tuesday_post'
        )
        
        # Среда - отчет или мемы
        wed_hour, wed_min = self._parse_time(settings.SCHEDULE_WEDNESDAY_TIME)
        try:
            self.scheduler.remove_job('wednesday_post')
        except:
            pass
        self.scheduler.add_job(
            self._generate_and_send_wednesday_post,
            CronTrigger(day_of_week='wed', hour=wed_hour, minute=wed_min),
            id='wednesday_post'
        )
        
        # Четверг - ответы на вопросы
        thu_hour, thu_min = self._parse_time(settings.SCHEDULE_THURSDAY_TIME)
        try:
            self.scheduler.remove_job('thursday_post')
        except:
            pass
        self.scheduler.add_job(
            self._generate_and_send_thursday_post,
            CronTrigger(day_of_week='thu', hour=thu_hour, minute=thu_min),
            id='thursday_post'
        )
        
        # Пятница - обзор проектов
        fri_hour, fri_min = self._parse_time(settings.SCHEDULE_FRIDAY_TIME)
        try:
            self.scheduler.remove_job('friday_post')
        except:
            pass
        self.scheduler.add_job(
            self._generate_and_send_friday_post,
            CronTrigger(day_of_week='fri', hour=fri_hour, minute=fri_min),
            id='friday_post'
        )
        
        # Суббота - услуги компании
        sat_hour, sat_min = self._parse_time(settings.SCHEDULE_SATURDAY_TIME)
        try:
            self.scheduler.remove_job('saturday_post')
        except:
            pass
        self.scheduler.add_job(
            self._generate_and_send_saturday_post,
            CronTrigger(day_of_week='sat', hour=sat_hour, minute=sat_min),
            id='saturday_post'
        )
        
        # Воскресенье - напоминания сотрудникам
        sun_hour, sun_min = self._parse_time(settings.SCHEDULE_SUNDAY_REMINDER_TIME)
        try:
            self.scheduler.remove_job('sunday_reminders')
        except:
            pass
        self.scheduler.add_job(
            self._send_sunday_reminders,
            CronTrigger(day_of_week='sun', hour=sun_hour, minute=sun_min),
            id='sunday_reminders'
        )
        
        logger.info("Расписание публикаций настроено")
    
    async def _generate_and_send_monday_post(self):
        """Генерирует и отправляет пост понедельника"""
        try:
            logger.info("Генерация поста понедельника...")
            post_text, photos = await self.post_service.generate_monday_post()
            await self.post_service.send_for_approval(post_text, photos)
        except Exception as e:
            logger.error(f"Ошибка при генерации поста понедельника: {e}")
    
    async def _generate_and_send_tuesday_post(self):
        """Генерирует и отправляет пост вторника"""
        try:
            logger.info("Генерация поста вторника...")
            post_text, photos = await self.post_service.generate_tuesday_post()
            await self.post_service.send_for_approval(post_text, photos)
        except Exception as e:
            logger.error(f"Ошибка при генерации поста вторника: {e}")
    
    async def _generate_and_send_wednesday_post(self):
        """Генерирует и отправляет пост среды"""
        try:
            logger.info("Генерация поста среды...")
            # Чередуем отчет и мемы
            day_of_month = datetime.now().day
            content_type = "meme" if day_of_month % 2 == 0 else "report"
            post_text, photos = await self.post_service.generate_wednesday_post(content_type)
            await self.post_service.send_for_approval(post_text, photos)
        except Exception as e:
            logger.error(f"Ошибка при генерации поста среды: {e}")
    
    async def _generate_and_send_thursday_post(self):
        """Генерирует и отправляет пост четверга"""
        try:
            logger.info("Генерация поста четверга...")
            post_text, photos = await self.post_service.generate_thursday_post()
            await self.post_service.send_for_approval(post_text, photos)
        except Exception as e:
            logger.error(f"Ошибка при генерации поста четверга: {e}")
    
    async def _generate_and_send_friday_post(self):
        """Генерирует и отправляет пост пятницы"""
        try:
            logger.info("Генерация поста пятницы...")
            post_text, photos = await self.post_service.generate_friday_post()
            await self.post_service.send_for_approval(post_text, photos)
        except Exception as e:
            logger.error(f"Ошибка при генерации поста пятницы: {e}")
    
    async def _generate_and_send_saturday_post(self):
        """Генерирует и отправляет пост субботы"""
        try:
            logger.info("Генерация поста субботы...")
            post_text, photos = await self.post_service.generate_saturday_post()
            await self.post_service.send_for_approval(post_text, photos)
        except Exception as e:
            logger.error(f"Ошибка при генерации поста субботы: {e}")
    
    async def _send_sunday_reminders(self):
        """Отправляет напоминания сотрудникам о подготовке материалов"""
        try:
            logger.info("Отправка напоминаний сотрудникам...")
            # TODO: Реализовать отправку напоминаний сотрудникам
            # Пока заглушка
            pass
        except Exception as e:
            logger.error(f"Ошибка при отправке напоминаний: {e}")
    
    def start(self):
        """Запускает планировщик"""
        self.setup_schedule()
        self.scheduler.start()
        logger.info("Планировщик запущен")
    
    def stop(self):
        """Останавливает планировщик"""
        self.scheduler.shutdown()
        logger.info("Планировщик остановлен")
    
    def enable(self):
        """Включает планировщик"""
        self.is_enabled = True
        self.setup_schedule()
        logger.info("Планировщик включен")
    
    def disable(self):
        """Отключает планировщик"""
        self.is_enabled = False
        self.scheduler.remove_all_jobs()
        logger.info("Планировщик отключен")

