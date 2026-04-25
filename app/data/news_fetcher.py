
import logging
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class NewsFetcher:
    """Fetches financial news from Indonesian sources using Google News RSS."""

    def __init__(self):
        self.base_url = "https://news.google.com/rss/search"

    async def fetch_news(self, query: str, limit: int = 5, region: str = "ID") -> List[Dict]:
        """
        Fetch recent news based on a query.
        region: "ID" for Indonesian, "US" for international/English.
        """
        logger.info(f"Fetching news for query: {query} (region: {region})...")
        
        params = {
            "q": query,
            "hl": "id" if region == "ID" else "en-US",
            "gl": region,
            "ceid": "ID:id" if region == "ID" else "US:en"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                
                # Parse RSS XML
                root = ET.fromstring(response.text)
                items = []
                
                for item in root.findall(".//item")[:limit]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    source_elem = item.find("source")
                    source = source_elem.text if source_elem is not None else "News Source"
                    
                    items.append({
                        "title": title,
                        "link": link,
                        "date": pub_date,
                        "source": source
                    })
                
                return items

        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {e}")
            return []

    async def get_news_summary_text(self, query: str, limit: int = 5, region: str = "ID") -> str:
        """Get a formatted string of news for the AI prompt."""
        news = await self.fetch_news(query, limit, region)
        
        if not news:
            return f"Tidak ada berita terbaru ditemukan untuk pencarian: {query}."
            
        summary = f"Berita terbaru ({region}) untuk '{query}':\n"
        for i, item in enumerate(news, 1):
            summary += f"{i}. {item['title']} (Sumber: {item['source']}, Tanggal: {item['date']})\n"
        
        return summary

# Singleton
news_fetcher = NewsFetcher()
