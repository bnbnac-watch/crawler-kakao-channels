import asyncio
import logging
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from watch_contract import BaseCrawler, RenderCrawler, Item, CrawlerException

logger = logging.getLogger(__name__)

_BASE_URL = "https://pf.kakao.com"
_POSTS_API_URL = _BASE_URL + "/rocket-web/web/profiles/{channel_id}/posts?includePinnedPost=true"
_API_TIMEOUT_SECONDS = 10
_ICON_MIN_SIZE = 50
_CONTENT_IMAGE_ALT = "이미지"  # 카카오 채널이 게시글 사진에 공통으로 붙이는 alt (프로필/QR 등은 다른 alt를 씀)


def build_item_id(href: str, text: str) -> str:
    """seen_items와 대조되는 키. API 경로와 렌더 경로가 같은 글에 대해 바이트 단위로 같은 값을
    만들어야 하므로 두 경로가 반드시 이 함수를 거친다 — 어긋나면 기존 글이 새 글로 오인식된다."""
    return f"{href}::{text}"


class KakaoPostsApiCrawler(BaseCrawler):
    """채널 페이지가 내부적으로 호출하는 posts JSON API를 직접 호출한다 (비공개 API).

    렌더 경로(KakaoChannelsCrawler)와 같은 Item을 만든다 — URL은 permalink(http://로 옴)를 쓰지 않고
    채널/글 id로 조합하고, 텍스트는 목록 앵커가 보여주는 제목+본문 미리보기를 재현한다.
    응답 형식이 예상과 다르면 일부만 쓰지 않고 통째로 CrawlerException을 던진다 — 호출자가
    렌더 경로로 폴백하게 해서 두 경로의 결과가 섞이지 않게 한다.
    """

    async def crawl(self, channel_id: str) -> list[Item]:
        url = _POSTS_API_URL.format(channel_id=channel_id)
        try:
            timeout = aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as res:
                    if res.status != 200:
                        raise CrawlerException(f"posts API 응답 {res.status}")
                    data = await res.json(content_type=None)
        except CrawlerException:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            raise CrawlerException(f"posts API 호출 실패: {type(e).__name__}: {e}") from e

        items = self.parse_posts(data, channel_id)
        logger.info("posts API 파싱 완료: channel=%s, %d개", channel_id, len(items))
        return items

    def parse_posts(self, data, channel_id: str) -> list[Item]:
        if not isinstance(data, dict):
            raise CrawlerException("posts API 응답이 객체가 아님")
        posts = data.get("items")
        if not isinstance(posts, list) or not posts:
            raise CrawlerException("posts API 응답에 items가 없거나 비어 있음")

        items = []
        for post in posts:
            if not isinstance(post, dict):
                raise CrawlerException("posts API 항목 형식 오류")
            post_id = post.get("id")
            title = post.get("title")
            contents = post.get("contents", [])
            if post_id is None or not isinstance(title, str) or not isinstance(contents, list):
                raise CrawlerException("posts API 항목에 id/title/contents가 없거나 형식이 다름")

            body = "".join(
                block["v"].strip()
                for block in contents
                if isinstance(block, dict) and block.get("t") == "text" and isinstance(block.get("v"), str)
            )
            text = title.strip() + body
            href = f"{_BASE_URL}/{channel_id}/{post_id}"
            items.append(Item(id=build_item_id(href, text), title=text, url=href))
        return items


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
                    items.append(Item(id=build_item_id(href, text), title=text, url=href))
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
                    if img.get("alt") != _CONTENT_IMAGE_ALT:
                        continue

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
