# 유료 외부 서비스 조사: 광고 · 검색 영역 (2026-11-10 기준)

조사 범위: 공개 문서, 가격 페이지, 예시 응답만 읽었다. 가입, 유료 API 호출, 개인정보 입력은 하지 않았다.
증거 등급: `docs` = 공식 문서, `샘플` = 문서에 실린 예시 응답, `마케팅` = 벤더 소개/가격 페이지, `블로그` = 제3자 글.

## 요약

| 갭 | 판정 | 추천 서비스 | 1회 전체 실행 비용(5개 브랜드) | 증거 등급 |
|---|---|---|---|---|
| 1. Meta 광고 라이브러리 (US 전체 활성 광고) | 대부분 해결 | SearchAPI.io `meta_ad_library` (보조: Apify 액터) | 약 $0.2~3 (광고 수 가정). 최소 결제 플랜 $40/월 | docs + 샘플 (SearchAPI), 마케팅 (Apify) |
| 2. TikTok US 광고 | 일부만 해결 | Apify "Creative Center Top Ads" 계열 액터 (US, 영상 URL) | 약 $0.1~1 | 마케팅 (액터 페이지). US 광고 라이브러리 지원은 확인 안 됨 |
| 3. Google 검색 결과, 광고/자연 결과 분리 | 해결 | DataForSEO (보조: SerpApi, SearchAPI.io) | DataForSEO $0.06~0.20, SerpApi 무료 250건 안에서 가능 | docs (DataForSEO), 샘플 (SerpApi, SearchAPI.io) |
| 4. Google Trends 12개월 주간 | 해결 (대체용) | DataForSEO Google Trends (보조: SerpApi) | 약 $0.01~0.25 | docs + 샘플 |
| 5. Google Ads Transparency Center | 직접 수집 유지 | SearchAPI.io (필요할 때만) | 해당 없음 | docs |

## 이 조사에서 계획에 가장 영향이 큰 사실

1. Serper는 광고를 반환하지 않는 것으로 보인다. 공식 홈페이지의 샘플 응답 키는 `knowledgeGraph`, `organic`, `peopleAlsoAsk`, `relatedSearches` 등이고 `ads`는 없다. 문서/가격 텍스트에도 "ads", "sponsored"가 나오지 않는다. 광고 분리 용도로는 제외한다.
2. TikTok은 US 광고 라이브러리 접근이 사실상 막혀 있다. 비공식 API인 ScrapeCreators 문서가 `region`에 대해 "US is not supported"라고 쓴다. 대안은 Creative Center의 "Top Ads"(성과 상위 광고)뿐이며, 브랜드 이름으로 검색하는 기능은 확인하지 못했다.
3. Meta 공식 Ad Library API는 US 상업 광고를 반환하지 않는다. 그래서 유료 스크래핑 서비스가 유일한 경로다. SearchAPI.io는 `page_id`로 US 활성 광고 목록을 `next_page_token`으로 이어서 받는다.

---

## 갭 1. Meta 광고 라이브러리: 페이지 ID 기준 US 활성 광고 전체

**Meta 공식 API 확인 (docs):** `ads_archive` 문서에 "Ads that did not reach any location in the EU will only return if they are about social issues, elections or politics."라는 문장이 있다. `ad_type`은 `ALL`, `EMPLOYMENT_ADS`, `FINANCIAL_PRODUCTS_AND_SERVICES_ADS`, `HOUSING_ADS`, `POLITICAL_AND_ISSUE_ADS`. 즉 질문 전제가 맞다. 상업 광고는 EU에 노출된 경우만 반환된다. US 전용 상업 광고는 공식 API로 받을 수 없다.

| 항목 | SearchAPI.io | ScrapeCreators | Apify 액터 (예: fascinating_lentil, scraptivo, good-apis) |
|---|---|---|---|
| 제품 URL | https://www.searchapi.io/docs/meta-ad-library-api | https://docs.scrapecreators.com/v1/facebook/adLibrary/company/ads | https://apify.com/fascinating_lentil/facebook-ad-library-scraper |
| 사용 방식 | REST API + 키 | REST API + 키 (`x-api-key`) | 액터 실행 (Apify 계정 + 토큰) |
| 페이지 ID 입력 | `page_id` | `pageId` | `pageIds` (최대 5개) 또는 `slug` |
| US 필터 | `country` (소문자 코드 예시 `gb`; 기본 `ALL`) | `country` (2글자 또는 `ALL`) | `country` (기본 US) |
| 활성 광고만 | `active_status`: active(기본)/inactive/all | `status`: ACTIVE(기본) | `adStatus`: active(기본) |
| 페이지 넘기기 | `pagination.next_page_token` (토큰이 길면 POST 사용) | `cursor` | `maxResults` 최대 1000 (한 번 실행에서 내부 처리) |
| 광고 문구 | `snapshot.body.text`, `snapshot.title`, `snapshot.cta_text`, `snapshot.link_url` | 응답 필드 목록 중 일부만 문서에 있음 (`ad_archive_id`, `is_active`, `collation_id`, `collation_count`) | `adCreativeText`, `adHeadline`, `adDescription`, `ctaButtonText`, `destinationUrl` |
| 시작일 | `start_date` (+ `end_date`) | 확인 못함 (문서에 필드 미기재) | `adStartDate` |
| 게재 플랫폼 | `publisher_platform` | 확인 못함 | `platformsList` (소스 누락 시 요청 필터 값으로 대체될 수 있다고 액터 문서에 명시) |
| 이미지/영상 URL | `snapshot.images`, `snapshot.videos`, `snapshot.cards[].original_image_url` / `resized_image_url`. 예시에서 `images`, `videos`는 빈 배열이라 구조 확인 못함 | 확인 못함 | `imageUrl`, `imageUrls`, `videoUrl`, `videoThumbnailUrl` |
| 가격 | 1,000건당 $4 (Developer, 월 $40, 10,000건) ~ $2.5 (BigData $250). 한 요청 = 1회 검색 | 1 요청 = 1 크레딧. 홈페이지: $47에 25,000 크레딧 (1,000건당 약 $1.88) | $1.00 / 1,000건 + 프록시/컴퓨트 별도. 다른 액터 $0.2~3.5 / 1,000건 |
| 무료/체험 | 100 무료 요청, 카드 불필요 (가격 페이지) | 가입 시 100 크레딧(일부 페이지는 1,000이라고 표기, 불일치). 카드 불필요라고 표기 | Apify 무료 플랜 월 $5 사용량, 카드 불필요. 유료 최소 $19/월 |
| 증거 | docs + 샘플 (필드명), 마케팅 (가격) | docs (일부 필드), 마케팅 (가격) | 마케팅 (액터 페이지), 액터 사용자 수 적음 (6~11명) |

- 한 페이지에 몇 건이 오는지는 SearchAPI 문서에 명시가 없다. 우리 코드가 30건에서 막힌 것과 같은 한계가 있는지는 실제 호출 전에는 알 수 없다. 확인 못함.
- SearchAPI 응답 `snapshot.images`/`videos` 안의 구조는 문서 예시가 비어 있어 확인 못함. 카드형 광고의 `original_image_url`은 확인됨.
- 광고 수에 대한 가정: 브랜드당 활성 광고 100~500건, 합계 약 1,500건. 이 숫자는 추정이다.
- 1회 비용 추정: SearchAPI는 페이지당 30건 가정 시 약 50회 요청, 약 $0.2 (종량 환산). 실제로는 최소 플랜 $40/월을 사야 한다. Apify는 1,500건 x $1/1,000 = 약 $1.5 + 프록시 비용.
- 액터 한계(액터 문서): 결과가 전체 보관소를 보장하지 않고, 지출/노출/타겟팅 필드는 대부분 null이다.

**판정: 대부분 해결.** SearchAPI.io가 문서상 필드가 가장 분명하다. 영상 URL 구조는 샘플 한 번 호출로 확인해야 한다.

---

## 갭 2. TikTok: 미국에 노출된 브랜드 광고와 영상

| 항목 | 내용 | 증거 |
|---|---|---|
| TikTok 공식 광고 라이브러리 | EEA/CH/GB/TR/BR만. US 없음 (질문 전제) | 사용자 제공 |
| ScrapeCreators `GET /v1/tiktok/ad-library/search` | `advertiser_name`, `adv_biz_ids`, `query`, `region` 파라미터 있음. 그러나 `region`은 기본 all이고 "US is not supported." 응답 필드와 크레딧 비용은 해당 페이지에 없음 (https://scrapecreators.com/tiktokAdLibrary-search-api) | 마케팅 페이지 |
| ScrapeCreators 블로그 | "None of these choices makes a public ad archive a complete US advertising database." 자사 샘플로 US 전체를 증명하지 못한다고 인정. 영상 배열이 빈 레코드도 있다고 함 (https://scrapecreators.com/blog/tiktok-ads-scrapers) | 벤더 블로그 |
| Apify Creative Center 액터 (예: dltik/tiktok-creative-center) | `countryCode` 기본 US. 키워드/광고주 검색은 없음 (산업 코드로만 필터). 출력: `video_url_720p`(MP4 직접 URL), `brand_name`(없으면 null), `ad_title`, `ctr`, `likes`. 최대 `maxResults` 기본 60. 성과 상위(Top Ads) 광고만 반환. 가격 표기가 $2/1,000과 $3.50/1,000으로 엇갈림. | 마케팅 (액터 페이지) |
| 다른 Creative Center 액터 (thenetaji, lexis-solutions, fetch_cat) | 키워드 + 국가(US) 입력 지원이라고 소개. 가격 $0.6/1,000부터. 직접 확인한 필드명은 없음 | 검색 결과 요약, 직접 페이지 확인 못함 |
| TikTok Creative Center 웹 | 지역, 목적, 언어, 형식 필터. 검색창은 있지만 광고주 검색인지 문서에 없음 (https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en) | 공식 웹 페이지 |
| 광고 스파이 도구 (PiPiADS, BigSpy, Minea) | PiPiADS 가격 페이지는 요금제, API, 무료 체험, 광고주 검색, US 필터 단어가 있다고만 확인됨(세부 불명). 블로그: PiPiADS 월 $77부터, API는 상위 플랜 $263/월; BigSpy API는 VIP $249~300+/월. 블로그끼리 수치가 다르고 벤더 가격 페이지로 확인 못함. Minea는 API 조건 확인 못함. | 블로그 (제3자, 제휴 링크 다수) |

- 브랜드 검색 가능 여부: 스파이 도구는 광고주/브랜드 검색이 있다고 소개하지만 문서로 확인하지 못했다. API 제공 여부는 PiPiADS와 BigSpy가 상위 플랜에서 제공한다는 블로그 주장뿐이다.
- 1회 비용 추정: Creative Center 액터로 브랜드 관련 키워드 5개 x 60건 = 300건이면 약 $0.6~1. 브랜드 자체 광고가 Top Ads에 들어 있을 보장은 없다.

**판정: 일부만 해결.** US 광고 전체 수집은 확인된 경로가 없다. Top Ads 안에 브랜드 광고가 있을 때만 영상 URL을 얻는다. 스파이 도구 구독은 US 커버리지와 API 조건을 직접 확인하기 전에는 권하지 않는다.

---

## 갭 3. Google 검색 결과: 광고/자연 결과 분리 (US, 약 100개 쿼리)

| 항목 | DataForSEO | SerpApi | SearchAPI.io | Bright Data | Serper |
|---|---|---|---|---|---|
| 문서 URL | https://docs.dataforseo.com/v3/serp/google/organic/live/advanced/ | https://serpapi.com/google-ads-api | https://www.searchapi.io/docs/google | https://brightdata.com/products/serp-api | https://serper.dev |
| 광고가 별도 블록으로 반환되나 | 예. 아이템 타입 `paid` | 예. `ads` 배열 | 예. `ads` 배열 | 불확실. 가격 페이지에 별도 "Ads" 엔드포인트가 있고 `parsed_light`는 광고 제외라는 설명이 있으나 필드명은 확인 못함 | 아니오로 보임. 샘플 키에 `ads` 없음 |
| 광고주 도메인 | `domain` | `source` (예시 "chatgpt.com"), `displayed_link`. 별도 `domain` 필드는 문서에 없음 | `domain` | 확인 못함 | 해당 없음 |
| 제목(헤드라인) | `title` | `title` | `title` | 확인 못함 | 해당 없음 |
| 설명 | `description` | `description` | `snippet` | 확인 못함 | 해당 없음 |
| 위치/순서 | `rank_group`, `rank_absolute`, `position`("left"/"right") | `position`, `block_position`(예시 "top") | `position`, `block_position` | 확인 못함 | 해당 없음 |
| 기타 | `url`, `breadcrumb` | `link`, `tracking_link`, `sitelinks` | `link`, `source`, `displayed_link`, `sitelinks`, `advertiser_info_token` | | |
| 미국 위치 지정 | `location_name` 또는 `location_code` 필수 | `location` | `location` (예: "New York,United States") | 확인 못함 | 있음(마케팅) |
| 가격 (1,000건) | 표준 큐 $0.60, 우선 $1.20, 라이브 $2.00 (결과 10개 기준. 깊이 100이면 10배) | 플랜제: $25/월에 1,000건 (건당 $25/1,000) ~ $75/월 5,000건 | $4 (월 $40, 10,000건) ~ $2.5 | $1.5 (종량제) | $1.00 (결제 $50에 50k 크레딧) |
| 무료/최소 | 신규 계정 $1 체험 크레딧(검색 결과 요약), 최소 충전 $50, 샌드박스는 무료지만 응답이 자동 생성 샘플 | 무료 250건/월, 시간당 50건. 카드 필요 여부는 가격 페이지에 없음 | 100 무료 요청, 카드 불필요 | 월 5,000건 무료, 카드 불필요 | 2,500 무료 쿼리, 카드 불필요 |
| 사용 방식 | REST + 로그인/비밀번호 방식 계정 | REST + 키 | REST + 키 | REST/프록시 + 키 | REST + 키 |
| 증거 | docs (필드명) + 마케팅 (가격) | 샘플 (필드명), docs 가격 | 샘플 (필드명), 마케팅 가격 | 마케팅 | 샘플 (광고 없음), 마케팅 |

- 100개 쿼리 1회 비용: DataForSEO 표준 큐 약 $0.06, 라이브 약 $0.20. SerpApi는 무료 250건 안에서 가능하며 유료로는 $25 플랜의 10% 사용. SearchAPI.io 약 $0.40 (플랜 최소 $40). Bright Data 약 $0.15. Serper 약 $0.10이지만 광고가 없어 의미 없음.
- 브랜드 키워드에 광고가 항상 뜨지는 않는다. 광고가 비어 있는 것이 정상인 쿼리가 있다.
- SerpApi 변경 기록에는 일부 검색에서 광고 추출이 빠졌다가 고쳐진 사례가 있다 (SerpApi 주간 변경 로그). 광고 누락이 서비스 쪽 문제일 수 있다는 뜻이다.
- DataForSEO는 Google Ads 검색 / 광고주 API도 따로 있는데 이는 Transparency Center 기반이고 키워드 광고 노출이 아니다. 이번 용도는 organic 엔드포인트의 `paid` 아이템이다.

**판정: 해결.** 추천은 DataForSEO(필드 문서 명확, 건당 가장 저렴). 소량이라 설정 부담을 피하려면 SerpApi 무료 250건/월이 충분하다. Serper는 제외.

---

## 갭 4. Google Trends 12개월 주간 (대체용)

| 항목 | DataForSEO Google Trends | SerpApi Google Trends | SearchAPI.io Google Trends | Google 공식 Trends API |
|---|---|---|---|---|
| URL | https://docs.dataforseo.com/v3/keywords_data/google_trends/explore/live/ | https://serpapi.com/google-trends-api | https://www.searchapi.io/docs/google-trends | https://developers.google.com/search/apis/trends |
| 한 요청에 5개 용어 비교 | 예. `keywords` 최대 5 | 예. 쿼리 최대 5 (interest over time) | 예. `q`에 쉼표로 최대 5 | 해당 없음 (수십 개 비교 가능하다고 소개) |
| 0~100 주간 시리즈 | 예. `values`는 0~100, "100 is the peak". `time_range: past_12_months`. 샘플 응답이 주 단위 구간(`date_from`, `date_to`, `values`) | 응답 `interest_over_time` 값은 `value`, `extracted_value`. 0~100 척도는 문서에 명시 없음, 주간 여부도 명시 없음 | `interest_over_time.timeline_data.values[].extracted_value`. `time=today 12-m`. 주간은 예시 날짜 구간으로 추정 | 아니오. 0~100 정규화를 하지 않음. 최근 5년, 일/주/월/년 집계 |
| 가격 | 표준 모드 $0.0027 / 태스크(최대 45분 대기), 라이브 $0.011 / 태스크 | 1 요청 = 1 검색. $25/월 1,000건, 무료 250건 | 1 요청 = 1 검색. $4/1,000, 100 무료 | 가격 미공개. 알파, 선별 테스터만 |
| 증거 | docs + 샘플 + 가격 페이지 | docs (일부), 가격 페이지 | docs | docs (공식) |

- 척도 주의: 0~100은 한 요청에 함께 넣은 용어끼리 상대값이다. 용어 묶음이 달라지면 값이 달라진다. 직접 코드와 같은 묶음 구성을 써야 비교 가능하다.
- 1회 비용: 5개 브랜드를 한 묶음으로 1~5요청이면 DataForSEO $0.003~0.06, SerpApi는 무료 한도 안.
- Google 공식 API는 알파이고 신청 후 선별되므로 계획에 넣지 않는다.

**판정: 해결(대체용).** DataForSEO가 가장 저렴하고 0~100 주간 구조가 문서에 있다.

---

## 갭 5. Google Ads Transparency Center

| 항목 | SerpApi | SearchAPI.io |
|---|---|---|
| URL | https://serpapi.com/google-ads-transparency-center-api | https://www.searchapi.io/docs/google-ads-transparency-center-api |
| 유료 API 존재 | 예 | 예 |
| 광고 문구가 텍스트로 오나 | 문서에 필드 없음. `format`(text/image/video), `link`(미리보기 링크)만 | 목록 응답에 문구 필드 없음. 상세는 별도 Ad Details API로 안내하나 거기에 문구가 있는지는 확인 못함 |
| 직접 수집에 없는 것 | `advertiser`, `first_shown`, `last_shown`, `total_days_shown` | `domain` 파라미터, `platform`, `ad_format`, `target_domain`, `total_days_shown`, 페이지당 `num` 최대 100 |

**판정: 직접 수집 유지.** 텍스트 문구를 주는 것이 확인되지 않았다.

---

## 확인하지 못한 것

- SearchAPI.io Meta 광고 응답에서 한 페이지당 건수, `images`/`videos` 내부 구조.
- ScrapeCreators Facebook 광고의 시작일, 플랫폼, 미디어 URL 필드와 TikTok 광고 응답 필드.
- 어떤 서비스가 US 상업 광고를 30건 이후까지 실제로 끝까지 돌려주는지 (호출하지 않았음).
- PiPiADS/BigSpy/Minea의 공식 API 조건과 가격, US TikTok 광고 커버리지.
- Bright Data의 광고 필드명, SerpApi의 카드 필요 여부, DataForSEO 체험 크레딧의 최신 조건(검색 요약만 확인).
- Apify 액터들의 실제 안정성. 사용자 수가 적고 일부는 성공률 0~85%로 표기됨.

## 사용한 출처

- https://developers.facebook.com/docs/graph-api/reference/ads_archive/
- https://transparency.meta.com/researchtools/ad-library-tools
- https://www.searchapi.io/docs/meta-ad-library-api
- https://www.searchapi.io/pricing
- https://docs.scrapecreators.com/v1/facebook/adLibrary/company/ads
- https://docs.scrapecreators.com/
- https://scrapecreators.com/ (검색 요약)
- https://scrapecreators.com/tiktokAdLibrary-search-api
- https://scrapecreators.com/blog/tiktok-ads-scrapers
- https://apify.com/pricing
- https://apify.com/fascinating_lentil/facebook-ad-library-scraper
- https://apify.com/good-apis/facebook-ads-scraper.md
- https://apify.com/dltik/tiktok-creative-center
- https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en
- https://www.pipiads.com/pricing
- https://affiliatetools-co.pages.dev/ad-spy-tools/pipiads-review/ (블로그)
- https://serpapi.com/google-ads-api
- https://serpapi.com/pricing
- https://serper.dev
- https://docs.dataforseo.com/v3/serp/google/organic/live/advanced/
- https://dataforseo.com/pricing/serp/google-organic-serp-api
- https://dataforseo.com/help-center/minimum-payment (검색 요약)
- https://www.searchapi.io/docs/google
- https://brightdata.com/products/serp-api
- https://serpapi.com/google-trends-api
- https://www.searchapi.io/docs/google-trends
- https://docs.dataforseo.com/v3/keywords_data/google_trends/explore/live/
- https://dataforseo.com/pricing/keywords-data/google-trends
- https://developers.google.com/search/apis/trends
- https://serpapi.com/google-ads-transparency-center-api
- https://www.searchapi.io/docs/google-ads-transparency-center-api
