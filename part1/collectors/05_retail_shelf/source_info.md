# 소스 5: 리테일러 진열대 (Sephora, Ulta, Target, Chewy 중 브랜드에 맞는 곳 하나)

- 확인일: 2026-11-10 (미국 IP이지만 데이터센터 대역, 화면이 뜨는 Chrome)
- 확인 대상: Ulta(Batiste 29건, Living Proof 45건, 상품 상세 1건, 리뷰 1쪽), Sephora(검색 목록 3회). Target과 Chewy는 직접 여는 방식으로는 막혔고, Apify 수집기 시험으로 Target 검색 3종(Death Wish 10건, Black Rifle 5건, Jinx 5건)과 리뷰 10건, Chewy 검색 10건을 받았다(11절).
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정이거나 미확인
- 나간 IP: `187.15.89.243`, ipinfo 기준 Seattle, `AS212238 Datacamp Limited`. 일반 가정용 회선이 아니라 데이터센터 대역이다 ✅. 아래 차단 중 일부는 이 때문일 수 있다 ❓.

## 1. 이 소스가 주는 것
리테일러 사이트의 상품 진열대 한 화면이다. **한 행은 (수집 시점, 리테일러, 목록, 상품) 1개**다. 목록 순서(위치), 가격, 평점, 리뷰 수, 배지가 오고, 상품 페이지에서는 리뷰 본문이 온다.

## 2. 접근 방법
4곳 중 **데이터를 실제로 받은 곳은 Ulta 하나뿐**이다. Sephora는 검색 목록만 열린다.

### 2-1. Ulta ✅ (가장 쉽다)
- 로그인이 필요 없다 ✅. 헤드리스는 확인하지 않았다 ❓.
- 목록 주소: `https://www.ulta.com/brand/<브랜드>` (예: `/brand/batiste`, `/brand/living-proof`). 검색은 `https://www.ulta.com/search?search=<검색어>&skipRedirect=true`. 홈 화면의 검색창이 이 주소 형식을 쓴다 ✅.
- **상품 목록은 별도 요청이 아니라 HTML 문서 안에 JSON으로 박혀 있다** ✅ (Batiste 문서 약 1.8MB, 상품 29개 전부). `ulta.com/dxl/graphql`은 헤더, 추천 상품, 매장 정보를 불러오는 요청이고 목록은 거기 없다 ✅.
- 한 화면에 `pageSize` 64가 들어가서 29건, 45건 모두 한 번에 온다 ✅. 64건을 넘는 브랜드는 `?page=2` 형식의 더보기 주소 템플릿이 응답에 있다(`loadMoreTemplateUrl`). 실제로 넘겨 보지는 않았다 ❓.
- 상품 페이지: 목록 안의 링크(`/p/<이름>-<productId>?sku=<sku>`)로 연다 ✅.
- 리뷰는 상품 페이지가 스스로 PowerReviews에 요청한다(4절).
- 브랜드당 요청 수: 목록 1회 + 보고 싶은 상품마다 상세 1회.

### 2-2. Sephora (검색만 열린다)
- 로그인이 필요 없다. 검색 주소 `https://www.sephora.com/search?keyword=<검색어>`는 200으로 열렸다 ✅ (3회 모두).
- 검색 페이지가 스스로 `https://www.sephora.com/api/v2/catalog/search/?type=keyword&q=<검색어>&page=60&currentPage=1&...`를 부른다. 이 응답 하나에 상품 57개(Living Proof)가 전부 들어 있다 ✅.
- **브랜드 페이지 `/brand/living-proof`와 상품 페이지 `/product/...`는 이 출구 IP에서 HTTP 403 "Access Denied"(Akamai)로 막혔다** ✅. 브랜드 페이지는 3번 시도했고 그중 한 번은 홈을 먼저 열고 갔다. 같은 세션에서 검색은 열렸다 ✅. CAPTCHA 화면은 뜨지 않았다. 한국 IP에서는 브랜드 페이지가 열렸다는 이전 기록이 있다(이번에 재확인 못 함 ❓).
- 상품 상세와 리뷰는 못 봤다. 리뷰 공급사도 못 봤다 ❓.

### 2-3. Target ✅ 막힘
- `https://www.target.com/s?searchTerm=death+wish+coffee`: 문서는 200이지만 화면은 "We're sorry! This page is currently unavailable."이다 ✅.
- 페이지가 보내는 `redsky.target.com/.../plp_search_v2`와 `cdui_orchestrations/.../pages/slp`가 모두 **HTTP 435**다 ✅. 본문은 PerimeterX 차단 정보(`appId: PXGWPp4wUS`, `captcha.px-cdn.net` 스크립트 주소)였다 ✅. 화면에 CAPTCHA는 뜨지 않았다. 규칙에 따라 여기서 멈췄다. 한국 IP만의 문제가 아니었다.
- 같은 페이지에서 `ZIP 95054 San Jose` 매장이 자동으로 잡혔다(IP 위치 기준으로 보임) ✅.
- Apify 공식 수집기로는 검색 목록과 리뷰가 받아졌다 ✅ (11-1, 11-2절).

### 2-4. Chewy ✅ 막힘
- `https://www.chewy.com/s?query=jinx+dog+food`: HTTP 429, 본문은 Kasada(`KPSDK`, `ips.js`) 스크립트뿐이고 화면 글자는 비어 있다 ✅. 한 번 시도하고 멈췄다.
- Apify 공식 수집기는 Chewy에서 쓸 수 없는 결과를 줬고, 대체 수집기 `parseforge/chewy-com-scraper`로는 Jinx 목록이 받아졌다 ✅ (11-3, 11-4절).

## 3. 브랜드 매칭
검색창에 브랜드 이름을 넣고 결과 수와 결과의 브랜드명을 같이 봤다. **결과 수만 보면 틀린다.** Sephora에서 `batiste`는 342건, `death wish coffee`는 44건이 나오지만 전부 다른 상품이다(퍼지 검색) ✅.

**20칸 모두 확인했다(2026-11-10).** 비어 있던 칸은 사용자 Chrome에서 검색 화면을 한 번씩 열어 채웠다(`samples/brand_x_retailer_presence_check.json`).

| 브랜드 | Ulta | Sephora | Target | Chewy |
|---|---|---|---|---|
| Batiste | **있음** ✅ 29개 (브랜드 페이지) | 없음 ✅ (341건, 브랜드 필터 30개에 Batiste 없음) | **있음** ✅ 1쪽 30칸 중 29칸 (광고 6칸) | 없음 ✅ (무관한 2건) |
| Living Proof | **있음** ✅ 45개 (브랜드 페이지) | **있음** ✅ 57개 (검색) | 없음 ✅ ("We don't carry this brand or item") | 없음 ✅ |
| Death Wish Coffee | 없음 ✅ (무관한 2건) | 없음 ✅ (44건 모두 향수 등) | **있음** ✅ | 없음 ✅ (커피 모양 반려동물 용품만) |
| Black Rifle Coffee | 없음 ✅ (무관한 2건) | 없음 ✅ (36건, 브랜드 필터 9개에 없음) | **있음** ✅ 1쪽 24개 중 13개 | 없음 ✅ |
| Jinx | 없음 ✅ ("No results found") | 없음 ✅ (94건, 브랜드 필터 20개에 없음) | **있음** ✅ 1쪽 24개 중 11개 | **있음** ✅ 1쪽 40개 중 39개 |

- 판매처가 둘인 브랜드: **Batiste(Ulta, Target), Living Proof(Ulta, Sephora), Jinx(Target, Chewy).** Death Wish와 Black Rifle은 Target 하나뿐이다.
- Target의 Living Proof "없음"은 San Jose North 매장 기준 화면이다. 화면 문구가 "We don't carry this brand"라서 매장 문제가 아니라 취급 안 함으로 본다 ❓.

**있는 칸별 수집 경로 (2026-11-10 시험 후, 11-12절)**
| 칸 | 목록·가격·별점 | 리뷰 본문 |
|---|---|---|
| Batiste @ Ulta | ✅ 직접 짠 코드 | ✅ 직접 짠 코드(PowerReviews) |
| Living Proof @ Ulta | ✅ 직접 짠 코드 | ✅ 같은 경로(Living Proof PhD로 확인) |
| Living Proof @ Sephora | ✅ 직접 짠 코드(검색 응답, Bestselling 정렬) | ✅ Apify 공식 수집기 |
| Batiste @ Target | ✅ automation-lab(매장 2581) | Apify 공식 수집기(Death Wish로 확인 ✅, Batiste로는 안 돌려 봄 ❓) |
| Death Wish, Black Rifle, Jinx @ Target | ✅ automation-lab(매장 2581) | ✅ Apify 공식 수집기(Death Wish로 확인) |
| Jinx @ Chewy | ✅ `parseforge/chewy-com-scraper`. 가격은 화면과 일치, **순서는 화면과 다름** ⚠️ | ✅ `automation-lab/chewy-product-reviews-scraper` |

수집 범위는 사용자가 정했다: 판매처가 있는 8칸 모두(10절).

## 4. 원본 구조

### 4-1. Ulta 목록 (`samples/ulta/batiste_listing_decoded.json`, `batiste_listing_raw_excerpt_product1.txt`)
HTML 안 JSON에서 상품 카드마다 아래 필드가 있다 ✅.

| 키 | 뜻 | 예시 | 근거 |
|---|---|---|---|
| `resultCount` / `pageSize` | 전체 건수 / 한 화면 건수 | 29 / 64 | ✅ 화면의 "29 results"와 같다 |
| (화면) Sort by | 기본 정렬 | **Best Sellers** | ✅ |
| `dataLayer...item_position[0]` | 목록 위치(1부터) | 1 | ✅ 1~29 연속 |
| `skuId` | SKU | `2625670` | ✅ 상품 주소의 `?sku=`와 같다 |
| `productId` | 상품 ID. `pimprod…`(단일) 또는 `xlsImpprod…`(여러 SKU 묶음) | `pimprod2045775` | ✅ 29건 중 4건이 `xlsImpprod` |
| `brandName`, `productName` | 브랜드, 이름 | `Batiste`, `Light Dry Shampoo - Mellow Melon` | ✅ |
| `listPrice` | 정가. 사이즈가 여러 개면 범위 문자열 | `"$12.99 - $20.99"` | ✅ 숫자가 아니라 문자열 |
| `salePrice`, `discount`, `promoText` | 할인 | 모두 `null` | ✅ 이번 29건에는 할인이 없었다 |
| `variantLabel` | 변형 안내 | `"2 sizes"` | ✅ |
| `rating`, `reviewCount` | 평점, 리뷰 수 | `4.5`, `28849` | ✅ 리뷰 없으면 `null` |
| `badge` | 배지 | `"Only at Ulta"` (2건) | ✅ |
| `sponsored` | 광고 여부 | `false` (29건 모두) | ✅ |

**조심할 점:** Batiste 29건 중 **9건이 똑같이 `4.5`, `28849`**다(Original, Volumizing, Bare 등). 이 리뷰 수는 상품이 아니라 같은 리뷰 묶음(`xlsImpprod2040049`)의 합계다 ✅. 상품별 리뷰 수로 쓰면 안 된다.

### 4-2. Ulta 상품 페이지 (`samples/ulta/pdp_text_excerpt.txt`)
Batiste Original Dry Shampoo(`?sku=2515942`)에서 화면에 보인 것 ✅:
- 가격 $20.99(7.62 oz 선택 상태), 사이즈 선택지 3.81 oz / 7.62 oz.
- 정기배송: 정가 $20.99, 할인가 $19.94("Save 5%").
- 재고 안내: "In stock and ready to ship", 픽업은 매장 기준("Ready in 2 hours or less").
- 같이 사는 상품, 비슷한 상품 추천(다른 브랜드 평점과 가격 포함).
- 단위 가격(온스당)은 화면에 없었다 ✅.
- 구조화된 JSON-LD는 확인하지 않았다 ❓. 상품 상세용 별도 JSON도 따로 보지 않았다 ❓.

### 4-3. Ulta 리뷰: PowerReviews ✅ (`samples/ulta/reviews_page1_powerreviews.json`)
- 공급사: **PowerReviews** (`ui.powerreviews.com`, `display.powerreviews.com`) ✅.
- 상품 페이지가 스스로 부른 요청: `GET https://display.powerreviews.com/m/6406/l/en_US/product/xlsImpprod2040049/reviews?apikey=<페이지가 보낸 키>&_noconfig=true`. 응답 약 160KB ✅. `6406`은 Ulta 계정 번호, 뒤는 상품 ID다. 키는 샘플에서 지웠다.
- 로그인 없이 본문까지 읽힌다 ✅.
- 한 번에 5건(`page_size` 5), 기본 정렬 `Newest` ✅. 다음 쪽 주소는 응답의 `paging.next_page_url`에 들어 있다(`paging.from=5&paging.size=5&...&native_only=true`) ✅. 이 상품은 5,564쪽 중 1쪽이라 1,113쪽이다. **다음 쪽을 실제로 불러 보지는 않았다** ❓. 크기를 키울 수 있는지도 확인하지 않았다 ❓.

| 키 | 뜻 | 예시 | 근거 |
|---|---|---|---|
| `results[0].rollup.rating_count`, `review_count` | 전체 리뷰 수 | 28,849 | ✅ 화면의 "28,849 Reviews"와 같다 |
| `rollup.average_rating` | 평균 평점 | `4.49` | ✅ 화면은 4.5 |
| `rollup.rating_histogram` | 1~5점 분포 | `[500, 694, 2178, 6307, 19170]` | ✅ |
| `rollup.native_review_count` / `syndicated_review_count` | Ulta에서 쓴 리뷰 / 다른 사이트에서 온 리뷰 | 5,564 / 23,285 | ✅ |
| `rollup.recommended_ratio` | 추천 비율 | `0.94` | ✅ |
| `reviews[].details.headline`, `comments` | 제목, 본문 | | ✅ |
| `details.created_date` | 작성 시각(밀리초) | `1793021408804` = 2026-10-26 | ✅ |
| `details.bottom_line` | 추천 여부 | `"Yes"` | ✅ |
| `metrics.rating` | 별점 | 5 | ✅ |
| `metrics.helpful_votes` / `not_helpful_votes` | 도움됨 / 안 됨 | 0 / 0 | ✅ |
| `badges.is_verified_buyer` | 구매 인증 | 받은 5건 모두 `false` | ✅ 값은 오지만 5건이 모두 false라서 의미를 확신 못 한다 ❓ |
| `details.nickname`, `location` | 작성자 이름, 지역 | | 수집하지 않는다(개인정보). 샘플에서 지웠다 |

**syndication(원 게시처, "originally posted on"):** 이 요청의 응답은 `paging.total_results` 5,564 = `native_review_count`와 같다. 즉 **Ulta에서 직접 쓴 리뷰만 온다** ✅. 외부에서 온 23,285건(합계의 81%)을 어떻게 요청하고 출처가 어느 필드에 있는지는 보지 못했다 ❓. 받은 5건에는 출처 필드가 없었다 ✅.

### 4-4. Sephora 검색 목록 (`samples/sephora/search_living_proof_response_trimmed.json`, `search_living_proof_decoded.json`)
`/api/v2/catalog/search/` 응답 ✅. 최상위 키: `products`, `totalProducts`(57), `refinements`, `categories`, `relatedSearches`, `responseSource`(`NLP`) 등.

| 키 | 뜻 | 예시 | 근거 |
|---|---|---|---|
| `products[]` 순서 | 목록 위치 | 1~57 | ✅ 화면 순서와 같다 |
| `productId` / `currentSku.skuId` | 상품 ID / 대표 SKU | `P525776` / `2999027` | ✅ |
| `brandName`, `displayName` | 브랜드, 이름 | | ✅ |
| `currentSku.listPrice` | 정가. 범위는 문자열 | `"$18.00 - $46.00"` | ✅ |
| `currentSku.salePrice`, `onSaleData` | 할인 | 57건 중 앞 40건에서 1건만 할인(`$38.00`, `FULL`) | ✅ |
| `rating`, `reviews` | 평점(소수 4자리 문자열), 리뷰 수(문자열) | `"4.5718"`, `"341"` | ✅ 화면은 "341" |
| `currentSku.isBestseller` | 베스트셀러 배지 | true | ✅ |
| `isNew`, `isLimitedEdition`, `isLimitedTimeOffer`, `isOnlineOnly`, `isSephoraExclusive`, `isBI` | 배지 | | ✅ |
| `sponsored` | 광고 여부 | `false` (앞 40건) | ✅ |
| `targetUrl` | 상품 페이지 경로 | `/product/...-P525776?skuId=2999027` | ✅ (열어 보니 403) |

기본 정렬은 화면에 **"Sort by: Relevance"**로 나온다 ✅. 앞 10건 중 9건에 `isBestseller`가 붙어 있어서 상위는 인기순과 비슷해 보이나 확정할 수 없다 ❓.

### 4-5. Sephora 상품, 리뷰 ❓ 전부 미확인 (403).

## 5. 집중해서 볼 것과 원본의 대응
과제가 요구한 것: 상위 상품의 순위, 가격, 평점, 리뷰 수, 리뷰 본문.

### 5-1. Ulta
| 요구 | 원본에서 얻는 방법 | 상태 |
|---|---|---|
| 순위 | 목록 위치(`item_position`). 브랜드 페이지는 Best Sellers 정렬이다 | ✅ |
| 가격 | `listPrice`(범위 문자열이면 분해 필요), 상품 페이지에서 사이즈별 가격 | ✅ 목록, ❓ 사이즈별 분해 |
| 평점, 리뷰 수 | `rating`, `reviewCount` (같은 묶음 상품은 값이 같음) | ✅ |
| 리뷰 본문 | PowerReviews 응답, 5건씩 | ✅ 1쪽, ❓ 다음 쪽 |

### 5-2. Sephora
| 요구 | 원본에서 얻는 방법 | 상태 |
|---|---|---|
| 순위 | 검색 결과 위치. 기본 정렬이 Relevance다 | ✅ |
| 가격, 평점, 리뷰 수 | 검색 응답 필드 | ✅ |
| 리뷰 본문 | 상품 페이지가 403이라 못 봤다 | ❓ |

### 5-3. Target, Chewy
데이터를 받지 못했다. 화면과 필드는 ❓.

## 6. 순위가 정직하게 뜻하는 것
- **Ulta 브랜드 페이지:** "해당 브랜드 안의 Best Sellers 정렬 위치"다 ✅. 카테고리 전체 순위가 아니다. 판매량 지표 없이 위치만 온다.
- **Ulta 검색:** 기본 정렬이 Relevance("Sort by Relevance")라서 위치는 순위가 아니다 ✅.
- **Sephora 검색:** Relevance 정렬이라 위치는 순위가 아니다. `isBestseller` 배지는 순위가 아니라 표시다 ✅.
- 정렬 파라미터를 바꾸면 Best Sellers를 얻을 수 있는지는 확인하지 않았다 ❓.
- 브랜드가 소수 상품이면(Batiste 29개) 순위 비교의 의미가 작다. 같은 브랜드끼리 비교가 아니라 "그 매장 안에서 우리 브랜드 상품이 어디 있나"를 보려면 카테고리 목록(예: Dry Shampoo)의 위치가 필요한데 보지 않았다 ❓.

## 7. 항목 식별과 재실행
- 고유 키: (리테일러, 목록 종류와 이름, 수집일, productId + sku). 상품 자체의 키는 (리테일러, productId, sku).
- Ulta: `productId`(`pimprod…`/`xlsImpprod…`)와 `skuId`. Sephora: `P…` ID와 `skuId`.
- 같은 날 다시 돌리면 같은 키 행을 덮어쓰고, 날이 바뀌면 새 행을 쌓아야 순위 변화를 볼 수 있다(제안).
- 매장/ZIP이 값에 영향을 주는지: Ulta는 IP로 매장을 자동 지정했다(`Westwood Village, Seattle 98126`) ✅. 목록 가격은 매장 없이도 나오지만 매장별 가격이 다른지는 확인하지 않았다 ❓. Sephora는 상단에 "DOWNTOWN SEATTLE"이 자동으로 표시됐다 ✅. Target은 `95054 San Jose`가 자동으로 잡혔다 ✅. 모두 IP 위치에 끌려가므로 수집 시 같은 위치로 고정하는 편이 안전하다(제안).

## 8. 이 소스에서 얻을 수 없는 것
- 판매량, 매출, 재고 수량, 카테고리 전체 순위
- 외부에서 온(syndicated) 리뷰의 출처. 이번 요청에는 오지 않았다
- 작성자 식별 정보(수집하지 않는다)
- Death Wish, Black Rifle, Jinx의 진열대를 직접 짠 코드로 받는 것 (Ulta와 Sephora에 없고, Target과 Chewy는 직접 열면 막힌다. Apify로는 받아진다, 11절)
- Sephora의 상품 상세와 리뷰 (이 IP에서는 403)

## 9. 이걸로 볼 수 있는 것
- **Batiste vs Living Proof, Ulta 안에서:** Batiste 29건의 가격대는 $4.99~$23.99(목록 29건의 범위 문자열 기준), 정가 하나인 상품이 많다. Living Proof는 $17~$82 범위가 많다. 가격 포지셔닝 차이가 목록에서 바로 보인다.
- **같은 브랜드, 매장별 차이:** Living Proof PhD 드라이 샴푸는 Ulta에서 리뷰 3,016건, Sephora에서 4,378건이다(각 리뷰 풀이 따로다) ✅.
- **리뷰 평점 분포:** Batiste Original은 5점이 19,170건(66%), 1점이 500건(1.7%) ✅. 리뷰 본문으로 불만 주제를 뽑을 수 있다.
- **프로모션:** Ulta 정기배송 5%, "Only at Ulta" 배지 2건, Living Proof에 "Free Gift with purchase" 문구 ✅.
- **리테일러 독점 라인:** Batiste "Only at Ulta" 상품(Duo Original-Berry Disco, Solar Bloom).

## 10. 정한 것 (2026-11-10. 자세한 내용은 12절)
1. **수집 범위 (사용자 결정):** 판매처가 있는 8칸 모두. Batiste(Ulta, Target), Living Proof(Ulta, Sephora), Death Wish(Target), Black Rifle(Target), Jinx(Target, Chewy).
2. **수집기 (이 스레드가 정함, 11절 시험 근거):** Ulta 목록·리뷰와 Sephora 목록은 직접 짠 코드. Target 목록은 `automation-lab/target-scraper`(매장 2581), Target·Sephora 리뷰는 `apify/e-commerce-scraping-tool`, Chewy 목록은 `parseforge/chewy-com-scraper`, Chewy 리뷰는 `automation-lab/chewy-product-reviews-scraper`.
3. **순위 (이 스레드가 정함):** 수집 시점의 목록 순서. Ulta는 브랜드 페이지 Best Sellers, Sephora는 검색 Bestselling, Target은 검색 Relevance(광고 행 포함, 광고 여부 기록), Chewy는 수집기가 주는 순서(정렬 기준 모름 ⚠️, 사용자 결정). 화면과 한 칸씩 맞는 순위는 약속하지 않는다(11-11, 11-12절).
4. **개수:** 칸당 상품 10개, 상품당 최신 리뷰 10건. Amazon 소스(#4)와 같은 개수다.
5. **외부(syndicated) 리뷰:** 받지 않는다. Ulta는 자체 리뷰만 받고, 상품 행에 자체/외부 리뷰 수를 따로 남긴다.
6. **리뷰 묶음:** 리뷰 행의 키를 (리테일러, 상품, 리뷰 ID)로 둔다. 같은 리뷰가 묶음 안의 여러 상품에 나오는 것은 사이트 화면과 같다(11-12절). 리뷰 수를 브랜드 단위로 더할 때는 리뷰 ID로 중복을 지운다.

## 11. Apify 시험 (2026-11-10, 13회 실행)
메인 스레드 방침: Target과 Chewy는 Apify 수집기로 작은 시험을 돌려 실제 응답을 본다. 이 소스의 시험 상한은 $0.30이고, 사용자가 이 세션에서 실행당 상한 $1을 허용했다.

**요약: Target은 공식 수집기로 세 브랜드(Death Wish, Black Rifle, Jinx)의 목록과 리뷰 본문이 왔다 ✅. Chewy는 공식 수집기가 엉뚱한 상품을 줬고(쓸 수 없음), 대체 수집기로 Jinx 목록이 왔다 ✅. 차감 합계 $0.2805 ✅. 화면 대조(11-9절): 별점·리뷰 수는 17개 모두 일치, 순서는 광고를 뺀 화면 순서와 대체로 일치, 가격은 17개 중 7개가 다르다(매장 차이로 보임).**

| # | 수집기 | 입력 | 결과 | 걸린 시간 | 차감 |
|---|---|---|---|---|---|
| 1 | `apify/e-commerce-scraping-tool` | Target, `death wish coffee`, 상품 10개 | ✅ 10건 | 7초 | $0.0606 |
| 2 | 같음 | Target 상품 1개(`A-88498115`)의 리뷰 10건, 최신순 | ✅ 10건 | 4초 | $0.0201 |
| 3 | 같음 | Chewy, `jinx dog food`, 상품 10개 | ❌ 10건이 모두 Jinx가 아님 | 8초 | $0.0636 |
| 4 | `parseforge/chewy-com-scraper` | `jinx dog food`, 10개 | ✅ 10건 모두 Jinx | 4초 | $0.0750 |
| 5 | `apify/e-commerce-scraping-tool` | Target, `black rifle coffee`, 상품 5개 | ✅ 5건 모두 Black Rifle | 18초 | $0.0306 |
| 6 | 같음 | Target, `jinx dog food`, 상품 5개 | ✅ 5건 모두 Jinx | 13초 | $0.0306 |

- 차감액은 실행마다 Apify가 기록한 `usageTotalUsd`다 ✅. 계정 전체 사용액은 다른 스레드의 실행도 포함하므로 여기 쓰지 않았다.
- 실패한 실행은 없어서 재실행하지 않았다.

### 11-1. 비용 상한
- 공식 수집기에 실행당 상한 $0.12를 걸었더니 **HTTP 400 `max-total-charge-usd-below-minimum`, "less than the allowed minimum of $1.00"**으로 거절됐다 ✅. 이 수집기는 실행당 상한을 $1 밑으로 걸 수 없다.
- 그래서 1~3번은 상한 $1로 걸고 입력의 개수 제한(`maxProductResults`, `maxReviewResults`)으로 비용을 묶었다. 개수 제한은 지켜졌다 ✅. 1번은 화면 1쪽의 24개를 읽었지만 10개만 저장하고 10개만 차감했다. 2번도 50건을 읽고 10건만 차감했다.
- 대체 수집기는 상한 $0.08이 그대로 받아들여졌다 ✅.

### 11-2. Target 검색 목록 ✅ (`samples/apify/target_search_death_wish_coffee.json`)
- 차단을 넘었다 ✅. 주거용 프록시나 브라우저 추가 요금은 붙지 않았다(시작 1, 목록 1쪽 1, 상품 10).
- 한 건의 필드 ✅: `url`, `name`, `offers.price`(숫자), `offers.priceCurrency`, `brand.name`, `rating`(소수 2자리), `reviewCount`, `image`, `description`(빈 값), `keyword`, `marketplace`, `scrapedAt`.
- **순위 필드는 없다** ✅. 결과 순서는 실행 로그에 찍힌 처리 순서와 같다 ✅. 화면과 대조한 결과는 11-9절: 광고를 뺀 순서와 대체로 같고, 가격은 일부 다르다.
- **검색 결과에 다른 브랜드가 섞인다** ✅. 받은 10건 중 7건이 Death Wish(`brand.name` = `Death Wish Coffee Co`)이고 3위가 Dunkin', 6위가 Good & Gather, 7위가 Starbucks다. 순위는 "검색 결과 전체 안의 위치"로 기록하고, 브랜드는 `brand.name`으로 골라야 한다.
- 없는 것 ✅: 할인 전 가격, 배지, 광고(sponsored) 여부, 재고, 정렬 기준. 가격이 어느 매장·ZIP 기준인지 ❓.
- Black Rifle 상품(`A-94409212`)도 같은 검색 1쪽의 20번째로 로그에 찍혔다 ✅. Black Rifle과 Jinx 검색은 11-6절.

| 위치 | 브랜드 | 상품 | 가격 | 별점 | 리뷰 수 |
|---|---|---|---|---|---|
| 1 | Death Wish Coffee Co | Medium Roast Ground Coffee 10oz | $12.49 | 4.72 | 1,197 |
| 2 | Death Wish Coffee Co | Dark Roast Ground Coffee 10oz | $12.49 | 4.83 | 4,681 |
| 3 | Dunkin' | Frosted Sugar Cookie Ground Coffee 11oz | $11.99 | 4.49 | 162 |
| 4 | Death Wish Coffee Co | Dark Roast Single-Serve Pods 18ct | $18.99 | 4.85 | 3,036 |
| 5 | Death Wish Coffee Co | Vanilla Cold Brew Latte 11 fl oz | $2.69 | 4.49 | 81 |

### 11-3. Target 리뷰 ✅ (`samples/apify/target_reviews_A-88498115.json`)
- 입력은 상품 주소 하나(`reviewDetailsUrls`)다. 리뷰 본문이 온다 ✅.
- 한 건의 필드 ✅: `reviewBody`(본문), `name`(리뷰 제목, 예: "Go to coffee"), `datePublished`, `reviewRating.ratingValue`(1~5), `productUrl`, `inputUrl`, `author`.
- `author`는 리뷰어 이름이라 저장할 때 지웠다. 수집기에서도 저장하지 않는다.
- 최신순 요청대로 2026-10-25부터 10-20까지 날짜 내림차순으로 왔다 ✅.
- 10건 중 2건의 본문이 **"[This review was collected as part of a promotion.]"**으로 시작한다 ✅. 프로모션으로 받은 리뷰가 본문 글자로만 표시된다.
- 없는 것 ✅: 리뷰 ID, 구매 인증, 도움됨 수, 원 게시처. 리뷰 ID가 없으므로 재실행 중복 방지 키는 (상품, 작성 시각, 본문 해시)로 만들어야 한다(제안).

### 11-4. Chewy, 공식 수집기 ❌ 쓸 수 없음 (`samples/apify/chewy_search_jinx_official_actor_BAD.json`)
- 실행은 성공으로 끝났고 차감도 됐다($0.0636, 주거용 프록시 1건 포함) ✅.
- 그러나 **받은 10건에 Jinx가 하나도 없다** ✅. American Journey(Chewy 자체 브랜드) 통조림과 Frisco 장난감·식기다. 로그에 찍힌 100개 주소에도 Jinx 상품이 없다 ✅.
- 10건 모두 가격이 `null`이다 ✅. 주소 중 일부는 Chewy 내부 서버 이름(`sfwprdblue.use1.demm.prd.chewy.com:8080/...`)이고 1건은 `https://www.chewy.com`뿐이다 ✅.
- 검색 결과가 아니라 다른 영역(추천 등)을 읽은 것으로 보인다 ❓. 이 수집기로 Chewy를 받지 않는다.
- **Chewy에 Jinx가 없는 것이 아니다.** 일반 웹 검색 색인에 `chewy.com/jinx-...` 상품 주소가 19개 나오고, 그중 `dp/845310`은 대체 수집기의 1위 상품과 같다 ✅. 이 수집기가 틀린 것이다.

### 11-5. Chewy, 대체 수집기 ✅ (`samples/apify/chewy_search_jinx_parseforge.json`)
- 로그에 "Found 64 total products"가 찍혔고 받은 10건이 모두 `manufacturer` = `Jinx`다 ✅.
- 한 건의 필드 ✅: `name`, `url`, `partNumber`(= 주소의 `/dp/` 번호), `manufacturer`, `price`(숫자), `displayPrice`, `strikePrice`(할인 전 가격), `strikeSavingsPct`, `autoshipPrice`, `autoshipDiscountPct`, `pricePerUnit`(예: `$2.02/lb`), `rating`(소수 4자리), `ratingCount`, `inStock`, `isDeal`, `isNew`, `isChewyExclusive`, `isDiscontinued`, `hasMoreChoices`, `categoryId`, `scrapedAt`.
- 가격 정보는 Target보다 풍부하다(할인 전 가격, 정기배송가, 단위 가격) ✅.
- **순위 필드는 없다** ✅. 순서는 수집기가 받은 순서(offset 0부터)이고, 어떤 정렬인지와 화면 순서와 같은지는 모른다 ❓.
- **리뷰 본문은 오지 않는다** ✅. 입력도 `searchTerm`, `maxItems` 둘뿐이다. Chewy 리뷰 경로는 아직 없다 ❓.
- 로그에 "Free user detected" 경고가 찍혔다 ✅. 무료 계정에 어떤 제한이 붙는지는 모른다 ❓. 최근 30일 사용자가 6명뿐인 수집기라서, 제출 전에 사람이 화면과 몇 건 대조해야 한다.

| 위치 | 상품 | 가격 | 할인 전 | 별점 | 리뷰 수 |
|---|---|---|---|---|---|
| 1 | Beef, Brown Rice & Sweet Potato ALS Kibble, 23.5-lb | $47.34 | $52.99 | 4.58 | 1,260 |
| 2 | Salmon, Brown Rice & Sweet Potato ALS Kibble | $59.99 | $61.99 | 4.58 | 1,560 |
| 3 | Grass-Fed Lamb, Sweet Potato & Carrot, 23.5-lb | $44.99 | $49.99 | 4.55 | 455 |
| 4 | Salmon, Sweet Potato & Carrot ALS Kibble | $47.34 | $52.99 | 4.63 | 1,859 |
| 5 | Homemades Variety Pack Pate, 18 pouches | $19.99 | 없음 | 4.71 | 144 |

### 11-6. Target, Black Rifle과 Jinx 검색 ✅ (`samples/apify/target_search_black_rifle_coffee.json`, `target_search_jinx_dog_food.json`)
- 둘 다 차단을 넘었다 ✅. 추가 요금 없이 시작 1, 목록 1쪽 1, 상품 5로 각 $0.0306이었다.
- 필드는 Death Wish 검색과 같다 ✅(11-2절).
- 로그에 1쪽 24개의 처리 순서가 모두 찍힌다 ✅. 샘플에 `page1_order_from_log`로 저장했다. 저장과 차감은 앞 5개만 됐다.
- **Black Rifle:** 1쪽 24개 중 13개가 Black Rifle이다(1~9위, 12~14위, 21위) ✅. 10, 11위는 Peet's이고, 나머지는 Nescafé, Café Bustelo, Death Wish(19위) 등이다.
- **Jinx:** 1쪽 24개 중 11개가 Jinx다(1~10위, 12위) ✅. 11위와 13위부터는 Purina, Iams, Blue Buffalo, Pedigree 등이다.
- Jinx Homemades 9oz 두 상품(4, 5위)이 같은 별점 4.4, 리뷰 수 23을 공유한다 ✅. Ulta의 Batiste처럼 리뷰가 묶여 있을 수 있다 ❓. 리뷰 수 합산 때 중복을 조심해야 한다.

| 위치 | 브랜드 | 상품 | 가격 | 별점 | 리뷰 수 |
|---|---|---|---|---|---|
| 1 | Black Rifle | Just Black Medium Roast Ground 12oz | $13.79 | 4.62 | 131 |
| 2 | Black Rifle | Tactisquatch Dark Roast Ground 12oz | $13.79 | 4.50 | 80 |
| 3 | Black Rifle | Just Black Medium Roast Pods 22ct | $17.89 | 4.73 | 332 |
| 4 | Black Rifle | Tactisquatch Dark Roast Pods 22ct | $17.89 | 4.71 | 311 |
| 5 | Black Rifle | Espresso with Cream RTD 11 fl oz | $3.39 | 3.44 | 64 |
| 1 | Jinx | Grain-Free Dry, Salmon, Sweet Potato & Carrot 11.5lbs | $27.49 | 4.66 | 1,230 |
| 2 | Jinx | Grain-Free Dry, Chicken, Sweet Potato & Carrot 11.5lbs | $27.49 | 4.67 | 725 |
| 3 | Jinx | Beef Flavor Dry 11.5lbs | $27.49 | 4.80 | 352 |
| 4 | Jinx | Homemades Wet, Chicken 9oz | $3.89 | 4.40 | 23 |
| 5 | Jinx | Homemades Wet, Chicken and Beef 9oz | $3.89 | 4.40 | 23 |

### 11-7. 레코드 1,000개당 비용 (무료 요금제, 실측 단가 기준)
| 경로 | 1,000개당 | 근거 |
|---|---|---|
| Target 상품 목록 | 약 $6.0 (+ 목록 1쪽마다 $0.0005) | 10개에 $0.0606 |
| Target 리뷰 | 약 $2.0 (+ 실행마다 $0.0001) | 10건에 $0.0201 |
| Chewy 상품 목록(대체 수집기) | 약 $5.5 (+ 실행마다 $0.02) | 10개에 $0.075 |
- 공식 수집기는 차단이 심해지면 상품당 주거용 프록시 $0.003, 언블로커 $0.0015가 더 붙는다. 이번 Target 실행에는 붙지 않았다 ✅.

### 11-8. 아직 모르는 것
- Chewy 결과 순서가 화면 순서와 같은지 ❓ (Target은 11-9절에서 대조함)
- Apify가 Target 가격을 어느 매장 기준으로 받는지 ❓. 입력에 매장·ZIP 항목이 없다 ✅.
- Black Rifle과 Jinx 상품의 Target 리뷰 본문 ❓ (같은 수집기, 같은 사이트라 Death Wish처럼 될 것으로 보지만 돌려 보지 않았다)
- Target 검색 2쪽 이후 ❓ (1쪽은 24개)
- Chewy 리뷰 본문 경로 ❓
- 같은 입력으로 다시 돌렸을 때 같은 결과가 오는지 ❓

### 11-9. Target 화면 대조 (2026-11-10 07:57~08:01 UTC) (`samples/target_screen/`)
**방법:** 사용자가 쓰는 Chrome에서 세 검색 화면을 한 번씩 열고, 화면에 그려진 상품 칸을 위에서부터 읽었다. 클릭, 매장 변경, 로그인은 하지 않았다. 차단 화면은 없었다 ✅. Apify 결과는 같은 날 07:10~07:52 UTC에 받은 것이다.

**화면의 매장:** San Jose North(`store_id` 2581), ZIP 95054 ✅. Target이 IP 위치로 자동으로 고른 매장이다. 화면이 보낸 검색 요청에 `store_id`, `zip`, 위도·경도, `include_sponsored=true`가 들어 있다 ✅. 즉 **가격과 진열 상품이 매장에 따라 달라지는 구조**다. Apify가 어느 매장 기준인지는 모른다 ❓.

**결론**
| 항목 | 결과 |
|---|---|
| 별점, 리뷰 수 | ✅ 겹치는 17개 상품이 **전부 일치**한다 |
| 순서 | ⚠️ Apify 순서는 **광고를 뺀 화면 순서와 대체로 같다**. 화면에는 광고 칸(Sponsored)과 묶음 칸(carousel)이 끼어 있어서, 화면의 칸 번호와는 맞지 않는다 |
| 가격 | ❌ 겹치는 17개 중 **8개 일치, 7개 불일치, 2개 판단 불가** |
| 광고 표시, 할인가, 프로모션 문구 | ❌ Apify 결과에 없다. 화면에는 있다 |

**순서 세부**
- Black Rifle: Apify 1~4위 = 화면의 광고 제외 1~4위 ✅. Apify 5위(Espresso with Cream)는 화면에서 광고 제외 6위다. 화면 5위(Good & Gather Black Unsweetened Cold Brew)가 Apify 1쪽 24개에 아예 없다.
- Jinx: Apify 1~5위 = 화면의 광고 제외 1~5위 ✅. 화면 첫 11칸 중 6칸이 광고다.
- Death Wish: Death Wish 상품끼리의 순서는 같다. 단 1, 2위(Dark Roast, Medium Roast)가 서로 바뀌어 있다. 다른 브랜드 칸은 계절 상품이 다르다(Apify: Dunkin' Frosted Sugar Cookie, Good & Gather Peppermint, Starbucks Peppermint Mocha / 화면: Good & Gather Cookie Butter, Tim Hortons Gingerbread). Caramel Cold Brew는 화면에 있고 Apify 1쪽 24개에 없다. 화면 첫 26칸 중 6칸이 광고다. 진열 상품 차이는 매장 차이로 보인다 ❓.

**가격 세부**
| 상품 | Apify | 화면 | 판정 |
|---|---|---|---|
| DW Dark Roast / Medium Roast Ground 10oz | $12.49 / $12.49 | $15.89 / $15.89 | ❌ |
| DW Dark Roast Pods 18ct | $18.99 | $17.99 | ❌ |
| DW Power Surge 10oz | $12.49 | $15.89 (was $17.49) | ❌ |
| DW Cold Brew Latte 3종 | $2.69 | $2.69 | ✅ |
| BRCC Ground 12oz 2종, Pods 22ct 2종 | $13.79, $17.89 | $13.79, $17.89 | ✅ |
| BRCC Espresso with Cream RTD | $3.39 | $3.49 | ❌ |
| Jinx Beef Dry 11.5lbs | $27.49 | $27.49 | ✅ |
| Jinx Salmon / Chicken Dry 11.5lbs | $27.49 | 사이즈 묶음 범위 `$10.89 - $27.49`, `$11.49 - $27.49` | ❓ 상단 값과 같지만 사이즈별 값은 못 봄 |
| Jinx Homemades 9oz 2종 | $3.89 | **$3.11 할인**(reg $3.89) | ❌ Apify는 정가만 줬다 |

**상품 ID 차이:** 화면 카드는 사이즈·맛 묶음의 부모 ID(예: Jinx Salmon `90127001`)를 쓰고, Apify는 사이즈별 자식 ID(`88766771`, 11.5lbs)를 준다 ✅. 같은 상품인지 맞출 때 ID가 아니라 이름, 별점, 리뷰 수로 맞췄다.

**리뷰 묶음 설명:** Jinx Homemades 두 상품(Chicken, Chicken & Beef)이 같은 별점 4.4, 리뷰 수 23인 이유는 화면에서 한 부모 상품(`1015557660`)의 맛 변형이기 때문이다 ✅.

**정해야 할 것 (이 대조에서 나온 것)**
1. 순위 정의: "광고를 뺀 검색 순서"로 하면 Apify 순서를 쓸 수 있다. 광고 칸까지 포함한 화면 순서가 필요하면 Apify로는 안 된다.
2. 가격: Apify는 매장을 지정할 수 없어서 가격이 어느 매장 기준인지 기록할 수 없다. 대안은 (가) 매장·ZIP을 입력으로 받는 Target 전용 수집기를 찾는다, (나) 가격 칸에 "기준 매장 모름"을 명시한다, (다) 사용자 Chrome 화면 읽기를 쓴다(매장이 고정되고 광고·할인가까지 나오지만, 다른 사람이 명령 하나로 다시 돌릴 수 없다).

### 11-10. Target 전용 수집기 2종 비교 (실행 전, 무료 조회만) (`samples/apify/target_actor_comparison_precheck.json`)
11-9절의 가격 문제(매장을 지정할 수 없음)를 풀 후보다. 수집기 정보와 README만 읽었고 돌려 보지 않았다. 아래 출력 필드는 README와 데이터셋 정의에 적힌 것이다 ❓(실측 아님).

| | `automation-lab/target-scraper` | `shahidirfan/target-product-scraper` |
|---|---|---|
| 최근 30일 사용자 / 실행 | 47명 / 3,643회(실패 5) | 39명 / 4,008회(실패 8) |
| 마지막 빌드 | 2026-11-07 | 2026-10-23 |
| 단가(무료 요금제) | 시작 $0.001 + 상품 $0.00105 | 시작 $0.00005 + 결과 $0.001 |
| 1,000개당 | 약 $1.05 | 약 $1.00 |
| 실행당 상한 최소값 | 없음 | 없음 |
| **매장·ZIP 지정** | **있음**: `storeId`(기본 3991 = Target 온라인 매장), `zipCode` | **없음** |
| 정렬 | relevance, price, bestselling, newest, rating | relevance, newest, price, best_seller, rating |
| 순위 | `position` (광고 행 포함한 위치) | `position`, `page`, `total_results` |
| 광고 표시 | 행마다 `isSponsored` | 광고 포함 여부 스위치(`include_sponsored`)만. 행마다 표시하는 필드는 README에 없다 |
| 할인 | `price`, `regularPrice`, `onSale`, `savePercent`, `priceType` | `current_retail`, `reg_retail`, `formatted_comparison_price`, `promotions` |
| 별점, 리뷰 수 | 있음 | 있음 |
| 리뷰 본문 | 없음 | 없음 |
| 매장 재고 | 픽업·매장 재고·수량(매장 지정 시) | 없음 |
| 프록시 | README에 명시 없음("브라우저 없이 Target JSON을 읽는다") | 주거용 프록시가 기본값 |

- 판단(제안): **automation-lab 쪽이 맞다.** 매장을 지정할 수 있는 것이 이쪽뿐이고, 행마다 광고 여부와 광고 포함 위치를 줘서 "광고 포함 순위"와 "광고 제외 순위"를 둘 다 만들 수 있다. 상품 단가도 공식 수집기($0.006)의 약 1/6이다.
- 리뷰 본문은 두 수집기 모두 없다. 리뷰는 공식 수집기(11-3절, 1,000건당 약 $2)로 따로 받아야 한다.
- 매장 2581로 돌린 시험 결과는 11-11절.

### 11-11. automation-lab 시험: 매장 2581, Death Wish 10개 (`samples/apify/target_al_store2581_death_wish_coffee.json`, `samples/target_screen/screen_death_wish_coffee_0810utc.json`)
- 입력: `searchQueries` ["death wish coffee"], `maxProductsPerSearch` 10, `maxSearchPages` 1, `storeId` "2581", `zipCode` "95054", `sort` relevance. 실행당 상한 $0.015가 그대로 받아들여졌다 ✅.
- 결과: 10건, 3초, **$0.0115**(시작 1, 상품 10) ✅. 08:09 UTC에 돌렸고, 1분 뒤 사용자 Chrome에서 같은 화면을 다시 읽어 대조했다.
- 행마다 매장이 찍힌다 ✅: `storeId` 2581, `fulfillmentStoreName` "San Jose North", `zipCode` 95054, `storeQuantity`(매장 재고 수량), 픽업·매장 재고 상태.

| 위치 | Apify (08:09) | 광고 | 가격 | 화면 (08:10) |
|---|---|---|---|---|
| 1 | DW Vanilla Cold Brew | S | $2.69 | 1칸, S, $2.69 |
| 2 | DW Classic Cold Brew | S | $2.69 | 2칸, S, $2.69 |
| 3 | DW Mocha Cold Brew | S | $2.69 | 9칸, S, $2.69 (화면 3칸은 Caramel 광고) |
| 4 | DW Dark Roast Ground 10oz | O | $15.89 | 4칸, O, $15.89 |
| 5 | DW Medium Roast Ground 10oz | O | $15.89 | 7칸, O, $15.89 |
| 6 | Starbucks Peppermint Mocha 11oz | O | $12.79 | 18칸, O, $12.79 |
| 7 | Starbucks Pike Place (자식 ID, 부모 `89169599`) | S | $12.79 | 10칸, S, `$12.79 - $24.29`(부모) |
| 8 | Everyday Dose | S | $16.99 | 12칸, S, $16.99 |
| 9 | VAHDAM Ashwagandha Instant Coffee | S | $17.59 | 첫 18칸에 없음 |
| 10 | DW Dark Roast Pods 18ct | O | $17.99 | 8칸, O, $17.99 |

**판정**
| 항목 | 결과 |
|---|---|
| 가격 | ✅ 겹치는 9개 모두 화면과 같다. 공식 수집기에서 틀렸던 $12.49/$18.99가 화면 값 $15.89/$17.99로 맞았다 |
| 광고 표시 | ✅ 겹치는 9개 모두 화면과 같다 |
| 별점, 리뷰 수 | ✅ 공식 수집기 값과 같다(11-9절에서 화면과 일치 확인) |
| 순서 | ⚠️ 광고 제외 1, 2위(Dark Roast, Medium Roast)는 같다. 3위부터 다르다: Apify는 Starbucks Peppermint Mocha, 화면은 Dark Roast Pods |
| 광고 칸 구성 | ⚠️ 1분 차이인데 광고 상품이 다르다(Apify에 Mocha, VAHDAM / 화면에 Caramel). 광고는 페이지를 열 때마다 바뀌는 것으로 보인다 ❓ |

- 위치 번호는 상품 행만 센다. 화면의 빈 칸과 묶음 칸(carousel)은 세지 않는다 ✅. 화면에서 같은 상품이 광고와 일반으로 두 번 나오면 Apify는 한 번만 준다(로그의 "10 new products") ❓.
- **결론:** 가격 문제는 이 수집기로 풀린다. 순서는 상위 두 개까지만 화면과 같고, 광고 칸은 볼 때마다 바뀐다. 그래서 순위는 "수집 시점의 Target 검색 순서(매장 2581)"로 정의하고, 광고 여부를 같이 기록해야 한다(제안). 화면과 한 칸씩 맞는 순위를 약속할 수는 없다.
- 비용: 1,000개당 약 $1.05. 이 스레드 누적 차감은 $0.2920이다.

### 11-12. 8칸 확장 시험 (2026-11-10 08:25~08:45 UTC)
사용자가 "예산 신경 쓰지 말고 다 돌려 보라"고 해서 남은 확인을 모두 돌렸다. 이번 차감 $0.2712, 이 스레드 누적 $0.5632.

| # | 확인 | 방법 | 결과 | 차감 |
|---|---|---|---|---|
| 1 | Target 4개 브랜드 목록 | `automation-lab/target-scraper` 1회, 검색어 4개, 각 24개, 매장 2581 | ✅ 87행 | $0.0924 |
| 2 | Sephora 리뷰 | 공식 수집기, Living Proof PhD(`P399330`) 10건 | ✅ 10건 최신순(11-09 → 08-26) | $0.0231 |
| 3 | Chewy 리뷰 | 공식 수집기, Jinx `dp/845310` 10건 | ❌ 9분간 결과 없음, 우리가 중단 | $0.0001 |
| 4 | Chewy 리뷰 | `automation-lab/chewy-product-reviews-scraper`, 같은 상품 10건 | ✅ 10건 최신순 | $0.0057 |
| 5 | Chewy 목록(정렬 지정) | `blueskyscraper/chewy-scraper`, Bestselling | ❌ 목록이 HTTP 429로 막힘 | $0 |
| 6 | Chewy 목록(정렬 지정) | `arcana/chewy-com-scraper`, Bestselling 검색 주소 | ⚠️ 받아졌으나 정렬 무시 | $0.1500 |
| 7 | Ulta 리뷰 2쪽, 상품 ID | 사용자 Chrome, 상품 페이지의 PowerReviews 요청 | ✅ | $0 |
| 8 | Sephora 정렬 | 사용자 Chrome, Sort by → Bestselling | ✅ | $0 |
| 9 | Chewy 화면 순서 | 사용자 Chrome, Relevance와 Bestselling 화면 | 수집기 순서와 다름 | $0 |

**Target (1번, `samples/apify/target_al_store2581_4brands.json`)**
- Batiste: 1쪽 24행이 모두 Batiste(광고 5행) ✅. `brand` 값은 `Batiste` ✅.
- Death Wish: **1쪽 24행 중 브랜드 상품이 9개뿐이다** ✅. 10개를 채우려면 2쪽까지 받아야 한다.
- Black Rifle: 22행 중 11개 ✅. 그런데 화면 2위인 Tactisquatch 12oz가 없다. 같은 실행의 Death Wish 검색에서 이미 나온 상품이라 빠졌다. **이 수집기는 한 실행 안에서 같은 상품을 한 번만 준다(검색어가 달라도)** ✅. 그래서 검색어마다 실행을 따로 해야 한다.
- Jinx: `brand`가 `Jinx`인 행 15개 중 3개는 다른 회사 상품이다(Warcraft 지갑, Witcher 목걸이, Cyberpunk 인형. `isMarketplace` true, 판매자 Toynk·POP Market, `itemType` Wallets 등) ✅. `isMarketplace`가 false이고 `itemType`이 Pet Food 또는 Pet Treats인 행만 고른다.
- 변형 규칙(부모 ID와 리뷰 수가 같으면 건너뜀)으로 Jinx에서 2개가 빠졌다(Chicken 11.5lb와 4lb, Homemades 두 맛) ✅. `parentTcin`은 Jinx 5행, Batiste 2행에만 채워졌다.
- Jinx Homemades는 `price` $3.11, `regularPrice` $3.89, `onSale` true로 왔다. 화면 할인가와 같다 ✅(11-9절에서 공식 수집기는 정가만 줬다).
- 리뷰가 없는 상품은 `rating` 0, `reviewCount` 0으로 온다(null이 아님) ✅. 0/0은 "리뷰 없음"으로 저장한다.

**Sephora (2번 `samples/apify/sephora_reviews_P399330.json`, 8번 `samples/sephora/search_living_proof_bestselling_top10.json`)**
- 리뷰 필드는 Target과 같다: `reviewBody`, `name`(제목), `datePublished`, `reviewRating.ratingValue`, `author`(지웠다). 리뷰 ID, 구매 인증, 도움됨 수는 없다 ✅. 주거용 프록시 요금 $0.003이 붙었다.
- 정렬 선택지: Relevance(기본), Bestselling, Top Rated, Price Low to High, Price High to Low, New ✅. Bestselling을 고르면 주소에 `sortBy=BEST_SELLING`이 붙고 검색 API에도 같은 값이 간다 ✅. Living Proof 57개가 모두 Living Proof이고 광고 0개다 ✅.

**Chewy (3~6번, 9번)**
- 리뷰 전용 수집기 필드 ✅: `reviewId`, `rating`, `title`, `reviewText`, `reviewDate`, `helpfulVotes`, `isIncentivized`, `contributorBadge`(예: TOP_50), 상품 단위 `averageRating`, `ratingCount`, `reviewCount`, 별점별 개수와 비율, `reviewerName`(지웠다). 상품 여러 개를 한 실행에 넣고 상품당 개수(`maxReviewsPerProduct`)를 정할 수 있다. 시작 $0.005 + 리뷰 1건 $0.000068.
- `dp/845310`(23.5lb)의 리뷰는 부모 상품 `765574` 아래에서 온다 ✅. 사이즈끼리 리뷰를 공유한다. `ratingCount` 1,261(별점만 포함), `reviewCount` 472(글 리뷰).
- **목록 순서:** parseforge(07:12)와 arcana(08:44)가 같은 순서를 준다(845310, 1938086, 1736694, 845262, 3885574, 1709350 …) ✅. 그러나 사용자 Chrome 화면은 Relevance(08:33)도 Bestselling(08:37)도 이 순서와 다르다 ✅. 예: 수집기 1위 `845310`이 화면 Relevance에서는 8칸(광고 제외 4위), Bestselling에서는 12위 안에 없다. 화면 순서는 사용자 브라우저 상태(쿠키 등)를 탈 수 있다 ❓.
- arcana는 주소의 `sort=byPopularity`를 무시했다 ✅. `maxItems` 12가 검색 결과 행에는 적용되지 않아 30행이 차감됐다(상한 $0.15에서 멈춤) ✅.
- 가격은 parseforge와 화면이 겹치는 7개 모두 같다 ✅(845310 $47.34, 1736694 $44.99, 845262 $47.34, 3885574 $19.99, 1709350 $24.32, 1889766 $59.99, 1938086 $59.99).
- Chewy 화면에도 광고 칸이 있다(Relevance 첫 12칸 중 4칸, Jinx 1칸과 Weruva 3칸) ✅. parseforge 결과에는 광고 표시가 없다 ✅.

**Ulta (7번, `samples/ulta/powerreviews_paging_check.json`)**
- Living Proof PhD 상품 페이지는 PowerReviews를 목록의 `productId`(`pimprod2037265`)로 부른다 ✅. 리뷰 수 3,016 = 목록 값 ✅.
- 2쪽 요청이 된다 ✅. 다음 쪽 주소(`next_page_url`)에는 키가 없어서 첫 요청의 키를 붙여야 한다 ✅.
- `paging.size=10`이면 10건이 한 번에 온다 ✅(1쪽+2쪽과 같은 리뷰). 상품당 요청 1회로 충분하다.
- Batiste Mellow Melon(`pimprod2045775`)은 자기 ID로 부르지만 Original과 같은 리뷰가 온다(첫 리뷰 ID `589138362` 일치, 합계 28,849) ✅. 리뷰 행의 `product_page_id`도 요청한 상품 ID로 찍힌다.

## 12. 확정: 수집 범위, 상위 상품, attribute (2026-11-10)
수집 범위(8칸)는 사용자가 정했다. 수집기, 순위, 개수, attribute는 사용자가 이 스레드에 맡겼고 11절 시험 결과로 정했다. 이름은 `docs/attribute-candidates.md` 3-1, 3-2절과 Amazon 소스(#4) 12절에 맞췄다. ❓ 표시는 구현하면서 확인한다.

### 12-1. 칸별 수집 경로
| 칸 | 목록 | 목록 입력 | 리뷰 |
|---|---|---|---|
| Batiste @ Ulta | 직접: 브랜드 페이지 HTML 안 JSON | `https://www.ulta.com/brand/batiste` (Best Sellers 기본) | 직접: PowerReviews, `paging.size=10`, `sort=Newest` |
| Living Proof @ Ulta | 같음 | `https://www.ulta.com/brand/living-proof` | 같음 |
| Living Proof @ Sephora | 직접: 검색 페이지가 부르는 `/api/v2/catalog/search/` 응답 | `https://www.sephora.com/search?keyword=living%20proof&sortBy=BEST_SELLING` | `apify/e-commerce-scraping-tool`, 상품당 1회, `maxReviewResults` 10, `sortReview` "Most recent" |
| Batiste @ Target | `automation-lab/target-scraper` | `batiste` | `apify/e-commerce-scraping-tool`, 상품당 1회 |
| Death Wish @ Target | 같음, **`maxSearchPages` 2** | `death wish coffee` | 같음 |
| Black Rifle @ Target | 같음 | `black rifle coffee` | 같음 |
| Jinx @ Target | 같음 | `jinx dog food` | 같음 |
| Jinx @ Chewy | `parseforge/chewy-com-scraper` | `searchTerm` "jinx dog food", `maxItems` 20 | `automation-lab/chewy-product-reviews-scraper`, 10개 상품을 1회에, `maxReviewsPerProduct` 10, `sort` newest |
- 유료 서비스 없이 받는 것: Ulta 2칸(목록, 리뷰), Sephora 목록.
- Target 목록: 검색어마다 **실행을 따로** 한다(11-12절, 한 실행 안 중복 제거 때문). 공통 입력은 `storeId` "2581", `zipCode` "95054", `sort` relevance, `maxProductsPerSearch` 24×쪽수.
- Sephora 목록을 직접 짠 코드로 받을 때의 화면 열기는 오전에 자동화 Chrome에서 200이었다 ✅. `sortBy=BEST_SELLING` 주소를 자동화 Chrome으로 연 적은 없다 ❓.

### 12-2. 상품 고르기 (칸당)
1. 목록을 1회 받는다.
2. 위에서부터 그 브랜드 상품만 순서대로 고른다. 광고 행도 고르고 `is_sponsored`로 표시한다.
   - Target 브랜드 판정: `brand`가 `Batiste`, `Death Wish Coffee Co`, `Black Rifle Coffee Company`, `Jinx`이고, `isMarketplace`가 false인 행. Jinx는 `itemType`이 Pet Food 또는 Pet Treats인 행만 ✅.
   - Chewy 브랜드 판정: `manufacturer`가 `Jinx` ✅.
   - Ulta 브랜드 페이지와 Sephora Living Proof 검색은 모든 행이 그 브랜드였다 ✅.
3. 같은 상품의 변형(맛, 용량)은 건너뛴다.
   - Target: 부모 ID와 리뷰 수가 둘 다 이미 고른 상품과 같으면 건너뛴다 ✅. Amazon 소스와 같은 규칙이다.
   - Chewy: 리뷰 수(`ratingCount`)와 이름의 사이즈 앞부분이 같으면 건너뛴다 ❓(parseforge에 부모 ID가 없다).
   - Ulta, Sephora: 목록 행이 이미 상품 단위다 ✅(사이즈는 가격 범위로 묶여 있다).
4. 10개가 모이면 멈춘다. 10개가 안 되면 모인 만큼 저장하고 부분 수집으로 표시한다.

### 12-3. 리뷰 받기
- 상품당 최신 10건.
- 상품마다 받은 리뷰 수를 기록한다. 0건이면 "could not look", 10건 미만이면 상품의 리뷰 수와 비교해 부분 수집인지 표시한다.
- 같은 리뷰가 묶음 안의 여러 상품에 나올 수 있다(Ulta Batiste, Chewy 사이즈 묶음) ✅. 리뷰 행 키는 (retailer, product_id, review_id)다.

### 12-4. 상품 행 attribute (확정)
| attribute | Ulta | Sephora | Target | Chewy | 비고 |
|---|---|---|---|---|---|
| retailer | `ulta` | `sephora` | `target` | `chewy` | 고정값 |
| brand | 우리 키 | 우리 키 | 우리 키 | 우리 키 | 5개 중 하나 |
| product_id | `productId` | `productId`(P…) | `tcin` | `partNumber`(= `/dp/` 번호) | 키(리테일러와 함께) |
| sku / parent_id | `skuId` | `currentSku.skuId` | `parentTcin`(일부만) | ✕ | |
| ★ rank | 12-2절 순서 | 같음 | 같음 | 같음 | 칸 안에서 1~10 |
| search_position | `item_position` | 응답 순서 | `position` | 응답 순서 | 원래 위치. Target은 광고 행 포함 |
| sort_basis | Best Sellers | Bestselling | Relevance | 수집기 순서(Chewy 검색 API, 기준 모름) | 순위가 무엇을 뜻하는지 |
| is_sponsored | `sponsored` | `sponsored` | `isSponsored` | ✕ 없음 | Chewy 화면에는 광고가 있다 |
| title | `productName` | `displayName` | `title` | `name` | |
| variant | `variantLabel` | ✕ | 제목 안 용량 | 이름 안 용량 | |
| ★ price | `salePrice` 또는 `listPrice` 낮은 값 | `currentSku.salePrice` 또는 `listPrice` 낮은 값 | `price` | `price` | USD 숫자 |
| price_max | 범위 높은 값 | 범위 높은 값 | `priceMax` | ✕ | 범위일 때만 |
| price_text | `listPrice` 원문 | `currentSku.listPrice` 원문 | `priceString` | `displayPrice` | 화면 표시 그대로 |
| list_price | `listPrice` | `currentSku.listPrice` | `regularPrice` | `strikePrice` | 정가 |
| on_sale, discount_pct | `salePrice`, `discount` | `onSaleData` | `onSale`, `savePercent` | `isDeal`, `strikeSavingsPct` | |
| unit_price | ✕ | ✕ | ✕ | `pricePerUnit` | |
| autoship_price | ✕ | ✕ | ✕ | `autoshipPrice`, `autoshipDiscountPct` | 정기배송가 |
| promo_badges | `badge`, `promoText` | `isBestseller`, `isNew`, `isLimitedEdition`, `isSephoraExclusive`, `isOnlineOnly` | ✕ | `isChewyExclusive`, `isNew` | |
| ★ rating_avg | `rating` | `rating`(문자열) | `rating` | `rating` | 0/0은 리뷰 없음 |
| ★ review_count | `reviewCount` | `reviews`(문자열) | `reviewCount` | `ratingCount` | 묶음 합계일 수 있다 |
| native_review_count, syndicated_review_count | PowerReviews `rollup` | ✕ | ✕ | ✕ | Ulta만 |
| rating_histogram | PowerReviews `rollup` | ✕ | ✕ | 리뷰 수집기 `rating1~5Count` | |
| availability | ❓ | ❓ | `availability`, `storeQuantity` 등 | `inStock` | |
| url | 상품 주소 | `targetUrl` | `url` | `url` | 대조용 |
| context | 목록 주소, 정렬 | 검색 주소, 정렬 | 검색어, 매장 2581, ZIP 95054, 정렬 | 검색어 | |
| collected_via | `direct:ulta` | `direct:sephora` | `apify:automation-lab/target-scraper` | `apify:parseforge/chewy-com-scraper` | 출처 |
| collected_at, run_id | 수집기 | 수집기 | 수집기 | 수집기 | 모든 행 공통 |

### 12-5. 리뷰 행 attribute (확정)
| attribute | Ulta | Sephora / Target (공식 수집기) | Chewy | 비고 |
|---|---|---|---|---|
| review_id | `ugc_id` | ✕ → (상품, 작성 시각, 본문)의 해시 | `reviewId` | |
| retailer, product_id | 상품 행과 같음 | 같음 | 같음 | 키: (retailer, product_id, review_id) |
| rank | 받은 순서 1~10 | 같음 | 같음 | 최신순 ✅ |
| ★ rating | `metrics.rating` | `reviewRating.ratingValue` | `rating` | 1~5 |
| ★ title | `details.headline` | `name` | `title` | 공식 수집기의 `name`은 리뷰 제목이다 ✅ |
| ★ body | `details.comments` | `reviewBody` | `reviewText` | 원문 그대로 |
| review_date | `details.created_date`(밀리초) | `datePublished` | `reviewDate` | UTC |
| verified_purchase | `badges.is_verified_buyer` | ✕ | ✕ | |
| helpful_votes | `metrics.helpful_votes` | ✕ | `helpfulVotes` | 시점별 값 |
| recommended | `details.bottom_line` | ✕ | ✕ | |
| incentivized | ❓ | Target: 본문이 "[This review was collected as part of a promotion.]"로 시작하면 true ✅ / Sephora ❓ | `isIncentivized` | |
| reviewer_badge | ✕ | ✕ | `contributorBadge` | 예: TOP_50. 사람 식별 정보는 아니다 |
| source_page_url | PowerReviews 요청 주소(키 제외) | 입력한 상품 주소 | `sourceUrl` | |
| collected_via | `direct:ulta-powerreviews` | `apify:apify/e-commerce-scraping-tool` | `apify:automation-lab/chewy-product-reviews-scraper` | |
| collected_at, run_id | 수집기 | 수집기 | 수집기 | |
- 저장하지 않는 것: 리뷰어 이름(Ulta `nickname`, 공식 수집기 `author`, Chewy `reviewerName`), 지역, 리뷰 사진과 영상.

### 12-6. 수집 1회 예상 비용 (무료 요금제 단가로 계산)
| 칸 | 목록 | 리뷰 | 합계 |
|---|---|---|---|
| Ulta 2칸 | $0 (2회) | $0 (상품 20개 × 1회) | $0 |
| Sephora | $0 (1회) | 10회 × $0.0231 | $0.231 |
| Target 4칸 | 4회, 약 120행 × $0.00105 + 시작 $0.004 | 40회 × $0.0201 | 약 $0.934 |
| Chewy | $0.02 + 20행 × $0.0055 | $0.005 + 100건 × $0.000068 | 약 $0.142 |
| 합계 | | | **약 $1.31** (상품 80행, 리뷰 최대 800행) |
- 1,000행당으로 바꾸면 약 $1.5다(880행 기준). 거의 전부 Target·Sephora 리뷰 비용이다.

### 12-7. 남은 것 (❓)
- Chewy 순위: 사용자가 "수집기 순서로 기록"으로 정했다(2026-11-10). `sort_basis`에 "수집기 순서(Chewy 검색 API, 기준 모름)"를 남기고, 노트에 화면 순서와 다르다는 사실(11-12절)을 적는다. 정확도 대조에서 순위는 틀린 것으로 보일 수 있다.
- Target 리뷰를 Batiste·Black Rifle·Jinx 상품으로는 안 돌려 봤다.
- Sephora 목록을 자동화 Chrome에서 `sortBy=BEST_SELLING`으로 연 적은 없다.
- Chewy 변형 판정 규칙(12-2절 3번)은 실제 데이터로 확인하지 않았다.
- Ulta와 Sephora 목록을 화면 없는 실행으로 받을 수 있는지 확인하지 않았다.

## samples/
| 파일 | 내용 |
|---|---|
| `brand_x_retailer_presence_check.json` | 브랜드 5개 × 리테일러 4곳 중 비어 있던 칸의 검색 화면 확인 결과 |
| `apify/target_al_store2581_4brands.json` | automation-lab, 매장 2581, 검색어 4개 87행(브랜드 판정·변형 규칙 근거) |
| `apify/sephora_reviews_P399330.json` | Sephora Living Proof PhD 리뷰 10건(`author` 제거) |
| `apify/chewy_reviews_alc_845310.json` | Chewy Jinx 리뷰 10건, 전용 수집기(`reviewerName` 제거) |
| `apify/chewy_reviews_ecom_tool_ABORTED.json`, `apify/chewy_search_bluesky_BLOCKED.json` | 실패한 Chewy 시험 2건의 입력과 결과 |
| `apify/chewy_search_jinx_arcana.json` | arcana Chewy 수집기 결과(정렬 무시, 30행 차감) |
| `chewy/screen_jinx_dog_food.json` | 사용자 Chrome에서 읽은 Chewy Relevance·Bestselling 화면 순서 |
| `ulta/powerreviews_paging_check.json` | Ulta PowerReviews 2쪽, 10건 한 번에, 리뷰 묶음 확인 |
| `sephora/search_living_proof_bestselling_top10.json` | Sephora Bestselling 정렬 상위 10개와 정렬 선택지 |
| `apify/target_actor_comparison_precheck.json` | Target 전용 수집기 2종의 단가, 입력 형식, 출력 필드 정의(실행 전) |
| `apify/target_al_store2581_death_wish_coffee.json` | automation-lab 수집기, 매장 2581, Death Wish 10건 원본과 실행 정보 |
| `target_screen/screen_death_wish_coffee_0810utc.json` | 위 실행 1분 뒤 사용자 Chrome에서 읽은 같은 검색 화면 |
| `apify/actor_pricing_and_input_precheck.json` | Apify 수집기 2종의 단가, 입력 형식 요약, 준비한 시험 입력(실행 전) |
| `apify/target_search_death_wish_coffee.json` | Target 검색 10건 원본과 실행 정보(입력, 차감 항목, 금액) |
| `apify/target_search_black_rifle_coffee.json` | Target Black Rifle 검색 5건 원본, 1쪽 24개 순서(로그), 실행 정보 |
| `apify/target_search_jinx_dog_food.json` | Target Jinx 검색 5건 원본, 1쪽 24개 순서(로그), 실행 정보 |
| `target_screen/screen_death_wish_coffee.json`, `screen_black_rifle_coffee.json`, `screen_jinx_dog_food.json` | 사용자 Chrome에서 읽은 Target 검색 화면의 칸 순서(광고 여부, 가격 문구, 별점, 리뷰 수), 매장과 ZIP |
| `apify/target_reviews_A-88498115.json` | Target 리뷰 10건 원본(`author` 제거)과 실행 정보 |
| `apify/chewy_search_jinx_official_actor_BAD.json` | 공식 수집기의 Chewy 결과 10건(Jinx 없음), 로그의 주소 일부 |
| `apify/chewy_search_jinx_parseforge.json` | 대체 수집기의 Chewy Jinx 10건 원본과 실행 정보 |
| `ulta/batiste_listing_decoded.json` | Batiste 29건 풀어 쓴 표(위치, ID, 가격, 평점, 배지) |
| `ulta/batiste_listing_raw_excerpt_product1.txt` | 상품 1개 분량의 원본 조각 |
| `ulta/living_proof_listing_decoded.json` | Living Proof 45건 중 앞 10건과 건수 |
| `ulta/pdp_text_excerpt.txt` | 상품 페이지 화면 글자 일부 |
| `ulta/reviews_page1_powerreviews.json` | 리뷰 1쪽에서 3건만(작성자 이름과 지역 제거), 쪽 정보, 요약 일부 |
| `ulta/search_death_wish_coffee_text.txt` | 검색 결과 글자 |
| `sephora/search_living_proof_response_trimmed.json` | 검색 응답 구조와 상품 3개 원본(세션 값 제거) |
| `sephora/search_living_proof_decoded.json` | 57건 풀어 쓴 표 |
| `sephora/search_batiste_and_deathwish_summary.txt` | 두 검색의 결과 요약 |
| `sephora/denied_403.txt` | 403이 난 주소와 상황 |
| `target/plp_search_v2_http435.json` | 435 응답 |
| `chewy/http429_kasada.txt` | 429 응답 앞부분 |
