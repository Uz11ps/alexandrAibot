"""Сервис для работы с AI (OpenAI)"""
import logging
import asyncio
from typing import Optional, List
from openai import AsyncOpenAI
import httpx
from config.settings import settings

logger = logging.getLogger(__name__)


class AIService:
    """Сервис для взаимодействия с OpenAI API"""
    
    def __init__(self):
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
            self.proxy_list = proxy_urls
            
            # Используем первый прокси по умолчанию
            proxy_url = proxy_urls[0]
            logger.info(f"Использование прокси для OpenAI API: {proxy_url.split('@')[1] if '@' in proxy_url else 'скрыт'}")
            if len(proxy_urls) > 1:
                logger.info(f"Доступно прокси для переключения: {len(proxy_urls)}")
            
            http_client = httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(120.0, connect=30.0, read=120.0)  # Увеличенные таймауты для прокси
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
                timeout=httpx.Timeout(120.0, connect=30.0, read=120.0)  # Увеличенные таймауты для прокси
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
                    timeout=httpx.Timeout(120.0, connect=30.0, read=120.0)
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
        photos_description: Optional[str] = None
    ) -> str:
        """
        Генерирует текст поста на основе промпта и контекста
        
        Args:
            prompt: Основной промпт для генерации
            context: Дополнительный контекст (документы, черновики)
            photos_description: Описание фотографий от AI vision
            
        Returns:
            Сгенерированный текст поста
        """
        # Формируем промпты перед блоком try для использования в обработке ошибок
        system_prompt = """Ты профессиональный копирайтер для строительной компании "Археон".
Твоя задача - создавать интересные, информативные и полезные посты для социальных сетей.
Посты должны быть понятными, без лишней воды, с практической пользой для читателей."""
        
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
                    "text": """Проанализируй эту фотографию со строительного объекта.
Опиши что на ней изображено: тип работ, этап строительства, особенности участка,
видимые проблемы или сложности, используемые материалы и технологии.
Будь конкретным и профессиональным."""
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
        
        except Exception as e:
            error_str = str(e)
            logger.error(f"Ошибка при анализе фотографии: {e}")
            
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
                        logger.info(f"Попытка {proxy_attempt + 1}/{max_proxy_retries} анализа фото с другим прокси...")
                        try:
                            timeout_seconds = 180.0
                            response = await asyncio.wait_for(
                                self.client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=[photo_message],
                                    max_tokens=500
                                ),
                                timeout=timeout_seconds
                            )
                            retry_success = True
                            return response.choices[0].message.content.strip()
                        except asyncio.TimeoutError:
                            logger.warning(f"Таймаут при попытке {proxy_attempt + 1} анализа фото с прокси")
                            if proxy_attempt < max_proxy_retries - 1:
                                continue  # Пробуем следующий прокси
                        except Exception as retry_error:
                            logger.warning(f"Ошибка при попытке {proxy_attempt + 1} анализа фото с прокси: {retry_error}")
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
                        logger.info(f"Попытка {key_attempt + 1}/{max_key_retries} анализа фото с другим API ключом и прокси...")
                        try:
                            timeout_seconds = 180.0 if self.proxy_enabled else 60.0
                            response = await asyncio.wait_for(
                                self.client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=[photo_message],
                                    max_tokens=500
                                ),
                                timeout=timeout_seconds
                            )
                            return response.choices[0].message.content.strip()
                        except asyncio.TimeoutError:
                            timeout_used = 180.0 if self.proxy_enabled else 60.0
                            logger.warning(f"Таймаут при попытке {key_attempt + 1} анализа фото с другим ключом (превышено {timeout_used} секунд)")
                            if key_attempt < max_key_retries - 1:
                                continue  # Пробуем следующую комбинацию
                        except Exception as retry_error:
                            logger.warning(f"Ошибка при попытке {key_attempt + 1} анализа фото с другим API ключом: {retry_error}")
                            if key_attempt < max_key_retries - 1:
                                continue  # Пробуем следующую комбинацию
                    else:
                        break  # Нет больше ключей для переключения
            
            # Финальная попытка: пробуем без прокси, если все прокси не работали
            if not retry_success and self.proxy_enabled and ("connection" in error_str.lower() or "timeout" in error_str.lower()):
                logger.info("Все прокси не работают. Пробуем финальную попытку анализа фото без прокси...")
                try:
                    # Создаем клиент без прокси
                    client_without_proxy = AsyncOpenAI(
                        api_key=self.api_keys[self.current_api_key_index]
                    )
                    timeout_seconds = 60.0  # Обычный таймаут без прокси
                    response = await asyncio.wait_for(
                        client_without_proxy.chat.completions.create(
                            model="gpt-4o",
                            messages=[photo_message],
                            max_tokens=500
                        ),
                        timeout=timeout_seconds
                    )
                    logger.info("Успешный анализ фото без прокси!")
                    return response.choices[0].message.content.strip()
                except Exception as final_error:
                    logger.warning(f"Финальная попытка анализа фото без прокси также не удалась: {final_error}")
            
            # Если ничего не помогло, возвращаем fallback
            from pathlib import Path
            file_name = Path(photo_path).name
            return f"Фотография со строительного объекта: {file_name}. На фотографии запечатлен текущий этап работ на объекте компании «Археон»."
            
            # Проверяем ошибку региона
            if "unsupported_country_region_territory" in error_str or "403" in error_str:
                logger.warning("OpenAI API недоступен в вашем регионе. Используем fallback описание.")
                # Возвращаем более информативное описание
                from pathlib import Path
                file_name = Path(photo_path).name
                return f"Фотография со строительного объекта: {file_name}. На фотографии запечатлен текущий этап работ на объекте компании «Археон»."
            
            raise
    
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
    
    async def refine_post(self, original_post: str, edits: str) -> str:
        """
        Перерабатывает пост с учетом правок
        
        Args:
            original_post: Исходный текст поста
            edits: Требуемые правки
            
        Returns:
            Переработанный текст поста
        """
        try:
            prompt = f"""Вот исходный пост:
{original_post}

Руководитель просит внести следующие правки:
{edits}

Переработай пост с учетом этих правок, сохранив стиль и структуру."""
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты профессиональный редактор текстов."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"Ошибка при переработке поста: {e}")
            raise
    
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

