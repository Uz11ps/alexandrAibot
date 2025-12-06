"""Сервис для генерации и управления постами"""
import logging
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from services.ai_service import AIService
from services.file_service import FileService
from services.telegram_service import TelegramService
from services.vk_service import VKService

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class PostService:
    """Сервис для генерации и публикации постов"""
    
    def __init__(
        self,
        ai_service: AIService,
        file_service: FileService,
        telegram_service: TelegramService,
        vk_service: VKService
    ):
        self.ai_service = ai_service
        self.file_service = file_service
        self.telegram_service = telegram_service
        self.vk_service = vk_service
    
    async def generate_monday_post(self) -> tuple[str, List[str]]:
        """
        Генерирует пост для понедельника (отчет по объектам)
        
        Returns:
            Кортеж (текст поста, список путей к фотографиям)
        """
        try:
            logger.info("Начало генерации поста для понедельника")
            
            # Получаем неиспользованные фотографии
            logger.info("Получение фотографий...")
            photos = await self.file_service.get_unused_photos(limit=5)
            logger.info(f"Получено фотографий: {len(photos)}")
            
            if not photos:
                logger.warning("Нет доступных фотографий для поста")
                return "Нет доступных фотографий для создания отчета.", []
            
            # Анализируем фотографии через AI
            logger.info(f"Начало анализа {len(photos)} фотографий через AI...")
            photos_descriptions = []
            ai_available = True
            
            for i, photo in enumerate(photos, 1):
                try:
                    logger.info(f"Анализ фотографии {i}/{len(photos)}: {photo.name}")
                    description = await self.ai_service.analyze_photo(str(photo))
                    photos_descriptions.append(description)
                    await self.file_service.mark_file_as_used(photo)
                    logger.info(f"Фотография {i} успешно проанализирована")
                except Exception as e:
                    error_str = str(e)
                    logger.error(f"Ошибка при анализе фото {photo}: {e}")
                    
                    # Если это ошибка региона, используем fallback
                    if "unsupported_country_region_territory" in error_str or "403" in error_str:
                        ai_available = False
                        photos_descriptions.append(f"Фотография: {photo.name}")
                    else:
                        photos_descriptions.append(f"Фотография: {photo.name}")
            
            logger.info(f"Анализ завершен. Получено описаний: {len(photos_descriptions)}")
            
            # Формируем промпт для генерации поста
            logger.info("Формирование промпта для генерации поста...")
            prompt = """Создай отчетный пост о текущих объектах компании "Археон".
Включи описание работ, сложности участков, способы решения проблем,
ошибки клиентов и рекомендации. Стиль: профессиональный, но понятный."""
            
            context = "\n\n".join(photos_descriptions)
            logger.info(f"Контекст подготовлен (длина: {len(context)} символов)")
            
            # Генерируем текст поста
            logger.info("Генерация текста поста через AI...")
            try:
                post_text = await self.ai_service.generate_post_text(
                    prompt=prompt,
                    context=context,
                    photos_description="\n".join(photos_descriptions)
                )
                logger.info(f"Текст поста успешно сгенерирован (длина: {len(post_text)} символов)")
            except Exception as e:
                error_str = str(e)
                logger.error(f"Ошибка при генерации текста поста: {e}")
                
                # Если AI недоступен, создаем базовый пост
                if "unsupported_country_region_territory" in error_str or "403" in error_str or "таймаут" in error_str.lower() or "timeout" in error_str.lower():
                    logger.warning("Создание базового поста без AI")
                    post_text = (
                        f"📊 Отчет по объектам компании «Археон»\n\n"
                        f"На этой неделе мы работали над {len(photos)} объектом(ами).\n\n"
                        f"📸 Фотографии объектов прикреплены.\n\n"
                        f"Наши специалисты продолжают качественно выполнять все работы, "
                        f"соблюдая сроки и стандарты качества.\n\n"
                        f"⚠️ Примечание: Из-за технических ограничений детальный анализ через AI временно недоступен. "
                        f"Для получения полного отчета свяжитесь с нашими специалистами."
                    )
                else:
                    raise
            
            logger.info("Генерация поста завершена успешно")
            return post_text, [str(photo) for photo in photos]
        
        except Exception as e:
            logger.error(f"Ошибка при генерации поста понедельника: {e}")
            # Возвращаем базовый пост даже при ошибке
            return (
                f"📊 Отчет по объектам компании «Археон»\n\n"
                f"Произошла ошибка при генерации поста: {str(e)}\n\n"
                f"Пожалуйста, создайте пост вручную или проверьте настройки AI сервиса."
            ), []
    
    async def generate_tuesday_post(self) -> tuple[str, List[str]]:
        """
        Генерирует пост для вторника (экспертная статья)
        
        Returns:
            Кортеж (текст поста, список путей к документам)
        """
        try:
            # Получаем документы из папки "Законы"
            law_documents = await self.file_service.get_law_documents()
            
            # Получаем черновики сотрудников
            drafts = await self.file_service.get_draft_files()
            
            context_parts = []
            
            # Читаем содержимое документов (пока только текстовые файлы)
            for doc in law_documents:
                if doc.suffix == '.txt':
                    try:
                        content = await self.file_service.read_file_content(doc)
                        context_parts.append(f"Документ {doc.name}:\n{content}")
                    except Exception as e:
                        logger.error(f"Ошибка при чтении документа {doc}: {e}")
            
            for draft in drafts:
                try:
                    content = await self.file_service.read_file_content(draft)
                    context_parts.append(f"Черновик {draft.name}:\n{content}")
                except Exception as e:
                    logger.error(f"Ошибка при чтении черновика {draft}: {e}")
            
            prompt = """Создай экспертную статью по земельным вопросам для компании "Археон".
Выдели изменения в законодательстве, важные моменты для клиентов.
Стиль: экспертный, но доступный для понимания."""
            
            context = "\n\n".join(context_parts) if context_parts else None
            
            post_text = await self.ai_service.generate_post_text(
                prompt=prompt,
                context=context
            )
            
            return post_text, []
        
        except Exception as e:
            logger.error(f"Ошибка при генерации поста вторника: {e}")
            raise
    
    async def generate_wednesday_post(self, content_type: str = "report") -> tuple[str, List[str]]:
        """
        Генерирует пост для среды
        
        Args:
            content_type: Тип контента ("report" или "meme")
            
        Returns:
            Кортеж (текст поста, список путей к файлам)
        """
        if content_type == "report":
            return await self.generate_monday_post()  # Аналогично понедельнику
        else:
            # Генерируем мем
            meme_idea = await self.ai_service.generate_meme_idea(
                "строительство и земельные работы"
            )
            return f"Идея для мема:\n{meme_idea}", []
    
    async def generate_thursday_post(self) -> tuple[str, List[str]]:
        """
        Генерирует пост для четверга (ответы на частые вопросы)
        
        Returns:
            Кортеж (текст поста, список путей к файлам)
        """
        try:
            topics = [
                "отступы от границ участка",
                "ЛПХ (личное подсобное хозяйство)",
                "СНТ (садовое некоммерческое товарищество)",
                "дачная амнистия",
                "кадастровые ошибки",
                "фундамент и его особенности"
            ]
            
            prompt = f"""Создай полезный пост на тему частых вопросов клиентов.
Темы для освещения: {', '.join(topics)}.
Сделай пост информативным, с практическими советами.
Стиль: дружелюбный, но профессиональный."""
            
            post_text = await self.ai_service.generate_post_text(prompt=prompt)
            
            return post_text, []
        
        except Exception as e:
            logger.error(f"Ошибка при генерации поста четверга: {e}")
            raise
    
    async def generate_friday_post(self) -> tuple[str, List[str]]:
        """
        Генерирует пост для пятницы (обзор проектов недели)
        
        Returns:
            Кортеж (текст поста, список путей к фотографиям)
        """
        try:
            photos = await self.file_service.get_unused_photos(limit=10)
            
            if not photos:
                return "Обзор проектов недели будет добавлен позже.", []
            
            prompt = """Создай обзорный пост о проектах компании "Археон" за неделю.
Сделай его интересным, покажи разнообразие работ.
Стиль: динамичный, с акцентом на достижения."""
            
            post_text = await self.ai_service.generate_post_text(prompt=prompt)
            
            # Помечаем фото как использованные
            for photo in photos:
                await self.file_service.mark_file_as_used(photo)
            
            return post_text, [str(photo) for photo in photos]
        
        except Exception as e:
            logger.error(f"Ошибка при генерации поста пятницы: {e}")
            raise
    
    async def generate_saturday_post(self) -> tuple[str, List[str]]:
        """
        Генерирует пост для субботы (услуги компании)
        
        Returns:
            Кортеж (текст поста, список путей к файлам)
        """
        try:
            services = [
                "Фундамент",
                "Межевание",
                "Сопровождение сделок",
                "Проекты домов"
            ]
            
            prompt = f"""Создай пост об услугах компании "Археон".
Услуги: {', '.join(services)}.
Сделай пост привлекательным для потенциальных клиентов.
Стиль: продающий, но не навязчивый."""
            
            post_text = await self.ai_service.generate_post_text(prompt=prompt)
            
            return post_text, []
        
        except Exception as e:
            logger.error(f"Ошибка при генерации поста субботы: {e}")
            raise
    
    async def send_for_approval(self, post_text: str, photos: List[str]) -> int:
        """
        Отправляет пост на согласование руководителю
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям
            
        Returns:
            ID сообщения с черновиком
        """
        return await self.telegram_service.send_draft_for_approval(post_text, photos)
    
    async def publish_approved_post(self, post_text: str, photos: List[str]) -> dict:
        """
        Публикует утвержденный пост в VK и Telegram
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям
            
        Returns:
            Словарь с ID опубликованных постов
        """
        results = {}
        
        try:
            # Публикуем в Telegram
            telegram_id = await self.telegram_service.publish_to_channel(post_text, photos)
            results['telegram'] = telegram_id
            
            # Публикуем в VK
            vk_id = self.vk_service.publish_post(post_text, photos)
            results['vk'] = vk_id
            
            # Архивируем пост
            post_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            await self.file_service.archive_post(post_text, post_date)
            
            logger.info(f"Пост опубликован: {results}")
            return results
        
        except Exception as e:
            logger.error(f"Ошибка при публикации поста: {e}")
            raise
    
    async def refine_post(self, original_post: str, edits: str) -> str:
        """
        Перерабатывает пост с учетом правок
        
        Args:
            original_post: Исходный текст поста
            edits: Требуемые правки
            
        Returns:
            Переработанный текст поста
        """
        return await self.ai_service.refine_post(original_post, edits)

