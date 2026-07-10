import logging

from bs4 import BeautifulSoup
from watch_contract import RenderCrawler, Item, CrawlerException

logger = logging.getLogger(__name__)

_BASE_URL = "https://pf.kakao.com"


class KakaoChannelsCrawler(RenderCrawler):
    def render_request(self, params: dict) -> dict:
        channel_id = params["channel_id"]
        return {
            "url": f"{_BASE_URL}/{channel_id}/posts",
            "sleep": 3,
        }

    def parse(self, html: str, params: dict) -> list[Item]:
        channel_id = params["channel_id"]
        url = f"{_BASE_URL}/{channel_id}/posts"
        try:
            soup = BeautifulSoup(html, "html.parser")
            items = []
            seen_hrefs = set()
            for link in soup.select("a"):
                try:
                    text = link.get_text(strip=True)
                    if not text:
                        continue
                    href = link.get("href")
                    if not href:
                        continue
                    if not href.startswith("http"):
                        href = f"{_BASE_URL}{href}"
                    if href in seen_hrefs or href == url:
                        continue
                    seen_hrefs.add(href)
                    items.append(Item(id=f"{href}::{text}", title=text, url=href))
                except Exception:
                    continue

            logger.info("파싱 완료: channel=%s, %d개", channel_id, len(items))
            return items
        except Exception as e:
            logger.error("parse 예외: channel=%s, %s", channel_id, e)
            raise CrawlerException(str(e)) from e
