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
        """
        self.prompt_config_service = prompt_config_service
        # Настройка прокси если указан
        http_client = None
        self.proxy_list = []
        self.current_proxy_index = 0
        
        # Определяем, поддерживает ли модель параметр temperature
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
            proxy_urls = [p.strip() for p in settings.OPENAI_PROXY_URL.split(',')]
            normalized_proxies = []
            for proxy in proxy_urls:
                if proxy.count(':') == 3 and not proxy.startswith('http'):
                    parts = proxy.split(':')
                    if len(parts) == 4:
                        domain, port, username, password = parts
                        proxy = f"http://{username}:{password}@{domain}:{port}"
                normalized_proxies.append(proxy)
            self.proxy_list = normalized_proxies
            
            proxy_url = normalized_proxies[0]
            http_client = httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0)
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
            http_client = httpx.AsyncClient(
                proxy=new_proxy,
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0)
            )
            self.client = AsyncOpenAI(
                api_key=self.api_keys[self.current_api_key_index],
                http_client=http_client
            )
            return True
        return False
    
    def _switch_api_key(self):
        """Переключается на следующий API ключ из списка"""
        if len(self.api_keys) > 1:
            self.current_api_key_index = (self.current_api_key_index + 1) % len(self.api_keys)
            new_key = self.api_keys[self.current_api_key_index]
            
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
    
    async def make_news_standalone(self, text: str) -> str:
        """
        Перерабатывает новость в полностью самостоятельный пост
        """
        if self.prompt_config_service:
            system_prompt = self.prompt_config_service.get_prompt("standalone_news", "system_prompt")
        else:
            system_prompt = "Сделай текст новости самостоятельным, удалив отсылки к прошлым постам."
            
        try:
            request_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Переработай этот текст:\n\n{text}"}
                ],
                "max_completion_tokens": 2000
            }
            if self.supports_temperature:
                request_params["temperature"] = 0.5
            response = await self.client.chat.completions.create(**request_params)
            result = response.choices[0].message.content.strip()
            return markdown_to_html(clean_ai_response(result))
        except Exception as e:
            logger.error(f"Ошибка в make_news_standalone: {e}")
            return text

    async def generate_post_text(
        self,
        prompt: str,
        context: Optional[str] = None,
        photos_description: Optional[str] = None
    ) -> str:
        """
        Генерирует текст поста на основе промпта и контекста
        """
        if self.prompt_config_service:
            system_prompt = self.prompt_config_service.get_prompt("generate_post", "system_prompt")
            if not system_prompt:
                system_prompt = self._get_default_system_prompt()
        else:
            system_prompt = self._get_default_system_prompt()
        
        if photos_description:
            system_prompt += "\n\n**КРИТИЧЕСКИ ВАЖНО:** Используй только описание фотографий ниже. Не придумывай ничего своего."
        
        user_prompt = prompt
        if context:
            user_prompt += f"\n\nКонтекст:\n{context}"
        if photos_description:
            user_prompt += f"\n\nОписание фотографий:\n{photos_description}"
        
        try:
            timeout_seconds = 180.0 if self.proxy_enabled else 60.0
            
            if self.model.startswith("gpt-5") or "o1" in self.model.lower():
                messages = [{"role": "user", "content": f"ИНСТРУКЦИЯ:\n{system_prompt}\n\nЗАДАНИЕ:\n{user_prompt}"}]
            else:
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            
            request_params = {
                "model": self.model,
                "messages": messages,
                "max_completion_tokens": 10000
            }
            if self.supports_temperature:
                request_params["temperature"] = 0.7
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**request_params),
                timeout=timeout_seconds
            )
            
            if not response.choices or not response.choices[0].message.content:
                raise Exception("Пустой ответ от AI")
            
            result = response.choices[0].message.content.strip()
            return markdown_to_html(clean_ai_response(result))
            
        except Exception as e:
            logger.error(f"Ошибка при генерации текста: {e}")
            return "📊 <b>Отчет компании «Археон»</b>\n\nВ данный момент мы работаем над вашим объектом. Подробности будут позже."

    async def analyze_photo(self, photo_path: str) -> str:
        """
        Анализирует фотографию
        """
        import base64
        from pathlib import Path
        from PIL import Image
        import io
        
        try:
            with Image.open(photo_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                max_size = 1024
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85, optimize=True)
                image_data = buffer.getvalue()
        except Exception as e:
            with open(photo_path, "rb") as photo_file:
                image_data = photo_file.read()
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        analysis_prompt = self._get_photo_analysis_prompt()
        vision_model = "gpt-5.2"
        
        if vision_model.startswith("gpt-5") or "o1" in vision_model.lower():
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"ИНСТРУКЦИЯ: Проанализируй это фото как технадзор Археон.\n\nЗАДАНИЕ: {analysis_prompt}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }]
        else:
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": analysis_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }]

        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=vision_model,
                    messages=messages,
                    max_completion_tokens=5000
                ),
                timeout=180.0 if self.proxy_enabled else 60.0
            )
            return response.choices[0].message.content.strip() or "Фото со стройплощадки."
        except Exception:
            return "Фото со стройплощадки Археон."

    async def analyze_multiple_photos(self, photo_paths: List[str]) -> str:
        if not photo_paths: return ""
        descriptions = []
        for i, path in enumerate(photo_paths, 1):
            desc = await self.analyze_photo(path)
            descriptions.append(f"Фото {i}: {desc}")
        return "\n\n".join(descriptions)

    async def analyze_video(self, video_path: str, frames_count: int = 8) -> str:
        try:
            import cv2
            import tempfile
            from pathlib import Path
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            step = total_frames // (frames_count + 1)
            frame_indices = [step * (i + 1) for i in range(frames_count)]
            
            descriptions = []
            temp_dir = Path(tempfile.gettempdir()) / "video_frames"
            temp_dir.mkdir(exist_ok=True)
            
            for i, idx in enumerate(frame_indices):
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret: continue
                f_path = temp_dir / f"f_{i}.jpg"
                cv2.imwrite(str(f_path), frame)
                desc = await self.analyze_photo(str(f_path))
                descriptions.append(f"Сцена {i+1}: {desc}")
                f_path.unlink(missing_ok=True)
            cap.release()
            return "\n\n".join(descriptions) or "Видео процесса строительства."
        except Exception:
            return "Видео процесса строительства Археон."

    def _get_default_system_prompt(self) -> str:
        return """Ты профессиональный копирайтер компании "Археон". Пиши развернуто, экспертно и интересно. Длина 1500-2000 символов."""

    def _get_photo_analysis_prompt(self) -> str:
        if self.prompt_config_service:
            return self.prompt_config_service.get_prompt("analyze_photo", "user_prompt") or "Опиши детали строительства на фото."
        return "Опиши детали строительства на фото."

    async def generate_post_from_sources(self, source_posts: List[Dict[str, str]]) -> str:
        """
        Генерирует пост на основе анализа постов из других источников
        """
        if not source_posts:
            return "🏗️ Новости Археон: следите за обновлениями."
        
        posts_text = []
        source_links = set()
        for i, post in enumerate(source_posts[:10], 1):
            text = post.get('text', '')
            link = post.get('source', '')
            if text: posts_text.append(f"Источник {i}:\n{text}")
            if link: source_links.add(link)
        
        sources_context = "\n---\n".join(posts_text)
        links_str = "\n".join([f"• {link}" for link in source_links])
        
        if self.prompt_config_service:
            system_prompt = self.prompt_config_service.get_prompt("generate_from_sources", "system_prompt")
        else:
            system_prompt = "Ты аналитик Археон. Пиши развернуто (1500-2000 симв)."

        user_prompt = f"""Напиши развернутый пост (1500-2000 символов) на основе этих данных:\n{sources_context}
\nКРИТИЧЕСКИ ВАЖНО: В конце добавь заголовок "📌 Источники:" и список ссылок:\n{links_str}"""
        
        try:
            messages = [{"role": "user", "content": f"ИНСТРУКЦИЯ:\n{system_prompt}\n\nЗАДАНИЕ:\n{user_prompt}"}]
            response = await asyncio.wait_for(
                self.client.chat.completions.create(model=self.model, messages=messages, max_completion_tokens=4000),
                timeout=180.0
            )
            result = response.choices[0].message.content.strip()
            clean_text = clean_ai_response(result)
            
            # ПРИНУДИТЕЛЬНО ПРИКЛЕИВАЕМ ИСТОЧНИКИ, ЕСЛИ ИХ НЕТ
            if source_links and "Источники" not in clean_text:
                clean_text += f"\n\n📌 <b>Источники:</b>\n{links_str}"
            
            return markdown_to_html(clean_text)
        except Exception:
            return f"🏗️ <b>Новости Археон</b>\n\n{sources_context[:500]}...\n\n📌 <b>Источники:</b>\n{links_str}"

    def _get_fallback_source_post(self) -> str:
        return "🏗️ Новости Археон: следите за обновлениями."

    async def analyze_sources(self, urls: List[str]) -> str:
        if not urls: return ""
        try:
            urls_text = "\n".join(urls)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": f"Проанализируй эти ссылки для контекста:\n{urls_text}"}],
                max_completion_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return f"Контекст: {', '.join(urls)}"

    async def generate_meme_idea(self, topic: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": f"Придумай строительный мем: {topic}"}],
                max_completion_tokens=300
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return "Идея для мема: прораб и сроки."
