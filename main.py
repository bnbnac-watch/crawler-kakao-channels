import logging
import os
from dataclasses import asdict

import aiohttp
from aiohttp import web

from crawler import KakaoChannelsCrawler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WATCH_PLAYWRIGHT_URL = os.getenv("WATCH_PLAYWRIGHT_URL", "http://watch-playwright:8080")

# 에러 알림 폭주로 임시 차단. 원인 정리되면 False로 되돌린다.
CRAWL_DISABLED = True

_crawler = KakaoChannelsCrawler()


async def health(request):
    return web.json_response({"status": "ok"})


async def crawl(request):
    if CRAWL_DISABLED:
        logger.warning("crawl 비활성화 상태 - 빈 배열 반환")
        return web.json_response([])

    try:
        body = await request.json()
        channel_id = body.get("channel_id")
        if not channel_id:
            raise web.HTTPBadRequest(reason="channel_id required")

        spec = _crawler.render_request(body)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(f"{WATCH_PLAYWRIGHT_URL}/render", json=spec) as res:
                data = await res.json()
                if res.status != 200:
                    raise Exception(f"render 실패 ({res.status}): {data.get('detail', '')}")
        items = _crawler.parse(data["html"], body)
        logger.info("crawl 완료: channel=%s, %d개", channel_id, len(items))
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
