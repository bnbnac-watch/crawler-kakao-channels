import pytest
from watch_contract import CrawlerException, Item

import main

BODY = {"channel_id": "_aZJxon"}


def _item(n):
    return Item(id=f"https://pf.kakao.com/_aZJxon/{n}::t{n}", title=f"t{n}", url=f"https://pf.kakao.com/_aZJxon/{n}")


async def test_crawl_items_uses_api_and_skips_render_when_api_succeeds(monkeypatch):
    async def fake_api(channel_id):
        return [_item(1)]
    async def fake_render(body):
        raise AssertionError("API가 성공하면 렌더링을 호출하면 안 된다")
    monkeypatch.setattr(main._api_crawler, "crawl", fake_api)
    monkeypatch.setattr(main, "_crawl_via_render", fake_render)

    items, source = await main.crawl_items(BODY)

    assert items == [_item(1)]
    assert source == "api"


async def test_crawl_items_falls_back_to_render_when_api_raises(monkeypatch):
    async def fake_api(channel_id):
        raise CrawlerException("응답 403")
    async def fake_render(body):
        return [_item(2)]
    monkeypatch.setattr(main._api_crawler, "crawl", fake_api)
    monkeypatch.setattr(main, "_crawl_via_render", fake_render)

    items, source = await main.crawl_items(BODY)

    assert items == [_item(2)]
    assert source == "render"


async def test_crawl_items_propagates_error_when_fallback_also_fails(monkeypatch):
    async def fake_api(channel_id):
        raise CrawlerException("api down")
    async def fake_render(body):
        raise Exception("render 실패 (500)")
    monkeypatch.setattr(main._api_crawler, "crawl", fake_api)
    monkeypatch.setattr(main, "_crawl_via_render", fake_render)

    with pytest.raises(Exception, match="render 실패"):
        await main.crawl_items(BODY)
