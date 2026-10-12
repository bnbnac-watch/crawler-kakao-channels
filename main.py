import logging
import os
from dataclasses import asdict

import aiohttp
from aiohttp import web

from crawler import KakaoChannelsCrawler, KakaoPostsApiCrawler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WATCH_PLAYWRIGHT_URL = os.getenv("WATCH_PLAYWRIGHT_URL", "http://watch-playwright:8080")

_crawler = KakaoChannelsCrawler()
_api_crawler = KakaoPostsApiCrawler()


async def health(request):
    return web.json_response({"status": "ok"})


async def _crawl_via_render(body: dict):
    spec = _crawler.render_request(body)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
        async with session.post(f"{WATCH_PLAYWRIGHT_URL}/render", json=spec) as res:
            data = await res.json()
            if res.status != 200:
                raise Exception(f"render 실패 ({res.status}): {data.get('detail', '')}")
    return _crawler.parse(data["html"], body)


async def crawl_items(body: dict):
    """posts API를 먼저 시도하고, 어떤 이유로든 실패하면 Playwright 렌더 경로로 폴백한다.

    API는 비공개 엔드포인트라 예고 없이 바뀌거나 막힐 수 있어서, 예상 밖의 예외(코드 버그 포함)도
    폴백으로 처리해 수집이 끊기지 않게 한다. 어느 경로였는지는 호출자가 로그로 남긴다.
    """
    channel_id = body["channel_id"]
    try:
        return await _api_crawler.crawl(channel_id), "api"
    except Exception as e:
        logger.warning(
            "posts API 실패, Playwright로 폴백: channel=%s, %s: %s", channel_id, type(e).__name__, e,
        )
    return await _crawl_via_render(body), "render"


async def crawl(request):
    try:
        body = await request.json()
        channel_id = body.get("channel_id")
        if not channel_id:
            raise web.HTTPBadRequest(reason="channel_id required")

        items, source = await crawl_items(body)
        logger.info("crawl 완료: channel=%s, source=%s, %d개", channel_id, source, len(items))
        return web.json_response([asdict(item) for item in items])
    except web.HTTPException:
        raise
    except Exception as e:
        logger.error("crawl 실패: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def extract_images(request):
    try:
        body = await request.json()
        url = body.get("url")
        if not url:
            raise web.HTTPBadRequest(reason="url required")

        spec = _crawler.render_request_for_images(url)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(f"{WATCH_PLAYWRIGHT_URL}/render", json=spec) as res:
                data = await res.json()
                if res.status != 200:
                    raise Exception(f"render 실패 ({res.status}): {data.get('detail', '')}")
        image_urls = _crawler.parse_images(data["html"], url)
        return web.json_response({"image_urls": image_urls})
    except web.HTTPException:
        raise
    except Exception as e:
        logger.error("이미지 추출 실패: %s", e)
        return web.json_response({"error": str(e)}, status=500)


app = web.Application()
app.router.add_get("/health", health)
app.router.add_post("/crawl", crawl)
app.router.add_post("/extract_images", extract_images)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8080)
