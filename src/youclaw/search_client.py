import aiohttp
import logging
import asyncio
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .config import config

logger = logging.getLogger(__name__)

class SearchClient:
    """Client for performing searches via the self-hosted SearXNG engine"""
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def search(self, query: str, use_fallback: bool = True) -> str:
        """
        Perform a search on SearXNG and return a synthesized summary of findings.
        """
        primary_url = config.search_url
        # Stable public instances as Plan B
        fallback_urls = [
            "https://searx.be/search",
            "https://searxng.site/search"
        ]
        
        urls_to_try = [primary_url] + (fallback_urls if use_fallback else [])
        
        for url in urls_to_try:
            logger.info(f"🛰️ Neural Search Attempt on {url}: {query}")
            try:
                params = {"q": query, "format": "json", "safesearch": 1}
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    async with session.get(url, params=params, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            results = []
                            
                            if data.get('infoboxes'):
                                for info in data['infoboxes'][:1]:
                                    results.append(f"DIRECT ANSWER: {info.get('infobox', '')}\nSUMMARY: {info.get('content', '')}")

                            for i, result in enumerate(data.get('results', [])[:5]):
                                title = result.get('title', 'Source')
                                link = result.get('url', '')
                                snippet = result.get('content', '').replace('<b>', '').replace('</b>', '')
                                results.append(f"SOURCE [{i+1}]: {title}\nURL: {link}\nSUMMARY: {snippet}")
                            
                            if results:
                                logger.info(f"✅ Search successful on {url}")
                                return "\n\n".join(results)
                        
                        logger.warning(f"Search node {url} failed with status {response.status}")
            except Exception as e:
                logger.error(f"Search failure on {url}: {e}")
                
        return "## [SYSTEM ALERT: ALL SEARCH NODES OFFLINE] - No live data reached the core."

# Global search client instance
search_client = SearchClient()
