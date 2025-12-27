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
        """
        try:
            match = re.search(r'vk\.com/([^/?]+)', url)
            if not match: return []
            
            group_screen_name = match.group(1)
            posts = self.vk_service.get_group_posts(group_screen_name, count)
            
            result = []
            for post in posts:
                owner_id = post.get('owner_id')
                post_id = post.get('id')
                direct_url = f"https://vk.com/wall{owner_id}_{post_id}" if owner_id and post_id else url
                
                # Извлекаем картинку
                image_url = None
                attachments = post.get('attachments', [])
                for att in attachments:
                    if att.get('type') == 'photo':
                        sizes = att.get('photo', {}).get('sizes', [])
                        if sizes: image_url = sizes[-1].get('url')
                        break
                
                result.append({
                    'text': post['text'],
                    'source': direct_url,
                    'source_type': 'vk',
                    'image': image_url,
                    'metadata': {'post_id': post_id, 'date': post.get('date')}
                })
            return result
        except Exception as e:
            logger.error(f"Ошибка при парсинге VK {url}: {e}")
            return []
    
    async def parse_telegram_source(self, url: str, count: int = 10) -> List[Dict[str, str]]:
        """Парсит посты и МЕДИА из Telegram канала"""
        messages_data = []
        
        # 1. Сначала пробуем Web-версию для быстрого получения картинок (как в вашем примере)
        try:
            import httpx
            from bs4 import BeautifulSoup
            channel_name = url.split('/')[-1]
            web_url = f"https://t.me/s/{channel_name}"
            
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(web_url)
                soup = BeautifulSoup(response.text, 'html.parser')
                web_messages = soup.find_all('div', class_='tgme_widget_message_wrap')
                
                for msg in web_messages[:count]:
                    text_el = msg.find('div', class_='tgme_widget_message_text')
                    if not text_el: continue
                    
                    # ПОИСК КАРТИНКИ (ваш метод)
                    image_url = None
                    photo = msg.find('div', class_='tgme_widget_message_photo_wrap')
                    if not photo: photo = msg.find('div', class_='tgme_widget_message_video_player')
                    if not photo: photo = msg.find('a', class_='tgme_widget_message_inline_image')

                    if photo:
                        style = photo.get('style', '')
                        img_match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
                        if img_match: image_url = img_match.group(1)

                    link_el = msg.find('a', class_='tgme_widget_message_date')
                    direct_url = link_el['href'] if link_el else f"https://t.me/{channel_name}"
                    
                    messages_data.append({
                        'text': text_el.get_text(separator="\n"),
                        'source': direct_url,
                        'source_type': 'telegram',
                        'image': image_url
                    })
        except Exception as e:
            logger.error(f"Web scraping error for {url}: {e}")

        # 2. Если есть Telethon, дополняем текст (он надежнее для длинных постов)
        if self.telegram_client and not messages_data:
            try:
                match = re.search(r't\.me/([^/?]+)', url)
                if match:
                    channel_username = match.group(1)
                    if not self.telegram_client.is_connected(): await self.telegram_client.start()
                    entity = await self.telegram_client.get_entity(channel_username)
                    async for message in self.telegram_client.iter_messages(entity, limit=count):
                        if not message.text: continue
                        direct_url = f"https://t.me/{channel_username}/{message.id}"
                        messages_data.append({
                            'text': message.text,
                            'source': direct_url,
                            'source_type': 'telegram',
                            'image': None
                        })
            except: pass

        return messages_data

    async def fetch_rss(self, url: str) -> List[Dict]:
        """RSS парсинг (как в вашем примере)"""
        import feedparser
        import httpx
        from bs4 import BeautifulSoup
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                feed = feedparser.parse(response.text)
                news_items = []
                for entry in feed.entries[:5]:
                    image_url = None
                    if 'media_content' in entry and len(entry.media_content) > 0:
                        image_url = entry.media_content[0].get('url')
                    if not image_url and 'links' in entry:
                        for link in entry.links:
                            if 'image' in link.get('type', ''):
                                image_url = link.get('href'); break
                    
                    news_items.append({
                        "text": f"{entry.get('title')}\n\n{entry.get('description', entry.get('summary', ''))}",
                        "source": entry.get("link"),
                        "source_type": "rss",
                        "image": image_url
                    })
                return news_items
        except: return []

    async def parse_website(self, url: str) -> List[Dict[str, str]]:
        """Парсинг сайтов с поиском статей"""
        import httpx
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                response = await client.get(url, headers=headers)
                if response.status_code != 200: return []
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Поиск статей на главной
                articles_data = []
                if any(domain in url for domain in ['blog.domclick.ru', 'ria.ru', 'rbc.ru']):
                    links = soup.find_all('a', href=True)
                    seen = set()
                    for link in links:
                        full_url = urljoin(url, link['href'])
                        if full_url not in seen and len(full_url) > len(url) + 5:
                            if any(x in full_url for x in ['/post/', '/article/', '/news/', '2025']):
                                seen.add(full_url)
                                if len(seen) > 3: break
                                try:
                                    art_resp = await client.get(full_url, headers=headers)
                                    art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                                    # Картинка статьи
                                    img_url = None
                                    og_img = art_soup.find("meta", property="og:image")
                                    if og_img: img_url = og_img.get("content")
                                    
                                    for s in art_soup(["script", "style", "nav", "footer"]): s.decompose()
                                    text = ' '.join(art_soup.get_text().split())[:3000]
                                    if len(text) > 500:
                                        articles_data.append({
                                            'text': text,
                                            'source': full_url,
                                            'source_type': 'website',
                                            'image': img_url
                                        })
                                except: continue
                return articles_data if articles_data else [{'text': ' '.join(soup.get_text().split())[:3000], 'source': url, 'source_type': 'website'}]
        except: return []

    async def parse_source(self, source_type: str, url: str, count: int = 10) -> List[Dict[str, str]]:
        if source_type == "vk": return await self.parse_vk_source(url, count)
        if 't.me/' in url: return await self.parse_telegram_source(url, count)
        return await self.parse_website(url)

    async def close(self):
        if self.telegram_client and self.telegram_client.is_connected():
            await self.telegram_client.disconnect()
