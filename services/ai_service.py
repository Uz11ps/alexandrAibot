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
    if not text:
        return ""
        
    # Удаляем заголовки-черновики, если они просочились
    text = re.sub(r'📝 Черновик поста для согласования:?\s*', '', text, flags=re.IGNORECASE)
    
    # Заменяем все виды длинных и средних тире на обычный дефис по просьбе заказчика
    text = text.replace(' — ', ' - ')
    text = text.replace(' – ', ' - ')
    text = text.replace('—', '-')
    text = text.replace('–', '-')
    
    # Удаляем технические примечания AI
    lines = text.split('\n')
    cleaned_lines = []
    skip_rest = False
    
    for line in lines:
        if line.strip().startswith('---'):
            skip_rest = True
            break
        if 'Этот текст соответствует' in line or 'соответствует требованиям' in line:
            skip_rest = True
            break
        if skip_rest:
            continue
        cleaned_lines.append(line)
    
    cleaned_text = '\n'.join(cleaned_lines).strip()
    
    # Удаляем остаточный мусор в конце
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
    if not text:
        return ""
    # Заменяем **текст** на <b>текст</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Заменяем *текст* на <i>текст</i>
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<i>\1</i>', text)
    # Заменяем `текст` на <code>текст</code>
    text = re.sub(r'`([^`]+?)`', r'<code>\1</code>', text)
    # Заменяем [текст](url) на <a href="url">текст</a>
    text = re.sub(r'\[([^\]]+?)\]\((https?://[^\)]+?)\)', r'<a href="\2">\1</a>', text)
    return text


class AIService:
    """Сервис для взаимодействия с OpenAI API"""
    
    def __init__(self, prompt_config_service=None):
        self.prompt_config_service = prompt_config_service
        self.proxy_list = []
        self.current_proxy_index = 0
        self.current_api_key_index = 0
        
        # Список ключей
        self.api_keys = [settings.OPENAI_API_KEY]
        if settings.OPENAI_API_KEYS:
            additional_keys = [k.strip() for k in settings.OPENAI_API_KEYS.split(',')]
            self.api_keys.extend(additional_keys)
        
        # Настройка прокси
        http_client = None
        if settings.OPENAI_PROXY_ENABLED and settings.OPENAI_PROXY_URL:
            proxy_urls = [p.strip() for p in settings.OPENAI_PROXY_URL.split(',')]
            normalized_proxies = []
            for proxy in proxy_urls:
                if proxy.count(':') == 3 and not proxy.startswith('http'):
                    parts = proxy.split(':')
                    normalized_proxies.append(f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}")
                else:
                normalized_proxies.append(proxy)
            self.proxy_list = normalized_proxies
            
            http_client = httpx.AsyncClient(
                proxy=self.proxy_list[0],
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0)
            )
        
        self.client = AsyncOpenAI(api_key=self.api_keys[0], http_client=http_client)
        self.model = settings.OPENAI_MODEL
        self.proxy_enabled = settings.OPENAI_PROXY_ENABLED
        
        # Поддержка temperature
        self.supports_temperature = not (self.model.startswith("gpt-5") or "o1" in self.model.lower())
    
    def _switch_proxy(self):
        if len(self.proxy_list) > 1:
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
            logger.info(f"Переключение на прокси #{self.current_proxy_index + 1}")
            http_client = httpx.AsyncClient(
                proxy=self.proxy_list[self.current_proxy_index],
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0)
            )
            self.client = AsyncOpenAI(api_key=self.api_keys[self.current_api_key_index], http_client=http_client)
            return True
        return False
    
    def _switch_api_key(self):
        if len(self.api_keys) > 1:
            self.current_api_key_index = (self.current_api_key_index + 1) % len(self.api_keys)
            logger.info(f"Переключение на API ключ #{self.current_api_key_index + 1}")
            self.client = AsyncOpenAI(api_key=self.api_keys[self.current_api_key_index])
            return True
        return False
    
    async def generate_post_text(self, prompt: str, context: Optional[str] = None, photos_description: Optional[str] = None) -> str:
        if self.prompt_config_service:
            system_prompt = self.prompt_config_service.get_prompt("generate_post", "system_prompt") or self._get_default_system_prompt()
        else:
            system_prompt = self._get_default_system_prompt()
        
        user_msg = f"ИНСТРУКЦИЯ:\n{system_prompt}\n\nЗАДАНИЕ:\n{prompt}"
        if context: user_msg += f"\n\nКОНТЕКСТ:\n{context}"
        if photos_description: user_msg += f"\n\nОПИСАНИЕ МЕДИА:\n{photos_description}"
        
        try:
            params = {
                "model": self.model,
                "messages": [{"role": "user", "content": user_msg}],
                "max_completion_tokens": 8000
            }
            if self.supports_temperature: params["temperature"] = 0.7
            
            response = await asyncio.wait_for(self.client.chat.completions.create(**params), timeout=180.0)
            result = response.choices[0].message.content.strip()
            return markdown_to_html(clean_ai_response(result))
        except Exception as e:
            logger.error(f"Ошибка генерации {self.model}: {e}. Пробую резервную модель gpt-4o...")
            try:
                # Резервная попытка на gpt-4o
                response = await self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": user_msg}],
                    max_tokens=4000,
                    temperature=0.7
                )
                result = response.choices[0].message.content.strip()
                return markdown_to_html(clean_ai_response(result))
            except Exception as e2:
                logger.error(f"Критическая ошибка даже на gpt-4o: {e2}")
                return "📊 <b>Новости Археон</b>\n\nСледим за рынком ИЖС. Самые важные обновления подготовим в ближайшее время!"
    
    async def analyze_photo(self, photo_path: str) -> str:
        import base64
            from PIL import Image
            import io
        try:
            with Image.open(photo_path) as img:
                if img.mode != 'RGB': img = img.convert('RGB')
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=85)
                image_data = buf.getvalue()
        except Exception:
            with open(photo_path, "rb") as f: image_data = f.read()
            
        b64 = base64.b64encode(image_data).decode('utf-8')
        prompt = self._get_photo_analysis_prompt()
        
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="gpt-5.2",
                    messages=[{
            "role": "user",
            "content": [
                            {"type": "text", "text": f"ИНСТРУКЦИЯ: Проанализируй фото как технадзор Археон.\nЗАДАНИЕ: {prompt}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                        ]
                    }],
                    max_completion_tokens=4000
                ),
                timeout=180.0
            )
            return response.choices[0].message.content.strip() or "Строительный объект Археон."
        except Exception:
            return "Объект компании Археон."

    async def analyze_multiple_photos(self, photo_paths: List[str]) -> str:
        descs = []
        for i, p in enumerate(photo_paths[:5], 1):
            d = await self.analyze_photo(p)
            descs.append(f"Фото {i}: {d}")
        return "\n\n".join(descs)
    
    async def generate_post_from_sources(self, source_posts: List[Dict[str, str]]) -> str:
        if not source_posts: return self._get_fallback_source_post()
        
        # Группируем данные для ИИ, сохраняя связь текста и ссылки
        context_items = []
        for i, p in enumerate(source_posts[:10], 1):
            text = p.get('text', '')
            source_url = p.get('source', 'Без ссылки')
            if text:
                context_items.append(f"НОВОСТЬ №{i}:\nТЕКСТ: {text}\nИСТОЧНИК: {source_url}")
            
        context = "\n\n---\n\n".join(context_items)
        
        sys_prompt = """Ты профессиональный аналитик компании Археон. 
Твоя задача: на основе предоставленных новостей составить качественный аналитический пост или дайджест.

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Если новостей несколько, сгруппируй их по темам или сделай дайджест.
2. В САМОМ ТЕКСТЕ ПОСТА НЕ ДОЛЖНО БЫТЬ ССЫЛОК, URL или упоминаний источников в скобках. Пиши чистый экспертный текст.
3. Используй понятный язык. Если используешь строительные или юридические термины (эскроу, УШП, ЗК РФ), кратко и понятно объясняй их суть для обычного человека. Избегай перегруженности жаргоном.
4. Стиль: деловой, экспертный, маркетинговый.
5. Объем: 1500-2000 символов.
6. Сделай текст автономным, как будто это эксклюзивная аналитика Археон.
7. Используй обычные дефисы (-) вместо длинных тире.
8. НИКОГДА не пиши, что у тебя нет доступа к ссылкам или интернету."""

        user_msg = f"ДАННЫЕ ИЗ ИСТОЧНИКОВ:\n{context}\n\nЗАДАНИЕ: Напиши экспертный пост БЕЗ ССЫЛОК внутри текста. Просто качественная аналитика на понятном для клиента языке."
        
        try:
            params = {
                "model": self.model,
                "messages": [{"role": "user", "content": f"ИНСТРУКЦИЯ:\n{sys_prompt}\n\nЗАДАНИЕ:\n{user_msg}"}],
                "max_completion_tokens": 5000
            }
            if self.supports_temperature: params["temperature"] = 0.7
            
            response = await asyncio.wait_for(self.client.chat.completions.create(**params), timeout=180.0)
            res = response.choices[0].message.content.strip()
            
            # Очищаем и конвертируем
            cleaned = clean_ai_response(res)
            return markdown_to_html(cleaned)
        except Exception as e:
            logger.error(f"Ошибка генерации по источникам: {e}")
            # Фолбэк с сырыми ссылками если ИИ подвел
            links = "\n".join([f"• {p.get('source')}" for p in source_posts[:5] if p.get('source')])
            return f"📊 <b>Новости ИЖС Крым</b>\n\nПроанализировали свежие данные с рынка. Основные тренды: закон об ИЖС и новые ипотечные ставки.\n\n🔗 <b>Источники:</b>\n{links}"

    async def refine_post(self, original_post: str, edits: str) -> str:
        sys_prompt = "Ты редактор Археон. Переработай текст с учетом правок, сохранив структуру и объем 1500-2000 симв."
        user_msg = f"ТЕКСТ:\n{original_post}\n\nПРАВКИ:\n{edits}"
        try:
            response = await self.client.chat.completions.create(
                                    model=self.model,
                messages=[{"role": "user", "content": f"ИНСТРУКЦИЯ:\n{sys_prompt}\n\nЗАДАНИЕ:\n{user_msg}"}],
                max_completion_tokens=5000
            )
            return markdown_to_html(clean_ai_response(response.choices[0].message.content.strip()))
        except Exception:
            return original_post

    def _get_default_system_prompt(self) -> str:
        return """Ты эксперт компании Археон. Пиши развернуто (1500-2000 симв), профессионально. 
ПРАВИЛА ЯЗЫКА:
1. Пиши как эксперт, но на понятном для обычного человека (заказчика дома) языке. 
2. Сложные термины кратко поясняй. 
3. Используй обычные дефисы (-) вместо длинных тире. 
4. НИКОГДА не пиши, что у тебя нет доступа к интернету или свежим новостям - пиши уверенно как лидер рынка ИЖС в декабре 2025 года."""

    def _get_photo_analysis_prompt(self) -> str:
        return "Опиши этап работ, материалы, качество и детали на фото как инженер технадзора."
    
    def _get_fallback_source_post(self) -> str:
        return "🏗️ <b>Новости Археон</b>\n\nСледим за рынком ИЖС Крыма. Подробности в следующих выпусках!"

    async def make_news_standalone(self, text: str) -> str:
        return await self.refine_post(text, "Сделай новость полностью автономной, убери отсылки к прошлому.")
        
    async def analyze_video(self, video_path: str) -> str:
        # Упрощенная версия через извлечение кадров (нужен cv2)
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            descs = []
            for i in range(3): # Берем 3 кадра
                cap.set(cv2.CAP_PROP_POS_FRAMES, (total // 4) * (i + 1))
                ret, frame = cap.read()
                if ret:
                    cv2.imwrite("temp_frame.jpg", frame)
                    d = await self.analyze_photo("temp_frame.jpg")
                    descs.append(d)
            cap.release()
            return "Анализ видео: " + " ".join(descs)
        except Exception:
            return "Видео процесса строительства Археон."
