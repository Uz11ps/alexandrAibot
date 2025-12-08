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
        
        # Ежедневный анализ источников (если включен)
        if settings.SOURCE_ANALYSIS_ENABLED:
            analysis_hour, analysis_min = self._parse_time(settings.SOURCE_ANALYSIS_TIME)
            try:
                self.scheduler.remove_job('source_analysis')
            except:
                pass
            self.scheduler.add_job(
                self._analyze_sources_and_generate_post,
                CronTrigger(hour=analysis_hour, minute=analysis_min),
                id='source_analysis'
            )
            logger.info(f"Задача анализа источников настроена на {settings.SOURCE_ANALYSIS_TIME}")
        
        logger.info("Расписание публикаций настроено")
    
    async def _check_photos_and_notify(self, day_name: str) -> bool:
        """
        Проверяет наличие фотографий для поста и отправляет уведомления если их нет
        
        Args:
            day_name: Название дня недели (например, "понедельник")
            
        Returns:
            True если фото есть, False если нет
        """
        try:
            from services import dependencies
            
            # Проверяем наличие неиспользованных фотографий
            photos = await dependencies.file_service.get_unused_photos(limit=1)
            
            if not photos or len(photos) == 0:
                logger.warning(f"Нет доступных фотографий для поста на {day_name}")
                
                # Получаем список администраторов
                admin_ids = self._get_admin_ids()
                
                # Формируем сообщение
                message_text = (
                    f"⚠️ <b>Внимание!</b>\n\n"
                    f"Нет доступных фотографий для создания поста на <b>{day_name}</b>.\n\n"
                    f"Пожалуйста, загрузите фотографии через меню бота."
                )
                
                # Отправляем уведомления всем администраторам
                for admin_id in admin_ids:
                    try:
                        await dependencies.telegram_service.bot.send_message(
                            chat_id=admin_id,
                            text=message_text,
                            parse_mode="HTML"
                        )
                        logger.info(f"Уведомление отправлено администратору {admin_id}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")
                
                # Отправляем уведомление ответственному за контент сотруднику
                if dependencies.employee_service:
                    content_manager_id = dependencies.employee_service.get_content_manager_id()
                    if content_manager_id:
                        try:
                            await dependencies.telegram_service.bot.send_message(
                                chat_id=content_manager_id,
                                text=message_text,
                                parse_mode="HTML"
                            )
                            logger.info(f"Уведомление отправлено ответственному за контент {content_manager_id}")
                        except Exception as e:
                            logger.error(f"Ошибка при отправке уведомления ответственному за контент: {e}")
                
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при проверке фотографий: {e}")
            return True  # В случае ошибки продолжаем генерацию
    
    def _get_admin_ids(self) -> list[int]:
        """Возвращает список ID всех администраторов"""
        admin_ids = []
        
        # Основной администратор
        if settings.TELEGRAM_ADMIN_ID:
            admin_ids.append(settings.TELEGRAM_ADMIN_ID)
        
        # Дополнительные администраторы
        if settings.TELEGRAM_ADMIN_IDS:
            try:
                additional_ids = [int(id.strip()) for id in settings.TELEGRAM_ADMIN_IDS.split(',') if id.strip()]
                admin_ids.extend(additional_ids)
            except Exception as e:
                logger.error(f"Ошибка при парсинге дополнительных администраторов: {e}")
        
        return admin_ids
    
    async def _generate_and_send_monday_post(self):
        """Публикует запланированный пост понедельника или генерирует новый"""
        try:
            from services import dependencies
            
            # Проверяем, есть ли запланированный пост
            if dependencies.scheduled_posts_service:
                scheduled_post = dependencies.scheduled_posts_service.get_scheduled_post('monday')
                if scheduled_post:
                    logger.info("Найден запланированный пост для понедельника, публикуем его")
                    results = await self.post_service.publish_approved_post(
                        scheduled_post.post_text,
                        scheduled_post.photos
                    )
                    # Удаляем пост из запланированных после публикации
                    dependencies.scheduled_posts_service.remove_scheduled_post('monday')
                    logger.info(f"Запланированный пост понедельника опубликован: {results}")
                    return
            
            # Проверяем наличие фотографий перед генерацией
            if not await self._check_photos_and_notify("понедельник"):
                logger.info("Генерация поста понедельника пропущена из-за отсутствия фотографий")
                return
            
            # Если запланированного поста нет, генерируем новый
            logger.info("Генерация нового поста понедельника...")
            post_text, photos = await self.post_service.generate_monday_post()
            await self.post_service.send_for_approval(post_text, photos, day_of_week='monday')
        except Exception as e:
            logger.error(f"Ошибка при публикации поста понедельника: {e}")
    
    async def _generate_and_send_tuesday_post(self):
        """Публикует запланированный пост вторника или генерирует новый"""
        try:
            from services import dependencies
            
            if dependencies.scheduled_posts_service:
                scheduled_post = dependencies.scheduled_posts_service.get_scheduled_post('tuesday')
                if scheduled_post:
                    logger.info("Найден запланированный пост для вторника, публикуем его")
                    results = await self.post_service.publish_approved_post(
                        scheduled_post.post_text,
                        scheduled_post.photos
                    )
                    dependencies.scheduled_posts_service.remove_scheduled_post('tuesday')
                    logger.info(f"Запланированный пост вторника опубликован: {results}")
                    return
            
            # Проверяем наличие фотографий перед генерацией
            if not await self._check_photos_and_notify("вторник"):
                logger.info("Генерация поста вторника пропущена из-за отсутствия фотографий")
                return
            
            logger.info("Генерация нового поста вторника...")
            post_text, photos = await self.post_service.generate_tuesday_post()
            await self.post_service.send_for_approval(post_text, photos, day_of_week='tuesday')
        except Exception as e:
            logger.error(f"Ошибка при публикации поста вторника: {e}")
    
    async def _generate_and_send_wednesday_post(self):
        """Публикует запланированный пост среды или генерирует новый"""
        try:
            from services import dependencies
            
            if dependencies.scheduled_posts_service:
                scheduled_post = dependencies.scheduled_posts_service.get_scheduled_post('wednesday')
                if scheduled_post:
                    logger.info("Найден запланированный пост для среды, публикуем его")
                    results = await self.post_service.publish_approved_post(
                        scheduled_post.post_text,
                        scheduled_post.photos
                    )
                    dependencies.scheduled_posts_service.remove_scheduled_post('wednesday')
                    logger.info(f"Запланированный пост среды опубликован: {results}")
                    return
            
            # Проверяем наличие фотографий перед генерацией
            if not await self._check_photos_and_notify("среду"):
                logger.info("Генерация поста среды пропущена из-за отсутствия фотографий")
                return
            
            logger.info("Генерация нового поста среды...")
            day_of_month = datetime.now().day
            content_type = "meme" if day_of_month % 2 == 0 else "report"
            post_text, photos = await self.post_service.generate_wednesday_post(content_type)
            await self.post_service.send_for_approval(post_text, photos, day_of_week='wednesday')
        except Exception as e:
            logger.error(f"Ошибка при публикации поста среды: {e}")
    
    async def _generate_and_send_thursday_post(self):
        """Публикует запланированный пост четверга или генерирует новый"""
        try:
            from services import dependencies
            
            if dependencies.scheduled_posts_service:
                scheduled_post = dependencies.scheduled_posts_service.get_scheduled_post('thursday')
                if scheduled_post:
                    logger.info("Найден запланированный пост для четверга, публикуем его")
                    results = await self.post_service.publish_approved_post(
                        scheduled_post.post_text,
                        scheduled_post.photos
                    )
                    dependencies.scheduled_posts_service.remove_scheduled_post('thursday')
                    logger.info(f"Запланированный пост четверга опубликован: {results}")
                    return
            
            # Проверяем наличие фотографий перед генерацией
            if not await self._check_photos_and_notify("четверг"):
                logger.info("Генерация поста четверга пропущена из-за отсутствия фотографий")
                return
            
            logger.info("Генерация нового поста четверга...")
            post_text, photos = await self.post_service.generate_thursday_post()
            await self.post_service.send_for_approval(post_text, photos, day_of_week='thursday')
        except Exception as e:
            logger.error(f"Ошибка при публикации поста четверга: {e}")
    
    async def _generate_and_send_friday_post(self):
        """Публикует запланированный пост пятницы или генерирует новый"""
        try:
            from services import dependencies
            
            if dependencies.scheduled_posts_service:
                scheduled_post = dependencies.scheduled_posts_service.get_scheduled_post('friday')
                if scheduled_post:
                    logger.info("Найден запланированный пост для пятницы, публикуем его")
                    results = await self.post_service.publish_approved_post(
                        scheduled_post.post_text,
                        scheduled_post.photos
                    )
                    dependencies.scheduled_posts_service.remove_scheduled_post('friday')
                    logger.info(f"Запланированный пост пятницы опубликован: {results}")
                    return
            
            # Проверяем наличие фотографий перед генерацией
            if not await self._check_photos_and_notify("пятницу"):
                logger.info("Генерация поста пятницы пропущена из-за отсутствия фотографий")
                return
            
            logger.info("Генерация нового поста пятницы...")
            post_text, photos = await self.post_service.generate_friday_post()
            await self.post_service.send_for_approval(post_text, photos, day_of_week='friday')
        except Exception as e:
            logger.error(f"Ошибка при публикации поста пятницы: {e}")
    
    async def _generate_and_send_saturday_post(self):
        """Публикует запланированный пост субботы или генерирует новый"""
        try:
            from services import dependencies
            
            if dependencies.scheduled_posts_service:
                scheduled_post = dependencies.scheduled_posts_service.get_scheduled_post('saturday')
                if scheduled_post:
                    logger.info("Найден запланированный пост для субботы, публикуем его")
                    results = await self.post_service.publish_approved_post(
                        scheduled_post.post_text,
                        scheduled_post.photos
                    )
                    dependencies.scheduled_posts_service.remove_scheduled_post('saturday')
                    logger.info(f"Запланированный пост субботы опубликован: {results}")
                    return
            
            # Проверяем наличие фотографий перед генерацией
            if not await self._check_photos_and_notify("субботу"):
                logger.info("Генерация поста субботы пропущена из-за отсутствия фотографий")
                return
            
            logger.info("Генерация нового поста субботы...")
            post_text, photos = await self.post_service.generate_saturday_post()
            await self.post_service.send_for_approval(post_text, photos, day_of_week='saturday')
        except Exception as e:
            logger.error(f"Ошибка при публикации поста субботы: {e}")
    
    async def _send_sunday_reminders(self):
        """Отправляет напоминания сотрудникам о подготовке материалов"""
        try:
            logger.info("Отправка напоминаний сотрудникам...")
            # TODO: Реализовать отправку напоминаний сотрудникам
            # Пока заглушка
            pass
        except Exception as e:
            logger.error(f"Ошибка при отправке напоминаний: {e}")
    
    async def _analyze_sources_and_generate_post(self):
        """Анализирует источники и генерирует пост на основе анализа"""
        try:
            logger.info("Начало анализа источников и генерации поста...")
            
            # Импортируем зависимости здесь, чтобы избежать циклических импортов
            from services import dependencies
            
            if not dependencies.source_service or not dependencies.source_parser_service:
                logger.error("Сервисы источников не инициализированы")
                return
            
            if not dependencies.ai_service:
                logger.error("AI сервис не инициализирован")
                return
            
            # Получаем все включенные источники
            sources = dependencies.source_service.get_enabled_sources()
            
            if not sources:
                logger.info("Нет включенных источников для анализа")
                return
            
            # Парсим посты из всех источников
            source_posts = await dependencies.source_parser_service.parse_all_sources(sources)
            
            if not source_posts:
                logger.warning("Не удалось получить посты из источников")
                return
            
            # Генерируем пост на основе анализа
            generated_post = await dependencies.ai_service.generate_post_from_sources(source_posts)
            
            # Определяем день недели для планирования (завтрашний день)
            from datetime import timedelta
            tomorrow = datetime.now() + timedelta(days=1)
            day_mapping = {
                0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday',
                4: 'friday', 5: 'saturday', 6: 'sunday'
            }
            tomorrow_day = day_mapping.get(tomorrow.weekday())
            
            # Отправляем на утверждение администратору с указанием дня недели
            await self.post_service.send_for_approval(generated_post, photos=[], day_of_week=tomorrow_day)
            
            logger.info("Пост на основе анализа источников отправлен на утверждение")
            
        except Exception as e:
            logger.error(f"Ошибка при анализе источников и генерации поста: {e}", exc_info=True)
    
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

