# 유료 외부 서비스 조사: 커머스·소셜 수집 공백

조사일: 2026-11-10. 공개 문서, 가격 페이지, 샘플 응답만 읽었다. 가입, 유료 API 호출, 개인정보 입력은 하지 않았다.

근거 등급 표기:
- 문서 = 벤더 공식 API 문서
- 샘플 = 벤더가 공개한 샘플 응답 또는 필드 목록
- 마케팅 = 벤더 소개/랜딩 페이지, Apify 액터 소개문
- 블로그 = 제3자 블로그

비용 가정: 브랜드 5개, 브랜드당 상품 약 10개(총 50개), 상품당 리뷰 20개, TikTok은 브랜드당 게시물 20개(총 100개). 환율은 쓰지 않고 USD로 적는다. "1회 실행 비용"은 사용량 비용이며 월 최소 플랜 요금은 따로 적는다.

## 요약

| 공백 | 판정 | 추천 서비스 | 1회 실행 비용 (브랜드 5개) | 근거 등급 |
|---|---|---|---|---|
| 1. Amazon 리뷰 본문 | 부분 해결 | Unwrangle (쿠키 없이 최근 8개, 쿠키 있으면 전체). 대안: Apify memo23 | Unwrangle 약 100 크레딧 (월 $99 플랜 기준 약 $0.10, 단 월 최소 $99) | 문서 + 블로그. 쿠키 없는 8개 한도는 일치. 쿠키 방식의 실제 동작은 미확인 |
| 2. Target 쉘프 | 대부분 해결 | RedCircle API (검색·상품·리뷰). 리뷰 필드 확인용 대안: Unwrangle | RedCircle 약 55~105 요청 (Hobbyist $18/월 안에 들어감) | 문서(검색 필드), 문서(리뷰 파라미터). RedCircle 리뷰 응답 필드명은 미확인 |
| 3. Chewy 쉘프 | 부분 해결 (Kasada 우회 미확인) | Apify parseforge/chewy-com-scraper (검색) + captivated_mix/chewy-reviews-scraper (리뷰) | 약 $0.5 이하 (Apify 무료 $5/월 안) | 마케팅. 필드명 일부만 확인 |
| 4. TikTok 게시물 | 해결 | Apify clockworks/tiktok-scraper. 대안: ScrapeCreators, EnsembleData | 약 $0.2 | 문서/액터 소개 (필드명 확인) |
| 5. TikTok Shop | 해결 (판매량 확인, 상품 평점은 서비스별 차이) | ScrapeCreators 또는 Apify lurkapi/tiktok-shop-scraper | 약 $0.1~0.3 | 샘플 + 마케팅 |
| 6. Cloudflare 뒤 Shopify | 부분 해결 / 전용 제공자 없음 | Apify Shopify 액터 (주거용 프록시 폴백). 아니면 범용 "웹 언블로커" 범주 | 약 $1 이하 + 프록시 비용 (확인 불가) | 마케팅 |

가장 중요한 사실 세 가지:
1. Amazon 리뷰는 로그인 벽 때문에 쿠키 없이는 상품당 약 8개가 상한이다. 쿠키 없이 20개를 보장하는 서비스는 찾지 못했다.
2. TikTok(게시물, Shop)과 Target은 공개 문서로 필요한 필드를 대부분 확인했다. 비용도 1회 1달러 미만이다.
3. Chewy(Kasada)와 Shopify(Cloudflare)는 "우회된다"는 벤더 주장만 있고 검증 자료가 없다. 시험 호출이 필요하다.

---

## 1. Amazon 리뷰 본문

로그인 벽에 대한 사실 (블로그, 2026-08-21 기준 Thunderbit 글 등): Amazon은 2024-11-14경부터 전체 리뷰 페이지(/product-reviews)를 로그인 뒤로 옮겼다. 로그아웃 상태에서는 상품 페이지(/dp/)의 대표 리뷰 약 8개만 보인다. Amazon 국가 도메인마다 벽이 따로 적용된다.

| 항목 | Unwrangle Amazon Reviews | Apify memo23/amazon-reviews-scraper | Rainforest API (Traject Data) | Bright Data Amazon Reviews |
|---|---|---|---|---|
| URL | https://www.unwrangle.com/scrapers/amazon-reviews-scraper/api/ , https://help.unwrangle.com/en/articles/10182781-tutorial-how-to-scrape-amazon-reviews | https://apify.com/memo23/amazon-reviews-scraper | https://docs.trajectdata.com/rainforestapi/product-data-api/parameters/reviews | https://brightdata.com/solutions/data-extraction/amazon/reviews |
| 로그인 벽 언급 | 있음. 쿠키 없이는 "최근 8개". 전체는 본인 Amazon 계정 쿠키를 `cookie` 파라미터로 전달 (문서/도움말) | 있음. 쿠키 입력 없음. amazon.com은 방문자에게 리뷰 0개라 다른 마켓(UK, CA, FR, DE)으로 대체. 2026-10 점검 결과 5~9개 (액터 소개) | 문서에 언급 없음. 블로그가 "8개 한도" 주장, Trustpilot 일부 후기(2026)가 reviews 타입 503 보고. 미확인 | "로그인 뒤 콘텐츠에 접근하지 않는다"고만 명시 (마케팅). 상품당 리뷰 수 미기재 |
| 쿠키 필요 | 전체 보려면 필요 (본인 계정) | 불필요 | 불명 | 불필요라고 주장, 단 개수 미기재 |
| 상품당 리뷰 수 | 쿠키 없음 8개. 쿠키 있음: 페이지 단위, 한 블로그는 최대 500개 가능이라 주장 (블로그, 불확실) | 보통 5~15개 (중복 제거 후) | 문서상 reviews 페이지 최대 500, `max_page`로 다중 페이지. 실제 로그인 벽 아래 동작은 미확인 | 미기재 |
| 반환 필드 | "페이지에 보이는 모든 필드" (도움말). 필드명 목록은 못 봄 | reviewId, asin, marketplace, rating, title, text, date, dateRaw, author, verifiedPurchase, helpfulVotes 등 (액터 소개 필드 목록) | 필드명 목록을 이번에 못 봄 (문서 URL 404) | 목록 일부만: URL, product name, rating, author name, ASIN "and more" |
| 가격 | 요청당 1 크레딧 (도움말: 10에서 인하, 실험적이라 변경 가능). 플랜: Starter $99/월 100,000 크레딧, Standard $249, Professional $499. 카드 불필요 표기, 무료 체험은 미확인 (가격 페이지) | $4.00 / 1,000 리뷰 (액터 소개). Apify 무료 플랜 월 $5, 카드 불필요 (가격 페이지) | Hobbyist $18/월 500 요청, Starter $66/월 10,000 요청. 무료 체험 100 요청, 카드 불필요 (가격 페이지) | 종량제 $0.75~1.5 / 1K 레코드, 월 5K 레코드 무료, 카드 필요 여부 미기재 |
| 사용 방식 | REST API + 키 | Apify 액터 실행 | REST API + 키 | Scraper API 또는 데이터셋 |
| 근거 등급 | 문서/도움말 | 마케팅(액터 소개) | 문서(파라미터), 블로그(문제 보고) | 마케팅 |

해석:
- 쿠키 없이 가능한 최대치는 상품당 약 8개다. 현실적으로 "20개"를 원하면 본인 Amazon 계정 쿠키가 필요하다. 쿠키는 몇 일~몇 주 지나면 만료된다는 보고가 있다 (블로그). 계정 약관과 보안 위험은 따로 판단해야 한다.
- Scrapingdog은 한 2026 비교 블로그에서 reviews 엔드포인트가 동작하지 않는다고 했다 (블로그, 미검증). Oxylabs는 리뷰 개수 설정 파라미터가 있다는 제3자 벤치마크만 있고 로그인 벽 언급은 못 찾았다.
- 확인하지 못한 것: Rainforest와 Bright Data가 지금 amazon.com 리뷰를 몇 개 주는지. 가입 후 상품 1개로 시험하는 수밖에 없다.

1회 실행 비용 (50상품, 상품당 20개 가정):
- 쿠키 없이 (Unwrangle): 50 요청 = 50 크레딧, 상품당 8개만 얻는다.
- 쿠키 있이 (Unwrangle): 약 2페이지 × 50 = 100 크레딧, 페이지당 리뷰 수는 미확인. 월 $99 플랜이 최소 비용이다.
- Apify memo23: 50상품 × 약 8개 = 400개 × $4/1K = 약 $1.6 (amazon.com 외 마켓 리뷰가 섞임).

판정: 부분 해결.

---

## 2. Target 쉘프

| 항목 | RedCircle API (Traject Data) | Unwrangle Target |
|---|---|---|
| URL | https://docs.trajectdata.com/redcircleapi/target-product-data-api/overview , .../parameters/reviews | https://docs.unwrangle.com/target-product-reviews-api , https://docs.unwrangle.com/target-product-search-api |
| 검색 (순위, ID, 제목, 가격, 평점, 리뷰 수) | `type=search` + `search_term`. 항목에 `position`, `product.title`, `product.tcin`, `product.rating`, `product.ratings_total`, `offers.primary.price` (문서 응답 필드) | `platform=target_search` + `search`. 항목에 `id`, `name`, `price`, `rating`, `total_ratings`, 검색당 최대 40개. `position` 필드는 없음 (배열 순서로 대체) (문서) |
| 리뷰 본문 | `type=reviews` + `tcin` 또는 `url`. 필터: `reviewer_type=verified_purchase`, `sort_by`, `page`, `max_page` (문서). 응답 필드명(rating, title, body, date)은 이번에 못 봄 | `platform=target_reviews`. 필드: `id`, `date`, `author_name`, `rating`, `review_title`, `review_text`, `meta_data`(구매 인증 등) (문서). 페이지당 개수는 미기재, 최대 51페이지 |
| 가격 | 요청당 1 크레딧. Hobbyist $18/월 500 요청, Starter $66/월 10,000 요청, 초과 요청 $0.06 / $0.0118. 무료 체험 100 요청, 카드 불필요 (가격 페이지) | 검색 2.5 크레딧(문서; 샘플은 1로 불일치), 리뷰 요청당 10 크레딧. 월 $99부터 (가격 페이지) |
| 사용 방식 | REST API + `api_key` | REST API + `api_key` |
| 근거 | 문서 | 문서 |

1회 실행 비용:
- RedCircle: 검색 5 요청 + 리뷰 50상품 × 1~2페이지 = 약 55~105 요청. Hobbyist $18/월(500 요청) 안에 들어간다. 무료 체험 100 요청으로 먼저 시험 가능.
- Unwrangle: 5 × 2.5 + 50 × 10 = 약 512 크레딧. 월 $99 플랜 필요.

Target이 PerimeterX로 막아도 이 서비스들은 자체 API로 제공하므로 우리 쪽 차단과 무관하다 (벤더 주장, 시험 호출 필요). 브랜드가 Target에 입점하지 않은 경우(예: 일부 브랜드)는 결과가 비어 있을 수 있다.

판정: 대부분 해결. RedCircle의 리뷰 응답 필드명만 가입 후 확인하면 된다.

---

## 3. Chewy 쉘프 ("jinx dog food")

| 항목 | Apify parseforge/chewy-com-scraper (검색) | Apify captivated_mix/chewy-reviews-scraper (리뷰) | Bright Data Chewy | Unwrangle Chewy |
|---|---|---|---|---|
| URL | https://apify.com/parseforge/chewy-com-scraper | https://apify.com/captivated_mix/chewy-reviews-scraper | https://brightdata.com/products/web-scraper/chewy | https://docs.unwrangle.com/chewy-product-data-api |
| 입력 | `searchTerm`, `maxItems` | 상품 URL, `maxReviews`(기본 200) | 상품 URL만 (키워드 검색 불가로 보임) | 상품 URL (`chewy_detail`). 검색/리뷰는 문서에서 확인 못 함 |
| 필드 | 가격, autoship 가격, 평점, 리뷰 수, 재고 (소개문). 정확한 필드명과 순위, 상품 ID는 미기재 | `productUrl`, `catalogEntryId`, `productName`, `reviewId`, `username`, `title`, `text`, `rating`, `submittedAt`, `helpfulVotes`, `verifiedPurchase` | URL, item id, GTIN, title, description, category. 가격/평점/리뷰 수는 목록에 없음 | 미확인 |
| 가격 | $5.00~5.50 / 1,000 결과 (페이지 내 두 수치 불일치) | $1.00 / 1,000 리뷰 + Apify 사용료 | 종량제 $1.5 / 1K, 월 5K 무료, 카드 불필요 | 미확인 |
| Kasada 대응 | 언급 없음. "요청 타이밍과 재시도 자동 관리"만 | 언급 없음 | 언급 없음 | 언급 없음 |
| 근거 | 마케팅 | 마케팅 | 마케팅 | 검색 결과 요약만 |

Apify는 무료 플랜 월 $5, 카드 불필요 (가격 페이지). Oxylabs는 Chewy 전용 파서가 없고 URL 기반 원본 HTML만 제공한다 (마케팅).

1회 실행 비용 (Jinx 한 브랜드, 상품 10개, 리뷰 20개씩): 검색 약 10결과 ≈ $0.06, 리뷰 200개 ≈ $0.2. 합계 약 $0.3, 무료 $5 안에 들어간다.

확인하지 못한 것: 이 액터들이 Kasada를 실제로 통과하는지. parseforge 액터는 사용자 6명/월, 총 57명이라 검증이 적다 (액터 페이지 통계). 다른 액터(arcana, jungle_synthesizer, stealth_mode)도 있으나 열어보지 않았다.

판정: 부분 해결. 필드는 대체로 맞지만 순위와 상품 ID 필드, 차단 우회는 시험 호출로 확인해야 한다.

---

## 4. TikTok 게시물

| 항목 | Apify clockworks/tiktok-scraper | ScrapeCreators | EnsembleData |
|---|---|---|---|
| URL | https://apify.com/clockworks/tiktok-scraper | https://scrapecreators.com/tiktok-keyword-api , https://scrapecreators.com/tiktok-hashtag-api | https://apify.com/ensembledata/tiktok-api/pricing (EnsembleData 자체 사이트는 열어보지 않음) |
| 조회 방식 | `hashtags`, `searchQueries`, `profiles` + `profileSorting=popular` (조회순 인기 정렬, 프로필당 약 400~500개 상한) | `GET /v1/tiktok/search/keyword` (`query`, `date_posted`, `sort_by`, `region`), `GET /v1/tiktok/search/hashtag`, `GET /v3/tiktok/profile/videos` (`sort_by`, `max_cursor`) | 키워드 검색은 1 유닛에 20개 게시물 (블로그), 해시태그 검색 1 유닛 |
| 필드 | `playCount`, `diggCount`, `authorMeta.name`, `createTimeISO` (액터 소개) | 프로필 영상 페이지: `play_count`, `digg_count`, `create_time`, `author` (소개 페이지). 키워드 응답 필드와 `sort_by` 허용값은 못 봄 | 미확인 |
| 가격 | $1.70 / 1,000 결과 + Apify 사용료 없음(pay-per-event). 무료 플랜 월 $5 | 크레딧 1/요청. 무료 100 크레딧(카드 불필요), $47 / 25,000 크레딧 ($1.88/1K), $497 / 500,000. 구매 크레딧은 만료 없음 | Wood $100/월 일 1,500 유닛, 무료 체험 일 50 유닛, 미사용 유닛 소멸 (블로그, 2026 중반) |
| 사용 방식 | 액터 실행 | REST + `x-api-key` | REST + 토큰 |
| 근거 | 마케팅(액터 소개, 필드명 명시) | 마케팅/문서 일부 | 블로그 |

보충:
- 해시태그 피드는 정렬 옵션이 없고 TikTok 기본 순서로 나온다 (khadinakbar 액터 소개). "조회수 상위"를 원하면 브랜드 공식 프로필을 `popular` 정렬로 받는 방식이 가장 직접적이다. 키워드 검색은 `most-liked`(좋아요순) 정렬이 있다 (khadinakbar/tiktok-video-search-scraper, $2/1,000). 조회수순 정렬은 확인 못 했고, 받은 뒤 `playCount`로 직접 정렬해야 한다.
- ScrapeCreators는 "게시물이 페이지를 다 넘겨도 누락될 수 있다"고 스스로 적었다 (소개 페이지).
- Bright Data TikTok Posts는 키워드/해시태그/프로필 입력, `create_time`, `digg_count`는 확인했으나 조회수 필드는 확인 못 했다. 종량제 $1.5/1K, 월 5K 무료.

1회 실행 비용: 100게시물 ≈ $0.17 (clockworks). 안전하게 3배 수집해도 $0.6 이하.

판정: 해결.

---

## 5. TikTok Shop

| 항목 | ScrapeCreators TikTok Shop | Apify lurkapi/tiktok-shop-scraper | Apify unseenuser/tiktok-shop-scraper | 분석 도구 (Kalodata, FastMoss, EchoTik) |
|---|---|---|---|---|
| URL | https://scrapecreators.com/tiktok-shop-search-api , https://scrapecreators.com/blog/tiktok-shop-api | https://apify.com/lurkapi/tiktok-shop-scraper | https://apify.com/unseenuser/tiktok-shop-scraper | https://api.echotik.live/guides/tiktok-shop-data-api-tools-comparison-2026 |
| 입력 | 검색: `GET /v1/tiktok/shop/search` (`query`, `page`, `region`). 상점 목록: `/v1/tiktok/shop/products` (상점 URL, `sort_by=top`) | `keywords`, `hashtags`, `shopIds`, `country=US` | `mode=shop_search` + `searchKeywords`, 또는 `shop_catalog` + `shopUrls` | EchoTik: "API 접근 요청" 버튼. Kalodata, FastMoss: 웹앱 중심, API 여부 미확인 |
| 판매량 | `sold_info.sold_count` (블로그 샘플 응답). 상품 상세: `product_base.sold_count` | `soldCount` (평생 판매량) | `soldCount` | EchoTik 페이지는 판매 지표 필드를 명시하지 않음 |
| 가격 | `product_price_info.sale_price_decimal`, `origin_price_format` | `price`, `originalPrice` | `price`, `priceDisplay` | 미확인 |
| 평점, 상점명 | 상점명 `seller_info.shop_name` 있음. 검색 응답에는 평점 없음. 상품 상세에 `shop_info.shop_rating`(상점 평점) | `rating`, `reviewCount`, `sellerName` | `rating`, `ratingStars`, `reviewCount`, `shopName`(TikTok이 노출할 때만) | 미확인 |
| 가격(비용) | 크레딧 1/요청 (제품 엔드포인트, 검색은 미기재). $47 / 25,000 크레딧. 무료 100 크레딧, 카드 불필요 | $1.99 / 1,000 상품. 리뷰 5개까지 포함, 추가 $2 / 1,000 리뷰 | $4.50 / 1,000 결과 | EchoTik 요금제는 제3자 블로그에서 $9.90~29.90/월이나 API 포함 여부 불명 |
| 미국 지원 | 기본 US. 타 지역 불안정 (소개) | US 지원 (UK, MX, TH도) | US만 | EchoTik은 US, UK, SEA 표기 (마케팅) |
| 근거 | 샘플(벤더 블로그 필드 목록) | 마케팅(액터 소개) | 마케팅. 이 액터는 `SCRAPECREATORS_API_KEY`가 필요해 ScrapeCreators 래퍼로 보임 | 마케팅. 필드와 가격 미확인 |

Bright Data TikTok Shop은 제품 스크레이퍼가 있으나 판매량 필드는 확인하지 못했다 (마케팅 페이지, 필드 목록에 없음). Oxylabs는 TikTok Shop Search 타깃이 있다고 하나 문서 페이지가 404여서 필드를 못 봤다.

브라우저의 "Verify to continue" 퍼즐은 이 API들이 자체 처리한다고 주장하지만 우리 쪽에서 검증하지 못했다. 단, TikTok Shop에서 "브랜드 공식 상점"이 미국에서 실제로 운영 중인지는 별개 문제다. 검색 결과가 비어 있을 수 있다.

1회 실행 비용: 브랜드 5개 × 상품 10개 = 50상품. lurkapi 약 $0.1, ScrapeCreators 약 5~10 요청.

판정: 해결 (판매량과 가격은 두 곳 이상에서 필드 확인). 상품 평점이 필요하면 lurkapi 쪽이 낫다. 분석 도구 3종은 이번 목적에는 쓸 수 없는 것으로 본다 (API 명세 미공개).

---

## 6. Cloudflare 뒤 Shopify (blackriflecoffee.com)

Shopify 상점 카탈로그 전용 구조화 데이터 제공자는 찾지 못했다. 가장 가까운 것은 `/products.json`을 감싼 Apify 액터들이다.

| 항목 | Apify jamhimself/shopify-products-scraper | 범용 "웹 언블로커 / 스크레이핑 API" 범주 |
|---|---|---|
| URL | https://apify.com/jamhimself/shopify-products-scraper | Bright Data Web Unlocker, Oxylabs Web Scraper API 등이 이 범주 (추천하지 않음, 범주만 명시) |
| 방식 | `products.json`을 직접 호출. 봇 방어가 있는 상점은 주거용 프록시 엔진으로 폴백 (소개문) | 임의 URL을 대신 받아 원본 JSON/HTML 반환. 구조화는 우리가 처리 |
| 필드 | `id`, `handle`, `title`, `vendor`, `productType`, `tags`, `priceMin`, `priceMax`, `variants`(sku, price, compareAtPrice, available), `url` | 원본 응답 그대로 |
| 가격 | $4.00 / 1,000 상품. 주거용 프록시 비용은 별도이고 미기재 | Oxylabs 예: /Scrape 일반 요금 $0.50 / 1K부터 (마케팅) |
| 403 우회 | 403이라는 말은 없고 "Cloudflare 뒤 상점은 주거용 프록시 필요"라고만 함 (마케팅). 미검증 | 범주 설명상 가능하나 blackriflecoffee.com에 대해서는 미검증 |
| 근거 | 마케팅 | 마케팅 |

참고:
- 상점이 `/products.json`을 아예 끈 경우(Shopify Plus, 헤드리스)에는 IP를 바꿔도 소용없다 (Decodo 블로그). blackriflecoffee.com은 일반 브라우저에서 열리므로 켜져 있다.
- 일부 액터는 `products.json`이 막히면 XML 사이트맵과 상품별 JSON으로 폴백한다 (검색 결과 요약, 액터 소개).
- Shopify는 robots.txt에서 자동 수집을 제한하는 문구를 추가했다 (블로그). 약관 확인이 필요하다.

1회 실행 비용: 상품 약 50~200개 ≈ $0.2~0.8 + 프록시 비용(확인 불가).

판정: 부분 해결. 전용 제공자는 없고, 액터 또는 범용 언블로커 범주만 있다.

---

## 확인하지 못한 것

- Rainforest API와 Bright Data가 지금 amazon.com 리뷰를 몇 개 주는지, 로그인 벽 아래 동작.
- RedCircle 리뷰 응답의 필드명, Target 리뷰 페이지당 개수.
- Chewy 액터가 Kasada를 통과하는지, 검색 결과의 순위/ID 필드.
- ScrapeCreators 키워드 검색의 `sort_by` 허용값, Shop Search의 크레딧 비용.
- Kalodata, FastMoss, EchoTik의 API 명세와 가격. EchoTik은 문의 후 접근이라고만 나옴.
- TikAPI 가격, EnsembleData 자체 사이트 가격 (블로그 수치만).
- Shopify 액터가 blackriflecoffee.com의 403을 실제로 통과하는지.
- 가격은 모두 2026년 문서 시점이며 벤더가 바꿀 수 있다 (예: Unwrangle은 크레딧 인하가 "실험"이라고 적음).

## 출처 URL

- https://docs.trajectdata.com/rainforestapi/product-data-api/parameters/reviews (검색 결과 요약으로만 확인, 직접 열면 404)
- https://trajectdata.com/amazon-reviews-api-insights-drive-sales/ (2025-09-29)
- https://trajectdata.com/pricing/
- https://trajectdata.com/ecommerce/red-circle-api/pricing/
- https://docs.trajectdata.com/redcircleapi/target-product-data-api/overview
- https://docs.trajectdata.com/redcircleapi/target-product-data-api/parameters/reviews
- https://www.unwrangle.com/#pricing
- https://help.unwrangle.com/en/articles/10182781-tutorial-how-to-scrape-amazon-reviews
- https://docs.unwrangle.com/target-product-reviews-api
- https://docs.unwrangle.com/target-product-search-api
- https://docs.unwrangle.com/chewy-product-data-api (검색 결과 요약으로만 확인)
- https://apify.com/memo23/amazon-reviews-scraper.md
- https://apify.com/pricing
- https://www.openwebninja.com/blog/best-amazon-apis-2026
- https://dev.to/psymall/how-to-get-amazon-review-rating-data-at-scale-and-whats-actually-public-in-2026-4o93
- https://thunderbit.com/blog/scrape-amazon-reviews-with-python (2026-08-21)
- https://www.shopifreaks.com/amazon-lets-some-shoppers-read-only-eight-customer-reviews-per-product-after-its-anti-scraping-systems-flag-them-as-bots/
- https://brightdata.com/solutions/data-extraction/amazon/reviews
- https://brightdata.com/products/web-scraper/chewy
- https://brightdata.com/products/web-scraper/tiktok/posts
- https://oxylabs.io/products/scraper-api/ecommerce/chewy
- https://apify.com/parseforge/chewy-com-scraper.md
- https://apify.com/captivated_mix/chewy-reviews-scraper.md
- https://apify.com/clockworks/tiktok-scraper
- https://apify.com/khadinakbar/tiktok-video-search-scraper.md
- https://scrapecreators.com/
- https://scrapecreators.com/tiktok-profile-videos-api
- https://scrapecreators.com/tiktok-shop-search-api
- https://scrapecreators.com/tiktok-shop-products-api
- https://scrapecreators.com/blog/tiktok-shop-api
- https://docs.scrapecreators.com/v1/tiktok/profile/videos
- https://apify.com/lurkapi/tiktok-shop-scraper.md
- https://apify.com/unseenuser/tiktok-shop-scraper.md
- https://api.echotik.live/guides/tiktok-shop-data-api-tools-comparison-2026
- https://www.socialcrawl.dev/blog/best-tiktok-data-apis-2026 (EnsembleData 가격, 블로그)
- https://apify.com/jamhimself/shopify-products-scraper.md
- https://community.shopify.dev/t/products-json-file/39186
