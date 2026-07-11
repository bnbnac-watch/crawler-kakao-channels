# crawler-kakao-channels

카카오톡 채널(`pf.kakao.com`) 게시글 크롤러. `RenderCrawler` 구현 — `watch-playwright`를 거쳐 렌더된 HTML을 파싱만 한다. 컨테이너 하나로 여러 채널을 처리한다(채널 추가는 `crawlers.params.channel_id` INSERT만으로 가능, 재배포 불필요).

## API

### POST /crawl

```json
{"channel_id": "_aZJxon"}
```

`channel_id` 필수 — 없으면 400. 내부적으로 `https://pf.kakao.com/{channel_id}/posts`를 `watch-playwright`에 렌더 요청(`sleep: 3`초 후 HTML 캡처)한 뒤 파싱한다.

응답: `Item[]` (JSON 배열)

### GET /health

`{"status": "ok"}`

## 파싱 방식

채널마다 페이지 내부 구조(CSS 클래스 등)가 달라 특정 셀렉터를 쓰지 않는다. 대신 페이지의 모든 `<a>` 태그를 순회하며 텍스트와 href가 둘 다 있는 링크를 아이템 후보로 취급하고, 자기 자신(목록 페이지 URL)이나 이미 본 href는 스킵한다. 채널 구조가 바뀌어도 깨지지 않는 대신, 노이즈(관련없는 링크)가 섞일 여지가 있다 — 현재는 `filter.title_keywords`(runner 단)나 목적지가 테스트용이라 감수하고 있는 상태.

## id (중복 감지 키)

```python
items.append(Item(id=f"{href}::{text}", title=text, url=href))
```

href만 쓰면 **게시글을 수정해도 같은 id로 취급되어 재알림이 가지 않는다**(카카오 채널 게시글은 URL이 수정 후에도 안 바뀜). 게시글 텍스트를 href에 조합해서, 내용이 바뀌면 id도 바뀌어 다시 새 글로 인식되게 했다.

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `WATCH_PLAYWRIGHT_URL` | `http://watch-playwright:8080` | |

## 포트

| 포트 | 용도 |
|---|---|
| 8080 | aiohttp — 컴포즈 내부에서만 노출 |
