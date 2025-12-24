"""Сервис для работы с AI (OpenAI)"""
import logging
import asyncio
import re
from typing import Optional, List, Dict
from openai import AsyncOpenAI
from openai import RateLimitError, APIError
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
        
        # Определяем, поддерживает ли модель параметр temperature
        # Модели GPT-5/o1 не поддерживают temperature (только дефолтное значение 1)
        self.supports_temperature = not (settings.OPENAI_MODEL.startswith("gpt-5") or 
                                         settings.OPENAI_MODEL.startswith("o1") or
                                         "o1" in settings.OPENAI_MODEL.lower())
        
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
        
        # Определяем, поддерживает ли модель параметр temperature
        # Модели GPT-5/o1 не поддерживают temperature (только дефолтное значение 1)
        self.supports_temperature = not (settings.OPENAI_MODEL.startswith("gpt-5") or 
                                         settings.OPENAI_MODEL.startswith("o1") or
                                         "o1" in settings.OPENAI_MODEL.lower())
    
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
        # Получаем системный промпт из конфигурации или используем дефолтный
        if self.prompt_config_service:
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
            
            # Определяем роль для системного промпта
            role = "developer" if self.use_developer_role else "system"
            
            # Формируем параметры запроса
            request_params = {
                "model": self.model,
                "messages": [
                    {"role": role, "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_completion_tokens": 2000
            }
            
            # Добавляем temperature только если модель его поддерживает
            if self.supports_temperature:
                request_params["temperature"] = 0.7
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**request_params),
                timeout=timeout_seconds
            )
            
            # Проверяем наличие контента в ответе
            if not response.choices or not response.choices[0].message.content:
                error_msg = f"Модель {self.model} вернула пустой ответ. Возможные причины: модель не поддерживает роль '{role}', превышены лимиты или ошибка прокси."
                logger.error(error_msg)
                try:
                    import json
                    logger.error(f"Полный ответ API: {json.dumps(response.model_dump(), ensure_ascii=False)}")
                except:
                    logger.error(f"Полный ответ API (raw): {response}")
                
                # Если это была попытка с developer ролью и она вернула пустоту, 
                # попробуем переключиться на system в следующий раз или выдать ошибку сейчас
                raise Exception(error_msg)
            
            result = response.choices[0].message.content.strip()
            
            if not result:
                error_msg = f"Модель {self.model} вернула пустую строку после обработки."
                logger.error(error_msg)
                logger.error(f"Полный ответ API: {response}")
                raise Exception(error_msg)
            
            # Очищаем от комментариев AI
            result = clean_ai_response(result)
            
            # Конвертируем markdown в HTML
            result = markdown_to_html(result)
            
            logger.info(f"Генерация текста завершена успешно (длина: {len(result)} символов)")
            return result
        
        except RateLimitError as e:
            error_msg = (
                f"❌ Превышен лимит запросов к OpenAI API (Rate Limit). "
                f"Пожалуйста, проверьте:\n"
                f"1. Лимит запросов в минуту/час на вашем тарифе\n"
                f"2. Баланс на счету OpenAI\n"
                f"3. Попробуйте позже или увеличьте лимиты\n\n"
                f"Детали ошибки: {str(e)}"
            )
            logger.error(error_msg)
            raise Exception(error_msg) from e
        
        except APIError as e:
            error_code = getattr(e, 'status_code', None)
            error_type = getattr(e, 'code', None)
            
            if error_code == 429 or error_type == 'insufficient_quota':
                error_msg = (
                    f"❌ Превышена квота OpenAI API. Пожалуйста:\n"
                    f"1. Проверьте баланс на счету OpenAI (https://platform.openai.com/account/billing)\n"
                    f"2. Проверьте лимиты вашего тарифа\n"
                    f"3. Пополните баланс или обновите тариф\n\n"
                    f"Детали ошибки: {str(e)}"
                )
            elif error_code == 401:
                error_msg = (
                    f"❌ Неверный API ключ OpenAI. Проверьте OPENAI_API_KEY в настройках."
                )
            else:
                error_msg = (
                    f"❌ Ошибка OpenAI API (код: {error_code}, тип: {error_type}): {str(e)}"
                )
            
            logger.error(error_msg)
            raise Exception(error_msg) from e
        
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
                            # Формируем параметры запроса
                            retry_request_params = {
                                "model": self.model,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                "max_completion_tokens": 2000
                            }
                            
                            # Добавляем temperature только если модель его поддерживает
                            if self.supports_temperature:
                                retry_request_params["temperature"] = 0.7
                            
                            response = await asyncio.wait_for(
                                self.client.chat.completions.create(**retry_request_params),
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
                            # Формируем параметры запроса
                            retry_request_params = {
                                "model": self.model,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                "max_completion_tokens": 2000
                            }
                            
                            # Добавляем temperature только если модель его поддерживает
                            if self.supports_temperature:
                                retry_request_params["temperature"] = 0.7
                            
                            response = await asyncio.wait_for(
                                self.client.chat.completions.create(**retry_request_params),
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
                            max_completion_tokens=2000
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
            logger.info(f"Отправка запроса на анализ фотографии в OpenAI API (модель: gpt-5)")
            logger.info(f"Размер изображения в base64: {len(base64_image)} символов")
            
            # Устанавливаем таймаут для запроса (увеличен для прокси)
            timeout_seconds = 180.0 if self.proxy_enabled else 60.0
            logger.info(f"Таймаут запроса: {timeout_seconds} секунд")
            
            # Формируем параметры запроса для анализа фото
            # Используем gpt-5.2 для анализа изображений
            vision_model = "gpt-5.2"
            photo_request_params = {
                "model": vision_model,
                "messages": [photo_message],
                "max_completion_tokens": 500
            }
            # gpt-5.2 не поддерживает temperature, не добавляем его
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**photo_request_params),
                timeout=timeout_seconds
            )
            
            # Проверяем наличие контента в ответе
            if not response.choices or not response.choices[0].message.content:
                error_msg = f"Модель GPT-5 вернула пустой ответ при анализе фото. Возможно, модель не поддерживает анализ изображений в этом формате."
                logger.error(error_msg)
                logger.error(f"Полный ответ API: {response}")
                # Возвращаем fallback описание вместо ошибки
                from pathlib import Path
                file_name = Path(photo_path).name
                return f"Фотография со строительного объекта: {file_name}. На фотографии запечатлен текущий этап работ на объекте компании «Археон»."
            
            result = response.choices[0].message.content.strip()
            
            if not result:
                logger.warning("Модель GPT-5 вернула пустую строку при анализе фото. Используем fallback описание.")
                from pathlib import Path
                file_name = Path(photo_path).name
                return f"Фотография со строительного объекта: {file_name}. На фотографии запечатлен текущий этап работ на объекте компании «Археон»."
            
            logger.info(f"Анализ фотографии завершен успешно (длина ответа: {len(result)} символов)")
            return result
        
        except RateLimitError as e:
            error_msg = (
                f"❌ Превышен лимит запросов к OpenAI API при анализе фото. "
                f"Пожалуйста, проверьте баланс и лимиты на https://platform.openai.com/account/billing"
            )
            logger.error(error_msg)
            raise Exception(error_msg) from e
        
        except APIError as e:
            error_code = getattr(e, 'status_code', None)
            error_type = getattr(e, 'code', None)
            
            if error_code == 429 or error_type == 'insufficient_quota':
                error_msg = (
                    f"❌ Превышена квота OpenAI API при анализе фото. "
                    f"Проверьте баланс на https://platform.openai.com/account/billing"
                )
            else:
                error_msg = f"❌ Ошибка OpenAI API при анализе фото (код: {error_code}): {str(e)}"
            
            logger.error(error_msg)
            raise Exception(error_msg) from e
        
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
            # Используем gpt-5.2 для анализа видео кадров
            model_name = "gpt-5.2"
            logger.info(f"Отправка запроса на анализ кадра {frame_number}/{total_frames} в OpenAI API (модель: {model_name})")
            
            timeout_seconds = 300.0 if self.proxy_enabled else 120.0  # Увеличенный таймаут для детального анализа
            
            # Формируем параметры запроса для анализа видео кадра
            video_frame_params = {
                "model": model_name,
                "messages": [photo_message],
                "max_completion_tokens": 1000  # Увеличенный лимит для более детального описания
            }
            # GPT-5 не поддерживает temperature, не добавляем его
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**video_frame_params),
                timeout=timeout_seconds
            )
            
            result = response.choices[0].message.content.strip()
            logger.info(f"Анализ кадра {frame_number} завершен успешно (длина ответа: {len(result)} символов)")
            return result
        
        except RateLimitError as e:
            error_msg = (
                f"❌ Превышен лимит запросов к OpenAI API при анализе видео кадра {frame_number}. "
                f"Проверьте баланс на https://platform.openai.com/account/billing"
            )
            logger.error(error_msg)
            raise Exception(error_msg) from e
        
        except APIError as e:
            error_code = getattr(e, 'status_code', None)
            error_type = getattr(e, 'code', None)
            
            if error_code == 429 or error_type == 'insufficient_quota':
                error_msg = (
                    f"❌ Превышена квота OpenAI API при анализе видео кадра {frame_number}. "
                    f"Проверьте баланс на https://platform.openai.com/account/billing"
                )
            else:
                error_msg = f"❌ Ошибка OpenAI API при анализе кадра {frame_number} (код: {error_code}): {str(e)}"
            
            logger.error(error_msg)
            raise Exception(error_msg) from e
        
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
            # Используем gpt-5.2 для анализа видео кадров
            model_name = "gpt-5.2"
            logger.info(f"Отправка запроса на анализ кадра {frame_number}/{total_frames} в OpenAI API (модель: {model_name})")
            
            timeout_seconds = 300.0 if self.proxy_enabled else 120.0  # Увеличенный таймаут для детального анализа
            
            # Формируем параметры запроса для анализа видео кадра
            video_frame_params = {
                "model": model_name,
                "messages": [photo_message],
                "max_completion_tokens": 1000  # Увеличенный лимит для более детального описания
            }
            # GPT-5 не поддерживает temperature, не добавляем его
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**video_frame_params),
                timeout=timeout_seconds
            )
            
            result = response.choices[0].message.content.strip()
            logger.info(f"Анализ кадра {frame_number} завершен успешно (длина ответа: {len(result)} символов)")
            return result
        
        except RateLimitError as e:
            error_msg = (
                f"❌ Превышен лимит запросов к OpenAI API при анализе видео кадра {frame_number}. "
                f"Проверьте баланс на https://platform.openai.com/account/billing"
            )
            logger.error(error_msg)
            raise Exception(error_msg) from e
        
        except APIError as e:
            error_code = getattr(e, 'status_code', None)
            error_type = getattr(e, 'code', None)
            
            if error_code == 429 or error_type == 'insufficient_quota':
                error_msg = (
                    f"❌ Превышена квота OpenAI API при анализе видео кадра {frame_number}. "
                    f"Проверьте баланс на https://platform.openai.com/account/billing"
                )
            else:
                error_msg = f"❌ Ошибка OpenAI API при анализе кадра {frame_number} (код: {error_code}): {str(e)}"
            
            logger.error(error_msg)
            raise Exception(error_msg) from e
        
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при анализе кадра {frame_number}")
            # Fallback на обычный анализ
            return await self.analyze_photo(frame_path)
        
        except Exception as e:
            logger.error(f"Ошибка при анализе кадра {frame_number}: {e}")
            # Fallback на обычный анализ
            return await self.analyze_photo(frame_path)
    
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
            
            # Формируем параметры запроса для refine_post_now
            role = "developer" if self.use_developer_role else "system"
            refine_now_params = {
                "model": self.model,
                "messages": [
                    {"role": role, "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "max_completion_tokens": 1500
            }
            
            # Добавляем temperature только если модель его поддерживает
            if self.supports_temperature:
                refine_now_params["temperature"] = 0.7
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**refine_now_params),
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
            
            # Формируем параметры запроса для refine_post
            role = "developer" if self.use_developer_role else "system"
            refine_params = {
                "model": self.model,
                "messages": [
                    {"role": role, "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_completion_tokens": 2000
            }
            
            # Добавляем temperature только если модель его поддерживает
            if self.supports_temperature:
                refine_params["temperature"] = 0.8  # Немного выше для большей креативности
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**refine_params),
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
                                    max_completion_tokens=2000
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
                                max_completion_tokens=2000
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
                    
                    # Формируем параметры запроса для финальной попытки без прокси
                    role = "developer" if self.use_developer_role else "system"
                    final_retry_params = {
                        "model": self.model,
                        "messages": [
                            {"role": role, "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_completion_tokens": 2000
                    }
                    
                    # Добавляем temperature только если модель его поддерживает
                    if self.supports_temperature:
                        final_retry_params["temperature"] = 0.8
                    
                    response = await asyncio.wait_for(
                        temp_client.chat.completions.create(**final_retry_params),
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
            
            # Формируем параметры запроса для analyze_sources
            sources_params = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_completion_tokens": 1000
            }
            
            # Добавляем temperature только если модель его поддерживает
            if self.supports_temperature:
                sources_params["temperature"] = 0.5
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**sources_params),
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
            
            # Формируем параметры запроса для summarize_text
            summarize_params = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_completion_tokens": 300
            }
            
            # Добавляем temperature только если модель его поддерживает
            if self.supports_temperature:
                summarize_params["temperature"] = 0.9
            
            response = await self.client.chat.completions.create(**summarize_params)
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"Ошибка при генерации идеи мема: {e}")
            raise

