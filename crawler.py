import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from watch_contract import RenderCrawler, Item, CrawlerException

logger = logging.getLogger(__name__)

_BASE_URL = "https://pf.kakao.com"
_ICON_MIN_SIZE = 50


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

    def render_request_for_images(self, post_url: str) -> dict:
        return {"url": post_url, "sleep": 3}

    def parse_images(self, html: str, post_url: str) -> list[str]:
        """게시글 상세 페이지에서 이미지 URL만 추출한다. parse()와 달리 Item을 만들지
        않는다 - watch-runner가 새 글로 판단한 게시글에 한해서만 호출되는 경로라
        여기서는 CrawlerException을 던지지 않고 빈 리스트를 반환해 알림 자체는
        막지 않는다(이미지는 부가 정보).
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            urls = []
            seen = set()
            for img in soup.select("img"):
                try:
                    src = img.get("src") or img.get("data-src")
                    if not src:
                        continue

                    width = img.get("width")
                    height = img.get("height")
                    if width and height:
                        try:
                            if int(width) < _ICON_MIN_SIZE or int(height) < _ICON_MIN_SIZE:
                                continue
                        except ValueError:
                            pass  # width/height가 숫자가 아니면 통과시킴

                    absolute_url = urljoin(post_url, src)
                    if absolute_url in seen:
                        continue
                    seen.add(absolute_url)
                    urls.append(absolute_url)
                except Exception:
                    continue

            logger.info("이미지 추출 완료: url=%s, %d개", post_url, len(urls))
            return urls
        except Exception as e:
            logger.error("이미지 파싱 예외: url=%s, %s", post_url, e)
            return []
