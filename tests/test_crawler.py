import pytest
from watch_contract import CrawlerException

from crawler import KakaoChannelsCrawler, KakaoPostsApiCrawler, build_item_id

CHANNEL = "_aZJxon"


def _post(post_id, title, texts=(), **extra):
    return {
        "id": post_id,
        "title": title,
        "contents": [{"t": "text", "v": v} for v in texts],
        **extra,
    }


def _api_response(*posts):
    return {"items": list(posts), "has_next": False}


def _html(*anchors):
    # 카카오 채널 목록 페이지: 글 하나에 같은 href의 앵커가 여러 개 있고 텍스트는 첫 번째에만 있다.
    parts = []
    for href, title, body in anchors:
        parts.append(
            f'<a href="{href}"><span>{title}</span><span>{body}</span></a>'
            f'<a href="{href}"></a><a href="{href}"></a>'
        )
    return "<html><body>" + "".join(parts) + "</body></html>"


# ---------------------------------------------------------------------------
# build_item_id
# ---------------------------------------------------------------------------

def test_build_item_id_joins_href_and_text():
    assert build_item_id("https://pf.kakao.com/_a/1", "제목본문") == "https://pf.kakao.com/_a/1::제목본문"


# ---------------------------------------------------------------------------
# API 경로 파싱
# ---------------------------------------------------------------------------

def test_parse_posts_builds_https_url_from_channel_and_post_id():
    items = KakaoPostsApiCrawler().parse_posts(
        _api_response(_post(114837151, "10월 8일 석식", ["즐거운 식사시간 되세요."])), CHANNEL
    )

    assert len(items) == 1
    assert items[0].url == "https://pf.kakao.com/_aZJxon/114837151"


def test_parse_posts_text_is_title_followed_by_body_without_separator():
    items = KakaoPostsApiCrawler().parse_posts(
        _api_response(_post(114837151, "10월 8일 석식", ["즐거운 식사시간 되세요."])), CHANNEL
    )

    assert items[0].title == "10월 8일 석식즐거운 식사시간 되세요."
    assert items[0].id == "https://pf.kakao.com/_aZJxon/114837151::10월 8일 석식즐거운 식사시간 되세요."


def test_parse_posts_post_without_body_uses_title_only():
    items = KakaoPostsApiCrawler().parse_posts(
        _api_response(_post(114829538, "10월 12일 메뉴입니다")), CHANNEL
    )

    assert items[0].title == "10월 12일 메뉴입니다"


def test_parse_posts_joins_multiple_text_blocks_and_ignores_non_text_blocks():
    post = _post(1, "제목")
    post["contents"] = [
        {"t": "text", "v": "가"},
        {"t": "link", "v": "https://x"},
        {"t": "text", "v": "나"},
    ]

    items = KakaoPostsApiCrawler().parse_posts(_api_response(post), CHANNEL)

    assert items[0].title == "제목가나"


def test_parse_posts_strips_each_text_node_like_html_get_text():
    items = KakaoPostsApiCrawler().parse_posts(
        _api_response(_post(1, " 제목 ", ["  본문  ", "\n둘째\n"])), CHANNEL
    )

    assert items[0].title == "제목본문둘째"


@pytest.mark.parametrize("payload", [
    None,
    [],
    {},
    {"items": None},
    {"items": "x"},
    {"items": []},
])
def test_parse_posts_rejects_unexpected_or_empty_payload(payload):
    with pytest.raises(CrawlerException):
        KakaoPostsApiCrawler().parse_posts(payload, CHANNEL)


@pytest.mark.parametrize("post", [
    {"title": "제목", "contents": []},
    {"id": 1, "contents": []},
    {"id": 1, "title": 5, "contents": []},
    {"id": 1, "title": "제목", "contents": "x"},
    "not-a-dict",
])
def test_parse_posts_rejects_the_whole_response_if_any_post_is_malformed(post):
    good = _post(2, "정상")

    with pytest.raises(CrawlerException):
        KakaoPostsApiCrawler().parse_posts(_api_response(good, post), CHANNEL)


# ---------------------------------------------------------------------------
# 두 경로의 item이 같아야 한다 (seen_items와 대조되는 키라서 바이트 단위로 일치해야 함)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("post_id, title, texts", [
    (114837151, "10월 8일 석식", ["즐거운 식사시간 되세요."]),
    (114829509, "10월 8일 중식", ["맛있는 식사 되세요😊"]),
    (114829538, "10월 12일 메뉴입니다", []),
])
def test_api_item_equals_html_item_for_same_post(post_id, title, texts):
    api_items = KakaoPostsApiCrawler().parse_posts(_api_response(_post(post_id, title, texts)), CHANNEL)
    html_items = KakaoChannelsCrawler().parse(
        _html((f"/{CHANNEL}/{post_id}", title, "".join(texts))), {"channel_id": CHANNEL}
    )

    assert len(html_items) == 1
    assert api_items == html_items


# ---------------------------------------------------------------------------
# parse_images: 게시글 상세 페이지에서 본문 이미지만 추출
# ---------------------------------------------------------------------------

_POST_URL = f"https://pf.kakao.com/{CHANNEL}/114934785"
_PROFILE_IMG = (
    '<img alt="프로필이미지" '
    'src="https://img1.kakaocdn.net/thumb/C100x100.mplusfriend/?fname=https%3A%2F%2Fk.kakaocdn.net%2Fdn%2Fabc%2Fprofile.jpg">'
)


def _content_img(alt, token):
    return f'<img alt="{alt}" src="https://k.kakaocdn.net/dn/{token}/img_xl.jpg">'


# 카카오가 본문 이미지 alt를 "이미지"에서 빈 값으로 바꿨다(2026-10-19 확인) —
# alt 값에 의존하지 않고 이미지 출처로 본문 이미지를 가려내야 한다.
@pytest.mark.parametrize("alt", ["", "이미지"])
def test_parse_images_returns_content_images_regardless_of_alt(alt):
    html = f"<body>{_PROFILE_IMG}{_content_img(alt, 'a')}{_content_img(alt, 'b')}</body>"

    urls = KakaoChannelsCrawler().parse_images(html, _POST_URL)

    assert urls == [
        "https://k.kakaocdn.net/dn/a/img_xl.jpg",
        "https://k.kakaocdn.net/dn/b/img_xl.jpg",
    ]


def test_parse_images_excludes_profile_image():
    assert KakaoChannelsCrawler().parse_images(f"<body>{_PROFILE_IMG}</body>", _POST_URL) == []


def test_parse_images_dedupes_same_url():
    html = f"<body>{_content_img('', 'a')}{_content_img('', 'a')}</body>"

    assert KakaoChannelsCrawler().parse_images(html, _POST_URL) == ["https://k.kakaocdn.net/dn/a/img_xl.jpg"]
