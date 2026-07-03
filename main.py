import logging
import os
from dataclasses import asdict

from aiohttp import web
from playwright.async_api import async_playwright

from crawler import KakaoChannelsCrawler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PLAYWRIGHT_WS = os.getenv("PLAYWRIGHT_WS_ENDPOINT", "ws://watch-playwright:3000")

_crawler = KakaoChannelsCrawler()


async def health(request):
    return web.json_response({"status": "ok"})


async def crawl(request):
    try:
        body = await request.json()
        channel_id = body.get("channel_id")
        if not channel_id:
            raise web.HTTPBadRequest(reason="channel_id required")

        async with async_playwright() as p:
            browser = await p.chromium.connect(PLAYWRIGHT_WS)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                items = await _crawler.crawl(page, channel_id)
                logger.info("crawl 완료: channel=%s, %d개", channel_id, len(items))
                return web.json_response([asdict(item) for item in items])
            finally:
                await context.close()
    except web.HTTPException:
        raise
    except Exception as e:
        logger.error("crawl 실패: %s", e)
        return web.json_response({"error": str(e)}, status=500)


app = web.Application()
app.router.add_get("/health", health)
app.router.add_post("/crawl", crawl)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8080)
