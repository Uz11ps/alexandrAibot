"""Сервис для парсинга постов из источников (Telegram и VK)"""
import logging
import re
from typing import List, Dict, Optional
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from config.settings import settings
from services.vk_service import VKService

logger = logging.getLogger(__name__)


class SourceParserService:
    """Сервис для парсинга постов из различных источников"""
    
    def __init__(self, vk_service: VKService):
        self.vk_service = vk_service
        self.telegram_client: Optional[TelegramClient] = None
        
        # Инициализируем Telegram клиент если есть credentials
        if settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH:
            try:
                self.telegram_client = TelegramClient(
                    'source_parser_session',
                    settings.TELEGRAM_API_ID,
                    settings.TELEGRAM_API_HASH
                )
                logger.info("Telegram клиент для парсинга инициализирован")
            except Exception as e:
                logger.error(f"Ошибка при инициализации Telegram клиента: {e}")
                self.telegram_client = None
        else:
            logger.warning("TELEGRAM_API_ID и TELEGRAM_API_HASH не указаны. Парсинг Telegram каналов будет недоступен.")
    
    async def parse_vk_source(self, url: str, count: int = 10) -> List[Dict[str, str]]:
        """
        Парсит посты из VK группы
        
        Args:
            url: URL группы VK (например, https://vk.com/group_name или https://vk.com/club123456)
            count: Количество постов для получения
            
        Returns:
            Список словарей с текстами постов
        """
        try:
            # Извлекаем screen_name из URL
            # Примеры: https://vk.com/group_name -> group_name
            #          https://vk.com/club123456 -> club123456
            match = re.search(r'vk\.com/([^/?]+)', url)
            if not match:
                logger.error(f"Неверный формат VK URL: {url}")
                return []
            
            group_screen_name = match.group(1)
            posts = self.vk_service.get_group_posts(group_screen_name, count)
            
            # Преобразуем в нужный формат
            result = []
            for post in posts:
                # Формируем прямую ссылку на пост в VK
                # Формат: https://vk.com/wall-{owner_id}_{post_id}
                owner_id = post.get('owner_id')
                post_id = post.get('id')
                direct_url = f"https://vk.com/wall{owner_id}_{post_id}" if owner_id and post_id else url
                
                result.append({
                    'text': post['text'],
                    'source': direct_url,
                    'source_type': 'vk',
                    'metadata': {
                        'post_id': post_id,
                        'date': post.get('date'),
                        'likes': post.get('likes', 0),
                        'reposts': post.get('reposts', 0),
                        'views': post.get('views', 0)
                    }
                })
            
            logger.info(f"Получено {len(result)} постов из VK источника {url}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге VK источника {url}: {e}")
            return []
    
    async def parse_telegram_source(self, url: str, count: int = 10) -> List[Dict[str, str]]:
        """
        Парсит посты из Telegram канала
        
        Args:
            url: URL канала Telegram (например, https://t.me/channel_name)
            count: Количество постов для получения
            
        Returns:
            Список словарей с текстами постов
        """
        if not self.telegram_client:
            logger.error("Telegram клиент не инициализирован. Укажите TELEGRAM_API_ID и TELEGRAM_API_HASH в .env")
            return []
        
        try:
            # Извлекаем username канала из URL
            # Пример: https://t.me/channel_name -> channel_name
            match = re.search(r't\.me/([^/?]+)', url)
            if not match:
                logger.error(f"Неверный формат Telegram URL: {url}")
                return []
            
            channel_username = match.group(1)
            
            # Убеждаемся, что клиент подключен
            if not self.telegram_client.is_connected():
                await self.telegram_client.start()
            
            # Получаем канал
            try:
                entity = await self.telegram_client.get_entity(channel_username)
            except Exception as e:
                logger.error(f"Не удалось получить канал {channel_username}: {e}")
                return []
            
            # Получаем сообщения из канала
            messages = []
            async for message in self.telegram_client.iter_messages(entity, limit=count):
                # Пропускаем сообщения без текста
                if not message.text or not message.text.strip():
                    continue
                
                # Формируем прямую ссылку на сообщение в Telegram
                # Формат: https://t.me/channel_username/message_id
                direct_url = f"{url.rstrip('/')}/{message.id}"
                
                messages.append({
                    'text': message.text,
                    'source': direct_url,
                    'source_type': 'telegram',
                    'metadata': {
                        'message_id': message.id,
                        'date': message.date.isoformat() if message.date else None,
                        'views': message.views if hasattr(message, 'views') else None
                    }
                })
            
            logger.info(f"Получено {len(messages)} постов из Telegram источника {url}")
            return messages
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге Telegram источника {url}: {e}")
            return []
    
    async def parse_website(self, url: str) -> List[Dict[str, str]]:
        """
        Парсит текстовое содержимое веб-сайта и ищет ссылки на статьи, если это главная страница
        """
        import httpx
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Если это главная страница (например, DomClick), ищем ссылки на статьи
                    articles_data = []
                    if any(domain in url for domain in ['blog.domclick.ru', 'pikabu.ru', 'ria.ru']):
                        # Ищем ссылки, которые похожи на статьи (обычно длинные пути или специальные классы)
                        links = soup.find_all('a', href=True)
                        seen_urls = set()
                        
                        for link in links:
                            href = link['href']
                            full_url = urljoin(url, href)
                            
                            # Простая фильтрация ссылок на статьи для DomClick и подобных
                            if full_url not in seen_urls and len(full_url) > len(url) + 5:
                                if any(x in full_url for x in ['/post/', '/article/', '/news/', '2025']):
                                    seen_urls.add(full_url)
                                    # Заходим в статью (только первые 3 для скорости)
                                    if len(seen_urls) <= 3:
                                        try:
                                            art_resp = await client.get(full_url, headers=headers)
                                            if art_resp.status_code == 200:
                                                art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                                                # Удаляем мусор
                                                for s in art_soup(["script", "style", "nav", "footer"]): s.decompose()
                                                art_text = art_soup.get_text(separator=' ')
                                                clean_art_text = ' '.join(art_text.split())[:3000]
                                                if len(clean_art_text) > 500:
                                                    articles_data.append({
                                                        'text': clean_art_text,
                                                        'source': full_url,
                                                        'source_type': 'website',
                                                        'metadata': {'title': art_soup.title.string if art_soup.title else 'Статья'}
                                                    })
                                        except: continue

                    if articles_data:
                        return articles_data

                    # Если не нашли статей или это уже страница статьи
                    for script in soup(["script", "style"]): script.decompose()
                    text = soup.get_text(separator=' ')
                    clean_text = ' '.join(text.split())[:3000]
                    
                    return [{
                        'text': clean_text,
                        'source': url,
                        'source_type': 'website',
                        'metadata': {'title': soup.title.string if soup.title else 'Без заголовка'}
                    }]
        except Exception as e:
            logger.error(f"Ошибка при парсинге сайта {url}: {e}")
            
        return []

    async def parse_source(self, source_type: str, url: str, count: int = 10) -> List[Dict[str, str]]:
        """
        Парсит посты из источника по типу
        """
        if source_type == "vk":
            return await self.parse_vk_source(url, count)
        elif source_type == "telegram":
            return await self.parse_telegram_source(url, count)
        elif source_type == "website":
            return await self.parse_website(url)
        else:
            # Пытаемся определить по URL
            if 't.me/' in url:
                return await self.parse_telegram_source(url, count)
            elif 'vk.com/' in url:
                return await self.parse_vk_source(url, count)
            else:
                return await self.parse_website(url)
    
    async def parse_all_sources(self, sources: List) -> List[Dict[str, str]]:
        """
        Парсит посты из всех переданных источников
        
        Args:
            sources: Список объектов Source
            
        Returns:
            Объединенный список всех постов из всех источников
        """
        all_posts = []
        
        for source in sources:
            if not source.enabled:
                continue
            
            try:
                posts = await self.parse_source(source.type, source.url, count=10)
                all_posts.extend(posts)
            except Exception as e:
                logger.error(f"Ошибка при парсинге источника {source.url}: {e}")
                continue
        
        logger.info(f"Всего получено {len(all_posts)} постов из {len(sources)} источников")
        return all_posts
    
    async def close(self):
        """Закрывает соединения"""
        if self.telegram_client and self.telegram_client.is_connected():
            await self.telegram_client.disconnect()

