
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

    async def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict]:
        """
        Fetch recent news for a stock from Indonesian sources.
        """
        logger.info(f"Fetching news for {ticker}...")
        
        # Search query for Indonesian news
        query = f"{ticker} saham indonesia"
        params = {
            "q": query,
            "hl": "id",
            "gl": "ID",
            "ceid": "ID:id"
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
                    source = item.find("source").text if item.find("source") is not None else "Google News"
                    
                    items.append({
                        "title": title,
                        "link": link,
                        "date": pub_date,
                        "source": source
                    })
                
                logger.info(f"Successfully fetched {len(items)} news items for {ticker}")
                return items

        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {e}")
            return []

    async def get_news_summary_text(self, ticker: str, limit: int = 5) -> str:
        """Get a formatted string of news for the AI prompt."""
        news = await self.fetch_news(ticker, limit)
        if not news:
            return "No recent news found for this stock."
            
        summary = ""
        for i, item in enumerate(news, 1):
            summary += f"{i}. {item['title']} (Sumber: {item['source']}, Tanggal: {item['date']})\n"
        
        return summary

# Singleton
news_fetcher = NewsFetcher()
