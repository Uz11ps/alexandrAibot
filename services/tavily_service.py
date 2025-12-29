"""Сервис для поиска информации через Tavily AI Search"""
import logging
from typing import List, Dict, Optional
from tavily import TavilyClient
from config.settings import settings

logger = logging.getLogger(__name__)

class TavilyService:
    """Сервис для выполнения поисковых запросов через Tavily"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TAVILY_API_KEY
        self.client = None
        if self.api_key:
            try:
                self.client = TavilyClient(api_key=self.api_key)
                logger.info("TavilyService инициализирован")
            except Exception as e:
                logger.error(f"Ошибка при инициализации TavilyClient: {e}")
        else:
            logger.warning("TAVILY_API_KEY не установлен. Поиск через Tavily будет недоступен.")

    async def search(self, query: str, search_depth: str = "advanced", max_results: int = 5) -> List[Dict]:
        """
        Выполняет поиск через Tavily
        """
        if not self.client:
            logger.error("TavilyClient не инициализирован")
            return []
            
        try:
            # Tavily client is synchronous, but we can wrap it if needed or use it as is
            # For simplicity in this bot, we'll call it directly since most handlers are async anyway
            # and it's a small bot.
            import asyncio
            
            # Wrap synchronous call in a thread
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.client.search(
                    query=query, 
                    search_depth=search_depth, 
                    max_results=max_results,
                    include_answer=True
                )
            )
            
            results = []
            for res in response.get('results', []):
                results.append({
                    'title': res.get('title'),
                    'text': res.get('content'),
                    'source': res.get('url'),
                    'source_type': 'web_search',
                    'score': res.get('score'),
                    'image': None # Tavily doesn't always provide images in standard search
                })
            
            # Добавляем сам ответ Tavily (answer) если он есть
            if response.get('answer'):
                results.insert(0, {
                    'title': 'Краткий итог поиска',
                    'text': response.get('answer'),
                    'source': 'Tavily AI Answer',
                    'source_type': 'web_answer'
                })
                
            return results
        except Exception as e:
            logger.error(f"Ошибка при поиске через Tavily: {e}")
            return []

