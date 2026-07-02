import asyncio
import logging
from watch_contract import BaseCrawler, Item, CrawlerException

logger = logging.getLogger(__name__)

_BASE_URL = "https://pf.kakao.com"


class KakaoChannelsCrawler(BaseCrawler):
    async def crawl(self, page, channel_id: str) -> list[Item]:
        url = f"{_BASE_URL}/{channel_id}/posts"
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)

            links = await page.query_selector_all("a")
            items = []
            seen_hrefs = set()
            for link in links:
                try:
                    text = (await link.inner_text()).strip()
                    if not text:
                        continue
                    href = await link.get_attribute("href")
                    if not href:
                        continue
                    if not href.startswith("http"):
                        href = f"{_BASE_URL}{href}"
                    if href in seen_hrefs or href == url:
                        continue
                    seen_hrefs.add(href)
                    items.append(Item(id=href, title=text, url=href))
                except Exception:
                    continue

            logger.info("파싱 완료: channel=%s, %d개", channel_id, len(items))
            return items
        except Exception as e:
            logger.error("crawl 예외: channel=%s, %s", channel_id, e)
            raise CrawlerException(str(e)) from e
