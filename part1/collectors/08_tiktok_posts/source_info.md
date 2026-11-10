# 소스 8: TikTok 게시물

- 확인일: 2026-11-10 (미국 IP, 화면이 뜨는 Chrome, 로그인 없음)
- 확인 대상: `@deathwishcoffee` 프로필, `#deathwishcoffee` 해시태그 페이지, 검색 페이지 1건, oEmbed 2건, 브랜드 프로필 4건(핸들 확인용). TikTok 도메인 요청은 총 11회.
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정, 문서에서 읽음, 또는 미확인
- 요약: **퍼즐은 뜨지 않았다. 그러나 브랜드 자신의 게시물 목록, 해시태그 게시물 목록, 검색 결과는 모두 비어 있었다.** 데이터가 나온 곳은 프로필의 "Reposts" 탭 하나뿐이다.

## 1. 이 소스가 주는 것
TikTok 영상 게시물 한 건(작성자, 조회수, 좋아요, 날짜 등). 브리프는 "브랜드 관련 상위 게시물"이다. 로그인 없이 직접 수집하면 **브랜드 계정이 다시 올린(repost) 크리에이터 영상**만 얻을 수 있었다. 이 영상들은 대부분 브랜드 제휴 크리에이터의 광고성 게시물이다.

## 2. 접근 방법
로그인이 필요 없다. 페이지를 열면 페이지가 스스로 보내는 요청의 응답을 가로채 저장한다(`cap_gatc.py`와 같은 방식). 서명이나 토큰을 직접 만들어 API를 부르지 않았다.

| 표면 | 주소 | 퍼즐 | 페이지 자체 API 응답 | 결과 |
|---|---|---|---|---|
| 프로필 | `https://www.tiktok.com/@deathwishcoffee` | 없음 ✅ | `/api/post/item_list/` 두 번 호출, **HTTP 200이지만 본문 0바이트** ✅ | 화면에 "Something went wrong" ✅ (`samples/profile_videos_tab_error.png`) |
| 프로필 Reposts 탭 | 같은 페이지가 `/api/repost/item_list/`를 자동 호출 | 없음 ✅ | **게시물 24건분 응답**(본문 679,675자) | 12건 해석 ✅, 아래 4번 |
| 해시태그 | `https://www.tiktok.com/tag/deathwishcoffee` | 없음 ✅ | `/api/challenge/detail/` 정상, `/api/challenge/item_list/` **200이지만 본문 0바이트** ✅ | 화면에 "Something went wrong" ✅ |
| 검색 | `https://www.tiktok.com/search/video?q=death%20wish%20coffee` | 없음 ✅ | 10초 동안 검색 API 호출 자체가 보이지 않았다 ✅ | 탭(Top, Users, Videos, LIVE, Photo)만 있고 본문은 빈 뼈대 화면 (`samples/search_page_skeleton.png`) |
| oEmbed | `https://www.tiktok.com/oembed?url=<영상 주소>` | 없음 ✅ | HTTP 200 JSON | 5번 참고 |

- 한국 IP 사전 조사와 다른 점: 한국에서는 해시태그와 검색에서 슬라이더 퍼즐이 떴다. 미국 IP에서는 **한 번도 뜨지 않았다** ✅. 대신 빈 응답으로 막힌다.
- 빈 응답의 원인(자동화 탐지인지, 비로그인 제한인지, 일시 오류인지)은 모른다 ❓. 재시도, 다른 시간대, 헤드리스는 시험하지 않았다 ❓.
- 프로필 HTML의 `__UNIVERSAL_DATA_FOR_REHYDRATION__` 스크립트는 있다 ✅. 안에 `webapp.user-detail`이 있고 사용자 정보와 통계가 들어 있지만 **`itemList`는 빈 배열**이다 ✅ (`samples/profile_user_detail.json`). 해시태그 페이지의 같은 스크립트에는 해시태그 정보가 아예 없다 ✅.
- 요청 수: 프로필 1회로 계정 통계와 Reposts 목록을 얻는다. 요청 간격 5초 이상, 프로필 1회당 약 12초 대기했다.

## 3. 브랜드 매칭과 공식 핸들
| 브랜드 | 핸들 | 근거 | 인증 | 팔로워 |
|---|---|---|---|---|
| Batiste | `@batiste` | 공식 사이트 batistehair.com HTML에 링크 ✅, 프로필 열림 ✅ | ✅ | 508,717 |
| Living Proof | `@livingproofinc` | livingproof.com HTML에 링크 ✅, 프로필 열림 ✅ | ✅ | 104,655 |
| Death Wish Coffee | `@deathwishcoffee` | 프로필 열림 ✅ (사이트 HTML에는 링크가 없었다) | ✅ | 371,950 |
| Black Rifle Coffee | `@blackriflecoffee` | 사이트가 403이라 링크를 못 봤다. **핸들을 추측해서 열었더니** 이름 "Black Rifle Coffee Company"로 열렸다 ✅ | ✅ | 606,784 |
| Jinx | `@jinx` | thinkjinx.com HTML에 링크 ✅, 프로필 열림 ✅ | ✅ | 56,013 |

- 다섯 계정 모두 `verified: true`, `isOrganization: 1` ✅ (`samples/handles_four_brands.json`, `profile_user_detail.json`). 영상 수는 336~1,613.
- 브랜드 매칭은 핸들로 한다. 브랜드를 언급한 다른 사람의 게시물을 찾으려면 해시태그나 검색이 필요한데 지금은 비어 있다.

## 4. 원본 구조
Reposts 응답은 이름 있는 JSON이다. 한 게시물은 `itemList[]`의 한 항목이다(`samples/repost_items_3.json`에 3건, `repost_items_12_table.json`에 12건 요약).

| 항목 | 위치 | 확인 |
|---|---|---|
| 게시물 ID | `id` | ✅ |
| 주소 | 만들어야 한다: `https://www.tiktok.com/@<author.uniqueId>/video/<id>` | ✅ 이 주소로 oEmbed가 200을 돌려줬다 |
| 캡션 | `desc` | ✅ |
| 작성 시각 | `createTime`(초 단위, UTC) | ✅ 예: 1780058820 = 2026-05-29 |
| 작성자 핸들, 인증 | `author.uniqueId`, `author.verified` | ✅ |
| 조회수 | `stats.playCount`, `statsV2.playCount` | ✅ |
| 좋아요 | `stats.diggCount` | ✅ |
| 댓글, 공유 | `stats.commentCount`, `stats.shareCount` | ✅ |
| 저장 수 | `stats.collectCount` | ✅ |
| 해시태그 | `challenges[].title`, `textExtra[].hashtagName` | ✅ 일부 게시물은 `challenges`가 없다(12건 중 2건) |
| 멘션 | `textExtra[].userUniqueId` | ✅ 브랜드 멘션이 여기에 들어 있다 |
| 사운드 | `music.title`, `music.authorName`, `music.original` | ✅ |
| 길이(초) | `video.duration` | ✅ 6~107초 |
| 광고 표시 | `isAd` | ✅ 값은 있다. 뜻은 ❓ (아래 참고) |

- **광고/제휴 표시가 애매하다.** 12건 중 `isAd: true`는 4건이다. 그런데 캡션에 `#sponsored #sponsoredad`가 있고 `#DWCPartner`가 달린 게시물도 `isAd: false`다 ✅. 반대로 `#ad`가 있는 게시물은 `isAd: true`다 ✅. "유료 제휴(paid partnership)"라는 별도 필드는 못 봤다. 제휴 여부는 `isAd`와 해시태그(`#ad`, `#sponsored`, `#DWCPartner`)를 함께 봐야 하는 것으로 보인다 ❓.
- **숫자가 반올림되어 있는 것으로 보인다.** 큰 값은 유효숫자 3자리처럼 보인다(46100, 121700, 1400000). 작은 값은 정확하다(2776, 692) ❓. 정확도 확인은 못 했다.
- 응답에 영상 파일 주소(서명이 붙은 만료 주소)와 작성자 아바타 주소가 들어 있다. 이번 샘플에는 저장하지 않았다.
- 응답 안에 음악 서비스 토큰이 섞여 있다. 저장하지 말 것.
- Reposts 응답은 `cursor: "24"`, `hasMore: false`다. 24건이 전부로 보이나 12건만 해석했다(본문 일부만 저장) ❓.

### 해시태그 통계 (`samples/challenge_detail_deathwishcoffee.json`)
`/api/challenge/detail/`은 정상 응답한다 ✅. `statsV2`에 **영상 8,715개, 조회 40,301,273회**가 있다. 같은 응답의 `stats.videoCount`는 0이라 `statsV2`를 써야 한다 ✅. 게시물 목록은 없다.

### 계정 통계 (`samples/profile_user_detail.json`)
`statsV2`: 팔로워 371,950, 총 좋아요 2,132,731, 영상 1,054 ✅. `ttSeller: true`와 `commerceUserInfo`도 있다(소스 9 참고).

## 5. oEmbed
`https://www.tiktok.com/oembed?url=https://www.tiktok.com/@<핸들>/video/<id>` (`samples/oembed_*`)
- 영상 2건 모두 HTTP 200 ✅. 로그인과 서명이 필요 없다.
- 돌아온 것: `html`(플레이어 iframe), `embed_product_id`(영상 ID), `width`, `height`, `provider_name`, `type`, `version` ✅.
- **없는 것: 제목, 작성자 이름, 작성자 주소, 썸네일, 조회수, 좋아요, 날짜** ✅. 문서에는 제목과 작성자가 있는 것으로 알려져 있으나 이 두 건에서는 오지 않았다. 다른 영상은 다를 수 있다 ❓.
- 쓸모: 영상 하나가 살아 있는지 확인하는 용도 정도다.

## 6. "상위 게시물"을 무엇으로 볼 수 있나
| 후보 | 지금 가능한가 | 비고 |
|---|---|---|
| 브랜드 자신의 게시물을 조회수순 | 아니오. `post/item_list`가 비어 있다 ✅ | 프로필의 Popular 정렬 탭은 시험하지 않았다 ❓ |
| 브랜드가 리포스트한 크리에이터 영상 | 예 ✅ (24건 안팎) | 조회수순이 아니다. 리포스트한 순서로 보인다. 브랜드가 고른 제휴 영상이므로 "브랜드가 밀어주는 콘텐츠"로 읽힌다 |
| 해시태그의 게시물 | 아니오 ✅ | 해시태그 총량(영상 수, 조회수)만 얻는다 |
| 검색 결과 | 아니오 ✅ | 빈 화면 |

## 7. 항목 식별과 재실행
- 고유 키: 게시물 ID(`id`). 전 세계에서 유일한 숫자다.
- 다시 돌리면 같은 ID의 행의 조회수, 좋아요 등을 갱신한다. 시간에 따른 변화를 보려면 수집 시각과 함께 이력을 쌓아야 한다.
- 대조용 주소: `https://www.tiktok.com/@<핸들>/video/<id>`

## 8. 이 소스에서 얻을 수 없는 것
- 브랜드 자신의 게시물 목록(지금은 빈 응답)
- 브랜드를 언급한 일반 사용자의 게시물, 해시태그/검색 결과
- 광고비, 노출량, 광고 여부의 확정(`isAd`는 참고용)
- 댓글 내용, 팔로워 목록(수집 대상 아님)

## 9. 이걸로 볼 수 있는 것
Death Wish Coffee Reposts 12건 기준이다(`samples/repost_items_12_table.json`).
- **제휴 크리에이터 중심:** 12건 중 5건에 `#DWCPartner` 등 제휴 표시가 있고 4건이 `isAd: true`다. 브랜드가 크리에이터 제휴를 리포스트로 모아 보여준다.
- **조회수 편차가 크다:** 692회부터 1,400,000회까지. 제휴 크리에이터 규모에 좌우된다. 인증 계정의 게시물이 항상 높지는 않다.
- **해시태그 규모:** `#deathwishcoffee`는 영상 8,715개, 조회 약 4,030만이다. 브랜드끼리 비교하려면 다섯 브랜드의 해시태그 통계를 같은 방식으로 모으면 된다(이번에는 DWC만 확인).
- **계정 규모:** 팔로워는 Black Rifle 60.7만, Batiste 50.9만, Death Wish 37.2만, Living Proof 10.5만, Jinx 5.6만.

## 10. 정해야 할 것
1. **"상위 게시물"의 정의.** 직접 수집으로는 브랜드 리포스트와 해시태그 통계만 나온다. 그것을 허용할지, 유료 공급자를 쓸지.
2. **유료 공급자(문서에서 읽음, 가입/호출은 안 했다) ❓:**

| 공급자 | 해시태그/키워드 검색 | 가격 | 필드 이름 |
|---|---|---|---|
| Apify `clockworks/tiktok-scraper` | 해시태그 지원(`hashtags` 입력), 키워드 지원(`searchQueries` 입력) | 1,000건당 1.70달러부터 | `id`, `webVideoUrl`, `text`, `createTime`, `createTimeISO`, `playCount`, `diggCount`, `shareCount`, `collectCount`, `commentCount`, `authorMeta`(`name`, `verified`, `fans` 등), `musicMeta`, `videoMeta`(`duration` 등), `isAd`, `isSponsored`, `hashtags`, `mentions` |
| Bright Data TikTok Scraper | 키워드/해시태그 게시물 검색 지원, 프로필 게시물, 검색 URL 지원 | 1,000건당 1.5달러(종량제), 월 5,000건 무료 | `post_id`, `url`, `description`, `create_time`, `digg_count`, `share_count`, `collect_count` 등 |

   - 다섯 브랜드 × 상위 N건이면 비용은 적다. 예: 브랜드당 100건이면 500건, 0.9달러 안팎(위 단가 기준).
   - ScrapeCreators(문서 기준 1,000건당 0.99~1.88달러)는 프로필 영상 엔드포인트가 있으나 해시태그/키워드 검색은 확인하지 못했다 ❓.
3. **재시도 정책.** 빈 응답이 일시적인지 확인하려면 다른 시간에 한 번 더 시험하고, 프로필의 Popular 정렬 탭도 확인할 필요가 있다.
4. **영상 파일.** 응답에 영상 주소가 있지만 서명이 붙은 만료 주소다. 과제가 영상 파일을 요구하면 별도 판단이 필요하다. 이번에는 내려받지 않았다.
5. **Black Rifle 핸들.** 추측으로 열어 확인했다. 사이트 링크로 재확인할지.

## 11. Apify 시험 (`clockworks/tiktok-scraper`)
- 상태(2026-11-10): **실행 2회 성공, 이 소스 차감액 합계 $0.076** ✅
  - 해시태그 `deathwishcoffee` 10건: $0.038
  - 프로필 `@deathwishcoffee` popular 정렬 10건: $0.038
  - 금액은 실행 기록의 `usageTotalUsd`와 `chargedEventCounts`(결과 10건 × $0.0037 + 시작 $0.001)로 확인했다.
  - 첫 시도(상한 $0.10)는 최소 상한에 걸려 거절됐고 차감은 없었다. 이후 두 실행은 사용자 승인을 받아 상한을 $0.50으로 걸었다.
  - 이 시점 계정 전체 사용액은 $0.62다(모든 소스 스레드 합계).
- 계정: 무료 요금제, 월 한도 $5 ✅. 시험 전 사용액 $0.0001 ✅.

### 단가 (수집기 정의의 `pricingInfos`, 무료 요금제 기준) ✅
| 과금 항목 | 단가 | 비고 |
|---|---|---|
| 결과 1건 | $0.0037 | 1,000건당 $3.70. 10절 표의 "$1.70부터"는 상위 요금제(GOLD) 단가다 |
| 실행 시작 | $0.001 | 실행 1회마다 한 번 |
| 날짜 필터, 인기 필터, 검색 정렬, 영상 내려받기, 국가 지정 | 건당 $0.0013씩 | 각각 따로 붙는다 |
| 댓글 | 건당 $0.00125 | |
| 팔로워/팔로잉 | 건당 $0.004 | |

- 수집기 정의에 `minimalMaxTotalChargeUsd: 0.5`가 있다 ✅. **실행 상한을 $0.10으로 걸면 거절된다** ✅: `maxTotalChargeUsd=0.10`으로 시작 요청을 보냈더니 HTTP 400 `max-total-charge-usd-below-minimum`("allowed minimum of $0.50")이 왔다. 실행은 만들어지지 않았다. 이 수집기는 상한을 $0.50 아래로 걸 수 없다.
- 예상 비용: 10건 실행 1회 = $0.038, 2회(해시태그 + 프로필) = $0.076.

### 입력 형식 (빌드 0.0.646의 입력 스키마) ✅
| 입력 | 값 | 과금 |
|---|---|---|
| `hashtags` | 해시태그 목록 | 없음. **해시태그에는 정렬 옵션이 없다** |
| `profiles` + `profileScrapeSections` | 핸들 목록, 구역 `videos`(기본) / `Reposts` / `Stories` | 없음 |
| `profileSorting` | `latest`(기본) / `popular` / `oldest` | 제목에 과금 표시가 없다. 실제로 안 붙는지는 ❓. 설명에 "popular은 프로필당 약 400~500건까지"라고 적혀 있다 |
| `searchQueries` + `searchSection` | 검색어, 구역 `''`(Top) / `/video` / `/user` | 없음 |
| `videoSearchSorting` | `MOST_RELEVANT`(기본) / `MOST_LIKED` / `LATEST` | 과금. `/video` 구역에서만 동작 |
| `resultsPerPage` | 해시태그, 프로필, 검색어 하나당 건수 | |
| `mostDiggs`, `leastDiggs`, 날짜 필터 | | 과금 |
| `shouldDownloadVideos`, `commentsPerPost` 등 | 기본값이 꺼짐 | 켜면 과금 |

- 조회수 순 정렬 옵션은 어디에도 없다 ✅. 좋아요 순(`MOST_LIKED`)은 검색에만 있고 과금이다.

### 해시태그 실행 결과 (run `DyYwrr03sEqM1ZF2r`, 14.6초, `samples/apify/`)
입력: `hashtags: ["deathwishcoffee"]`, `resultsPerPage: 10`. 내려받기, 댓글, 자막, 필터, 정렬은 모두 껐다. 상태 메시지는 "Scraped 1/1 hashtags"였다.

**과제의 네 값은 10건 모두에 있다** ✅
| 과제 값 | 필드 | 비고 |
|---|---|---|
| 크리에이터 | `authorMeta.name`(핸들), `authorMeta.verified`, `authorMeta.fans`(팔로워) | `authorMeta.nickName`에는 실명일 수 있는 표시 이름이 있어 저장하지 않는다 |
| 조회수 | `playCount`(정수) | 큰 값은 반올림돼 있다(608300, 52400). 직접 수집 때와 같은 양상이다 |
| 좋아요 | `diggCount`(정수) | |
| 날짜 | `createTime`(초), `createTimeISO`(UTC) | |

- 그 밖의 필드 ✅: `id`, `webVideoUrl`(대조용 주소 그대로), `text`, `commentCount`, `shareCount`, `collectCount`, `repostCount`, `hashtags[].name`, `mentions`, `detailedMentions[].name`, `isAd`, `isSponsored`, `isPinned`, `isSlideshow`, `hasTikTokShopProduct`, `videoMeta.duration`, `musicMeta`, `textLanguage`, `searchHashtag`(이름, 조회 40,300,000). `locationMeta`는 2건에만 있다(저장 샘플에서 값 제거).
- **순서는 조회수 순이 아니다** ✅. 좋아요 순도, 날짜 순도 아니다. 1번이 조회 398회, 10번이 608,300회다. 날짜는 2023-11-21부터 2026-11-06까지 섞여 있다. TikTok 해시태그 페이지의 기본 순서로 보인다 ❓.
- **브랜드와의 관련성이 고르지 않다** ✅. 10건 중 2건은 브랜드 계정(`@deathwishcoffee`) 본인 게시물이다. 캡션에 `#deathwishcoffee`가 있는 것은 5건, "Death Wish"라는 말이나 멘션이 있는 것은 8건이다. **2건(8번 `#onthisday`, 10번 `#coffee`)은 캡션, 해시태그, 멘션 어디에도 브랜드가 없다.** 해시태그 피드가 정확한 해시태그 일치만 주지는 않는다.
- **`hashtags` 필드가 빠질 때가 있다** ✅. 7번(브랜드 본인 게시물)은 캡션에 해시태그가 4개 있는데 `hashtags`는 빈 배열이다. 해시태그는 캡션에서도 뽑아야 한다.
- 광고 표시: `isAd`는 10건 모두 false, `isSponsored`는 1건 true다 ✅. 두 필드의 뜻은 아직 모른다 ❓.
- 리포스트 12건과 겹치는 게시물은 **없다** ✅. 그래서 직접 수집한 값과 Apify 값을 같은 게시물로 대조하지는 못했다.
- 실제 화면과 대조(1건, 10번 `@usa.top.list` 영상, 내장 브라우저): 좋아요 8,238, 댓글 382, 저장 2,503이 일치한다 ✅. 공유는 화면에 "11K"로 표시되고 Apify 값은 11000이라 어긋나지 않는다 ✅. 조회수는 영상 페이지에 표시되지 않는다. 날짜는 읽기 전에 "Log in to TikTok" 팝업이 떠서 그 자리에서 멈췄다(아무것도 누르지 않았다) ❓. 대신 7번(브랜드 본인 게시물 `7704412939951901966`)의 조회수 481을 프로필 격자에서 확인했다 ✅.
- 비용 환산: 이번 실행은 10건에 $0.038이다. 1,000건이면 결과 $3.70에 실행 1회당 $0.001이 더해진다(무료 요금제).

### 프로필 popular 실행 결과 (run `n2AqBFXajcYSVlXCC`, 16.2초, `samples/apify/profile_*`)
입력: `profiles: ["deathwishcoffee"]`, `profileScrapeSections: ["videos"]`, `profileSorting: "popular"`, `resultsPerPage: 10`. 부가 기능은 모두 껐다. 상태 메시지는 "Scraped 1/1 profiles"였다.

- **popular 정렬에는 추가 요금이 붙지 않았다** ✅. 과금 건수는 `result: 10`, `actor-start: 1`뿐이다.
- **popular은 좋아요 순이다. 조회수 순이 아니다** ✅. 10건의 `diggCount`가 420,500에서 45,000까지 내림차순이다. 조회수는 순서가 없다. 7번이 690만 회로 가장 많고 1번은 180만 회다.
- **TikTok 화면과 순서와 조회수가 모두 같다** ✅. 내장 브라우저(사용자의 데스크톱 앱 브라우저)에서 `@deathwishcoffee` 프로필을 열고 Popular 탭을 눌렀다. 앞 10칸의 영상 ID와 순서가 Apify 결과와 같았다. 화면의 조회수 10개(1.8M, 2.2M, 640.5K, 702.2K, 919.2K, 226.3K, 6.9M, 330K, 217.8K, 865.8K)도 Apify `playCount`와 같았다. 퍼즐과 로그인 팝업은 뜨지 않았다. 대조표는 `profile_deathwishcoffee_popular_10_table.json`에 있다.
- **조회수의 정밀도는 TikTok 화면 수준이 한계다** ✅. `playCount`는 화면 표시를 숫자로 바꾼 값과 같다(6.9M = 6,900,000). 이보다 정확한 조회수는 이 경로로 얻지 못한다. 좋아요는 1,000 단위가 아니라 정확한 값으로 보인다(420,500, 304,900) ❓.
- **화면 11번째와 12번째 칸은 조회수 510만 회, 130만 회였다** ✅. 좋아요 순 상위 10건 밖에 조회수 상위 게시물이 있다. "조회수 상위 10건"이 필요하면 popular로 더 많이(예: 30~50건) 받아 조회수로 다시 정렬해야 한다.
- 10건 모두 작성자가 `@deathwishcoffee`이고 고정 게시물은 없다(`isPinned` 모두 false) ✅. 날짜는 2022-02~2025-07이며 8건이 2022년이다. 예전 게시물이 상위를 차지한다.
- `isAd`가 10건 중 7건 true다 ✅. 브랜드 본인 게시물에 붙는 것을 보면, 광고로 집행(부스트)한 게시물 표시일 수 있다 ❓.
- 프로필 결과에만 있는 필드: `fromProfileSection`("videos"), `authorMeta.ttSeller`, `authorMeta.commerceUserInfo`, `authorMeta.createTime`. 해시태그 결과에 있던 `searchHashtag`는 없다 ✅.
- 해시태그 실행 결과와 겹치는 게시물은 없다 ✅.
- 참고: 같은 날 Playwright 자동화 Chrome에서는 프로필 영상 목록이 비어 왔다(2절). 내장 브라우저에서는 Latest 16칸과 Popular 16칸이 모두 떴다 ✅. 차이의 원인은 모른다 ❓.

### "상위 게시물"을 정하는 데 필요한 것
- 해시태그 피드만으로는 "상위"가 되지 않는다. 피드 앞쪽 N건을 받아 조회수로 다시 정렬하면 "피드 앞 N건 중 조회수 상위"가 된다. N이 클수록 비용이 늘고, 관련 없는 게시물(이번에 10건 중 2건)을 걸러내는 규칙이 필요하다.
- 프로필 popular은 TikTok 화면의 Popular 탭을 그대로 재현한다. 채점자가 같은 탭을 열어 대조할 수 있다. 다만 기준이 좋아요이고, 크리에이터는 늘 브랜드 본인이다.
- 검색의 `MOST_LIKED`(건당 +$0.0013)는 실행하지 않았다 ❓.

## 12. "상위 게시물"의 정의와 attribute
- **사용자 결정(2026-11-10): 해시태그와 프로필을 병행한다.**
- **확정(2026-11-10, 사용자):** 프로필 popular 10건, 해시태그 30건. 해시태그는 브랜드 전용 태그로 정했다: `#batistedryshampoo`, `#livingproofhair`, `#deathwishcoffee`, `#blackriflecoffee`, `#jinxdogfood`. 근거는 `samples/hashtag_check_20261110.json`이다(`#jinx`는 첫 20건 중 브랜드 0건, `#livingproof`는 11건).
- **수집기는 걸러내지 않는다.** 아래 경로 B의 처리 순서(브랜드 본인 제외, 관련성 필터, 조회수 정렬)는 수집기가 아니라 나중에 파이프라인이 한다. 수집기 요구사항은 `part1/collectors/08_tiktok_posts/spec.md`에 있고, 이 절과 다르면 spec이 우선한다.
- attribute 목록은 아래 제안 그대로이며, 아직 합의 전이다.
- 수집 경로는 Apify `clockworks/tiktok-scraper` 하나다. 두 경로 모두 실제 실행으로 확인했다(11절).

### 경로 A: 브랜드 본인의 인기 게시물 (`surfaced_by = profile_popular`)
- 입력: `profiles: [<브랜드 핸들>]`, `profileSorting: "popular"`, `resultsPerPage: 10`
- 순위: TikTok 프로필 Popular 탭의 순서를 그대로 쓴다(rank 1~10). 화면과 순서, 조회수가 10건 모두 일치했다 ✅. 기준은 좋아요다.
- 크리에이터는 늘 브랜드 본인이다(`creator_is_brand = true`).
- 핸들: `@batiste`, `@livingproofinc`, `@deathwishcoffee`, `@blackriflecoffee`, `@jinx` (3절, 모두 인증 계정)

### 경로 B: 브랜드를 다룬 크리에이터 게시물 (`surfaced_by = hashtag`)
- 입력: `hashtags: [<브랜드 해시태그>]`, `resultsPerPage: N`. 제안 N은 30이다. 해시태그 피드에서 10건 중 8건이 브랜드와 관련 있었으므로, 30건이면 관련 게시물이 20건 이상 남을 것으로 본다 ❓.
- 처리 순서:
  1. 브랜드 본인 계정의 게시물을 뺀다(경로 A와 겹치지 않게 한다).
  2. 관련성 필터를 적용한다. 캡션, 해시태그, 멘션 중 하나에 브랜드 키워드(이름, 핸들, 브랜드 해시태그)가 있어야 통과한다. 통과하지 못한 건수는 실행 기록에 남긴다.
  3. 남은 것을 조회수 내림차순으로 정렬해 상위 10건을 rank 1~10으로 저장한다. 피드에서의 원래 위치는 `feed_position`으로 남긴다.
- 브랜드 해시태그:

| 브랜드 | 해시태그(확정) | 첫 20건 중 브랜드·제품 관련 | 영상 수 |
|---|---|---|---|
| Batiste | `#batistedryshampoo` | 20 ✅ (`#batiste`는 18, Jon Batiste 섞임) | 6,475 |
| Living Proof | `#livingproofhair` | 20 ✅ (`#livingproof`는 11) | 560 |
| Death Wish Coffee | `#deathwishcoffee` | Apify 10건 중 8 ✅ | 8,715 |
| Black Rifle Coffee | `#blackriflecoffee` | 20 ✅ | 18,648 |
| Jinx | `#jinxdogfood` | 20 ✅ (`#jinx`는 0, `#jinxpartner`는 5) | 159 |

### 비용 (무료 요금제 단가 기준, 계산값)
- 1회 전체 수집: 경로 A 5×10건 + 경로 B 5×30건 = 200건 × $0.0037 + 시작 요금 = 약 $0.74
- 저장되는 행은 100건이므로 저장 행 1,000건당 약 $7.4다(받은 결과 1,000건당 $3.70).

### 재실행과 ended
- 게시물의 정체성 키는 `post_id`다. 같은 게시물이라도 경로와 순위는 실행마다 바뀌므로 `surfaced_by`, `rank`와 함께 관측으로 쌓는다.
- 순위 목록에서 빠진 게시물은 삭제된 것이 아니라 상위 10건 밖으로 밀려난 것이다. "ended"를 "이 경로의 상위 목록에서 빠짐"으로 정의할지는 스키마에서 정한다 ❓.

### attribute 제안 (`attribute-candidates.md` 3-4절과 같은 이름을 썼다)
| attribute | Apify 필드 | 확인 | 비고 |
|---|---|---|---|
| post_id | `id` | ✅ | 정체성 키 |
| url | `webVideoUrl` | ✅ | 대조용. 슬라이드쇼는 화면 주소가 `/photo/`인데 `webVideoUrl`이 어떻게 오는지 미확인 ❓ |
| ★ posted_at | `createTimeISO` | ✅ | UTC |
| ★ creator_handle | `authorMeta.name` | ✅ | 공개 핸들만 저장한다 |
| creator_verified | `authorMeta.verified` | ✅ | |
| creator_followers | `authorMeta.fans` | ✅ | 반올림된 값이다. Apify는 371,900을 주고, 프로필 HTML 내장 JSON의 `statsV2` 값은 371,950이다 |
| creator_is_brand | 핸들 비교로 계산 | ✅ | |
| ★ views | `playCount` | ✅ | TikTok 화면 표시 수준의 정밀도 |
| ★ likes | `diggCount` | ✅ | |
| comments, shares, saves | `commentCount`, `shareCount`, `collectCount` | ✅ | |
| caption | `text` | ✅ | |
| hashtags | `hashtags[].name`과 캡션에서 뽑은 해시태그의 합집합 | ✅ | 필드가 비어 오는 경우가 있다 |
| mentions | `detailedMentions[].name` | ✅ | 핸들만 저장한다 |
| sound | `musicMeta.musicName`, `musicMeta.musicOriginal` | ✅ | 음원 작성자 이름은 저장하지 않는다(개인 이름일 수 있다) |
| duration_s | `videoMeta.duration` | ✅ | |
| is_slideshow | `isSlideshow` | ✅ | |
| is_ad, is_sponsored | `isAd`, `isSponsored` | ✅ 값 / ❓ 뜻 | 원본 값만 저장하고 해석하지 않는다 |
| has_shop_product | `hasTikTokShopProduct` | ✅ | 소스 9와 연결 |
| surfaced_by | 계산(`profile_popular:@핸들` / `hashtag:#태그`) | | |
| rank | 계산 | | A는 화면 순서, B는 필터 후 조회수 순위 |
| feed_position | 경로 B의 받은 순서 | ✅ | |
| collected_at, run_id | 수집기 | | 모든 행 공통 |

- 저장하지 않는 것: 표시 이름(`nickName`), 소개글, 아바타, 소개 링크, 위치(`locationMeta`), 영상·표지·자막의 서명 주소, 음원 작성자 이름.
- 브랜드 계정 스냅샷: 경로 A 응답의 `authorMeta`에 팔로워, 총 좋아요, 영상 수가 함께 온다 ✅. 별도 요청 없이 시계열로 쌓을 수 있다.

## samples/
| 파일 | 내용 |
|---|---|
| `repost_items_3.json` | Reposts 응답에서 3건을 줄인 것(아바타, 서명 주소, 토큰 제거) |
| `repost_items_12_table.json` | 해석한 12건의 요약표 |
| `profile_user_detail.json` | 프로필 HTML 내장 JSON의 사용자/통계(소개글, 아바타 제거). `itemList`가 비어 있다 |
| `challenge_detail_deathwishcoffee.json` | 해시태그 상세 응답 원본 |
| `oembed_video_1_with_headers.txt`, `oembed_video_2.json` | oEmbed 응답 |
| `handles_four_brands.json` | 4개 브랜드 프로필 통계 요약 |
| `profile_videos_tab_error.png`, `search_page_skeleton.png` | 빈 응답 때의 화면 |
| `apify/hashtag_deathwishcoffee_10.json` | Apify 해시태그 실행 결과 10건 전부(받은 순서 그대로). 표시 이름, 소개글, 아바타, 서명 주소, 위치 값은 `<removed>`로 바꿨다 |
| `apify/hashtag_deathwishcoffee_10_table.json` | 위 10건의 요약표(순서, 핸들, 날짜, 수치, 주소) |
| `apify/hashtag_run.json` | 입력과 실행 기록(상태, 시각, 상한, 과금 건수, 차감액) |
| `apify/profile_deathwishcoffee_popular_10.json` | Apify 프로필 popular 실행 결과 10건 전부(받은 순서 그대로). 위와 같은 값을 지웠다 |
| `apify/profile_deathwishcoffee_popular_10_table.json` | 위 10건 요약표와 TikTok 화면 Popular 탭의 조회수 표시 |
| `apify/profile_run.json` | 프로필 실행의 입력과 실행 기록 |
| `hashtag_check_20261110.json` | 브랜드별 해시태그 후보 9개의 첫 20건 관련성과 영상 수(내장 브라우저로 태그 페이지 확인) |

줄인 것: Reposts 24건 중 12건만 해석, 그중 3건만 상세 저장. 응답 원본 전체(약 680KB)는 저장하지 않았다.
