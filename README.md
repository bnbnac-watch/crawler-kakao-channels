# crawler-kakao-channels

카카오톡 채널(`pf.kakao.com`) 게시글 크롤러. 채널 페이지가 내부적으로 호출하는 posts JSON API를 먼저 직접 호출하고(`BaseCrawler`), 실패하면 `watch-playwright`로 렌더된 HTML을 파싱하는 기존 경로(`RenderCrawler`)로 폴백한다. 컨테이너 하나로 여러 채널을 처리한다(채널 추가는 `crawlers.params.channel_id` INSERT만으로 가능, 재배포 불필요).

## API

### POST /crawl

```json
{"channel_id": "_aZJxon"}
```

`channel_id` 필수 — 없으면 400. 수집 경로는 두 가지다.

1. **API 경로(우선):** `GET https://pf.kakao.com/rocket-web/web/profiles/{channel_id}/posts?includePinnedPost=true`를 직접 호출한다(타임아웃 10초, 브라우저 미경유).
2. **렌더 경로(폴백):** 1번이 실패하면 `https://pf.kakao.com/{channel_id}/posts`를 `watch-playwright`에 렌더 요청(`sleep: 3`초 후 HTML 캡처)한 뒤 파싱한다.

5분 폴링이라 매번 Chromium을 띄우면 `watch-playwright` 호출의 대부분을 이 크롤러가 차지하게 되어, 정상 시에는 렌더링을 건너뛰도록 했다. 어느 경로로 수집했는지는 로그의 `source=api|render`로 남기고, 폴백이 발동하면 이유와 함께 `WARNING`을 남긴다 — 폴백 빈도가 높으면 절약 효과가 없으니 이 로그로 확인한다.

API 응답은 다음 중 하나라도 해당하면 실패로 본다: 네트워크 오류·타임아웃, HTTP 200이 아님, JSON이 아님, `items`가 없거나 비어 있음, 항목 중 하나라도 `id`/`title`/`contents`가 없거나 형식이 다름. 일부만 쓰지 않고 통째로 폴백해서 두 경로의 결과가 섞이지 않게 한다. 예상 밖의 예외(코드 버그 포함)도 폴백으로 처리해 수집이 끊기지 않게 하되, 로그에는 예외 타입을 남긴다.

이 API는 카카오의 공식 API가 아니라 채널 페이지가 쓰는 비공개 엔드포인트라 예고 없이 바뀌거나 막힐 수 있다. 그래서 렌더 경로를 폴백으로 유지한다.

응답: `Item[]` (JSON 배열)

### POST /extract_images

```json
{"url": "https://pf.kakao.com/_aZJxon/12345"}
```

`url` 필수 — 없으면 400. `/crawl`이 잡아오는 건 게시글 링크뿐이고 사진은 그 상세 페이지에
있어서, 목록을 훑을 때마다 매번 모든 게시글의 상세 페이지를 렌더링하면 낭비다. 그래서 이
엔드포인트는 `watch-runner`가 dedup으로 "새 글"이라고 판단한 게시글에 대해서만, 그 URL을
받아 상세 페이지를 렌더링해 이미지만 뽑아온다.

응답: `{"image_urls": string[]}`. 파싱 실패해도 500 대신 빈 배열을 반환한다 — 이미지는
부가 정보라 실패해도 텍스트 알림 자체를 막으면 안 되기 때문.

### GET /health

`{"status": "ok"}`

## 파싱 방식

### API 경로

글마다 `id`, `title`, `contents[]`(본문 텍스트 블록)가 온다. URL은 응답의 `permalink`(`http://`로 온다)를 쓰지 않고 `https://pf.kakao.com/{channel_id}/{id}`로 조합하고, 텍스트는 `title` 뒤에 `contents`의 `t == "text"` 블록 `v`를 구분자 없이 이어 붙인다(각 조각은 `strip`). 목록 앵커의 `get_text(strip=True)`와 같은 값을 만들기 위한 것이다. 한 번에 최대 20개(`has_next`)만 오고, 최신 글만 보면 되므로 첫 페이지만 쓴다.

### 렌더 경로

채널마다 페이지 내부 구조(CSS 클래스 등)가 달라 특정 셀렉터를 쓰지 않는다. 대신 페이지의 모든 `<a>` 태그를 순회하며 텍스트와 href가 둘 다 있는 링크를 아이템 후보로 취급하고, 자기 자신(목록 페이지 URL)이나 이미 본 href는 스킵한다. 채널 구조가 바뀌어도 깨지지 않는 대신, 노이즈(관련없는 링크)가 섞일 여지가 있다 — 현재는 `filter.title_keywords`(runner 단)나 목적지가 테스트용이라 감수하고 있는 상태.

## id (중복 감지 키)

```python
build_item_id(href, text)  # f"{href}::{text}"
```

href만 쓰면 **게시글을 수정해도 같은 id로 취급되어 재알림이 가지 않는다**(카카오 채널 게시글은 URL이 수정 후에도 안 바뀜). 게시글 텍스트를 href에 조합해서, 내용이 바뀌면 id도 바뀌어 다시 새 글로 인식되게 했다. 여기서 텍스트는 제목뿐 아니라 목록에 보이는 본문 미리보기까지 포함한다(예: `10월 8일 석식즐거운 식사시간 되세요.`). 따라서 제목·본문 텍스트 수정은 감지하지만 **사진만 바뀐 수정은 감지하지 못한다**.

**두 경로는 같은 글에 대해 바이트 단위로 같은 id를 만들어야 한다.** `seen_items`와 대조되는 키라서 다르면 기존 글이 전부 새 글로 오인식되어 알림이 몰리고, 경로가 번갈아 쓰일 때마다 중복 알림이 난다. 그래서 두 경로가 모두 `build_item_id`를 거치고, 같은 글을 두 경로로 파싱했을 때 `Item`이 같은지 `tests/test_crawler.py`가 검증한다. 텍스트 구성(`title` + 본문 블록)을 바꾸려면 두 경로를 함께 바꾸고 기존 `seen_items`와의 호환을 먼저 확인해야 한다.

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `WATCH_PLAYWRIGHT_URL` | `http://watch-playwright:8080` | |

## 테스트

```bash
pip install -r requirements-dev.txt
pytest
```

## 포트

| 포트 | 용도 |
|---|---|
| 8080 | aiohttp — 컴포즈 내부에서만 노출 |
