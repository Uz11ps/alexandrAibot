"""Сервис для работы с постами"""
import logging
import time
from typing import List, Tuple, Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class PostService:
    """Сервис для генерации, редактирования и публикации постов"""
    
    def __init__(
        self,
        ai_service,
        telegram_service,
        vk_service,
        file_service,
        post_history_service=None
    ):
        self.ai_service = ai_service
        self.telegram_service = telegram_service
        self.vk_service = vk_service
        self.file_service = file_service
        self.post_history_service = post_history_service
    
    async def generate_monday_post(self) -> Tuple[str, List[str]]:
        """Генерирует пост для понедельника"""
        return await self._generate_post_by_day("monday", "понедельник")
    
    async def generate_tuesday_post(self) -> Tuple[str, List[str]]:
        """Генерирует пост для вторника"""
        return await self._generate_post_by_day("tuesday", "вторник")
    
    async def generate_wednesday_post(self) -> Tuple[str, List[str]]:
        """Генерирует пост для среды"""
        return await self._generate_post_by_day("wednesday", "среду")
    
    async def generate_thursday_post(self) -> Tuple[str, List[str]]:
        """Генерирует пост для четверга"""
        return await self._generate_post_by_day("thursday", "четверг")
    
    async def generate_friday_post(self) -> Tuple[str, List[str]]:
        """Генерирует пост для пятницы"""
        return await self._generate_post_by_day("friday", "пятницу")
    
    async def generate_saturday_post(self) -> Tuple[str, List[str]]:
        """Генерирует пост для субботы"""
        return await self._generate_post_by_day("saturday", "субботу")
    
    async def _generate_post_by_day(self, day: str, day_name_ru: str) -> Tuple[str, List[str]]:
        """Универсальный метод для генерации поста по дню недели"""
        logger.info(f"Начало генерации поста для '{day_name_ru}'")
        
        # Получаем неиспользованные фото
        photos = await self.file_service.get_unused_photos(limit=3)
        photo_paths = [str(p) for p in photos] if photos else []
        
        # Генерируем промпт для дня недели
        prompt = f"Создай отчетный пост о работах на объекте для {day_name_ru}"
        
        # Генерируем пост
        request_id = None
        if photo_paths:
            post_text, photo_paths, request_id = await self._generate_post_from_photo_and_prompt(
                photo_paths, prompt, admin_id=0, request_type=f"scheduled_{day}", day_of_week=day
            )
        else:
            # Получаем контекст из истории
            context_from_history = ""
            if self.post_history_service:
                context_from_history = self.post_history_service.get_context_for_generation(prompt)
            
            post_text = await self.ai_service.generate_post_text(
                prompt=prompt,
                context=context_from_history if context_from_history else None
            )
            from services.ai_service import markdown_to_html
            post_text = markdown_to_html(post_text)
            
            # Сохраняем в историю
            request_id = None
            if self.post_history_service:
                request_id = f"scheduled_{day}_{time.time()}"
                self.post_history_service.add_request(
                    request_id=request_id,
                    admin_id=0,  # Системный запрос
                    request_type=f"scheduled_{day}",
                    prompt=prompt,
                    photos_count=len(photo_paths),
                    day_of_week=day
                )
                self.post_history_service.update_request(
                    request_id=request_id,
                    generated_post=post_text,
                    status="pending"
                )
        
        logger.info(f"Пост для '{day_name_ru}' сгенерирован успешно")
        return post_text, photo_paths
    
    async def _generate_post_from_photo_and_prompt(
        self,
        photo_paths: List[str],
        prompt: str,
        admin_id: Optional[int] = None,
        request_type: str = "publish_now",
        day_of_week: Optional[str] = None
    ) -> Tuple[str, List[str], Optional[str]]:
        """
        Генерирует пост на основе фотографий и промпта
        
        Args:
            photo_paths: Список путей к фотографиям
            prompt: Промпт пользователя
            admin_id: ID администратора (для истории)
            request_type: Тип запроса (для истории)
            day_of_week: День недели (для запланированных постов)
            
        Returns:
            Кортеж (текст поста, список путей к фото, request_id)
        """
        logger.info(f"Генерация поста из {len(photo_paths)} фото с промптом: {prompt[:50]}...")
        
        # Получаем контекст из истории для улучшения генерации
        context_from_history = ""
        if self.post_history_service:
            context_from_history = self.post_history_service.get_context_for_generation(prompt)
        
        # Анализируем фото
        if len(photo_paths) == 1:
            photos_description = await self.ai_service.analyze_photo(photo_paths[0])
        else:
            photos_description = await self.ai_service.analyze_multiple_photos(photo_paths)
        
        # Добавляем контекст из истории к промпту
        enhanced_prompt = prompt
        if context_from_history:
            enhanced_prompt = f"{prompt}\n\nКонтекст из успешных похожих постов:\n{context_from_history}"
        
        # Определяем промпт на основе контента и запроса
        current_prompt_key = "generate_post"
        combined_text_for_detection = (prompt + photos_description).lower()
        if any(kw in combined_text_for_detection for kw in ["планировк", "чертеж", "план этажа", "экспликация", "план дома"]):
            current_prompt_key = "layout_description"
            logger.info(f"Обнаружена планировка в фото, используем промпт: {current_prompt_key}")

        # Генерируем пост
        post_text = await self.ai_service.generate_post_text(
            prompt=enhanced_prompt,
            photos_description=photos_description,
            context=context_from_history if context_from_history else None,
            prompt_key=current_prompt_key
        )
        
        # Применяем очистку и форматирование
        from services.ai_service import clean_ai_response, markdown_to_html
        post_text = clean_ai_response(post_text)
        post_text = markdown_to_html(post_text)
        
        # Обрезка убрана по просьбе заказчика, теперь генерируется полный текст
        
        # Сохраняем в историю
        request_id = None
        if self.post_history_service and admin_id:
            request_id = f"{request_type}_{time.time()}"
            self.post_history_service.add_request(
                request_id=request_id,
                admin_id=admin_id,
                request_type=request_type,
                prompt=prompt,
                photos_count=len(photo_paths),
                day_of_week=day_of_week
            )
            self.post_history_service.update_request(
                request_id=request_id,
                generated_post=post_text,
                status="pending"
            )
        
        logger.info(f"Пост сгенерирован: {len(post_text)} символов, request_id: {request_id}")
        return post_text, photo_paths, request_id
    
    async def refine_post(
        self,
        original_post: str,
        edits: str,
        request_id: Optional[str] = None
    ) -> str:
        """
        Перерабатывает пост с учетом правок
        
        Args:
            original_post: Исходный текст поста
            edits: Требуемые правки
            request_id: ID запроса в истории (опционально)
            
        Returns:
            Переработанный текст поста
        """
        logger.info(f"Переработка поста. Исходная длина: {len(original_post)} символов. Правки: {edits}")
        refined_post = await self.ai_service.refine_post(original_post, edits)
        logger.info(f"Пост переработан. Новая длина: {len(refined_post)} символов")
        
        # Обновляем историю
        if self.post_history_service and request_id:
            self.post_history_service.update_request(
                request_id=request_id,
                generated_post=refined_post,
                status="edited",
                edits=edits
            )
        
        return refined_post
    
    async def refine_post_now(
        self,
        original_post: str,
        edits: str,
        request_id: Optional[str] = None
    ) -> str:
        """
        Перерабатывает пост для функции "Опубликовать сейчас" с учетом правок
        
        Args:
            original_post: Исходный текст поста
            edits: Требуемые правки
            request_id: ID запроса в истории (опционально)
            
        Returns:
            Переработанный текст поста
        """
        logger.info(f"Переработка поста 'Опубликовать сейчас'. Исходная длина: {len(original_post)} символов. Правки: {edits}")
        refined_post = await self.ai_service.refine_post_now(original_post, edits)
        logger.info(f"Пост 'Опубликовать сейчас' переработан. Новая длина: {len(refined_post)} символов")
        
        # Обновляем историю
        if self.post_history_service and request_id:
            self.post_history_service.update_request(
                request_id=request_id,
                generated_post=refined_post,
                status="edited",
                edits=edits
            )
        
        return refined_post
    
    async def send_for_approval(
        self,
        post_text: str,
        photos: List[str],
        day_of_week: Optional[str] = None,
        triggered_by: Optional[str] = None
    ):
        """
        Отправляет пост на согласование администратору
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям
            day_of_week: День недели (опционально)
            triggered_by: Имя пользователя, инициировавшего генерацию (опционально)
        """
        logger.info(f"Отправка поста на согласование. Длина текста: {len(post_text)}, фото: {len(photos)}")
        
        # Отправляем через telegram_service
        await self.telegram_service.send_for_approval(post_text, photos, day_of_week=day_of_week, triggered_by=triggered_by)
    
    async def publish_approved_post(
        self,
        post_text: str,
        photos: List[str],
        request_id: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Публикует одобренный пост в Telegram и VK
        
        Args:
            post_text: Текст поста
            photos: Список путей к фотографиям
            request_id: ID запроса в истории (опционально)
            
        Returns:
            Словарь с результатами публикации
        """
        logger.info(f"Публикация поста. Длина текста: {len(post_text)}, фото: {len(photos)}")
        
        results = {}
        
        # Публикуем в Telegram
        try:
            telegram_result = await self.telegram_service.publish_post(post_text, photos)
            results['telegram'] = telegram_result or "Опубликовано"
        except Exception as e:
            logger.error(f"Ошибка при публикации в Telegram: {e}")
            results['telegram'] = f"Ошибка: {str(e)}"
        
        # Публикуем в VK
        try:
            vk_result = await self.vk_service.publish_post(post_text, photos)
            results['vk'] = vk_result or "Опубликовано"
        except Exception as e:
            logger.error(f"Ошибка при публикации в VK: {e}")
            results['vk'] = f"Ошибка: {str(e)}"
        
        # Обновляем историю
        if self.post_history_service and request_id:
            published_at = datetime.now().isoformat()
            self.post_history_service.update_request(
                request_id=request_id,
                final_post=post_text,
                status="published",
                published_at=published_at
            )
            
            # Автоматическая адаптация промптов на основе обратной связи
            # Адаптируем каждые 10 опубликованных постов
            self.post_history_service._update_stats()  # Обновляем статистику перед проверкой
            stats = self.post_history_service.stats
            published_count = stats.get("published_posts", 0)
            
            if published_count > 0 and published_count % 10 == 0:
                logger.info(f"Запуск автоматической адаптации промптов на основе обратной связи (опубликовано: {published_count})...")
                if hasattr(self.ai_service, 'prompt_config_service') and self.ai_service.prompt_config_service:
                    self.ai_service.prompt_config_service.auto_adapt_prompts(self.post_history_service)
        
        logger.info(f"Пост опубликован. Результаты: {results}")
        return results
