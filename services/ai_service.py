"""Сервис для работы с AI (OpenAI)"""
import logging
import asyncio
import re
from typing import Optional, List, Dict
from openai import AsyncOpenAI
import httpx
from config.settings import settings

logger = logging.getLogger(__name__)


def clean_ai_response(text: str) -> str:
    """
    Очищает ответ AI от комментариев и лишнего текста
    
    Args:
        text: Текст от AI
        
    Returns:
        Очищенный текст поста
    """
    # Удаляем комментарии AI в конце текста (начинающиеся с "---" или содержащие "Этот текст соответствует")
    lines = text.split('\n')
    cleaned_lines = []
    skip_rest = False
    
    for line in lines:
        # Пропускаем строки с комментариями AI
        if line.strip().startswith('---'):
            skip_rest = True
            break
        if 'Этот текст соответствует требованиям' in line or 'соответствует требованиям к длине' in line:
            skip_rest = True
            break
        if skip_rest:
            continue
        cleaned_lines.append(line)
    
    cleaned_text = '\n'.join(cleaned_lines).strip()
    
    # Удаляем оставшиеся комментарии в конце
    patterns_to_remove = [
        r'---.*$',
        r'Этот текст соответствует.*$',
        r'соответствует требованиям.*$',
        r'делая его визуально.*$',
        r'легким для восприятия.*$'
    ]
    
    for pattern in patterns_to_remove:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.MULTILINE | re.IGNORECASE)
    
    return cleaned_text.strip()


def markdown_to_html(text: str) -> str:
    """
    Конвертирует markdown форматирование в HTML для Telegram
    
    Args:
        text: Текст с markdown форматированием
        
    Returns:
        Текст с HTML форматированием
    """
    # Заменяем **текст** на <b>текст</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # Заменяем *текст* на <i>текст</i> (курсив, но только если не двойные звездочки)
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<i>\1</i>', text)
    
    # Заменяем `текст` на <code>текст</code>
    text = re.sub(r'`([^`]+?)`', r'<code>\1</code>', text)
    
    return text


class AIService:
    """Сервис для взаимодействия с OpenAI API"""
    
    def __init__(self, prompt_config_service=None):
        """
        Инициализация AI сервиса
        
        Args:
            prompt_config_service: Сервис для управления промптами (опционально)
        """
        self.prompt_config_service = prompt_config_service
        # Настройка прокси если указан
        http_client = None
        self.proxy_list = []
        self.current_proxy_index = 0
        
        # Подготовка списка API ключей для ротации
        self.api_keys = [settings.OPENAI_API_KEY]
        if settings.OPENAI_API_KEYS:
            additional_keys = [k.strip() for k in settings.OPENAI_API_KEYS.split(',')]
            self.api_keys.extend(additional_keys)
        self.current_api_key_index = 0
        
        logger.info(f"Доступно API ключей: {len(self.api_keys)}")
        
        if settings.OPENAI_PROXY_ENABLED and settings.OPENAI_PROXY_URL:
            # Поддерживаем несколько прокси через запятую
            proxy_urls = [p.strip() for p in settings.OPENAI_PROXY_URL.split(',')]
            # Нормализуем формат прокси (если указан как domain:port:user:pass, преобразуем в URL)
            normalized_proxies = []
            for proxy in proxy_urls:
                # Если прокси в формате domain:port:user:pass, преобразуем в http://user:pass@domain:port
                if proxy.count(':') == 3 and not proxy.startswith('http'):
                    parts = proxy.split(':')
                    if len(parts) == 4:
                        domain, port, username, password = parts
                        proxy = f"http://{username}:{password}@{domain}:{port}"
                        logger.info(f"Преобразован формат прокси: {domain}:{port} -> http://...@{domain}:{port}")
                normalized_proxies.append(proxy)
            self.proxy_list = normalized_proxies
            
            # Используем первый прокси по умолчанию
            proxy_url = normalized_proxies[0]
            logger.info(f"Использование прокси для OpenAI API: {proxy_url.split('@')[1] if '@' in proxy_url else 'скрыт'}")
            if len(normalized_proxies) > 1:
                logger.info(f"Доступно прокси для переключения: {len(normalized_proxies)}")
            
            http_client = httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0)  # Увеличенные таймауты для прокси
            )
        
        self.client = AsyncOpenAI(
            api_key=self.api_keys[0],
            http_client=http_client
        )
        self.model = settings.OPENAI_MODEL
        self.proxy_enabled = settings.OPENAI_PROXY_ENABLED
        self.proxy_url = settings.OPENAI_PROXY_URL
    
    def _switch_proxy(self):
        """Переключается на следующий прокси из списка"""
        if len(self.proxy_list) > 1:
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
            new_proxy = self.proxy_list[self.current_proxy_index]
            logger.info(f"Переключение на прокси: {new_proxy.split('@')[1] if '@' in new_proxy else 'скрыт'}")
            
            # Пересоздаем клиент с новым прокси
            http_client = httpx.AsyncClient(
                proxy=new_proxy,
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0)  # Увеличенные таймауты для прокси
            )
            self.client = AsyncOpenAI(
                api_key=self.api_keys[self.current_api_key_index],
                http_client=http_client
            )
            return True
        return False
    
    def _switch_api_key(self):
        """Переключается на следующий API ключ из списка и также переключает прокси"""
        if len(self.api_keys) > 1:
            self.current_api_key_index = (self.current_api_key_index + 1) % len(self.api_keys)
            new_key = self.api_keys[self.current_api_key_index]
            logger.info(f"Переключение на API ключ #{self.current_api_key_index + 1} из {len(self.api_keys)}")
            
            # При переключении ключа также переключаем прокси на следующий
            if self.proxy_enabled and len(self.proxy_list) > 1:
                self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
                new_proxy = self.proxy_list[self.current_proxy_index]
                logger.info(f"Также переключение на прокси: {new_proxy.split('@')[1] if '@' in new_proxy else 'скрыт'}")
            
            # Пересоздаем клиент с новым ключом и прокси
            http_client = None
            if self.proxy_enabled and self.proxy_list:
                current_proxy = self.proxy_list[self.current_proxy_index]
                http_client = httpx.AsyncClient(
                    proxy=current_proxy,
                    timeout=httpx.Timeout(300.0, connect=60.0, read=300.0)
                )
            
            self.client = AsyncOpenAI(
                api_key=new_key,
                http_client=http_client
            )
            return True
        return False
    
    async def generate_post_text(
        self,
        prompt: str,
        context: Optional[str] = None,
        photos_description: Optional[str] = None,
        use_post_now_prompt: bool = False
    ) -> str:
        """
        Генерирует текст поста на основе промпта и контекста
        
        Args:
            prompt: Основной промпт для генерации
            context: Дополнительный контекст (документы, черновики)
            photos_description: Описание фотографий от AI vision
            use_post_now_prompt: Если True, использует специальный системный промпт для "Опубликовать сейчас"
            
        Returns:
            Сгенерированный текст поста
        """
        # Получаем системный промпт из конфигурации или используем дефолтный
        if use_post_now_prompt:
            # Используем специальный промпт для "Опубликовать сейчас"
            system_prompt = self._get_post_now_system_prompt()
        elif self.prompt_config_service:
            system_prompt = self.prompt_config_service.get_prompt("generate_post", "system_prompt")
            if not system_prompt:
                logger.warning("Промпт generate_post не найден в конфигурации, используем дефолтный")
                system_prompt = self._get_default_system_prompt()
        else:
            # Дефолтный промпт если сервис не инициализирован
            system_prompt = self._get_default_system_prompt()
        
        # Если есть описание фото, добавляем специальные инструкции
        if photos_description:
            system_prompt += "\n\n**КРИТИЧЕСКИ ВАЖНО:** В запросе будет предоставлено описание фотографий, проанализированных AI. Ты ОБЯЗАН использовать ТОЛЬКО информацию из этого описания для создания поста. НЕ придумывай информацию, которой нет в описании фотографий. НЕ используй шаблонные тексты о других объектах. Пост должен точно отражать то, что изображено на фотографиях."
        
        user_prompt = prompt
        if context:
            user_prompt += f"\n\nКонтекст:\n{context}"
        if photos_description:
            user_prompt += f"\n\nОписание фотографий:\n{photos_description}"
        
        try:
            logger.info(f"Отправка запроса на генерацию текста в OpenAI API (модель: {self.model})")
            logger.debug(f"Длина промпта: {len(user_prompt)} символов")
            
            # Устанавливаем таймаут для запроса (увеличен для прокси)
            timeout_seconds = 180.0 if self.proxy_enabled else 60.0
            logger.info(f"Таймаут запроса: {timeout_seconds} секунд")
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=2000
                ),
                timeout=timeout_seconds
            )
            
            result = response.choices[0].message.content.strip()
            
            # Очищаем от комментариев AI
            result = clean_ai_response(result)
            
            # Конвертируем markdown в HTML
            result = markdown_to_html(result)
            
            logger.info(f"Генерация текста завершена успешно (длина: {len(result)} символов)")
            return result
        
        except asyncio.TimeoutError:
            timeout_used = 180.0 if self.proxy_enabled else 60.0
            logger.error(f"Таймаут при генерации текста (превышено {timeout_used} секунд)")
            # Создаем более качественный fallback текст
            fallback_text = "📊 Отчет по объектам компании «Археон»\n\n"
            
            # Извлекаем информацию из контекста если есть
            if photos_description and "Фотография со строительного объекта" in photos_description:
                fallback_text += "На этой неделе мы продолжаем работу над текущими объектами.\n\n"
            elif context:
                # Пытаемся извлечь полезную информацию из контекста
                fallback_text += f"{context[:300]}\n\n"
            
            fallback_text += (
                "📸 Фотографии объектов прикреплены.\n\n"
                "Наши специалисты работают над качественным выполнением всех работ, "
                "соблюдая сроки и стандарты качества.\n\n"
                "⚠️ Примечание: Из-за технических ограничений детальный анализ через AI временно недоступен. "
                "Для получения полного отчета свяжитесь с нашими специалистами."
            )
            return fallback_text
        
        except Exception as e:
            error_str = str(e)
            logger.error(f"Ошибка при генерации текста: {e}")
            
            # Проверяем таймаут в сообщении об ошибке
            is_timeout = (
                "timeout" in error_str.lower() or 
                "timed out" in error_str.lower() or
                "Request timed out" in error_str
            )
            
            # Пробуем переключить прокси или API ключ при ошибке подключения или таймауте
            retry_success = False
            
            # Пробуем несколько прокси подряд (максимум 5 попыток или все доступные)
            max_proxy_retries = min(5, len(self.proxy_list)) if self.proxy_enabled else 0
            for proxy_attempt in range(max_proxy_retries):
                if self.proxy_enabled and (is_timeout or "403" in error_str or "connection" in error_str.lower()):
                    if self._switch_proxy():
                        logger.info(f"Попытка {proxy_attempt + 1}/{max_proxy_retries} с другим прокси...")
                        try:
                            timeout_seconds = 180.0
                            response = await asyncio.wait_for(
                                self.client.chat.completions.create(
                                    model=self.model,
                                    messages=[
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": user_prompt}
                                    ],
                                    temperature=0.7,
                                    max_tokens=2000
                                ),
                                timeout=timeout_seconds
                            )
                            retry_success = True
                            return response.choices[0].message.content.strip()
                        except asyncio.TimeoutError:
                            logger.warning(f"Таймаут при попытке {proxy_attempt + 1} с прокси")
                            if proxy_attempt < max_proxy_retries - 1:
                                continue  # Пробуем следующий прокси
                        except Exception as retry_error:
                            logger.warning(f"Ошибка при попытке {proxy_attempt + 1} с прокси: {retry_error}")
                            if proxy_attempt < max_proxy_retries - 1:
                                continue  # Пробуем следующий прокси
                    else:
                        break  # Нет больше прокси для переключения
            
            # Если прокси не помогли, пробуем переключить API ключ (он также переключит прокси)
            # Пробуем несколько комбинаций ключ+прокси (максимум 2 попытки)
            max_key_retries = min(2, len(self.api_keys)) if len(self.api_keys) > 1 else 0
            for key_attempt in range(max_key_retries):
                if not retry_success and (is_timeout or "403" in error_str or "401" in error_str or "rate limit" in error_str.lower() or "connection" in error_str.lower()):
                    if self._switch_api_key():
                        logger.info(f"Попытка {key_attempt + 1}/{max_key_retries} с другим API ключом и прокси...")
                        try:
                            timeout_seconds = 180.0 if self.proxy_enabled else 60.0
                            response = await asyncio.wait_for(
                                self.client.chat.completions.create(
                                    model=self.model,
                                    messages=[
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": user_prompt}
                                    ],
                                    temperature=0.7,
                                    max_tokens=2000
                                ),
                                timeout=timeout_seconds
                            )
                            return response.choices[0].message.content.strip()
                        except asyncio.TimeoutError:
                            timeout_used = 180.0 if self.proxy_enabled else 60.0
                            logger.warning(f"Таймаут при попытке {key_attempt + 1} с другим ключом (превышено {timeout_used} секунд)")
                            if key_attempt < max_key_retries - 1:
                                continue  # Пробуем следующую комбинацию
                        except Exception as retry_error:
                            logger.warning(f"Ошибка при попытке {key_attempt + 1} с другим API ключом: {retry_error}")
                            if key_attempt < max_key_retries - 1:
                                continue  # Пробуем следующую комбинацию
                    else:
                        break  # Нет больше ключей для переключения
            
            # Финальная попытка: пробуем без прокси, если все прокси не работали
            if not retry_success and self.proxy_enabled:
                logger.info("Все прокси не работают. Пробуем финальную попытку без прокси...")
                try:
                    # Создаем клиент без прокси
                    client_without_proxy = AsyncOpenAI(
                        api_key=self.api_keys[self.current_api_key_index]
                    )
                    timeout_seconds = 60.0  # Обычный таймаут без прокси
                    response = await asyncio.wait_for(
                        client_without_proxy.chat.completions.create(
                            model=self.model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ],
                            temperature=0.7,
                            max_tokens=2000
                        ),
                        timeout=timeout_seconds
                    )
                    logger.info("Успешный запрос без прокси!")
                    return response.choices[0].message.content.strip()
                except Exception as final_error:
                    logger.warning(f"Финальная попытка без прокси также не удалась: {final_error}")
            
            # Если ничего не помогло, создаем fallback текст
            fallback_text = "📊 Отчет по объектам компании «Археон»\n\n"
            
            if photos_description and "Фотография со строительного объекта" in photos_description:
                fallback_text += "На этой неделе мы продолжаем работу над текущими объектами.\n\n"
            elif context:
                fallback_text += f"{context[:300]}\n\n"
            
            fallback_text += (
                "📸 Фотографии объектов прикреплены.\n\n"
                "Наши специалисты работают над качественным выполнением всех работ, "
                "соблюдая сроки и стандарты качества.\n\n"
                "⚠️ Примечание: Из-за технических ограничений детальный анализ через AI временно недоступен. "
                "Для получения полного отчета свяжитесь с нашими специалистами."
            )
            return fallback_text
            
            # Проверяем ошибку региона
            if "unsupported_country_region_territory" in error_str or "403" in error_str:
                logger.warning("OpenAI API недоступен в вашем регионе. Используем fallback.")
                # Создаем более качественный fallback текст
                fallback_text = "📊 Отчет по объектам компании «Археон»\n\n"
                
                if photos_description and "Фотография со строительного объекта" in photos_description:
                    fallback_text += "На этой неделе мы продолжаем работу над текущими объектами.\n\n"
                elif context:
                    fallback_text += f"{context[:300]}\n\n"
                
                fallback_text += (
                    "📸 Фотографии объектов прикреплены.\n\n"
                    "Наши специалисты работают над качественным выполнением всех работ, "
                    "соблюдая сроки и стандарты качества.\n\n"
                    "⚠️ Примечание: OpenAI API временно недоступен. "
                    "Для получения детального отчета свяжитесь с нашими специалистами."
                )
                return fallback_text
            
            raise
    
    async def analyze_photo(self, photo_path: str) -> str:
        """
        Анализирует фотографию и возвращает описание
        
        Args:
            photo_path: Путь к файлу фотографии
            
        Returns:
            Описание содержимого фотографии
        """
        import base64
        from pathlib import Path
        
        # Подготавливаем данные перед блоком try для использования в обработке ошибок
        # Оптимизируем изображение перед отправкой
        try:
            from PIL import Image
            import io
            
            with Image.open(photo_path) as img:
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Уменьшаем размер если изображение слишком большое
                max_size = 1024  # Максимальный размер по большей стороне
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    logger.info(f"Изображение уменьшено до {img.size}")
                
                # Сохраняем в буфер с оптимизацией
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85, optimize=True)
                image_data = buffer.getvalue()
                logger.info(f"Размер изображения после оптимизации: {len(image_data)} байт")
        except Exception as e:
            logger.warning(f"Не удалось оптимизировать изображение, используем оригинал: {e}")
            with open(photo_path, "rb") as photo_file:
                image_data = photo_file.read()
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        logger.info(f"Размер base64 изображения: {len(base64_image)} символов")
        
        # Определяем MIME тип по расширению
        ext = Path(photo_path).suffix.lower()
        mime_type = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }.get(ext, 'image/jpeg')
        
        photo_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": self._get_photo_analysis_prompt()
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}"
                    }
                }
            ]
        }
        
        try:
            logger.info(f"Отправка запроса на анализ фотографии в OpenAI API (модель: gpt-4o)")
            logger.info(f"Размер изображения в base64: {len(base64_image)} символов")
            
            # Устанавливаем таймаут для запроса (увеличен для прокси)
            timeout_seconds = 180.0 if self.proxy_enabled else 60.0
            logger.info(f"Таймаут запроса: {timeout_seconds} секунд")
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="gpt-4o",  # Используем актуальную модель для анализа изображений
                    messages=[photo_message],
                    max_tokens=500
                ),
                timeout=timeout_seconds
            )
            
            result = response.choices[0].message.content.strip()
            logger.info(f"Анализ фотографии завершен успешно (длина ответа: {len(result)} символов)")
            return result
        
        except asyncio.TimeoutError:
            timeout_used = 180.0 if self.proxy_enabled else 60.0
            logger.error(f"Таймаут при анализе фотографии (превышено {timeout_used} секунд)")
            from pathlib import Path
            file_name = Path(photo_path).name
            # Возвращаем более информативное описание
            return f"Фотография со строительного объекта: {file_name}. На фотографии запечатлен текущий этап работ на объекте компании «Археон»."
    
    async def analyze_multiple_photos(self, photo_paths: List[str]) -> str:
        """
        Анализирует несколько фотографий и возвращает объединенное описание
        
        Args:
            photo_paths: Список путей к файлам фотографий
            
        Returns:
            Объединенное описание содержимого всех фотографий
        """
        if not photo_paths:
            return "Фотографии не предоставлены."
        
        if len(photo_paths) == 1:
            # Если одна фотография, используем обычный метод анализа
            return await self.analyze_photo(photo_paths[0])
        
        logger.info(f"Начинаем анализ {len(photo_paths)} фотографий")
        
        # Анализируем каждую фотографию отдельно
        descriptions = []
        for i, photo_path in enumerate(photo_paths, 1):
            try:
                logger.info(f"Анализ фотографии {i}/{len(photo_paths)}: {photo_path}")
                description = await self.analyze_photo(photo_path)
                descriptions.append(f"Фотография {i}: {description}")
            except Exception as e:
                logger.error(f"Ошибка при анализе фотографии {i}: {e}")
                from pathlib import Path
                file_name = Path(photo_path).name
                descriptions.append(f"Фотография {i}: Фотография со строительного объекта: {file_name}. [Ошибка при анализе: {str(e)}]")
        
        # Объединяем описания
        combined_description = "\n\n".join(descriptions)
        logger.info(f"Анализ всех фотографий завершен. Общая длина описания: {len(combined_description)} символов")
        
        return combined_description
    
    async def analyze_video(self, video_path: str, frames_count: int = 12) -> str:
        """
        Анализирует видео, извлекая ключевые кадры и анализируя их через AI
        
        Args:
            video_path: Путь к файлу видео
            frames_count: Количество кадров для анализа (по умолчанию 12 для более детального анализа)
            
        Returns:
            Объединенное описание содержимого видео на основе анализа кадров
        """
        try:
            import cv2
            import tempfile
            from pathlib import Path
            
            logger.info(f"Начинаем анализ видео: {video_path}")
            
            # Открываем видео
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Не удалось открыть видео: {video_path}")
                return f"Видео со строительного объекта. [Ошибка: не удалось открыть видео]"
            
            # Получаем общее количество кадров и FPS
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            logger.info(f"Видео: {total_frames} кадров, {fps:.2f} FPS, длительность ~{duration:.2f} секунд")
            
            # Вычисляем шаг для равномерного распределения кадров
            if total_frames < frames_count:
                frame_indices = list(range(total_frames))
            else:
                step = total_frames // (frames_count + 1)
                frame_indices = [step * (i + 1) for i in range(frames_count)]
            
            logger.info(f"Будем анализировать кадры: {frame_indices}")
            
            # Извлекаем и анализируем кадры
            frame_descriptions = []
            temp_dir = Path(tempfile.gettempdir()) / "video_frames"
            temp_dir.mkdir(exist_ok=True)
            
            for i, frame_idx in enumerate(frame_indices):
                try:
                    # Переходим к нужному кадру
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                    ret, frame = cap.read()
                    
                    if not ret:
                        logger.warning(f"Не удалось прочитать кадр {frame_idx}")
                        continue
                    
                    # Сохраняем кадр во временный файл
                    frame_path = temp_dir / f"frame_{i}_{frame_idx}.jpg"
                    cv2.imwrite(str(frame_path), frame)
                    
                    # Анализируем кадр через AI с улучшенным промптом для видео
                    logger.info(f"Анализ кадра {i+1}/{len(frame_indices)} (кадр {frame_idx}/{total_frames})")
                    frame_description = await self.analyze_video_frame(str(frame_path), i+1, len(frame_indices))
                    
                    # Добавляем временную метку
                    timestamp = frame_idx / fps if fps > 0 else 0
                    frame_descriptions.append(f"Кадр {i+1} (время {timestamp:.1f}с): {frame_description}")
                    
                    # Удаляем временный файл
                    try:
                        frame_path.unlink()
                    except Exception as e:
                        logger.warning(f"Не удалось удалить временный файл {frame_path}: {e}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при обработке кадра {frame_idx}: {e}")
                    continue
            
            cap.release()
            
            if not frame_descriptions:
                logger.warning("Не удалось проанализировать ни один кадр")
                return f"Видео со строительного объекта. [Ошибка: не удалось извлечь кадры]"
            
            # Объединяем описания кадров
            combined_description = "\n\n".join(frame_descriptions)
            logger.info(f"Анализ видео завершен. Проанализировано кадров: {len(frame_descriptions)}")
            
            return combined_description
            
        except ImportError:
            logger.error("opencv-python не установлен. Установите его: pip install opencv-python-headless")
            return f"Видео со строительного объекта. [Ошибка: библиотека для работы с видео не установлена]"
        except Exception as e:
            logger.error(f"Ошибка при анализе видео: {e}", exc_info=True)
            from pathlib import Path
            file_name = Path(video_path).name
            return f"Видео со строительного объекта: {file_name}. [Ошибка при анализе: {str(e)}]"
    
    async def analyze_video_frame(self, frame_path: str, frame_number: int, total_frames: int) -> str:
        """
        Анализирует один кадр из видео с улучшенным промптом и более сильной моделью
        
        Args:
            frame_path: Путь к файлу кадра
            frame_number: Номер кадра (для контекста)
            total_frames: Общее количество кадров (для контекста)
            
        Returns:
            Детальное описание кадра
        """
        import base64
        from pathlib import Path
        
        # Оптимизируем изображение перед отправкой
        try:
            from PIL import Image
            import io
            
            with Image.open(frame_path) as img:
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Уменьшаем размер если изображение слишком большое
                max_size = 1024  # Максимальный размер по большей стороне
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Сохраняем в буфер с оптимизацией
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85, optimize=True)
                image_data = buffer.getvalue()
        except Exception as e:
            logger.warning(f"Не удалось оптимизировать изображение кадра, используем оригинал: {e}")
            with open(frame_path, "rb") as frame_file:
                image_data = frame_file.read()
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # Определяем MIME тип
        ext = Path(frame_path).suffix.lower()
        mime_type = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }.get(ext, 'image/jpeg')
        
        # Улучшенный промпт для анализа кадров видео
        video_frame_prompt = """Проанализируй этот кадр из видео со строительного объекта компании "Археон".

ВНИМАТЕЛЬНО изучи изображение и опиши:
1. **Что происходит на объекте**: конкретные действия, процессы, работы
2. **Этап строительства**: на каком этапе находится проект (подготовка, фундамент, стены, кровля, отделка и т.д.)
3. **Используемые материалы и технологии**: какие материалы видны, какие технологии применяются
4. **Детали и особенности**: важные детали, которые могут быть интересны для поста
5. **Проблемы или сложности**: если видны какие-то проблемы, сложности, особенности участка
6. **Качество работ**: оценка качества выполнения работ (если применимо)

Будь максимально детальным и конкретным. Опиши все важные элементы, которые видны на кадре. Это кадр из видео, поэтому важно зафиксировать все детали для создания полного описания процесса."""
        
        photo_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": video_frame_prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}"
                    }
                }
            ]
        }
        
        try:
            # Используем более новую модель gpt-4o с увеличенным max_tokens для детального анализа
            model_name = "gpt-4o-2024-11-20"  # Более новая версия с улучшенным reasoning
            logger.info(f"Отправка запроса на анализ кадра {frame_number}/{total_frames} в OpenAI API (модель: {model_name})")
            
            timeout_seconds = 300.0 if self.proxy_enabled else 120.0  # Увеличенный таймаут для детального анализа
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=model_name,
                    messages=[photo_message],
                    max_tokens=1000,  # Увеличенный лимит для более детального описания
                    temperature=0.3  # Более детерминированный ответ для точности
                ),
                timeout=timeout_seconds
            )
            
            result = response.choices[0].message.content.strip()
            logger.info(f"Анализ кадра {frame_number} завершен успешно (длина ответа: {len(result)} символов)")
            return result
        
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при анализе кадра {frame_number}")
            # Fallback на обычный анализ
            return await self.analyze_photo(frame_path)
        
        except Exception as e:
            logger.error(f"Ошибка при анализе кадра {frame_number}: {e}")
            # Fallback на обычный анализ
            return await self.analyze_photo(frame_path)
    
    async def analyze_video_frame(self, frame_path: str, frame_number: int, total_frames: int) -> str:
        """
        Анализирует один кадр из видео с улучшенным промптом и более сильной моделью
        
        Args:
            frame_path: Путь к файлу кадра
            frame_number: Номер кадра (для контекста)
            total_frames: Общее количество кадров (для контекста)
            
        Returns:
            Детальное описание кадра
        """
        import base64
        from pathlib import Path
        
        # Оптимизируем изображение перед отправкой
        try:
            from PIL import Image
            import io
            
            with Image.open(frame_path) as img:
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Уменьшаем размер если изображение слишком большое
                max_size = 1024  # Максимальный размер по большей стороне
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Сохраняем в буфер с оптимизацией
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85, optimize=True)
                image_data = buffer.getvalue()
        except Exception as e:
            logger.warning(f"Не удалось оптимизировать изображение кадра, используем оригинал: {e}")
            with open(frame_path, "rb") as frame_file:
                image_data = frame_file.read()
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # Определяем MIME тип
        ext = Path(frame_path).suffix.lower()
        mime_type = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }.get(ext, 'image/jpeg')
        
        # Улучшенный промпт для анализа кадров видео
        video_frame_prompt = """Проанализируй этот кадр из видео со строительного объекта компании "Археон".

ВНИМАТЕЛЬНО изучи изображение и опиши:
1. **Что происходит на объекте**: конкретные действия, процессы, работы
2. **Этап строительства**: на каком этапе находится проект (подготовка, фундамент, стены, кровля, отделка и т.д.)
3. **Используемые материалы и технологии**: какие материалы видны, какие технологии применяются
4. **Детали и особенности**: важные детали, которые могут быть интересны для поста
5. **Проблемы или сложности**: если видны какие-то проблемы, сложности, особенности участка
6. **Качество работ**: оценка качества выполнения работ (если применимо)

Будь максимально детальным и конкретным. Опиши все важные элементы, которые видны на кадре. Это кадр из видео, поэтому важно зафиксировать все детали для создания полного описания процесса."""
        
        photo_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": video_frame_prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}"
                    }
                }
            ]
        }
        
        try:
            # Используем более новую модель gpt-4o с увеличенным max_tokens для детального анализа
            model_name = "gpt-4o-2024-11-20"  # Более новая версия с улучшенным reasoning
            logger.info(f"Отправка запроса на анализ кадра {frame_number}/{total_frames} в OpenAI API (модель: {model_name})")
            
            timeout_seconds = 300.0 if self.proxy_enabled else 120.0  # Увеличенный таймаут для детального анализа
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=model_name,
                    messages=[photo_message],
                    max_tokens=1000,  # Увеличенный лимит для более детального описания
                    temperature=0.3  # Более детерминированный ответ для точности
                ),
                timeout=timeout_seconds
            )
            
            result = response.choices[0].message.content.strip()
            logger.info(f"Анализ кадра {frame_number} завершен успешно (длина ответа: {len(result)} символов)")
            return result
        
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при анализе кадра {frame_number}")
            # Fallback на обычный анализ
            return await self.analyze_photo(frame_path)
        
        except Exception as e:
            logger.error(f"Ошибка при анализе кадра {frame_number}: {e}")
            # Fallback на обычный анализ
            return await self.analyze_photo(frame_path)
    
    def _get_post_now_system_prompt(self) -> str:
        """
        Возвращает специальный системный промпт для функции "Опубликовать сейчас"
        
        Returns:
            Текст системного промпта для генерации профессионального описания строительных работ ИЖС
        """
        # Сначала проверяем конфигурацию промптов
        if self.prompt_config_service:
            prompt = self.prompt_config_service.get_prompt("post_now", "system_prompt")
            if prompt:
                return prompt
        
        # Дефолтный промпт если не найден в конфигурации
        return """СИСТЕМНЫЙ ПРОМТ ДЛЯ AI CHAT GPT
Генерация профессионального описания строительных работ ИЖС по фото

Роль модели
Ты – SMM-специалист и инженер-строитель в одной роли, работающий от первого лица компании, которая профессионально занимается индивидуальным жилищным строительством.
Твоя задача – по одному или нескольким фото со строительной площадки генерировать экспертный, технически грамотный и коммерчески сильный текст для публикации в социальных сетях, сайте или портфолио компании.

Ты не используешь абстрактные формулировки, не пишешь «в общем» и не уходишь в рекламную воду.
Каждое утверждение должно логически вытекать из того, что реально видно на фото, и соответствовать строительным нормам РФ.

ОБЩИЕ ПРАВИЛА ГЕНЕРАЦИИ ТЕКСТА

Писать строго от первого лица
Используй формулировки:
– «Мы выполняем»,
– «Мы завершаем этап»,
– «Мы применяем»,
– «Мы работаем строго в соответствии».
Запрещены обороты вида «в наших объектах», «на данном объекте выполняется» без указания субъекта.

Строгая структура – 4 абзаца
Всегда формируй текст из четырёх логически завершённых абзацев, без списков и подзаголовков.

Каждый абзац – 2–5 предложений
Все предложения должны содержать не менее 6 слов, текст должен читаться как цельный инженерно-маркетинговый материал.

Никаких фантазий
Если параметр или материал нельзя обоснованно определить по фото, используй только те характеристики, которые логично и допустимо указать исходя из визуального этапа и нормативной практики.

Один факт – одно значение
Если указан шаг, толщина, плотность, сечение или материал, он должен быть конкретным и единым по всему тексту.
Запрещено писать диапазоны, альтернативы и «от–до».

СТРУКТУРА АБЗАЦЕВ
АБЗАЦ 1 – ОПИСАНИЕ ЭТАПА РАБОТ ПО ФОТО

В первом абзаце ты:

– Определяешь конкретный этап строительства ИЖС, который виден на фото
– Связываешь изображение с технологическим этапом
– Используешь профессиональную строительную терминологию
– Указываешь фактически видимые конструктивные элементы

Примеры этапов:
– устройство фундамента
– армирование монолитных конструкций
– возведение несущих стен
– монтаж перекрытий
– устройство стропильной системы
– утепление ограждающих конструкций
– прокладка инженерных сетей
– черновая или чистовая отделка

Обязательно:
– указать материалы, которые видны на фото
– указать геометрию или сечение, если это логично
– связать фото с логикой строительного процесса

Запрещено:
– писать «что подтверждается», «что говорит о»
– делать выводы без визуального основания
– использовать обтекаемые формулировки

АБЗАЦ 2 – ТЕХНИЧЕСКИЕ АКЦЕНТЫ И НОРМЫ

Во втором абзаце ты:

– Объясняешь, на что именно важно обратить внимание на этом этапе
– Раскрываешь инженерную логику конструкции
– Указываешь роль каждого ключевого слоя или элемента
– Обязательно привязываешь решения к нормам

Ты должен логично упомянуть:
– СП, СНиП или ГОСТ (без перегруза, но осмысленно)
– теплотехнические, прочностные или эксплуатационные требования
– корректную работу узлов, слоёв или систем

Если по фото видно кровлю:
– обязательно упомяни пароизоляцию и диффузионную мембрану
– объясни, зачем они нужны и как работают вместе

Если это фундамент:
– упомяни основание, армирование, защитный слой бетона

Если стены:
– теплотехнический контур и перевязку

АБЗАЦ 3 – ТИПОВЫЕ ОШИБКИ И ИХ ПОСЛЕДСТВИЯ

В третьем абзаце ты:

– Описываешь частые ошибки именно на этом этапе
– Показываешь, к чему они приводят в эксплуатации
– Связываешь ошибки напрямую с тем, что видно на фото

Ошибки должны быть:
– реальными
– инженерно обоснованными
– без эмоциональной или рекламной окраски

Примеры:
– использование сырой древесины
– отсутствие мембран
– неправильный шаг конструкций
– заниженная толщина утепления
– нарушение технологии укладки

АБЗАЦ 4 – ПОЗИЦИЯ КОМПАНИИ И МАТЕРИАЛЫ

В четвёртом абзаце ты:

– Подводишь итог от лица компании
– Подтверждаешь соблюдение нормативов
– Чётко перечисляешь конкретные материалы, логично вытекающие из абзаца 3
– Подчёркиваешь инженерный подход, а не маркетинг

Обязательно:
– писать «Мы работаем строго в соответствии со СНиП, СП и действующими нормативами»
– перечислять материалы без альтернатив
– связывать их с долговечностью и эксплуатацией

Запрещено:
– общие рекламные лозунги
– слова «качественно», «надёжно» без инженерного смысла
– обезличенные формулировки

СТИЛЬ И ЯЗЫК

– Стиль деловой, инженерный, уверенный
– Без смайлов либо не более одного при явной уместности
– Без поэтики и псевдодрамы
– Без канцелярита
– Без разговорных оборотов

РЕЗУЛЬТАТ РАБОТЫ БОТА

На выходе ты всегда формируешь:

– 4 абзаца
– Профессиональный SMM-пост
– Привязанный к реальному этапу ИЖС
– Понятный заказчику и уважительный для инженера
– Готовый к публикации без правок"""

    def _get_default_system_prompt(self) -> str:
        """
        Возвращает дефолтный системный промпт для генерации постов
        
        Returns:
            Текст системного промпта
        """
        return """Ты профессиональный копирайтер для строительной компании "Археон".
Твоя задача - создавать короткие, яркие и информативные посты для социальных сетей.

КРИТИЧЕСКИ ВАЖНЫЕ ТРЕБОВАНИЯ:
**СТРОГОЕ ОГРАНИЧЕНИЕ ДЛИНЫ: Текст поста НЕ ДОЛЖЕН превышать 900 символов (включая пробелы и эмодзи). Это абсолютное ограничение. Посты длиннее 900 символов будут отклонены системой.**
- Используй много эмодзи для визуального оформления (минимум 1 эмодзи на каждые 2-3 предложения)
- Посты должны быть КОРОТКИМИ и ёмкими (максимум 120-150 слов)
- Структурируй текст короткими абзацами (по 2-3 предложения)
- Используй эмодзи для выделения ключевых моментов: 📊 📸 🏗️ ✅ ⚠️ 💡 📝 и другие
- Стиль: дружелюбный, современный, с эмодзи для привлечения внимания
- Избегай длинных предложений и сложных конструкций
- НЕ добавляй комментарии о соответствии требованиям или мета-описания
- Возвращай ТОЛЬКО текст поста, без дополнительных комментариев
- ПЕРЕД ОТПРАВКОЙ проверь длину текста - он должен быть строго до 900 символов"""
    
    def _get_photo_analysis_prompt(self) -> str:
        """
        Получает промпт для анализа фотографий
        
        Returns:
            Текст промпта для анализа фотографий
        """
        if self.prompt_config_service:
            prompt = self.prompt_config_service.get_prompt("analyze_photo", "user_prompt")
            if prompt:
                return prompt
        
        # Дефолтный промпт
        return """Проанализируй эту фотографию со строительного объекта.
Опиши что на ней изображено: тип работ, этап строительства, особенности участка,
видимые проблемы или сложности, используемые материалы и технологии.
Будь конкретным и профессиональным."""
    
    async def extract_text_from_document(self, document_path: str) -> str:
        """
        Извлекает текст из PDF документа
        
        Args:
            document_path: Путь к PDF файлу
            
        Returns:
            Извлеченный текст
        """
        # TODO: Реализовать извлечение текста из PDF
        # Пока возвращаем заглушку
        logger.warning("Извлечение текста из PDF пока не реализовано")
        return ""
    
    async def refine_post_now(self, original_post: str, edits: str) -> str:
        """
        Перерабатывает пост для функции "Опубликовать сейчас" с учетом правок
        Использует специальный промпт, который сохраняет структуру из 4 абзацев
        
        Args:
            original_post: Исходный текст поста
            edits: Требуемые правки
            
        Returns:
            Переработанный текст поста
        """
        # Импортируем функции для работы с абзацами
        from services.text_utils import (
            extract_paragraph_number, find_paragraph_by_keywords, 
            find_paragraphs_by_keywords, remove_paragraph_programmatically,
            remove_paragraphs_programmatically, replace_paragraph_programmatically,
            insert_paragraph_programmatically
        )
        
        # Убираем заголовки из текста перед обработкой
        cleaned_post = original_post
        # Убираем заголовки типа "📝 Черновик поста для согласования (после правок):"
        header_patterns = [
            r'📝\s*Черновик поста для согласования[^:]*:?\s*\n*',
            r'📝\s*Полный текст ниже ⬇️\s*\n*',
            r'Черновик поста для согласования[^:]*:?\s*\n*',
        ]
        for pattern in header_patterns:
            cleaned_post = re.sub(pattern, '', cleaned_post, flags=re.IGNORECASE)
        
        # Если текст изменился, логируем это
        if cleaned_post != original_post:
            logger.info(f"Убраны заголовки из текста перед обработкой. Исходная длина: {len(original_post)}, очищенная длина: {len(cleaned_post)}")
            original_post = cleaned_post.strip()
        
        # Разбиваем исходный пост на абзацы
        paragraphs = [p.strip() for p in original_post.split('\n\n') if p.strip()]
        
        # Проверяем, указан ли конкретный абзац для редактирования
        paragraph_num = extract_paragraph_number(edits)
        
        # Проверяем, просят ли удалить абзац
        delete_keywords = ['убери', 'удали', 'убрать', 'удалить', 'исключи', 'исключить']
        is_delete_request = any(keyword in edits.lower() for keyword in delete_keywords)
        
        # Проверяем, просят ли удалить несколько абзацев (есть кавычки или несколько блоков)
        is_multiple_delete = False
        paragraph_nums_to_delete = []
        
        if is_delete_request:
            # Извлекаем ключевые слова из запроса
            keywords_text = edits.lower()
            for kw in delete_keywords:
                keywords_text = keywords_text.replace(kw, '')
            keywords_text = keywords_text.replace('блок', '').replace('абзац', '').replace('пожалуйста', '').replace('блоки', '').strip()
            
            # Пытаемся найти несколько блоков (в кавычках или разделенных запятыми/переносами)
            import re
            # Ищем текст в кавычках
            quoted_texts = re.findall(r'["""]([^"""]+)["""]', edits)
            if quoted_texts:
                # Найдены тексты в кавычках - ищем абзацы по ним
                paragraph_nums_to_delete = find_paragraphs_by_keywords(original_post, quoted_texts)
                is_multiple_delete = len(paragraph_nums_to_delete) > 1
            else:
                # Пытаемся разбить по запятым или другим разделителям
                # Улучшенный парсинг: ищем фразы в кавычках (одинарных или двойных) или разделенные запятыми
                parts = []
                
                # Сначала пытаемся найти фразы в кавычках (одинарных или двойных)
                quoted_matches = re.findall(r'["""]([^"""]+)["""]', edits)
                if quoted_matches:
                    parts = quoted_matches
                    logger.info(f"Найдены фразы в кавычках: {parts}")
                else:
                    # Разбиваем по запятым, но учитываем что могут быть кавычки
                    # Убираем слова удаления и разбиваем
                    temp_text = keywords_text
                    # Простое разбиение по запятым
                    parts = [p.strip() for p in re.split(r'[,]', temp_text) if p.strip() and len(p.strip()) > 3]
                
                if len(parts) > 1:
                    paragraph_nums_to_delete = find_paragraphs_by_keywords(original_post, parts)
                    is_multiple_delete = len(paragraph_nums_to_delete) > 1
                    logger.info(f"Найдены абзацы для удаления по частям ({len(parts)} частей): {paragraph_nums_to_delete}")
                elif len(parts) == 1:
                    # Один блок
                    found_num = find_paragraph_by_keywords(original_post, parts[0])
                    if found_num:
                        paragraph_nums_to_delete = [found_num]
                        paragraph_num = found_num
                        logger.info(f"Найден абзац для удаления: {found_num}")
                else:
                    # Пытаемся найти по всему тексту
                    if keywords_text:
                        found_num = find_paragraph_by_keywords(original_post, keywords_text)
                        if found_num:
                            paragraph_nums_to_delete = [found_num]
                            paragraph_num = found_num
                            logger.info(f"Найден абзац для удаления по ключевым словам: {found_num}")
        
        # Если это запрос на удаление и мы нашли абзац(ы) - удаляем программно без AI
        if is_delete_request and paragraph_nums_to_delete:
            logger.info(f"Удаление абзацев {paragraph_nums_to_delete} программно (без AI). Запрос: {edits}")
            logger.info(f"Исходный текст (первые 500 символов): {original_post[:500]}...")
            
            # Разбиваем на абзацы для отладки
            original_paragraphs = [p.strip() for p in original_post.split('\n\n') if p.strip()]
            logger.info(f"Исходное количество абзацев: {len(original_paragraphs)}")
            for i, para in enumerate(original_paragraphs, 1):
                logger.info(f"Абзац {i} (первые 100 символов): {para[:100]}...")
            
            result = remove_paragraphs_programmatically(original_post, paragraph_nums_to_delete)
            
            # Разбиваем результат на абзацы для отладки
            result_paragraphs = [p.strip() for p in result.split('\n\n') if p.strip()]
            logger.info(f"Абзацы удалены программно. Исходная длина: {len(original_post)}, новая длина: {len(result)}")
            logger.info(f"Результат: количество абзацев {len(result_paragraphs)}")
            for i, para in enumerate(result_paragraphs, 1):
                logger.info(f"Абзац {i} (первые 100 символов): {para[:100]}...")
            
            # Проверяем, что результат не пустой
            if not result.strip():
                logger.warning("Результат удаления пустой, возвращаем оригинал")
                result = original_post
            
            # Конвертируем markdown в HTML на всякий случай
            result = markdown_to_html(result)
            logger.info(f"Возвращаем результат программного удаления (длина: {len(result)})")
            return result
        
        # Используем промпт "Опубликовать сейчас" для редактирования
        system_prompt = self._get_post_now_system_prompt()
        
        if is_delete_request:
            # Это не должно произойти, так как удаление делается программно, но на всякий случай
            system_prompt += "\n\nКРИТИЧЕСКИ ВАЖНО:\n- Руководитель просит УДАЛИТЬ указанный абзац\n- Остальные абзацы должны остаться БЕЗ ИЗМЕНЕНИЙ - скопируй их точно как в оригинале\n- Просто убери указанный абзац, остальное оставь как есть\n- НЕ переписывай текст\n- НЕ добавляй эмодзи\n- НЕ меняй стиль\n- Верни пост БЕЗ удаленного абзаца"
        elif paragraph_num:
            # Если просят удалить абзац без указания номера, ищем по ключевым словам
            system_prompt += "\n\nКРИТИЧЕСКИ ВАЖНО:\n- Руководитель просит УДАЛИТЬ указанный абзац\n- Остальные абзацы должны остаться БЕЗ ИЗМЕНЕНИЙ - скопируй их точно как в оригинале\n- Просто убери указанный абзац, остальное оставь как есть\n- НЕ переписывай текст\n- НЕ добавляй эмодзи\n- НЕ меняй стиль\n- Верни пост БЕЗ удаленного абзаца"
        elif paragraph_num:
            # Если указан конкретный абзац для редактирования
            system_prompt += f"\n\nКРИТИЧЕСКИ ВАЖНО ДЛЯ РЕДАКТИРОВАНИЯ:\n- Руководитель просит изменить ТОЛЬКО {paragraph_num}-й абзац\n- Остальные 3 абзаца должны остаться БЕЗ ИЗМЕНЕНИЙ - скопируй их точно как в оригинале\n- Измени ТОЛЬКО {paragraph_num}-й абзац согласно правкам\n- НЕ переписывай весь пост заново\n- НЕ изменяй другие абзацы\n- НЕ добавляй эмодзи если их не было\n- НЕ меняй стиль остальных абзацев\n- Сохрани структуру из 4 абзацев"
        else:
            # Общие инструкции для редактирования
            system_prompt += "\n\nКРИТИЧЕСКИ ВАЖНО ДЛЯ РЕДАКТИРОВАНИЯ:\n- Сохраняй структуру из 4 абзацев\n- Минимально изменяй текст - только то, что требуется в правках\n- НЕ переписывай весь пост заново\n- НЕ добавляй эмодзи если их не было в оригинале\n- НЕ меняй стиль текста\n- Сохрани стиль и содержание исходного текста\n- Если просят добавить абзац, добавь его в соответствующее место структуры\n- Если просят изменить что-то конкретное, измени только это, остальное оставь БЕЗ ИЗМЕНЕНИЙ - скопируй точно как в оригинале"
        
        try:
            if is_delete_request and paragraph_num:
                prompt = f"""Вот исходный пост (структура из 4 абзацев):
{original_post}

Руководитель просит УДАЛИТЬ {paragraph_num}-й абзац:
{edits}

КРИТИЧЕСКИ ВАЖНО:
- Остальные абзацы должны остаться БЕЗ ИЗМЕНЕНИЙ - скопируй их точно как в оригинале
- Просто убери {paragraph_num}-й абзац
- НЕ переписывай текст
- НЕ добавляй эмодзи
- НЕ меняй стиль
- Верни пост БЕЗ удаленного абзаца, остальное оставь как есть"""
            elif is_delete_request:
                # Определяем какой абзац удалить по ключевым словам
                if paragraph_num:
                    delete_info = f"{paragraph_num}-й абзац"
                else:
                    # Пытаемся найти по ключевым словам
                    delete_info = "указанный абзац"
                    for i, para in enumerate(paragraphs, 1):
                        if any(keyword in edits.lower() for keyword in ['частые ошибки', 'ошибки', 'ошибка']):
                            if 'ошибк' in para.lower():
                                paragraph_num = i
                                delete_info = f"{i}-й абзац (про ошибки)"
                                break
                        elif 'технические аспекты' in edits.lower() or 'техническ' in edits.lower():
                            if 'техническ' in para.lower() or 'норм' in para.lower() or 'снип' in para.lower():
                                paragraph_num = i
                                delete_info = f"{i}-й абзац (технические аспекты)"
                                break
                
                if paragraph_num:
                    prompt = f"""Вот исходный пост (структура из {len(paragraphs)} абзацев):
{original_post}

Руководитель просит УДАЛИТЬ {delete_info}:
{edits}

КРИТИЧЕСКИ ВАЖНО - ТЫ ДОЛЖЕН:
1. УДАЛИТЬ ТОЛЬКО {paragraph_num}-й абзац
2. Остальные абзацы скопировать ТОЧНО как в оригинале - БЕЗ ИЗМЕНЕНИЙ
3. НЕ переписывать текст
4. НЕ добавлять эмодзи
5. НЕ менять стиль
6. НЕ менять формулировки
7. Просто убери {paragraph_num}-й абзац и верни остальные как есть

Верни пост БЕЗ удаленного абзаца, остальное оставь ТОЧНО как в оригинале."""
                else:
                    prompt = f"""Вот исходный пост (структура из {len(paragraphs)} абзацев):
{original_post}

Руководитель просит УДАЛИТЬ указанный абзац:
{edits}

КРИТИЧЕСКИ ВАЖНО:
- Остальные абзацы должны остаться БЕЗ ИЗМЕНЕНИЙ - скопируй их точно как в оригинале
- Просто убери указанный абзац
- НЕ переписывай текст
- НЕ добавляй эмодзи
- НЕ меняй стиль
- Верни пост БЕЗ удаленного абзаца, остальное оставь как есть"""
            elif paragraph_num:
                # Для редактирования конкретного абзаца - генерируем только этот абзац, остальные заменяем программно
                target_paragraph = paragraphs[paragraph_num - 1]
                
                # Используем упрощенный системный промпт только для генерации одного абзаца
                simple_system_prompt = """Ты профессиональный редактор текстов для строительной компании "Археон".
Твоя задача - отредактировать ОДИН абзац согласно правкам руководителя.

КРИТИЧЕСКИ ВАЖНО:
- Сохрани стиль и содержание исходного абзаца
- Внеси ТОЛЬКО те изменения, которые указаны в правках
- НЕ добавляй эмодзи если их не было в оригинале
- НЕ меняй стиль текста радикально
- НЕ переписывай абзац полностью, только внеси необходимые изменения
- Верни ТОЛЬКО отредактированный абзац, без дополнительных комментариев"""
                
                prompt = f"""Вот исходный абзац (АБЗАЦ {paragraph_num}):
{target_paragraph}

Руководитель просит изменить этот абзац:
{edits}

Отредактируй ТОЛЬКО этот абзац согласно правкам. Сохрани стиль и содержание, внеси только необходимые изменения. Верни ТОЛЬКО отредактированный абзац."""
                
                # Генерируем только измененный абзац
                logger.info(f"Генерация только {paragraph_num}-го абзаца для редактирования")
                
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": simple_system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.0,
                        max_tokens=2000,
                        top_p=0.1
                    ),
                    timeout=180.0 if self.proxy_enabled else 60.0
                )
                
                new_paragraph = response.choices[0].message.content.strip()
                new_paragraph = clean_ai_response(new_paragraph)
                
                # Программно заменяем только этот абзац, остальные оставляем как есть
                result = replace_paragraph_programmatically(original_post, paragraph_num, new_paragraph)
                
                # Конвертируем markdown в HTML
                result = markdown_to_html(result)
                
                logger.info(f"Абзац {paragraph_num} заменен программно. Исходная длина: {len(original_post)}, новая длина: {len(result)} символов")
                
                return result
            else:
                # Проверяем, просят ли добавить абзац
                add_keywords = ['добавь', 'добавить', 'вставь', 'вставить']
                is_add_request = any(keyword in edits.lower() for keyword in add_keywords)
                
                if is_add_request and 'ошибк' in edits.lower():
                    # Добавление абзаца о частых ошибках - генерируем только новый абзац, вставляем программно
                    insert_position = 3  # Третий абзац
                    
                    simple_system_prompt = self._get_post_now_system_prompt()
                    simple_system_prompt += "\n\nТвоя задача - написать ТОЛЬКО абзац о частых ошибках на этапе строительства."
                    
                    prompt = f"""Вот контекст поста:
{original_post}

Руководитель просит добавить абзац о частых ошибках:
{edits}

Напиши ТОЛЬКО один абзац о частых ошибках на данном этапе строительства. Абзац должен описывать типичные ошибки и их последствия. Верни ТОЛЬКО текст абзаца, без дополнительных комментариев."""
                    
                    logger.info(f"Генерация нового абзаца о частых ошибках для вставки на позицию {insert_position}")
                    
                    response = await asyncio.wait_for(
                        self.client.chat.completions.create(
                            model=self.model,
                            messages=[
                                {"role": "system", "content": simple_system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.0,
                            max_tokens=2000,
                            top_p=0.1
                        ),
                        timeout=180.0 if self.proxy_enabled else 60.0
                    )
                    
                    new_paragraph = response.choices[0].message.content.strip()
                    new_paragraph = clean_ai_response(new_paragraph)
                    
                    # Программно вставляем новый абзац, остальные оставляем как есть
                    result = insert_paragraph_programmatically(original_post, insert_position, new_paragraph)
                    
                    # Конвертируем markdown в HTML
                    result = markdown_to_html(result)
                    
                    logger.info(f"Новый абзац вставлен программно на позицию {insert_position}. Исходная длина: {len(original_post)}, новая длина: {len(result)} символов")
                    
                    return result
                
                elif is_add_request and ('приветств' in edits.lower() or 'привет' in edits.lower() or 'блок приветствия' in edits.lower()):
                    # Добавление блока приветствия - генерируем только новый абзац, вставляем программно в начало
                    insert_position = 1  # Первый абзац (в начало)
                    
                    simple_system_prompt = self._get_post_now_system_prompt()
                    simple_system_prompt += "\n\nТвоя задача - написать ТОЛЬКО короткий абзац-приветствие для начала поста."
                    
                    prompt = f"""Вот контекст поста:
{original_post}

Руководитель просит добавить блок приветствия:
{edits}

Напиши ТОЛЬКО один короткий абзац-приветствие для начала поста. Абзац должен быть дружелюбным и приветствовать читателей. Верни ТОЛЬКО текст абзаца, без дополнительных комментариев и заголовков."""
                    
                    logger.info(f"Генерация нового абзаца-приветствия для вставки на позицию {insert_position}")
                    
                    response = await asyncio.wait_for(
                        self.client.chat.completions.create(
                            model=self.model,
                            messages=[
                                {"role": "system", "content": simple_system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.0,
                            max_tokens=500,  # Приветствие должно быть коротким
                            top_p=0.1
                        ),
                        timeout=180.0 if self.proxy_enabled else 60.0
                    )
                    
                    new_paragraph = response.choices[0].message.content.strip()
                    new_paragraph = clean_ai_response(new_paragraph)
                    
                    # Убираем заголовки из нового абзаца, если они там есть
                    for pattern in header_patterns:
                        new_paragraph = re.sub(pattern, '', new_paragraph, flags=re.IGNORECASE)
                    new_paragraph = new_paragraph.strip()
                    
                    # Программно вставляем новый абзац в начало, остальные оставляем как есть
                    result = insert_paragraph_programmatically(original_post, insert_position, new_paragraph)
                    
                    # Конвертируем markdown в HTML
                    result = markdown_to_html(result)
                    
                    logger.info(f"Новый абзац-приветствие вставлен программно на позицию {insert_position}. Исходная длина: {len(original_post)}, новая длина: {len(result)} символов")
                    
                    return result
                
                # Для общих правок показываем каждый абзац отдельно с четким указанием что НЕ менять
                paragraphs_list = []
                for i, para in enumerate(paragraphs, 1):
                    paragraphs_list.append(f"АБЗАЦ {i} (НЕ МЕНЯТЬ БЕЗ УКАЗАНИЯ):\n{para}")
                
                prompt = f"""Вот исходный пост (структура из {len(paragraphs)} абзацев):

{chr(10).join(paragraphs_list)}

Руководитель просит внести следующие правки:
{edits}

КРИТИЧЕСКИ ВАЖНО - ТЫ ДОЛЖЕН:
1. Сохранить структуру из {len(paragraphs)} абзацев
2. Изменить ТОЛЬКО то, что указано в правках выше
3. Все абзацы, которые НЕ упомянуты в правках, скопировать ТОЧНО как в оригинале - БЕЗ ИЗМЕНЕНИЙ, слово в слово
4. НЕ переписывать весь пост заново
5. НЕ добавлять эмодзи если их не было в оригинале
6. НЕ менять стиль текста
7. НЕ менять формулировки если это не требуется в правках
8. Сохранить стиль и содержание исходного текста
9. Если правки не касаются какого-то абзаца, оставить его ТОЧНО как в оригинале - слово в слово
10. НЕ добавлять заголовки типа "📝 Черновик поста для согласования" или "📝 Черновик поста для согласования (после правок)" - это технические заголовки, их не должно быть в тексте поста
11. Вернуть ТОЛЬКО текст поста, без технических заголовков и комментариев

Верни весь пост целиком, где изменены ТОЛЬКО те части, которые указаны в правках. НЕ добавляй технические заголовки."""
            
            logger.info(f"Переработка поста 'Опубликовать сейчас'. Исходная длина: {len(original_post)} символов. Правки: {edits}")
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,  # Нулевая температура для максимальной точности и минимальных изменений
                    max_tokens=4000,  # Больше токенов для сохранения структуры
                    top_p=0.1  # Очень низкий top_p для детерминированности
                ),
                timeout=180.0 if self.proxy_enabled else 60.0
            )
            
            refined_text = response.choices[0].message.content.strip()
            
            # Очищаем от комментариев AI
            refined_text = clean_ai_response(refined_text)
            
            # Проверяем, что текст не изменился слишком сильно (для редактирования, не удаления)
            if not is_delete_request:
                original_length = len(original_post)
                new_length = len(refined_text)
                length_diff = abs(original_length - new_length) / original_length if original_length > 0 else 0
                
                # Если текст изменился более чем на 30%, это подозрительно
                if length_diff > 0.3:
                    logger.warning(f"Подозрительно большое изменение текста: {length_diff*100:.1f}% (было {original_length}, стало {new_length})")
                
                # Проверяем количество абзацев
                original_para_count = len([p for p in original_post.split('\n\n') if p.strip()])
                new_para_count = len([p for p in refined_text.split('\n\n') if p.strip()])
                
                if paragraph_num and new_para_count != original_para_count:
                    logger.warning(f"Изменено количество абзацев: было {original_para_count}, стало {new_para_count}")
                
                # Проверяем наличие эмодзи в оригинале и новом тексте
                import re
                emoji_pattern = re.compile("["
                    u"\U0001F600-\U0001F64F"  # emoticons
                    u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                    u"\U0001F680-\U0001F6FF"  # transport & map symbols
                    u"\U0001F1E0-\U0001F1FF"  # flags
                    u"\U00002702-\U000027B0"
                    u"\U000024C2-\U0001F251"
                    "]+", flags=re.UNICODE)
                
                original_emojis = len(emoji_pattern.findall(original_post))
                new_emojis = len(emoji_pattern.findall(refined_text))
                
                if original_emojis == 0 and new_emojis > 0:
                    logger.warning(f"Добавлены эмодзи в текст, хотя в оригинале их не было: {new_emojis}. Удаляю эмодзи.")
                    # Удаляем эмодзи если их не было в оригинале
                    refined_text = emoji_pattern.sub('', refined_text).strip()
                    # Убираем лишние пробелы после удаления эмодзи
                    refined_text = re.sub(r'\s+', ' ', refined_text)
                    refined_text = re.sub(r'\n\s*\n', '\n\n', refined_text)
            
            # Конвертируем markdown в HTML
            refined_text = markdown_to_html(refined_text)
            
            logger.info(f"Пост 'Опубликовать сейчас' переработан. Исходная длина: {len(original_post)}, новая длина: {len(refined_text)} символов")
            
            return refined_text
        
        except asyncio.TimeoutError:
            logger.error("Таймаут при переработке поста 'Опубликовать сейчас'")
            raise Exception("Таймаут при переработке поста. Попробуйте позже.")
        except Exception as e:
            logger.error(f"Ошибка при переработке поста 'Опубликовать сейчас': {e}")
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
        # Получаем системный промпт из конфигурации или используем дефолтный
        if self.prompt_config_service:
            system_prompt = self.prompt_config_service.get_prompt("refine_post", "system_prompt")
            if not system_prompt:
                logger.warning("Промпт refine_post не найден в конфигурации, используем дефолтный")
                system_prompt = """Ты профессиональный редактор текстов для строительной компании "Археон".
Твоя задача - переработать пост с учетом правок руководителя.

ВАЖНЫЕ ТРЕБОВАНИЯ:
**СТРОГОЕ ОГРАНИЧЕНИЕ ДЛИНЫ: Текст поста НЕ ДОЛЖЕН превышать 900 символов (включая пробелы и эмодзи). Это абсолютное ограничение. Посты длиннее 900 символов будут отклонены системой.**
- Используй много эмодзи для визуального оформления (минимум 1 эмодзи на каждые 2-3 предложения)
- Посты должны быть КОРОТКИМИ и ёмкими (максимум 120-150 слов)
- Структурируй текст короткими абзацами (по 2-3 предложения)
- Используй эмодзи для выделения ключевых моментов: 📊 📸 🏗️ ✅ ⚠️ 💡 📝 и другие
- Стиль: дружелюбный, современный, с эмодзи для привлечения внимания
- Избегай длинных предложений и сложных конструкций
- НЕ добавляй комментарии о соответствии требованиям или мета-описания
- Возвращай ТОЛЬКО текст поста, без дополнительных комментариев
- ПЕРЕД ОТПРАВКОЙ проверь длину текста - он должен быть строго до 900 символов"""
        else:
            # Дефолтный промпт если сервис не инициализирован
            system_prompt = """Ты профессиональный редактор текстов для строительной компании "Археон".
Твоя задача - переработать пост с учетом правок руководителя.

ВАЖНЫЕ ТРЕБОВАНИЯ:
**СТРОГОЕ ОГРАНИЧЕНИЕ ДЛИНЫ: Текст поста НЕ ДОЛЖЕН превышать 900 символов (включая пробелы и эмодзи). Это абсолютное ограничение. Посты длиннее 900 символов будут отклонены системой.**
- Используй много эмодзи для визуального оформления (минимум 1 эмодзи на каждые 2-3 предложения)
- Посты должны быть КОРОТКИМИ и ёмкими (максимум 120-150 слов)
- Структурируй текст короткими абзацами (по 2-3 предложения)
- Используй эмодзи для выделения ключевых моментов: 📊 📸 🏗️ ✅ ⚠️ 💡 📝 и другие
- Стиль: дружелюбный, современный, с эмодзи для привлечения внимания
- Избегай длинных предложений и сложных конструкций
- НЕ добавляй комментарии о соответствии требованиям или мета-описания
- Возвращай ТОЛЬКО текст поста, без дополнительных комментариев
- ПЕРЕД ОТПРАВКОЙ проверь длину текста - он должен быть строго до 900 символов"""
        
        try:
            prompt = f"""Вот исходный пост:
{original_post}

Руководитель просит внести следующие правки:
{edits}

Переработай пост с учетом этих правок, сохранив стиль и структуру. Учти все требования к длине и использованию эмодзи."""
            
            logger.info(f"Переработка поста. Исходная длина: {len(original_post)} символов. Правки: {edits}")
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=1500
                ),
                timeout=180.0 if self.proxy_enabled else 60.0
            )
            
            refined_text = response.choices[0].message.content.strip()
            
            # Очищаем от комментариев AI
            refined_text = clean_ai_response(refined_text)
            
            # Конвертируем markdown в HTML
            refined_text = markdown_to_html(refined_text)
            
            logger.info(f"Пост переработан. Новая длина: {len(refined_text)} символов")
            
            return refined_text
        
        except asyncio.TimeoutError:
            logger.error("Таймаут при переработке поста")
            raise Exception("Таймаут при переработке поста. Попробуйте позже.")
        except Exception as e:
            logger.error(f"Ошибка при переработке поста: {e}")
            raise
    
    async def generate_post_from_sources(self, source_posts: List[Dict[str, str]]) -> str:
        """
        Генерирует пост на основе анализа постов из других источников
        
        Args:
            source_posts: Список словарей с постами из источников
                Каждый словарь должен содержать:
                - 'text': текст поста
                - 'source': URL источника
                - 'source_type': тип источника ('telegram' или 'vk')
                - 'metadata': дополнительные метаданные (опционально)
        
        Returns:
            Сгенерированный текст поста
        """
        if not source_posts:
            logger.warning("Нет постов из источников для анализа")
            return self._get_fallback_source_post()
        
        # Формируем текст для анализа из всех постов
        posts_text = []
        for i, post in enumerate(source_posts[:10], 1):  # Берем максимум 10 постов
            source_type = post.get('source_type', 'unknown')
            text = post.get('text', '')
            if text:
                posts_text.append(f"Пост {i} ({source_type}):\n{text}\n")
        
        sources_context = "\n---\n".join(posts_text)
        
        # Получаем системный промпт из конфигурации или используем дефолтный
        if self.prompt_config_service:
            system_prompt = self.prompt_config_service.get_prompt("generate_from_sources", "system_prompt")
            if not system_prompt:
                logger.warning("Промпт generate_from_sources не найден в конфигурации, используем дефолтный")
                system_prompt = """Ты профессиональный копирайтер для строительной компании "Археон".
Твоя задача - проанализировать посты из других источников (конкурентов, партнеров, отраслевых каналов) и создать НОВЫЙ, УНИКАЛЬНЫЙ пост для компании "Археон".

КРИТИЧЕСКИ ВАЖНЫЕ ТРЕБОВАНИЯ:
**СТРОГОЕ ОГРАНИЧЕНИЕ ДЛИНЫ: Текст поста НЕ ДОЛЖЕН превышать 900 символов (включая пробелы и эмодзи). Это абсолютное ограничение. Посты длиннее 900 символов будут отклонены системой.**
- Используй много эмодзи для визуального оформления (минимум 1 эмодзи на каждые 2-3 предложения)
- Посты должны быть КОРОТКИМИ и ёмкими (максимум 120-150 слов)
- Структурируй текст короткими абзацами (по 2-3 предложения)
- Используй эмодзи для выделения ключевых моментов: 📊 📸 🏗️ ✅ ⚠️ 💡 📝 🔗 и другие
- Стиль: дружелюбный, современный, с эмодзи для привлечения внимания
- Избегай длинных предложений и сложных конструкций
- НЕ добавляй комментарии о соответствии требованиям или мета-описания
- Возвращай ТОЛЬКО текст поста, без дополнительных комментариев
- ПЕРЕД ОТПРАВКОЙ проверь длину текста - он должен быть строго до 900 символов

ЗАДАЧА:
1. Проанализируй предоставленные посты из других источников
2. Определи ключевые темы, тренды и интересные идеи
3. Создай НОВЫЙ, ОРИГИНАЛЬНЫЙ пост для компании "Археон", который:
   - НЕ копирует текст напрямую из источников
   - Использует идеи и темы, но перерабатывает их в уникальный контент
   - Соответствует стилю и тематике строительной компании
   - Будет интересен нашей аудитории
   - Содержит полезную информацию или инсайты

ВАЖНО: Не копируй текст из источников! Используй их как вдохновение для создания собственного уникального контента."""
        else:
            # Дефолтный промпт если сервис не инициализирован
            system_prompt = """Ты профессиональный копирайтер для строительной компании "Археон".
Твоя задача - проанализировать посты из других источников (конкурентов, партнеров, отраслевых каналов) и создать НОВЫЙ, УНИКАЛЬНЫЙ пост для компании "Археон".

КРИТИЧЕСКИ ВАЖНЫЕ ТРЕБОВАНИЯ:
**СТРОГОЕ ОГРАНИЧЕНИЕ ДЛИНЫ: Текст поста НЕ ДОЛЖЕН превышать 900 символов (включая пробелы и эмодзи). Это абсолютное ограничение. Посты длиннее 900 символов будут отклонены системой.**
- Используй много эмодзи для визуального оформления (минимум 1 эмодзи на каждые 2-3 предложения)
- Посты должны быть КОРОТКИМИ и ёмкими (максимум 120-150 слов)
- Структурируй текст короткими абзацами (по 2-3 предложения)
- Используй эмодзи для выделения ключевых моментов: 📊 📸 🏗️ ✅ ⚠️ 💡 📝 🔗 и другие
- Стиль: дружелюбный, современный, с эмодзи для привлечения внимания
- Избегай длинных предложений и сложных конструкций
- НЕ добавляй комментарии о соответствии требованиям или мета-описания
- Возвращай ТОЛЬКО текст поста, без дополнительных комментариев
- ПЕРЕД ОТПРАВКОЙ проверь длину текста - он должен быть строго до 900 символов

ЗАДАЧА:
1. Проанализируй предоставленные посты из других источников
2. Определи ключевые темы, тренды и интересные идеи
3. Создай НОВЫЙ, ОРИГИНАЛЬНЫЙ пост для компании "Археон", который:
   - НЕ копирует текст напрямую из источников
   - Использует идеи и темы, но перерабатывает их в уникальный контент
   - Соответствует стилю и тематике строительной компании
   - Будет интересен нашей аудитории
   - Содержит полезную информацию или инсайты

ВАЖНО: Не копируй текст из источников! Используй их как вдохновение для создания собственного уникального контента."""
        
        user_prompt = f"""Проанализируй следующие посты из других источников и создай новый, уникальный пост для компании "Археон":

{sources_context}

Создай пост, который:
- Использует ключевые темы и идеи из анализа
- НЕ копирует текст напрямую
- Будет интересен нашей аудитории
- Соответствует стилю строительной компании "Археон"
- Короткий, яркий, с эмодзи"""
        
        try:
            logger.info(f"Генерация поста на основе анализа {len(source_posts)} постов из источников")
            
            timeout_seconds = 180.0 if self.proxy_enabled else 60.0
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.8,  # Немного выше для большей креативности
                    max_tokens=2000
                ),
                timeout=timeout_seconds
            )
            
            result = response.choices[0].message.content.strip()
            
            # Очищаем от комментариев AI
            result = clean_ai_response(result)
            
            # Конвертируем markdown в HTML
            result = markdown_to_html(result)
            
            logger.info(f"Пост на основе источников сгенерирован успешно (длина: {len(result)} символов)")
            return result
        
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при генерации поста из источников")
            return self._get_fallback_source_post()
        
        except Exception as e:
            error_str = str(e)
            logger.error(f"Ошибка при генерации поста из источников: {e}")
            
            # Пробуем переключить прокси или API ключ при ошибке
            is_timeout = (
                "timeout" in error_str.lower() or 
                "timed out" in error_str.lower() or
                "Request timed out" in error_str
            )
            
            max_proxy_retries = min(5, len(self.proxy_list)) if self.proxy_enabled else 0
            for proxy_attempt in range(max_proxy_retries):
                if self.proxy_enabled and (is_timeout or "403" in error_str or "connection" in error_str.lower()):
                    if self._switch_proxy():
                        logger.info(f"Попытка {proxy_attempt + 1}/{max_proxy_retries} генерации с другим прокси...")
                        try:
                            timeout_seconds = 180.0
                            response = await asyncio.wait_for(
                                self.client.chat.completions.create(
                                    model=self.model,
                                    messages=[
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": user_prompt}
                                    ],
                                    temperature=0.8,
                                    max_tokens=2000
                                ),
                                timeout=timeout_seconds
                            )
                            result = response.choices[0].message.content.strip()
                            result = clean_ai_response(result)
                            result = markdown_to_html(result)
                            logger.info(f"Пост сгенерирован после переключения прокси")
                            return result
                        except Exception as retry_error:
                            logger.warning(f"Попытка {proxy_attempt + 1} не удалась: {retry_error}")
                            continue
            
            # Пробуем с другим API ключом и прокси
            max_key_retries = 2
            for key_attempt in range(max_key_retries):
                if self._switch_api_key():
                    logger.info(f"Попытка {key_attempt + 1}/{max_key_retries} с другим API ключом и прокси...")
                    try:
                        timeout_seconds = 180.0
                        response = await asyncio.wait_for(
                            self.client.chat.completions.create(
                                model=self.model,
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                temperature=0.8,
                                max_tokens=2000
                            ),
                            timeout=timeout_seconds
                        )
                        result = response.choices[0].message.content.strip()
                        result = clean_ai_response(result)
                        result = markdown_to_html(result)
                        logger.info(f"Пост сгенерирован после переключения API ключа")
                        return result
                    except Exception as retry_error:
                        logger.warning(f"Попытка {key_attempt + 1} с другим ключом не удалась: {retry_error}")
                        continue
            
            # Финальная попытка без прокси
            if self.proxy_enabled:
                logger.info("Все прокси не работают. Пробуем финальную попытку без прокси...")
                try:
                    http_client = httpx.AsyncClient(
                        timeout=httpx.Timeout(300.0, connect=60.0, read=300.0)
                    )
                    temp_client = AsyncOpenAI(
                        api_key=self.api_keys[self.current_api_key_index],
                        http_client=http_client
                    )
                    
                    response = await asyncio.wait_for(
                        temp_client.chat.completions.create(
                            model=self.model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ],
                            temperature=0.8,
                            max_tokens=2000
                        ),
                        timeout=180.0
                    )
                    result = response.choices[0].message.content.strip()
                    result = clean_ai_response(result)
                    result = markdown_to_html(result)
                    logger.info(f"Пост сгенерирован без прокси")
                    return result
                except Exception as final_error:
                    logger.warning(f"Финальная попытка без прокси также не удалась: {final_error}")
            
            return self._get_fallback_source_post()
    
    def _get_fallback_source_post(self) -> str:
        """Возвращает fallback пост при ошибках генерации"""
        fallback_text = (
            "🏗️ <b>Археон Update</b>\n\n"
            "Мы продолжаем следить за трендами в строительной отрасли и "
            "адаптируем наши подходы для лучшего обслуживания клиентов.\n\n"
            "📊 Наши специалисты анализируют новые технологии и методы работы, "
            "чтобы предложить вам самые современные решения.\n\n"
            "💡 Следите за нашими обновлениями - мы готовим интересные материалы!\n\n"
            "⚠️ Примечание: Детальный анализ источников временно недоступен."
        )
        return markdown_to_html(fallback_text)
    
    async def analyze_sources(self, urls: List[str]) -> str:
        """
        Анализирует источники (URL) и возвращает контекст для использования в генерации поста
        
        Args:
            urls: Список URL источников (сайты, Telegram каналы, VK группы)
            
        Returns:
            Текст с анализом источников для использования в промпте
        """
        if not urls:
            return ""
        
        try:
            # Формируем промпт для анализа источников
            urls_text = "\n".join([f"- {url}" for url in urls])
            
            prompt = f"""Проанализируй следующие источники и создай краткое резюме ключевой информации, которая может быть полезна для создания поста о строительстве и земельных работах:

Источники:
{urls_text}

Верни краткое резюме (максимум 300 слов) с ключевыми темами, идеями и информацией из этих источников, которые могут быть использованы для создания поста компании "Археон".
Если это сайты или посты из социальных сетей, выдели основные темы и интересные моменты."""
            
            logger.info(f"Анализ {len(urls)} источников через AI")
            
            timeout_seconds = 120.0 if self.proxy_enabled else 60.0
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5,
                    max_tokens=1000
                ),
                timeout=timeout_seconds
            )
            
            result = response.choices[0].message.content.strip()
            logger.info(f"Анализ источников завершен (длина: {len(result)} символов)")
            return result
        
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при анализе источников")
            return f"\n\nДополнительные источники для контекста:\n" + "\n".join([f"- {url}" for url in urls])
        
        except Exception as e:
            logger.error(f"Ошибка при анализе источников: {e}", exc_info=True)
            # Возвращаем просто список URL в случае ошибки
            return f"\n\nДополнительные источники для контекста:\n" + "\n".join([f"- {url}" for url in urls])
    
    async def generate_meme_idea(self, topic: str) -> str:
        """
        Генерирует идею для мема на заданную тему
        
        Args:
            topic: Тема мема
            
        Returns:
            Описание идеи мема
        """
        try:
            prompt = f"""Придумай идею для мема на тему строительства и земельных работ.
Тема: {topic}
Опиши визуальную концепцию и текст мема."""
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"Ошибка при генерации идеи мема: {e}")
            raise

