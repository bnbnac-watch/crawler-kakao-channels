import asyncio

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from watch_contract import CrawlerException

import crawler
from crawler import KakaoPostsApiCrawler

CHANNEL = "_aZJxon"
GOOD = {"items": [{"id": 1, "title": "제목", "contents": [{"t": "text", "v": "본문"}]}], "has_next": False}


@pytest_asyncio.fixture
async def api_server(monkeypatch):
    state = {"status": 200, "body": GOOD, "raw": None, "delay": 0.0, "calls": 0}

    async def handler(request):
        state["calls"] += 1
        if state["delay"]:
            await asyncio.sleep(state["delay"])
        if state["raw"] is not None:
            return web.Response(status=state["status"], text=state["raw"], content_type="text/html")
        return web.json_response(state["body"], status=state["status"])

    app = web.Application()
    app.router.add_get("/rocket-web/web/profiles/{channel_id}/posts", handler)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(
        crawler, "_POSTS_API_URL",
        f"http://{server.host}:{server.port}" + "/rocket-web/web/profiles/{channel_id}/posts?includePinnedPost=true",
    )
    yield state
    await server.close()


async def test_crawl_returns_items_on_200(api_server):
    items = await KakaoPostsApiCrawler().crawl(CHANNEL)

    assert [i.title for i in items] == ["제목본문"]
    assert api_server["calls"] == 1


async def test_crawl_raises_on_non_200(api_server):
    api_server["status"] = 403

    with pytest.raises(CrawlerException, match="403"):
        await KakaoPostsApiCrawler().crawl(CHANNEL)


async def test_crawl_raises_on_non_json_body(api_server):
    api_server["raw"] = "<html>blocked</html>"

    with pytest.raises(CrawlerException):
        await KakaoPostsApiCrawler().crawl(CHANNEL)


async def test_crawl_raises_on_timeout(api_server, monkeypatch):
    monkeypatch.setattr(crawler, "_API_TIMEOUT_SECONDS", 0.2)
    api_server["delay"] = 1.0

    with pytest.raises(CrawlerException):
        await KakaoPostsApiCrawler().crawl(CHANNEL)


async def test_crawl_raises_when_server_is_unreachable(monkeypatch):
    monkeypatch.setattr(
        crawler, "_POSTS_API_URL", "http://127.0.0.1:1/posts/{channel_id}",
    )

    with pytest.raises(CrawlerException):
        await KakaoPostsApiCrawler().crawl(CHANNEL)
