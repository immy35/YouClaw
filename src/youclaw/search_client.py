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

    async def search(self, query: str) -> str:
        """
        Perform a search on SearXNG and return a synthesized summary of findings.
        """
        url = config.search_url
        logger.info(f"🛰️ Neural Search Initiated on {url}: {query}")
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, params={"q": query}) as response:
                    if response.status != 200:
                        logger.error(f"Search engine returned status {response.status}")
                        return f"Search engine offline (Status {response.status})"
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    results = []
                    
                    # 1. Capture Infobox (Direct Answer/Fact Sheet)
                    infobox = soup.select_one('.infobox, aside.infobox')
                    if infobox:
                        title = infobox.select_one('.title, h2')
                        content = infobox.select_one('.content, p')
                        if title and content:
                            results.append(f"DIRECT ANSWER: {title.get_text(strip=True)}\nSUMMARY: {content.get_text(strip=True)}")

                    # 2. Capture regular results
                    articles = soup.select('article.result') or soup.select('.result')
                    for i, article in enumerate(articles[:5]):
                        title_tag = article.select_one('h3 a, .title a')
                        snippet_tag = article.select_one('.content, .snippet')
                        date_tag = article.select_one('.published_date, .date')
                        
                            # Extract all highlight text to ensure key data isn't missed
                            highlights = [h.get_text(strip=True) for h in article.select('.highlight')]
                            if highlights:
                                snippet = f"[KEY DATA: {' | '.join(highlights[:5])}] " + snippet
                            
                            results.append(f"SOURCE [{i+1}]: {title} ({date})\nURL: {link}\nSUMMARY: {snippet}")
                    
                    if not results:
                        logger.warning("Search returned 0 results.")
                        return "No real-time data found in the neural streams."
                    
                    logger.info(f"✅ Search complete. Found {len(results)} items.")
                    return "\n\n".join(results)
                    
        except Exception as e:
            logger.error(f"Search Execution Fault: {e}")
            return f"Neural Search Error: {str(e)}"

# Global search client instance
search_client = SearchClient()
