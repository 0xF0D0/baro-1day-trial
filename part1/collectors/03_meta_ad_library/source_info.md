# 소스 3: Meta Ad Library (Facebook, Instagram 광고 라이브러리)

- 확인일: 2026-11-10 (미국 IP, 화면이 뜨는 Chrome). facebook.com 페이지 로드 12회
- 확인 대상: 브랜드 5개의 페이지 ID 찾기와 활성 광고 개수, 광고 목록 6건(Death Wish 30건, Black Rifle 19건, Batiste 4+8건, Living Proof 30건, Jinx 30건), 상세 화면 2종
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정이거나 미확인

## 1. 이 소스가 주는 것
Facebook 페이지 하나가 지금 집행 중인 광고 목록이다. 한 행은 **광고 1건(Library ID 1개)**이다. 같은 소재(이미지/영상과 문구가 같은 광고)는 "그룹"으로 묶여서 온다(4-2). 광고 문구, 제목, 랜딩 주소, 행동 유도 문구(CTA), 이미지와 영상 파일 주소, 시작일, 노출 지면(플랫폼)이 텍스트로 온다 ✅. 구글 소스와 달리 문구가 그림이 아니라 글자로 온다.

## 2. 접근 방법
- 주소 (페이지 ID 검색):
  `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&view_all_page_id=<페이지 ID>&search_type=page&media_type=all`
- 로그인이 필요 없다 ✅. CAPTCHA나 로그인 벽은 한 번도 뜨지 않았다 ✅. 헤드리스 실행은 확인하지 않았다 ❓.
- **HTTP 상태 코드로 성공을 판단하면 안 된다.** 키워드 검색 주소의 본문은 403으로 왔는데 화면은 정상이었다 ✅. 페이지 ID 주소는 200이었다 ✅. 내용(`~N results` 문구나 `search_results_connection`)으로 판단한다.
- 검색어도 ID도 없는 기본 주소는 6초 뒤에도 빈 화면이었다 ✅(그 뒤는 확인하지 않았다).
- 로드 후 12초 기다리면 목록이 뜬다 ✅.

### 2-1. 데이터가 오는 길 (구글과 다르다)
| 길 | 무엇이 오나 | 상태 |
|---|---|---|
| **첫 HTML 안의 JSON** | 광고 첫 30건 전부. `<script type="application/json" data-sjs>` 안, `...result.data.ad_library_main.search_results_connection` | ✅ 이 경로로 6개 목록을 모두 얻었다 (`samples/list_*.json`) |
| `api/graphql/` `AdLibrarySearchPaginationQuery` | 스크롤하면 나가는 다음 페이지 요청 | ✅ 요청은 나가는데 **전부 "Rate limit exceeded"**(4-5) |
| `api/graphql/` `AdLibraryV3AdCollationDetailsQuery` | "See summary details" 클릭 시, 그룹의 광고 전체 | ✅ |
| `api/graphql/` `AdLibraryV3AdDetailsQuery` | "See ad details" 클릭 시, 광고주 정보 | ✅ |
| `api/graphql/` `useAdLibraryTypeaheadSuggestionDataSourceQuery` | 검색창에 글자를 칠 때 나오는 제안(페이지 ID 포함) | ✅ |

- 즉 첫 30건은 **HTML 한 번**으로 끝난다. graphql을 가로채지 않아도 된다. 가로챌 필요가 있는 것은 30건을 넘는 부분과 상세뿐이다.
- 요청 수: 브랜드당 페이지 로드 1회(30건까지).
- 정중하게 돌린 방법: 로드 사이 15~20초 간격. 첫 30건만 필요하면 스크롤하지 않는다.

## 3. 브랜드 매칭
**페이지 ID로 찾는다.** 키워드 검색은 쓸 수 없다: `Batiste` 키워드는 약 160건이 나오는데 첫 화면부터 다른 회사 광고(The Company Store)가 섞여 있었다 ✅. 기존에 알려진 `death wish coffee` 키워드 약 7,600건도 같은 이유로 못 쓴다(재확인하지 않았다).

### 3-1. 페이지 ID 찾는 방법
검색창에 브랜드명을 치면 "Advertisers" 제안 목록이 뜨고, 그 응답(`typeahead_suggestions.page_results[]`)에 `page_id`, 이름, 팔로워 수, 카테고리, 인증 여부, 인스타 계정이 들어 있다 ✅ (`samples/typeahead_page_results_selected.json`). 브랜드 한 곳당 제안은 10~30개 나온다. 이름이 같은 다른 페이지가 많다(Jinx 연예인 계정, Living Proof 교회 등).

### 3-2. 결과
| 브랜드 | 페이지 이름, 주소 이름 | 페이지 ID | 활성 광고 수 (US) | 공식 근거 |
|---|---|---|---|---|
| Batiste (글로벌 페이지) | Batiste, `@batistedryshampoopage` | `95597922197` | **4** | 파란 인증 ✅, 팔로워 1.18M, 인스타 `batiste_hair` 172K. 광고 랜딩이 ulta.com ✅ |
| Batiste (미국 페이지) | Batiste, `@batisteus` | `230750427654291` | **8** | 파란 인증 ✅, 국가 US, 인스타 `batiste_us` 94K. 랜딩이 `buy.batistehair.com`(브랜드 공식 도메인) ✅ |
| Living Proof | Living Proof, `@livingproofinc` | `40730897173` | **98** | 파란 인증 ✅, 팔로워 466.8K, 인스타 `livingproofinc` 382K, 카테고리 Beauty. 랜딩이 `livingproof.com` ✅ |
| Death Wish Coffee | Death Wish Coffee, `@deathwishcoffee` | `159943490729618` | **47** | 파란 인증 ✅, 팔로워 693.6K, Food & Beverage. 랜딩이 `deathwishcoffee.com` ✅ |
| Black Rifle Coffee | Black Rifle Coffee Company, `@blackriflecoffeeco` | `497476893723547` | **19** | 인증 없음 ❓, 팔로워 2.1M, 인스타 `blackriflecoffee` 1.98M. 랜딩이 `blackriflecoffee.com` ✅ |
| Jinx | Jinx, `@thinkjinx` | `2012712129023317` | **250** | 인증 없음 ❓, 카테고리 Pet Supplies, 인스타 `thinkjinx` 106K. 랜딩이 `thinkjinx.com` ✅ |

- 활성 광고 수는 화면의 `~N results`이고, JSON의 `count`(정수)와 같다 ✅(47, 250 등).
- **Batiste는 페이지가 여러 개다.** 같은 이름 "Batiste"에 국가별 페이지가 있다(독일, 프랑스, 그리스, 네덜란드, 북유럽, 호주, 스페인, 남아공 등 ✅ 제안 목록). 미국에 광고를 내는 페이지는 위 2개를 확인했다. 다른 국가 페이지의 US 광고는 확인하지 않았다 ❓. 두 미국 페이지 모두 지금은 Instagram 전용이다 ✅.
- Living Proof는 `@livingproofuk`(ID `228842154551249`, 국가 표시 IT, 팔로워 같은 466.8K)도 같은 이름으로 나온다. US 활성 광고는 0건이다("No ads match your search criteria") ✅. 수집 대상에서 제외한다.
- 위 숫자는 페이지 하나, 국가 US, 활성만 센 값이다. 끝난 광고(active_status 다른 값)는 로드하지 않았다 ❓.
- `Death Wish Coffee Egypt` 같은 지역 지점 페이지가 따로 있다 ✅. 모두 대상이 아니다.

## 4. 원본 구조

### 4-1. 목록 응답 (`samples/list_*.json`)
`search_results_connection`의 구조:
| 키 | 뜻 | 예시 | 근거 |
|---|---|---|---|
| `count` | 전체 활성 광고 수 | `47` | ✅ 화면 `~47 results`와 같다 |
| `edges[]` | 소재 그룹 배열. 한 번에 약 20~27개 | 20 | ✅ |
| `edges[].node.collated_results[]` | 그 그룹의 광고들(Library ID 하나가 한 항목) | 1~2개 | ✅ |
| `page_info.end_cursor`, `has_next_page` | 다음 페이지 커서 | 있음/없음 | ✅ 값은 있다. 커서로 가져오지는 못했다(4-5) |

- **첫 페이지는 광고 30건 단위로 끊긴다** ✅ (Death Wish: 그룹 20개에 광고 30건, Living Proof와 Jinx: 그룹 27개에 광고 30건). 광고가 30건 이하이면 `has_next_page: false`다(Black Rifle 19, Batiste 4와 8) ✅.
- `count`는 그룹 수가 아니라 **광고 수**로 보인다: Batiste 글로벌 `count 4`, 그룹 2개, 광고 4건 ✅.
- 정렬 기준은 모르겠다. 시작일순이 아니다 ✅(Death Wish: 9/29, 9/29, 9/29, 9/29, 10/12, 10/12, 8/22, 9/15 ... 순서). 노출이 많은 순일 수 있으나 ❓.

### 4-2. 광고 한 건 (`collated_results[]`의 항목)
| 키 | 뜻 | 예시 | 근거 |
|---|---|---|---|
| `ad_archive_id` | Library ID. 광고의 고유 키 | `"2538999246566264"` | ✅ 화면 "Library ID:"와 같다 |
| `collation_id` | 같은 소재 그룹의 ID | `"1108329491692291"` | ✅ |
| `collation_count` | "N ads use this creative and text"의 N. 그룹 첫 항목에만 값이 있고 나머지는 `null` | `2` | ✅ 화면 문구와 일치. 단 그룹 중 7개(Living Proof 27개 중)는 `collation_count`가 `collated_results` 길이보다 크다 ❓ 이유 미확인 |
| `is_active` | 활성 여부 | `true` | ✅ 화면 "Active" 배지 |
| `page_id`, `page_name` | 광고를 낸 페이지 | `159943490729618`, `Death Wish Coffee` | ✅ |
| `start_date` | 시작일. 초 단위 epoch, **태평양 시간 자정** | `1790665200` = 2026-09-29 07:00Z | ✅ 화면 "Started running on Sep 29, 2026"과 일치 |
| `end_date` | 끝난 날짜로 보이는 값 | `1794211200` = 2026-11-09 | ✅ 값은 있다. **뜻은 믿을 수 없다**(6절) |
| `publisher_platform[]` | 노출 지면 | `["FACEBOOK","INSTAGRAM","THREADS"]` | ✅ (7절) |
| `snapshot` | 광고 내용(4-3) | | ✅ |
| `impressions_with_index.impressions_text` | 노출 구간 | 보통 `null`, Batiste 1건만 `"<100"` | ✅ |
| `reach_estimate`, `spend`, `currency`, `total_active_time`, `ad_id`, `report_count`, `fev_info` | 도달, 광고비 등 | 전부 `null` 또는 빈 문자열 | ✅ 121건 전부 |
| `targeted_or_reached_countries` | 타기팅 국가 | `[]` | ✅ 121건 전부 |
| `categories`, `gated_type`, `hide_data_status` | 분류, 노출 제한 상태 | `["UNKNOWN"]`, `"ELIGIBLE"`, `"NONE"` | ✅ 의미 없는 상수 |

### 4-3. `snapshot` (광고 내용)
| 키 | 뜻 | 근거 |
|---|---|---|
| `body.text` | 본문 문구 | ✅ |
| `title` | 제목(카드 아래 굵은 글씨). 이미지, 영상 광고에서는 `null`일 수 있다(Batiste 영상 광고는 전부 `null`) | ✅ |
| `link_description` | 제목 아래 작은 글씨 | ✅ |
| `caption` | 카드에 표시되는 도메인 | ✅ 예: `deathwishcoffee.com`, `www.ulta.com` |
| `link_url` | **랜딩 주소(UTM 포함)** | ✅ |
| `cta_type`, `cta_text` | 행동 유도 | ✅ 관찰한 값: `SHOP_NOW`(91건), `LEARN_MORE`(18), `SEE_DETAILS`(12) |
| `display_format` | 형식 | ✅ 관찰한 값: `DCO`, `DPA`, `IMAGE`, `VIDEO`. `CAROUSEL`이라는 값은 보지 못했다 ❓ |
| `images[]` | 이미지 광고의 파일: `original_image_url`, `resized_image_url`(600px), `watermarked_resized_image_url` | ✅ |
| `videos[]` | 영상 광고의 파일: `video_hd_url`, `video_sd_url`, `video_preview_image_url` | ✅ |
| `cards[]` | 카드형 광고의 카드별 `body`, `title`, `link_url`, `cta_type`, 이미지와 영상 주소 | ✅ |
| `branded_content` | 제휴 광고(Paid partnership)면 `{page_id, page_name, ...}`, 아니면 `null` | ✅ |
| `page_name`, `page_profile_uri`, `page_profile_picture_url`, `page_like_count`, `page_categories` | 광고 카드 위쪽 페이지 정보 | ✅ |
| `byline`, `disclaimer_label`, `extra_*`, `event`, `root_reshared_post` | 이번 데이터에서는 전부 비었다 | ✅ |

**`display_format`별로 미디어가 있는 곳이 다르다** ✅:
| 형식 | 의미 | 미디어 위치 | 관찰 |
|---|---|---|---|
| `IMAGE` | 이미지 1장 | `images[]` | Black Rifle 14, Living Proof 2 |
| `VIDEO` | 영상 1개 | `videos[]` | Black Rifle 5, Batiste 10, Jinx 17, Living Proof 2 |
| `DCO` | 동적 소재(여러 이미지, 문구 조합) | **`cards[]`** (`images[]`는 빈 배열) | Death Wish 30건 전부, Living Proof 24, Jinx 13 |
| `DPA` | 동적 상품 광고(카탈로그) | `cards[]` (카드마다 상품) | Living Proof 2 |

- DCO와 DPA의 `cards[]` 안에 **영상이 들어 있는 경우도 있다** ✅(Death Wish 2개, Living Proof 10개, Jinx 10개). 영상을 모으려면 `videos[]`와 `cards[].video_*_url` 둘 다 봐야 한다.
- 카드가 2~6개이고 카드마다 `link_url`, `title`이 다를 수 있다 ✅.

### 4-4. 같은 소재 그룹 (한 소재가 여러 광고 번호로 나뉨)
- 광고주는 같은 소재를 시작일, 지역, 예산만 바꿔 여러 번 만든다. 라이브러리는 이를 묶어 "N ads use this creative and text"로 보여 준다 ✅.
- **광고 건수와 소재 수가 많이 다르다** ✅: Death Wish 30건의 서로 다른 본문은 14개, Black Rifle 19건은 4개, Jinx 30건은 16개, Living Proof 30건은 6개. 건수로 세면 부풀려진다.
- 같은 그룹 안의 광고도 `publisher_platform`이 다를 수 있다 ✅ (Death Wish `2538999246566264`는 Facebook, Instagram, Threads이고, 같은 그룹의 `4617137888604729`는 Audience Network와 Messenger가 더 있다. `samples/ui_summary_details_modal.png`).

### 4-5. 페이지 넘김 (30건을 넘는 광고)
- 스크롤하면 `AdLibrarySearchPaginationQuery`가 나간다 ✅. 변수: `first: 10`, `cursor: <page_info.end_cursor>`, `viewAllPageID`, `countries: ["US"]`, `activeStatus: "active"`, `sessionID`, `v` 등. `doc_id`는 `24922295957467452` ✅ (`samples/pagination_request_and_ratelimit.json`).
- **응답은 매번 `{"errors":[{"message":"Rate limit exceeded","code":1675004}]}`였다** ✅. Death Wish에서 25번, Jinx에서 24번, 스크롤 한 번에 5~8번씩 연속으로 나갔고(페이지가 스스로 재시도한다) 전부 같은 오류였다.
- **HTTP 상태는 429가 아니라 200이다** ✅(원본 캡처 49건 전부). 오류는 본문에만 있다. 여기서도 상태 코드로 판단하면 안 된다.
- **원인은 데이터센터 VPN IP다** ✅(14절). 같은 스크립트, 같은 로그아웃 새 세션, 같은 Playwright Chrome으로 IP만 한국 가정용 회선으로 바꾸자 넘김 요청 29번이 전부 성공했다. 같은 날 다시 VPN IP로 열자 또 막혀서 시간 경과 때문도 아니다 ✅(14-5). 아래는 그 전에 정리한 사실이다.
- (이전 정리) 확인된 사실: 새 브라우저 세션의 첫 넘김 요청부터 거절됐다(쌓여서 걸린 것이 아니다) ✅. 같은 IP, 같은 세션에서 다른 graphql 요청(필터 옵션, 그룹 상세, 단일 상세)은 넘김 실패 앞뒤로 정상이었다 ✅. 요청은 로그아웃 상태(`av=0`, `__user=0`)였다 ✅. 시험 조건이 매번 "데이터센터 VPN IP + 로그아웃 + 쿠키 없는 새 세션 + Playwright가 띄운 Chrome"으로 같아서, 넷 중 무엇이 원인인지 가를 수 없다. 다른 IP나 사람이 직접 여는 브라우저로는 시험하지 않았다.
- 그래서 **30건을 넘는 광고는 가져오지 못했다**: Death Wish 17건, Living Proof 68건, Jinx 220건이 안 보인다.
- 아직 모르는 것 ❓: 사람처럼 아주 느리게 스크롤하면 되는지, 새 세션에서 되는지, 시간이 지나면 풀리는지, 지금 이 IP에서만 막히는지. 12번의 로드 한도 때문에 더 시도하지 않았다.
- 우회 가능성 ❓(시험하지 않음): 화면에 `Keyword`, `Filters`, `Sort by`가 있다. 키워드, 플랫폼, 미디어 유형, 날짜 필터로 결과를 30건 이하로 쪼개서 각각 첫 HTML로 받는 방법이 있을 수 있다.

## 5. 집중해서 볼 것과 원본의 대응
| 과제가 요구한 것 | 원본에서 얻는 방법 | 상태 |
|---|---|---|
| 지금 도는 모든 광고 | 첫 30건은 HTML에서 | ✅ / **30건 초과는 막힘** (Jinx 250건 중 30건) |
| 미디어 파일 | `images[]`, `videos[]`, `cards[]` 안의 주소를 일반 GET으로 | ✅ 아래 |
| 문구 | `body.text`, `title`, `link_description` | ✅ 텍스트로 온다 |
| 랜딩, CTA | `link_url`, `cta_type` | ✅ (구글에 없던 것) |
| 노출 지면 | `publisher_platform[]` | ✅ |
| 시작일 | `start_date` | ✅ 화면과 대조 |
| 노출량, 광고비, 타기팅 | | **없다**(8절) |

### 5-1. 미디어 파일 내려받기 (Black Rifle 광고 1건 시험)
일반 GET(헤더 없음, 로그인 없음)으로 전부 200이었다 ✅.
| 파일 | content-type | 크기 | 비고 |
|---|---|---|---|
| 이미지 `resized_image_url` (600px) | image/jpeg | 71,531 B | `samples/brcc_image_resized_600.jpg`로 저장 |
| 이미지 `original_image_url` | image/jpeg | 419,987 B | 저장 안 함 |
| 영상 SD | video/mp4 | 1,286,535 B (31초 광고) | 저장 안 함(폴더 용량) |
| 영상 HD | video/mp4 | 5,021,426 B | 3MB 초과라 저장 안 함 |
| 영상 미리보기 | image/jpeg | 169,773 B | 저장 안 함 |

- **주소에 만료와 서명이 들어 있다** ✅. 주소 끝의 `oe=<16진수>`가 만료 시각(초 단위 epoch)이다. 2026-11-10 05:18Z에 받은 주소들의 만료는 11-14 13:33Z~16:58Z였다. 즉 **약 3.3~4.5일 뒤 만료**된다 ✅(확인한 것은 만료 시각 값이고, 만료 후 실제로 막히는지는 시험하지 않았다 ❓). `oh=`는 서명이다. 그래서 **수집하는 날 바로 내려받아야 한다**. 주소만 저장하면 며칠 뒤 못 쓴다.
- 같은 이미지라도 응답마다 주소의 서명(`oh`, `_nc_gid`)이 달라진다 ✅(Death Wish 목록과 상세 응답 비교). 파일 경로 부분(`.../828311735_1654833936303319_..._n.jpg`)은 같았다 ✅. 중복 확인에는 이 경로를 쓸 수 있다.
- 서버는 `scontent-sea5-*.xx.fbcdn.net`(이미지), `video-sea5-*.xx.fbcdn.net`(영상)이다 ✅. 접속 위치에 따라 달라질 수 있다 ❓.
- HD 영상은 `cache-control` 헤더가 없고, 나머지는 `max-age=1209600`(14일)이다 ✅.
- 영상 `watermarked_*` 필드는 전부 `null`이었다 ✅.

## 6. 지금 돌고 있는 광고의 판정
- **주소의 `active_status=active` 필터와 `is_active: true`를 쓴다.** 화면의 "Active" 배지와 같다 ✅. 필터를 건 121건은 전부 `true`였다.
- **`end_date`로 active를 판정하면 안 된다** ✅. 활성인데 `end_date`가 오래된 광고가 있다. Jinx의 `1808352910146171`은 `is_active: true`, 시작 2026-06-16, `end_date` 2026-06-19다. 활성 광고 대부분의 `end_date`는 2026-11-09(수집 전날)다. 마지막으로 노출을 확인한 날짜에 가까워 보이나 ❓ 확실하지 않다.
- 게재 일수는 `수집일 - start_date`로 계산한다. 서버가 주는 `total_active_time`은 전부 `null`이다 ✅.
- 끝난 광고의 표현(`active_status=inactive` 또는 `all`)은 로드하지 않았다 ❓. 한 번 활성 필터로 받았다가 다음 수집에서 목록에 없으면 ended로 보는 방식이 안전하다(제안).

## 7. 항목 식별과 재실행, Facebook과 Instagram 중복
- 고유 키: `ad_archive_id` (Library ID). 화면 주소로 대조: `https://www.facebook.com/ads/library/?id=<ad_archive_id>` ❓ 이 주소 형식은 열어 보지 않았다.
- **한 광고가 Facebook과 Instagram 양쪽에 나가도 행은 하나**다 ✅. 지면은 `publisher_platform` 배열로 온다. 관찰한 값: `FACEBOOK`, `INSTAGRAM`, `AUDIENCE_NETWORK`, `MESSENGER`, `WHATSAPP`, `THREADS` ✅. 과제는 Facebook과 Instagram이라고 했지만 Threads, WhatsApp도 같이 온다.
- 지면 조합이 광고마다 다르다 ✅: Batiste는 Instagram 전용(12건 전부), Death Wish는 Facebook+Instagram+Threads(11건) 또는 거기에 Audience Network와 Messenger(19건), Living Proof는 Facebook+Instagram만(12건)인 광고도 있다.
- 다시 돌리면 같은 `ad_archive_id`의 행을 갱신한다. 목록에서 사라지면 ended로 표시한다.
- 소재 중복 제거용 키: `collation_id` (같은 그룹) ✅.
- 제휴 광고(Paid partnership) 처리 ✅: Jinx 광고 중 7건은 `snapshot.page_name`이 제휴 계정(The Dodo 등)이고 `branded_content`가 Jinx 페이지를 가리킨다. 최상위 `page_name`은 `Jinx`다. 브랜드 귀속은 최상위 `page_id`로 한다. 이 일부는 창작자 개인 계정이므로 수집 시 개인 이름을 분석 대상에 넣지 않는 것이 좋다(제안).

## 8. 이 소스에서 얻을 수 없는 것
- **노출량, 도달, 광고비, 타기팅.** 미국 상업 광고는 이 값들이 비어 있다 ✅. `reach_estimate`, `spend`는 121건 전부 `null`, `impressions_text`는 Batiste 1건만 `"<100"`이고 나머지 `null`이다. 상세 화면의 합계 응답도 비었다(`impressions: null`, `age_gender_data: []`, `location_data: []`, `spend_by_currency: []`) ✅. EU, UK, 브라질 투명성 필드도 `null`이다 ✅.
- **30건을 넘는 광고**(4-5). Jinx는 250건 중 30건만 보인다.
- 끝난 광고(과거 이력)는 시험하지 않았다 ❓.
- 광고 변형별 "A/B 결과"나 성과.
- 구글의 `domain=` 같은 도메인 검색은 없다. 페이지 단위로만 모인다.

## 9. 이걸로 볼 수 있는 것
각 브랜드 첫 30건(Black Rifle, Batiste는 전체) 기준이다.
- **형식 비중이 브랜드마다 다르다:** Death Wish는 30건이 전부 동적 소재(DCO)다. Black Rifle은 이미지 14, 영상 5. Batiste는 영상 10, 동적 2(전체 12건). Jinx는 영상 17, 동적 13. Living Proof는 동적 24, 상품 카탈로그 2, 영상 2, 이미지 2.
- **시작일로 캠페인 시점을 읽는다:** Death Wish는 8/22~10/28에 걸치고 9/29, 10/12, 10/28에 몰린다(화이트 초콜릿 피스타치오, 진저데드, 초콜릿 럼볼 등 시즌 한정 맛 중심, 랜딩은 맛별 컬렉션 주소). Batiste 12건은 전부 11/4~11/5에 시작했다(홀리데이 캠페인, 인스타 전용). Black Rifle은 10/16과 11/4~11/6에 시작이 몰린다. Living Proof는 10/19~11/3. Jinx는 5월부터 도는 소재가 있고 10/18과 10/28에 몰린다.
- **랜딩 도메인이 브랜드 도메인과 다르다:** Batiste는 `ulta.com`, `target.com`, `buy.batistehair.com`, Jinx는 `walmart.com`, `airbnb.org`(Airbnb.org 제휴 캠페인)로 보낸다 ✅. 리테일러로 보내는 전략을 읽을 수 있다. 반대로 도메인으로 광고를 찾는 방식은 이 광고들을 놓친다.
- **랜딩 주소의 UTM에서 타기팅이 새어 나온다:** Batiste 미국 광고 주소의 `utm_term`에 `rtg_f18-44_video_viewers,_mm_visitors,_and_followers`(리타기팅, 18~44세 여성), `ir_..._beauty_and_personal_care`(관심사) 같은 값이 보인다 ✅. 캠페인 이름(`q4_2026_bat_traffic_lpv`)과 소재 이름(`btugc_cohley` 창작자 UGC)도 나온다.
- **문구 비교:** 본문, 제목, 오퍼 문구가 글자로 와서 브랜드끼리 바로 비교된다. 한 소재가 여러 번 복제되므로 서로 다른 본문 수(Death Wish 14, Black Rifle 4)로 세는 편이 낫다.
- **미디어 비교:** 이미지와 영상 파일을 받으면 소재의 색, 인물, 상품 노출을 볼 수 있다.

## 10. 정해야 할 것
1. **수집 길**: **결정 ✅(사용자, 2026-11-10)**. Apify(`apify/facebook-ads-scraper`)로 모은다(13-7). 다시 돌리는 환경이 어느 IP든 되는 것이 우선이다. 자체 코드의 넘김은 데이터센터 IP에서 막혀서(14-5) 기본 길로 쓰지 않는다.
2. **수집 단위**: 광고 건(Library ID)으로 저장하고 `collation_id`를 같이 둘지, 소재 단위로 합칠지. (제안: 건 단위 저장, 분석할 때 그룹으로 묶는다)
3. **영상과 이미지 파일**: 만료되는 주소라서 수집 당일에 받아야 한다. 모든 광고의 HD 영상을 받을지(예: 31초 광고가 5MB), SD나 미리보기 이미지만 받을지. (제안: 이미지는 `original`, 영상은 SD와 미리보기, HD는 선택)
4. **Batiste 페이지**: 글로벌(`95597922197`)과 미국(`230750427654291`) 둘 다 넣을지, 다른 국가 페이지의 US 광고도 볼지. (제안: 두 페이지 다 넣는다)
5. **Threads, WhatsApp 지면**: 과제는 Facebook과 Instagram이라고 했다. 이 두 지면의 광고도 모을지, 표시만 해 둘지. (제안: 전부 모으고 `publisher_platform`으로 나중에 거른다)
6. **제휴 광고**: 창작자 계정 이름이 섞여 오는 항목을 어떻게 다룰지. (제안: 최상위 `page_id`로 브랜드에 귀속, 창작자 이름은 저장하지 않는다)

## samples/
| 파일 | 내용 |
|---|---|
| `counts_per_brand.json` | 브랜드별 활성 광고 수와 쓴 주소 |
| `typeahead_page_results_selected.json` | 검색창 제안 응답에서 해당 브랜드 행만 추림(이미지 주소 제거) |
| `list_deathwishcoffee_3edges.json` | Death Wish 목록(20개 그룹 중 3개로 줄임. 전부 DCO) |
| `list_blackriflecoffee_video_and_image.json` | Black Rifle 목록(19개 중 영상 1, 이미지 1) |
| `list_batiste_us_2edges.json` | Batiste 미국 페이지(4개 그룹 중 2개. Instagram 전용) |
| `list_jinx_video_and_branded.json` | Jinx 목록(27개 중 영상 1, 제휴 광고 1) |
| `list_livingproof_dpa.json` | Living Proof 목록(27개 중 상품 카탈로그 광고 1) |
| `detail_collation_dwc.json` | "See summary details" 응답: 그룹의 광고 2건 전체 |
| `detail_collation_aggregate_dwc.json` | 그룹 합계 응답(비어 있음) |
| `detail_single_ad_jinx.json` | "See ad details" 응답: 광고주 페이지 정보 |
| `pagination_request_and_ratelimit.json` | 다음 페이지 요청 변수와 "Rate limit exceeded" 응답 |
| `brcc_image_resized_600.jpg` | 내려받기를 시험한 이미지 1장 |
| `ui_summary_details_modal.png`, `ui_ad_details_modal.png` | 상세 화면 두 가지 모습 |
| `apify/input.json`, `apify/input_schema.json` | Apify 시험 입력과 수집기 입력 형식 |
| `apify/items_livingproof_40.json` | Apify가 준 Living Proof 40건 원본(제휴 계정 이름, 주소, ID만 지움) |
| `apify/run_summary.json`, `apify/run_log.txt` | 실행 요약(과금 건수, 차감액, 옵션)과 실행 기록 |
| `apify/items_livingproof_98.json`, `apify/run_summary_98.json` | 2회차(13-7): Living Proof 98건 전부(제휴 계정 값 지움)와 실행 요약 |
| `apify/run_post_response_40.json`, `apify/run_object_succeeded_unsettled.json`, `apify/run_object_succeeded_settled.json` | Apify 실행 객체 원본(`userId`만 지움): 1회차 POST 응답(과금 20/40), 2회차 종료 직후(80/98)와 확정 뒤(98/98) |
| `site/list_page_livingproof.html` | 화면 없는 Chrome으로 연 Living Proof 목록 문서. `search_results_connection`이 든 스크립트 하나만 남기고 그룹을 2개로 줄임(`count` 98) |
| `site/list_page_zero.html` | 미국 활성 광고가 없는 페이지(228842154551249)의 같은 스크립트(`count` 0) |
| `site/challenge_403.html` | 브라우저 없이 요청했을 때 받은 403 검사 페이지(경로의 토큰만 가림) |
| `novpn/livingproof_pagination_log.json`, `novpn/jinx_pagination_log.json` | VPN 없이 한 넘김 시험: 요청마다 시각, HTTP 상태, 오류, 받은 광고 ID, `has_next_page` |
| `novpn/livingproof_vpn_recheck_log.json` | VPN IP로 다시 한 넘김 시험(14-5): 같은 형식, 20번 모두 거절 |

각 `list_*.json`은 실제 응답에서 줄이기만 했다(그룹 일부만 남김). 영상 파일은 용량 때문에 저장하지 않았다.

### 상세 화면 요약 (6번 항목 "상세 화면이 주는 것")
- 그룹 상세(`See summary details`, 같은 소재가 2건 이상일 때): 그룹의 광고를 전부 보여 준다(목록에는 일부만 올 수 있다). 목록과 같은 필드에 새 필드가 거의 없다 ✅. 합계(노출, 연령, 성별, 지역, 광고비)는 비어 있다 ✅.
- 단일 상세(`See ad details`): 광고 본문은 목록과 같고, 추가로 **광고주 페이지 정보**를 준다 ✅: 소개 글(`about.text`), 팔로워 수, 카테고리, 인스타 계정과 팔로워, 커버 사진, 페이지 별칭, 정치 광고 집행액(`page_spend`, 비어 있음).
- 따라서 상세를 따로 호출해야 얻는 광고 정보는 사실상 없다. 광고주 소개 글과 인스타 팔로워 수 정도다.

## 12. 30건 한계를 넘는 방법 (시험 결과)
- 측정일 2026-11-10. 네트워크: 미국(Seattle), AS212238 Datacamp Limited(데이터센터 VPN IP) ✅. facebook.com 로드 24회(한도 25). CAPTCHA, 로그인 벽, 차단 화면은 한 번도 안 떴다 ✅.
- 결론: **필터로 쪼개 전부 가져오기는 되지 않았다.** Death Wish 47건은 로드 3종을 합쳐 47건 전부 얻었으나, Jinx 250건은 로드 9회로 150건(60%)까지만 닿았다 ✅. 어떤 필터도 각 조각을 30건 이하로 나누지 못했다.

### 12-1. 화면에 있는 필터와 주소 이름
화면 Filters 창: Language, Platform, Media type, Active status, **Impressions by date**(From/To). Sort by: `Impressions: high to low`, `Most recent` ✅.
| 필터 | 주소 | 결과 |
|---|---|---|
| 날짜 최대값 | `start_date[min]=YYYY-MM-DD&start_date[max]=YYYY-MM-DD` | **max만 먹힌다** ✅. 이름은 "시작일"이 아니라 "노출일(Impressions by date)"이다. 활성 광고는 오늘까지 노출 중이라 `min`은 아무것도 거르지 못한다(`min=2026-09-29`도 47건 그대로, 첫 30건도 똑같음 ✅). `max=X`는 "시작일이 X 이하인 광고"만 남긴다(count가 바뀌고 JSON도 그 조각만 담음 ✅). 즉 **한쪽이 열린 누적 조각만** 만들 수 있고, 가장 새 광고만 따로 뽑는 조각은 못 만든다 |
| 미디어 유형 | `media_type=image|video|meme|none` | Jinx: video 181, meme 70(합 251, 화면 250과 1 어긋남), image 0, none 0 ✅. 사실상 2조각. Death Wish는 시험 안 함 |
| 정렬 | `sort_data[mode]=relevancy_monthly_grouped&sort_data[direction]=desc`(Most recent, 화면에서 눌러 주소 확인 ✅), 기본은 `total_impressions` ✅ | Most recent는 새 광고 순에 가깝다. 완전한 시작일순은 아니다 ✅. `direction=asc`는 desc와 같은 결과 ✅ |
| 플랫폼 | `publisher_platforms[0]=instagram|facebook` | Jinx에서 count가 250 그대로 ✅. 주소 이름이 맞는지 화면에서 확인하지 않았다 ❓ (이름이 틀렸거나 전 광고가 양쪽 지면) |
| 언어 | `content_languages[0]=en` | 시험하지 않았다 ❓ |
| 화면 정렬 메뉴로 바꾸기 | | 클릭 이동은 "No ads match"만 떴다(graphql 한도 때문으로 보임 ❓). 새 주소로 로드하면 정상 ✅ |

### 12-2. Death Wish Coffee (47건)
- 로드 `max=2026-09-28` → count 25, JSON 25건, 시작일 8/22~9/15 ✅. `min`만 바꾼 로드 3개는 기본과 같은 30건(ID 집합 동일) ✅. 날짜로 나눈 "나머지 22건"은 못 얻는다.
- 서로 다른 로드 3종의 합집합: 기본 30 + 날짜 max 25 + Most recent 30 = **47건 전부, 겹침 있음** ✅. 겹침: 기본과 날짜 12건이 겹침(합 43), Most recent가 4건을 더했다. 우연히 맞은 것이다. 47건에 대해 "빈틈 없는 조각"을 만든 것은 아니다.

### 12-3. Jinx (250건)
- 시험한 것: Most recent 정렬에서 직전 묶음의 가장 이른 시작일을 `max`로 걸어 내려가기(5회 로드). count가 250 → 199 → 163 → 38 → 5로 줄고 새로 얻은 건수는 30, 30, 30, 30, 5, 합 125건 ✅.
- **빈틈이 생겼다** ✅: `max=2026-11-02`의 count가 199이므로 그 이후 시작한 광고가 51건인데, 첫 묶음은 30건뿐이다. `max=2026-10-18` count 38에서도 30건만 보이고 바로 다음 로드는 `max=2026-06-16`(5건)으로 건너뛴다. 정렬이 시작일순이 아니어서, 묶음 안의 가장 이른 날짜를 기준으로 삼으면 사이의 광고가 새어 나간다.
- 추가 4회(video, meme, instagram, facebook, 모두 Most recent): 새로 25건 → **총 150건 / 250건**, 로드 9회 ✅. 어느 조각도 30건을 넘어서 `has_next_page: true`였다.
- 못 한 것 ❓: 미디어 유형과 날짜 max와 정렬을 모두 겹쳐 count가 30 이하가 될 때까지 쪼개는 것은 로드 한도(25) 때문에 하지 않았다. 이론상 `max` 값을 count로 조정하면 오래된 쪽 조각은 완전히 얻는다(`max=2026-06-16`처럼 count 5). 문제는 가장 새 광고가 많이 몰린 쪽이다: 11-02 이후 51건을 video/meme으로 나눠도 각 30을 넘을 수 있다.

### 12-4. 느리게 다시 해 본 페이지 넘김
- Death Wish 기본 주소를 로드해 12초 기다린 뒤 한 번 맨 아래로 스크롤, 20초 대기: `AdLibrarySearchPaginationQuery`가 **20회**(페이지 자동 재시도) 나갔고 전부 `{"errors":[{"message":"Rate limit exceeded","code":1675004}]}` ✅. 아직도 막혀 있다. 반복하지 않았다.

### 12-5. 정리와 제안
- 필터 슬라이싱은 30건 이하 브랜드(대부분)에는 필요 없고, 31~60건대(Death Wish 47)는 서로 다른 설정 3~4회 로드의 합집합으로 닿을 수 있었다(보장 아님). 100건 이상(Jinx 250, Living Proof 98)에서는 이번 필터 조합으로 닿지 못했다 ✅.
- 공식 API(`ads_archive`)는 이 과제에 쓸 수 없다 ✅(공식 문서 2026-11-10 확인): "Ads that did not reach any location in the EU will only return if they are about social issues, elections or politics." 미국에만 나간 상업 광고는 반환되지 않는다. 액세스 토큰도 필요하다.
- 유료 스크레이핑 서비스의 Ad Library 수집기는 Meta 공식 경로가 아니다. 같은 공개 화면을 제3자가 긁는 것이다. Apify 수집기로 30건을 넘기는 것은 확인했다 ✅(13절).
- 시험하지 않은 것 ❓: 다른 네트워크(주거용 IP)에서의 페이지 넘김, `content_languages`, 키워드(`q=`)로 조각내기(주소의 키워드는 페이지 ID 검색과 같이 쓰이는지 미확인), 플랫폼 필터의 올바른 주소 이름.

## 13. Apify 수집기 시험 (`apify/facebook-ads-scraper`)
- 상태(2026-11-10): 시험 2회 실행. 1회차는 **30건을 넘겨 40건이 왔고, 직접 받은 30건과 값이 같았다**(차감액 $0.232). 2회차는 Living Proof 98건을 전부 받았다(13-7, 차감액 $0.5684). **이 소스의 수집 길로 정했다**(13-7).
- 수집기 ✅: `apify/facebook-ads-scraper`(ID `JJghSZmShuco4j9gJ`), 빌드 0.0.400(2026-11-09), 최근 30일 사용자 11,031명.
- 요금 ✅: 이벤트 과금. 광고 1건(데이터셋 항목 1개)에 $0.0058(무료 요금제). 부가 기능 `ecommerce-enrichment`는 랜딩 주소 1개에 $0.0057이 따로 붙고 기본값이 꺼짐이다. 실행 시작 요금은 없다.
- 계정 ✅: 무료 요금제, 월 한도 $5, 시험 전 사용액 $0.0004.
- 입력 형식 ✅ (`samples/apify/input_schema.json`): 필수는 `startUrls`뿐이고 **Ad Library 주소를 그대로 받는다**(페이지 ID 검색 주소 가능). `resultsLimit`(주소당 개수), `activeStatus`, `sorting`, `onlyAdsNewerThan`/`onlyAdsOlderThan`, `onlyTotal`(페이지별 전체 광고 수만 1건으로 반환), `isDetailsPerAd`, `includeAboutPage`, `enrichWithEcommerceData`.
- 준비한 시험 입력 ✅ (`samples/apify/input.json`): Living Proof 페이지 `40730897173`, 미국, 활성, `resultsLimit: 40`, 부가 기능 전부 끔. 실행 인자는 `maxTotalChargeUsd=0.30`, `maxItems=40`. 예상 차감액 40 × $0.0058 = $0.232.
- 대조 기준 ✅: 직접 받은 Living Proof 30건(첫 HTML, `count` 98, 그룹 27개, 제휴 광고 4건).

### 13-1. 실행 결과 (`samples/apify/run_summary.json`, `run_log.txt`)
- 실행 ✅: 2026-11-10 07:09:39Z~07:10:11Z, **31.5초**, 상태 SUCCEEDED, 실행 ID `N5ygERHh1fi3kXuOD`.
- **40건이 왔다** ✅. 고유 광고 ID 40개, 전부 `pageID 40730897173`, 전부 `isActive: true`. 30건 한계를 넘는다.
- **직접 받은 30건이 40건 안에 전부 들어 있다** ✅(겹침 30, 직접 수집에만 있는 것 0). 새로 온 것은 10건이다(시작일 10/19~11/6, DCO 5, DPA 2, VIDEO 3).
- 차감액 ✅: 광고 40건 × $0.0058 = **$0.232**(`usageTotalUsd` 0.232, 과금 항목 40, 부가 기능 0). 종료 직후 조회에서는 20건/$0.116으로 보였고 몇 분 뒤 40건으로 확정됐다. **과금 집계는 늦게 반영되므로 종료 직후 값으로 판단하면 안 된다.**
- 전체 개수(98)는 응답 항목에 **없다** ✅. `onlyTotal` 옵션으로 따로 받거나(써 보지 않았다 ❓), 직접 여는 첫 HTML의 `count`(무료)로 안다.

### 13-2. 같은 광고의 값 대조 (겹치는 30건)
- 대조한 필드 ✅: 시작일, `end_date`, 활성 여부, 지면 배열, `collation_id`, 페이지 ID, 본문, 제목, 랜딩 주소, CTA, 형식, `caption`, 카드 수, 미디어 파일 경로(주소에서 서명 뺀 부분), 제휴 여부. **30건 모두 일치했다.**
- 유일한 차이 ✅: `collationCount` 2건. 직접 받은 응답은 그룹 첫 항목에만 값이 있고 나머지는 `null`인데, Apify는 그룹의 모든 광고에 값을 채운다.
- 필드 이름만 다르다 ✅: 낙타 표기다. `adArchiveID`, `startDate`, `publisherPlatform`, `collationId`, `snapshot.linkUrl`, `snapshot.displayFormat`, `snapshot.cards[].originalImageUrl`, `snapshot.videos[].videoHdUrl` 등. 직접 수집의 `ad_archive_id`, `start_date` 등과 1:1로 대응한다.
- 추가로 오는 것 ✅: `startDateFormatted`, `endDateFormatted`(ISO 시각), `inputUrl`, `pageInfo`(연관 페이지 목록, 숨겨진 광고 수 `hiddenAds: 0`, `xfbAdLibraryIsCaptchaRequired: false`).
- 미디어 주소는 40건 모두 있다 ✅. 그 주소로 파일이 받아지는지는 시험하지 않았다 ❓(경로가 직접 받은 것과 같다).
- 도달, 광고비, `totalActiveTime`은 여기서도 `null`이다 ✅.

### 13-3. 수집기가 쓰는 길 (실행 기록에서 본 것)
- 브라우저가 아니라 **일반 HTTP 요청**(CheerioCrawler)으로 `https://www.facebook.com/api/graphql/`을 부르고 10건씩 받는다 ✅("Found 10 new ads" 4회, 요청 5회).
- 그중 2회는 "BLOCKED" 뒤 재시도해서 성공했다 ✅. 즉 Apify도 막히지만 다른 출구로 다시 시도해 넘긴다.
- 뜻: 로그아웃 상태이고 브라우저가 아니어도 넘김이 되는 IP가 있다. 우리 쪽이 막힌 원인이 IP라는 것은 14절에서 확인했다 ✅.

### 13-4. 개인정보
- 40건 중 **7건이 제휴 광고**이고, `snapshot.pageName`, `pageProfileUri`, `pageProfilePictureUrl`, `snapshot.pageId`가 창작자 개인 계정을 가리킨다 ✅(팔로워 9~1,589명, 분류 "Personal blog", "Blogger" 등). `brandedContent`는 7건 모두 브랜드 페이지를 가리킨다 ✅.
- 저장한 `samples/apify/items_livingproof_40.json`에서는 이 네 값을 지웠다. 수집기도 제휴 광고에서는 이 값을 저장하지 않아야 한다(10절 6번).

### 13-5. 비용과 쓰는 범위
| 방안 | 건수 | 1회 비용 | 비고 |
|---|---|---|---|
| 5개 브랜드 전부 Apify | 426 | 약 $2.47 | 1,000건당 $5.80 |
| 30건 넘는 3개만(Jinx 250, Living Proof 98, Death Wish 47) | 395 | 약 $2.29 | 나머지 2개(31건)는 자체 코드 |
- **둘의 비용 차이는 $0.18뿐이다.** 범위를 줄여 아끼는 돈은 거의 없다. 30건 넘는 브랜드는 처음 30건도 다시 과금된다(앞부분만 건너뛰는 입력이 없다).
- 무료 요금제 월 한도 $5로는 전체 수집을 **2회**쯤 돌릴 수 있다. 다시 돌릴 때마다 전 건이 다시 과금된다.
- 다른 사람이 다시 돌리려면 **자기 Apify 토큰**이 있어야 한다. 토큰 없이는 이 경로가 돌지 않는다.
- (이전 제안, 13-7 결정으로 대체됨) 자체 코드를 기본 길로 쓰고 Apify는 넘김이 막힐 때만 쓰는 보충 길로 둔다.

### 13-6. 아직 모르는 것 ❓
- 250건(Jinx) 전부가 끝까지 오는지. 98건은 끝까지 왔다(13-7).
- 큰 페이지에서 "BLOCKED" 재시도가 늘 때의 소요 시간과 실패율.
- `onlyTotal`의 과금 방식.
- `startUrls`에 주소 여러 개를 넣은 1회 실행.

### 13-7. Living Proof 전부 받기(2회차)와 결정
- 실행 ✅: 2026-11-10 08:55Z(17:55 한국 시각), 실행 ID `JJdRBH0bwHIEnrswb`, **63.7초**, SUCCEEDED. 입력은 1회차와 같고 `resultsLimit: 100`, 실행 인자 `maxItems=100`, `maxTotalChargeUsd=0.60`. 이때 우리 IP는 넘김이 막힌 데이터센터 VPN이었다(14-5). Apify는 자기 쪽 출구로 요청하므로 우리 IP와 상관없다.
- **98 / 98건이 왔다** ✅(화면 `count`와 같음). 중복 0, 전부 `isActive: true`, 최상위 `pageId` 전부 `40730897173`, 미디어 주소가 없는 광고 0. 형식은 DCO 76, VIDEO 9, IMAGE 9, DPA 4로 14-3과 같다.
- 차감액 ✅: 98 × $0.0058 = **$0.5684**(과금 항목 98, 부가 기능 0). 이번에도 몇 분 뒤에 확정됐다.
- 미디어 파일 ✅: Apify가 준 주소로 이미지 원본 1개(2.2MB, image/jpeg)와 SD 영상 1개(1.5MB, video/mp4)를 데이터센터 VPN IP에서 일반 GET으로 받았다(둘 다 200).
- 가정용 회선에서 직접 받은 98건(14절)과 ID 집합이 같다 ✅. 13-2의 필드도 `end_date`만 빼고 같다. `end_date` 46건이 하루 뒤 날짜인 것은 두 수집 사이에 태평양 시각 날짜가 바뀌었기 때문이다(직접 수집 23:20 PST, Apify 00:55 PST). 활성 광고의 `end_date`는 "오늘"을 뜻하므로 활성 판정에는 `is_active`를 쓴다(6절).
- 제휴 광고 11건 ✅: 저장본 `samples/apify/items_livingproof_98.json`에서는 13-4의 네 값을 지웠다.
- 여러 브랜드를 1회에 ✅(입력 형식): `resultsLimit`는 **주소당** 개수다. `startUrls`에 페이지 6개(Batiste 2개 포함)를 넣어 한 번에 돌릴 수 있다.
- **결정 ✅(사용자, 2026-11-10)**: Meta 광고는 **Apify로 모은다.** 다시 돌리는 환경이 어느 IP든 되는 것이 우선이다.
- 이 결정에 따라 정해지는 것:
  - 실행에는 환경 변수 `APIFY_TOKEN`이 필요하다. 다시 돌리는 사람은 자기 토큰을 쓴다. 토큰이 없으면 이 소스는 "could not look(토큰 없음)"으로 기록한다(제안).
  - 비용: 5개 브랜드 1회 약 $2.47(426건), 1,000건당 $5.80. 이 계정의 이번 달 사용액은 $2.05 / $5(모든 소스 합계)라서, 남은 한도로는 전체 수집을 **1회**만 돌릴 수 있다. 개발 중에는 `resultsLimit`를 작게 두고 시험한다.
  - VPN 순서 문제가 없어진다. 미국 IP가 필요한 다른 소스와 같은 네트워크에서 돌려도 된다(14-4의 순서 제약은 해당 없음).
  - 유료 서비스 없이 직접 짠 코드로 모으는 소스는 이 소스가 아니라 다른 소스가 맡아야 한다.
  - 미디어는 Apify가 준 주소로 수집 당일 바로 내려받는다(5-1의 만료 때문).
  - 가장 먼저 깨질 부분: Apify 수집기의 출력 형식이나 요금이 바뀌는 것, 그리고 Meta가 막아서 Apify가 일부만 주는 것. 받은 건수를 첫 HTML의 `count`(무료, 어느 IP에서든 열림)와 비교해 모자라면 "일부 수집(받은 수/`count`)"으로 기록한다(제안).

## 14. VPN 없이 한 페이지 넘김 (시험 결과)
- 측정일 2026-11-10 16:18~16:23(한국 시각). 네트워크: 한국 서울, AS9318 SK Broadband(가정용 회선) ✅. facebook.com 로드 2회(Living Proof, Jinx), 넘김 요청 29회. CAPTCHA, 로그인 벽, 차단 화면은 없었다 ✅.
- 조건은 4-5절, 12절 시험과 같다: 로그아웃, 쿠키 없는 새 세션, Playwright가 띄운 Chrome(`channel="chrome"`, 화면 있음), 주소의 `country=US`. **바뀐 것은 IP뿐이다.**
- 결론: **넘김 요청이 전부 성공했고 두 브랜드의 활성 광고를 끝까지 받았다** ✅. 자체 코드만으로 30건 한계를 넘는다.

### 14-1. 결과
| 브랜드 | 화면 `count` | 첫 HTML | 넘김 요청 | 받은 광고(고유) | 걸린 시간 |
|---|---|---|---|---|---|
| Living Proof | 98 | 30 | 7회, 전부 성공(10건씩, 마지막 8건) | **98 / 98** | 50초 |
| Jinx | 250 | 30 | 22회, 전부 성공(10건씩) | **250 / 250** | 144초 |
- 두 브랜드 모두 마지막 응답의 `has_next_page`가 `false`였다 ✅. 중복 ID 0, 전부 `is_active: true`, 전부 해당 페이지 ID ✅.
- 넘김 응답의 구조는 첫 HTML과 같다(`search_results_connection.edges[].node.collated_results[]`, 필드 이름도 같음) ✅. HTTP 상태는 전부 200 ✅.
- 한국 IP에서도 `country=US` 결과가 같다 ✅: Living Proof `count` 98과 첫 30건의 ID 집합이 미국 VPN IP에서 받은 것과 똑같았다.
- 스크롤 동작 ✅: Living Proof는 스크롤하기 전에 페이지가 스스로 7번 연달아 불러 98건을 채웠다(로드 후 약 11~17초). Jinx는 스크롤 한 번에 요청 2번(20건)씩 나갔다. 스크롤 사이에 8초를 쉬었다.

### 14-2. 다른 결과와 대조
- Apify 40건(13절)은 자체 수집 98건 안에 전부 들어 있고, 시작일, 활성 여부, 지면 배열, `collation_id`, 본문, 제목, 랜딩 주소, CTA, 형식, 카드 수, 미디어 파일 경로가 **40건 모두 같았다** ✅.
- Jinx: 12절의 필터 쪼개기로 받은 광고 중 저장된 HTML에 남은 115건은 자체 수집 250건 안에 전부 들어 있다 ✅.
- 실제 사이트 화면과 한 건씩 대조하지는 않았다 ❓(같은 응답을 화면이 그린다).

### 14-3. 새로 보인 것
- Living Proof 98건: DCO 76, VIDEO 9, IMAGE 9, DPA 4. 시작일 10/19~11/9. 미디어 주소가 없는 광고 0건 ✅.
- Jinx 250건: VIDEO 143, DCO 107. **제휴 광고가 100건(40%)이다** ✅. 창작자 개인 계정 이름이 붙어 오는 광고가 많으므로 10절 6번(창작자 이름을 저장하지 않음)이 수집기에서 꼭 지켜져야 한다.
- 지면 조합(Living Proof): FB+IG+Audience Network+WhatsApp+Threads 56건, FB+IG만 36건, FB+IG+WhatsApp 4건, FB+IG+AN+Threads 2건 ✅.

### 14-4. 남은 것과 판단할 것
- **시간 경과 때문이 아니다** ✅(14-5). 같은 날 VPN IP로 돌아가 다시 열자 또 막혔다.
- (13-7 결정으로 해당 없음) 자체 코드로 넘김을 받으려면 데이터센터 IP가 아닌 곳에서 돌려야 한다.
- **다른 사람이 자기 환경에서 다시 돌릴 때가 위험하다.** 그 환경이 클라우드 VM, CI, 회사 보안 게이트웨이처럼 데이터센터 IP로 나갈 수 있다. 우리가 막힌 것은 여러 사람이 함께 쓰는 상용 VPN 출구 IP 하나였다 ✅. "Rate limit exceeded"라는 문구도 IP 하나에 몰린 요청을 세는 한도와 맞는다. 한 사람만 쓰는 클라우드 VM IP도 막히는지는 시험하지 않았다 ❓.
- 어느 IP에서든 되는 것 ✅: 첫 HTML(30건과 `count`)은 막힌 VPN IP에서도 36번 모두 열렸다. 최악의 경우에도 "could not look"이 아니라 "일부 수집"이 된다.
- (13-7 결정으로 대체됨. 지금은 Apify가 기본 길이다.) 대비책(이전 제안): 수집기를 3단으로 둔다. (1) 자체 코드로 첫 HTML과 넘김을 받는다. (2) 넘김이 `code 1675004`로 거절되고 환경 변수 `APIFY_TOKEN`이 있으면, 그 페이지만 Apify로 받는다(1회 전체 약 $2.5). (3) 토큰이 없으면 받은 만큼 저장하고 "일부 수집 30/98"로 표시한다. 실행 안내에 "넘김이 막히는 네트워크에서는 `APIFY_TOKEN`을 넣으라"고 적는다.
- 하지 않을 것: 주거용 프록시나 IP를 돌려 쓰는 방식으로 한도를 피하는 것. 차단 회피 장치에 해당한다.
- **가장 먼저 깨질 부분**: 실행하는 IP가 막히면 넘김이 본문 오류 `code 1675004`로 거절된다. HTTP 200이라 상태 코드로는 모른다. 수집기는 이 오류를 보면 "일부 수집(받은 수/`count`)"으로 기록하고, 토큰이 있으면 Apify로 보충한다.
- 요청 수 ✅: 브랜드당 로드 1회 + 넘김 `ceil((count-30)/10)`회. 5개 브랜드 426건이면 로드 6회(Batiste 2페이지) + 넘김 약 37회. 비용은 0이다.
- Death Wish(47)는 이번에 다시 열지 않았다 ❓. 같은 방식이면 넘김 2회로 끝날 것이다.

### 14-5. VPN IP로 다시 시험 (17:50)
- 2026-11-10 17:50(한국 시각). 처음 막혔던 것과 같은 VPN(시애틀, AS212238 Datacamp)으로 돌아가 같은 스크립트로 Living Proof를 1회 열었다. 가정용 회선에서 전부 성공한 시험(16:18)보다 약 1.5시간 뒤다.
- 첫 HTML은 열렸다 ✅(`count` 98, 30건, 차단 화면 없음). 넘김 요청은 **20번 모두 "Rate limit exceeded"** ✅(HTTP 200). 받은 광고는 30/98.
- 순서가 막힘(14:11~14:54, VPN) → 성공(16:18~16:23, 가정용) → 막힘(17:50, VPN)이므로 시간이 지나 풀린 것이 아니다 ✅. 원인은 이 VPN IP다.
- 스크롤 한 번 뒤에 페이지가 스스로 약 1초 간격으로 20번 재시도했다. 수집기가 브라우저 응답을 가로채는 방식이면, 첫 `1675004`를 보는 즉시 페이지를 닫아 요청 수를 줄여야 한다.
- 기록: `samples/novpn/livingproof_vpn_recheck_log.json`.
