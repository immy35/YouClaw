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
            params = {
                "q": query,
                "format": "json",
                "safesearch": 1
            }
            
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, params=params, timeout=15) as response:
                    if response.status != 200:
                        logger.error(f"Search engine returned status {response.status}")
                        return f"## [SYSTEM ALERT: SEARCH NODE OFFLINE (Status {response.status})]"
                    
                    data = await response.json()
                    results = []
                    
                    # 1. Capture Infobox / Answer
                    if data.get('infoboxes'):
                        for info in data['infoboxes'][:1]:
                            infobox_text = f"DIRECT ANSWER: {info.get('infobox', '')}\nSUMMARY: {info.get('content', '')}"
                            results.append(infobox_text)

                    # 2. Capture regular results
                    for i, result in enumerate(data.get('results', [])[:5]):
                        title = result.get('title', 'Unknown Source')
                        link = result.get('url', '')
                        snippet = result.get('content', 'No details available.')
                        date = result.get('publishedDate', 'Recent')
                        
                        # Clean snippet
                        snippet = snippet.replace('<b>', '').replace('</b>', '')
                        results.append(f"SOURCE [{i+1}]: {title} ({date})\nURL: {link}\nSUMMARY: {snippet}")
                    
                    if not results:
                        logger.warning("Search returned 0 results.")
                        return "## [SYSTEM WARNING: NEURAL SEARCH RETURNED NO LIVE DATA]"
                    
                    logger.info(f"✅ Search complete. Found {len(results)} items.")
                    return "\n\n".join(results)
                    
        except Exception as e:
            logger.error(f"Search Execution Fault: {e}")
            return f"Neural Search Error: {str(e)}"

# Global search client instance
search_client = SearchClient()
