# 소스 4: Amazon

- 확인일: 2026-11-10 (미국 IP, 화면이 뜨는 Chrome)
- 확인 대상: 검색 4건(Batiste, Death Wish, Jinx, Death Wish 브랜드 필터), 제품 3건(Batiste B00OQKOO02, Death Wish B006CQ1ZHI, Jinx B0F5LZXCDH), 카테고리 베스트셀러 1건, 브랜드 스토어 1건, 리뷰 목록 2건, Apify 리뷰 수집기 2회(Batiste B00OQKOO02 20건, 두 상품 × 5건)
- 구현 전 추가 확인(2026-11-10 08:04~08:06 UTC, 로그아웃): 제품 3건(Death Wish Dark Roast B006CQ1ZHI, Medium Roast B08VFVSBXM, Batiste B00OQKOO02), 검색 3건(Living Proof 일반 검색, Living Proof 브랜드 필터, Batiste 브랜드 필터), 리뷰 고유 주소 1건. 결과는 10-1절에 있다.
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정이거나 미확인
- 확인 방법은 셋이고, 아래에서 결과를 항상 따로 적는다.
  - **(가) 로그아웃:** Playwright로 새 Chrome 프로필을 열었다(페이지 8회).
  - **(나) 로그인:** 사용자가 직접 로그인해 둔 Chrome("baro" 프로필)을 Claude in Chrome 확장으로 읽기만 했다(페이지 6회).
  - **(다) Apify:** 유료 리뷰 수집기를 1회 실행했다(11절).
- Living Proof는 구현 전 확인에서 일반 검색과 브랜드 필터를 1회씩 열었다(3절). 제품 페이지는 열지 않았다.
- 결정된 범위(10절, 12절): 브랜드마다 서로 다른 상품 10개, 상품당 Top reviews 10건이다. 광고 카드는 저장하지 않는다.

## 1. 이 소스가 주는 것
Amazon.com에서 팔리는 상품의 **가격, 평점, 평점 수, 판매 순위, 배지, 리뷰**를 준다. 광고 소재가 아니라 "어떻게 팔고 있나"를 보여 주는 소스다. 과제가 요구하는 것은 "상위 상품의 순위, 가격, 평점, 평점 수, 리뷰 본문"이다. 검색 결과에는 광고(Sponsored) 노출도 섞여 있지만, 이 소스에서는 저장하지 않기로 했다(10절).

## 2. 접근 방법
- 주소 형태 (모두 ✅ 열림):
  - 검색: `https://www.amazon.com/s?k=<검색어>`
  - 브랜드 필터 검색: `https://www.amazon.com/s?k=<검색어>&rh=p_123%3A<브랜드ID>`
  - 제품: `https://www.amazon.com/dp/<ASIN>`. 변형이 있는 제품은 `?th=1`이 붙어 돌아온다 ✅.
  - 카테고리 베스트셀러: `https://www.amazon.com/gp/bestsellers/<대분류>/<카테고리ID>`
  - 브랜드 스토어: `https://www.amazon.com/stores/<브랜드>/page/<GUID>`
  - 리뷰 목록: `https://www.amazon.com/product-reviews/<ASIN>`. 로그아웃 상태에서는 로그인 페이지로 넘어간다(4-4절).
- **수집은 모두 Apify로 한다(사용자 결정, 2026-11-10).** 검색은 `apt_marble/amazon-search-results-scraper`, 상품 상세는 `junglee/Amazon-crawler`, 리뷰 본문은 `delicious_zebu/amazon-reviews-scraper-with-advanced-filters`가 맡는다(12절, 13절). 아래 주소 형태와 로그아웃 확인 결과는 조사와 대조에 쓴 것이다.
- 리뷰 본문은 직접 짠 코드로는 로그인 없이 얻지 못한다(4-4절). 그래서 리뷰는 처음부터 Apify로 정했다(11절).
- **ZIP을 지정하지 않아도 미국 IP에서는 USD로 나온다** ✅. 처음부터 "Delivering to Miami 33166"이 표시됐다. IP 기준으로 자동 지정된 것으로 보인다 ❓. 한국 IP에서 KRW가 나왔던 문제는 미국 IP에서 재현되지 않았다. 한국 IP로 돌릴 때는 ZIP 설정이 필요할 것이다 ❓(이번에 재확인하지 않음).
- 캡차, 로봇 확인, 차단 페이지는 한 번도 나오지 않았다 ✅ (페이지 21회, 요청 간격 4초 이상. 로그인 벽은 4-4절의 두 주소에서만 나왔다). 데이터센터 대역 IP였는데도 그랬다. 많이 돌렸을 때의 한도는 모른다 ❓.
- 검색 결과는 자바스크립트 없이 내려온 HTML에 이미 들어 있다 ✅. 스크롤 없이 카드 60개가 있다. 제품 페이지는 스크롤해야 아래쪽(고객 리뷰 요약)이 채워진다 ✅. 헤드리스 실행은 확인하지 않았다 ❓.
- 실행 수: Apify 실행 3회(검색, 상세, 리뷰)로 5개 브랜드를 모두 처리한다(12절).

## 3. 브랜드 매칭과 "상위 상품"
**"브랜드 상위 상품"을 고르는 방법과 비용:**

| 방법 | 요청 수 | 확인한 결과 | 판정 |
|---|---|---|---|
| (a) 브랜드명 검색의 유기(organic) 상위 N | 1회 | Batiste 검색: 유기 48개가 전부 Batiste ✅. Death Wish 검색: 유기 48개 중 34개만 Death Wish(나머지는 경쟁 브랜드) ✅. Jinx: 48개 중 31개 ✅ | **채택**(12절). Apify 검색 수집기가 검색어만 받기 때문이다. 브랜드 줄로 거르고 광고를 뺀다 |
| (b) 브랜드 스토어 페이지 | 첫 화면 1회, 탭마다 1회 | Batiste 스토어 첫 화면에 상품 10개(브랜드가 직접 고른 진열, 순위 아님) ✅. 주소의 GUID는 제품 페이지의 "Visit the Batiste Store" 링크에서 얻는다 ✅ | 순위 정보 없음 |
| (c) 브랜드 필터(`rh=p_123:<ID>`) | 1회 | Death Wish 필터: 상품 39개가 전부 Death Wish이고 광고는 0개였다 ✅. 화면 문구는 "1-48 of 60 results"인데 카드는 39개만 읽혔다(이유 미확인 ❓). Living Proof 필터와 Batiste 필터는 **60칸이 유기 48 + 광고 12**였다 ✅. 광고도 모두 같은 브랜드 상품이었다. 즉 필터를 걸어도 광고가 나올 수 있으므로 Sponsored 라벨로 건너뛴다 | 처음 채택했으나, Apify 검색 수집기가 검색 주소를 받지 않아 (a)로 바꿨다 |
| (d) 카테고리 베스트셀러 | 페이지당 1회(50개씩, 100위까지) | Dry Shampoos 1페이지에서 스크롤 후 38개를 읽었다(나머지는 늦게 불러오는 것으로 추정 ❓). 브랜드를 고르려면 제목 앞부분으로 걸러야 한다. Batiste 14개, Living Proof 2개(8위, 34위) ✅ | 보조. 시장 안 위치를 볼 때 좋다 |

브랜드 ID는 어느 검색 결과든 왼쪽 "Brand" 목록의 링크(`rh=p_123%3A<ID>`)에서 얻는다 ✅. 아래는 이번에 읽은 값이다.

| 브랜드 | 필터 ID | 상태 |
|---|---|---|
| Batiste | 233425 | ✅ 읽고 실행까지 함. `k=batiste`에서 "1-48 of 122 results" |
| Death Wish Coffee | 238605 | ✅ 읽고 실행까지 함. "1-48 of 60 results" |
| Black Rifle Coffee Company | 168628 | ✅ 읽음, 실행 안 함 |
| Jinx | 5024707 | ✅ 읽음, 실행 안 함 |
| Living Proof | 254796 | ✅ `k=living+proof` 검색의 Brand 목록 첫 줄에서 읽고 실행까지 함. "1-48 of 70 results" |

주의:
- 필터는 "브랜드" 속성이 일치하는 모든 판매자의 목록을 포함한다. 재판매자 목록이 섞였다(제목이 "OG2 DTHWSH DKRST KCP COF …"인 줄 등 ✅). 판매자를 따로 걸러야 할 수 있다 ❓.
- Death Wish 필터 결과 39개 중 6개는 가격과 평점이 없었다(품절 또는 재판매자 목록으로 추정 ❓). Batiste 필터는 60칸 중 1칸(B0BW4MWL2G, 47번째)에 가격이 없었다 ✅. Living Proof 필터는 0칸이었다 ✅.
- 제3자 판매자 목록도 상위에 들어온다. Batiste B00OQKOO02(필터 14번째 칸)는 buy box를 제3자 판매자 "Deals 2 Grab"이 갖고 있다(4-2절). 검색 카드만으로는 판매자를 알 수 없다. 거르지 않고 `seller`에 남긴다.
- 브랜드명만 검색하면 경쟁사 광고가 섞인다. `k=living+proof` 검색에 Batiste 광고 2개가 나왔다 ✅.
- 정렬은 기본 관련도순이다. 인기순 같은 정렬 파라미터는 확인하지 않았다 ❓.

## 4. 원본 구조
### 4-1. 검색 결과 카드 (`samples/search_*.json`, `samples/html_fragments/search_card_*.html`)
카드는 `div[data-component-type="s-search-result"]`이고 `data-asin`이 ASIN이다 ✅. 한 페이지에 60개(유기 48 + 광고 12)가 있다 ✅. 상단에 "1-48 of 328 results" 같은 문구가 있다 ✅.

| 항목 | 읽는 곳 | 예시 |
|---|---|---|
| 순서 | `data-index`. 위젯이 끼어서 번호를 건너뛸 수 있다 ✅. 유기 순위는 광고를 뺀 뒤 센다 | 2, 3, 4 … |
| 광고 여부 | 카드 안에 `.puis-sponsored-label-text`("Sponsored")가 있으면 광고다 ✅ | 60개 중 12개 |
| 브랜드 | 카드의 `h2` 텍스트 ✅. **`h2`는 제목이 아니라 브랜드다.** 광고 카드는 제목이 `h2`에 들어가는 경우가 있었다 ✅. 브랜드 필터 결과에서는 39개 모두 `h2`에 제목이 들어왔다 ✅ | `Batiste` |
| 제목 | `[data-cy="title-recipe"]` 안 텍스트에서 브랜드를 뺀 부분 ✅ | |
| 현재가 | `.a-price`(취소선 아닌 것) 안 `.a-offscreen` ✅ | `$9.99` |
| 단가 | 텍스트 `($1.75/ounce)` ✅ | |
| 정가 | 텍스트 `List: $12.99` ✅ (없는 카드가 많다) | |
| 평점 | `4.5 out of 5 stars` ✅ | |
| 평점 수 | 괄호 안 `(1.9K)`. **K/M으로 줄여서 온다** ✅ | 정확한 값은 제품 페이지의 `1,014` |
| 한 달 구매량 | `10K+ bought in past month` ✅ | 구간값이고 정확한 수가 아니다 |
| 배지 | `.a-badge-text` ✅. "Overall Pick"(`Amazon's Choice`와 비슷한 새 이름, 60개 중 1개). "Best Seller"는 이 4건 검색에서 못 봤다 ❓ | |
| 쿠폰 | 이 4건의 검색 카드에서는 못 봤다 ❓ (검색 정규식으로 찾았으나 0건) | |
| 구독 할인 | 텍스트 "subscribe …"(S&S) ✅ | 커피, 사료 카드에 나옴 |
| 배송 | `FREE delivery Sun, Nov 15 …` ✅ | |
| 다른 판매자 | `$9.98(9 new offers)` ✅ | |

광고 표시 규칙 (✅, 참고용. 이 소스에서는 광고를 저장하지 않는다):
- 광고 카드는 **가격, 평점, 구매량까지 유기 카드와 같은 모양**이라 "Sponsored" 라벨 말고는 구별할 수 없다. 광고 링크는 `/sspa/click?…`로 간다.
- 같은 상품이 광고와 유기 결과에 **동시에** 나온다(Death Wish 검색에서 B0CGRPR2PW 등 3개). 그래서 Death Wish 검색 60칸의 ASIN은 57개였다.
- 브랜드 검색 결과 맨 위에 **자기 광고**가 4개 나왔다(Death Wish 검색 3~6번째 카드). 경쟁사 광고도 섞인다: Death Wish 검색에 Black Rifle, Bulletproof, Jinx 검색에 Open Farm, ORIJEN, Purina, IAMS 광고 ✅. 광고는 위치 3~6, 13~16처럼 덩어리로 끼어든다 ✅.

### 4-2. 제품 페이지 (`samples/product_*.json`, `samples/html_fragments/product_*`)
| 항목 | 읽는 곳 / 결과 | 상태 |
|---|---|---|
| 제목 | `#productTitle` | ✅ |
| 브랜드와 스토어 링크 | `#bylineInfo` "Visit the Batiste Store" → `/stores/Batiste/page/<GUID>` | ✅ |
| 카테고리 경로 | `#wayfinding-breadcrumbs_feature_div` "Beauty & Personal Care › Hair Care › … › Dry Shampoos" | ✅ |
| 현재가 | `#corePrice_feature_div .priceToPay .a-offscreen` `$28.80` | ✅ |
| 단가 | 같은 영역 `$0.71 per fluid ounce` | ✅ |
| 정가, 할인율 | 할인이 있을 때만 `List: $…`, `-18%`가 나온다. 이번 3건에서는 정가가 없었다. 검색 카드와 스토어에는 있었다 | ✅ |
| 한 달 구매량 | `600+ bought in past month` | ✅ |
| 배지 | `Amazon's Choice` (Batiste 제품, Jinx 제품) | ✅ |
| 구독 할인 | `Subscribe & Save $17.55`(Death Wish), `$56.99`(Jinx). Batiste는 없었다 | ✅ |
| 쿠폰 | **이 3개 제품에는 본인 쿠폰이 없었다.** Jinx 페이지의 "You pay $30.59 with coupon"은 추천 상품의 쿠폰이었다 ✅. 쿠폰 UI 형태는 미확인 | ❓ |
| 재고 | `#availability` "In Stock" | ✅ |
| 판매자 | Batiste는 "Ships from Amazon / Sold by Deals 2 Grab"(제3자 판매자가 buy box를 가짐 ✅). Death Wish는 "Ships from Amazon / Sold by Death Wish Coffee Co.". Jinx는 문구가 다르다: "Shipper / Seller Amazon.com" | ✅ |
| 평점, 평점 수 | `#acrPopover`, `#acrCustomerReviewText` "(1,014)" | ✅ |
| 별점 분포 | 텍스트 `5 star 86% / 4 star 9% / 3 star 3% / 2 star 1% / 1 star 1%` (퍼센트만, 건수 아님) | ✅ |
| 판매 순위 2줄 | 아래 표 | ✅ |
| "Customers say" | AI 요약문 1단락과 항목 태그, 언급 수 `Residue(25)` | ✅ (로그아웃으로도 보인다) |
| 변형 선택기 | Batiste B00OQKOO02에는 없음. Death Wish는 `Flavor Name`(15개)와 `Size`(20개), Jinx는 `Size`(5개)와 `Flavor`(3개) | ✅ |
| 부모 ASIN | 페이지 HTML의 JSON 조각 `"parentAsin":"<ASIN>"`(이미지·영상 블록, `immutableParams` 등 여러 곳에 같은 값) ✅. Death Wish Dark Roast와 Medium Roast는 둘 다 B0C81Y83CT, 변형이 없는 Batiste B00OQKOO02는 자기 자신(B00OQKOO02)이다 ✅. 처음 샘플 3건에서 비어 있던 것은 추출 코드의 문제였다 | ✅ |

판매 순위 (Best Sellers Rank) 2줄 형식 (✅):

| 제품 | 큰 분류 줄 | 세부 분류 줄 |
|---|---|---|
| Batiste B00OQKOO02 | `#38,823 in Beauty & Personal Care` | `#149 in Dry Shampoos` |
| Death Wish B006CQ1ZHI | `#751 in Grocery & Gourmet Food` | `#15 in Ground Coffee` |
| Jinx B0F5LZXCDH | `#475 in Pet Supplies` | `#38 in Dry Dog Food` |

세부 분류 줄의 링크가 그 카테고리 베스트셀러 주소다(`/gp/bestsellers/beauty/10656664011` 등 ✅).

**평점 수는 변형끼리 공유된다 (확인된 범위).**
- 같은 제품의 크기·팩 수가 다른 ASIN은 같은 평점 수를 보여 준다. Death Wish 낱개 16oz(48,586), "16oz 2팩"(B00TXTNL2S), "5lb"(B00FPQKBOE)가 모두 `48.5K`다 ✅. Jinx 사료의 크기별 ASIN도 모두 `2K`다 ✅.
- 형태가 다르면(분쇄 vs 원두) 평점 수가 다르다(48.5K vs 19.1K) ✅.
- **맛이 다르면 같은 부모 아래에 있어도 평점을 공유하지 않는다** ✅. Death Wish Dark Roast(B006CQ1ZHI)는 48,586개, Medium Roast(B08VFVSBXM)는 3,357개인데 부모 ASIN은 둘 다 B0C81Y83CT다. 가격도 $18.47과 $17.48로 다르다.
- 리뷰도 같은 단위로 묶인다. Apify가 Dark Roast(`variant_scope: all_variants`)로 돌려준 리뷰 5건은 모두 Dark Roast의 크기 변형(B006CQ1ZHI, B00TXTNL2S, B00PCRUU7E)이었다 ✅.
- 그래서 **"같은 상품"의 단위는 부모 ASIN이 아니라 평점을 공유하는 묶음**이다. 부모 ASIN으로만 묶으면 Death Wish의 맛 15개가 한 상품이 된다. ASIN마다 한 행씩 저장하면 같은 평점이 여러 번 세어진다. 12절에서 "부모 ASIN과 정확한 평점 수가 모두 같으면 같은 상품"으로 묶는다.
- **판매 순위는 부모 단위로 보인다** ✅(한 쌍에서 확인). Dark Roast와 Medium Roast의 제품 페이지가 똑같이 `#742 in Grocery & Gourmet Food`, `#15 in Ground Coffee`를 보여 줬다. 평점 수는 15배 차이가 나는데 순위가 같다. 맛별 순위가 아니라 부모 묶음의 순위일 가능성이 크다 ❓.

### 4-3. 카테고리 베스트셀러 (`samples/bestsellers_dry_shampoos_page1.json`)
`#gridItemRoot` 한 칸이 상품 1개다. 순위 `#1`…, 제목, 평점, 평점 수(정확한 숫자 `15,739`), 가격이 있다 ✅. 1페이지에 50칸이 있고, 스크롤해서 38칸을 읽었다. 2페이지는 `?pg=2` 링크가 있다(열어 보지 않음 ❓). 광고는 없었다 ✅.

### 4-4. 리뷰
#### (가) 로그아웃 상태 (Playwright, 미국 IP) ✅
- 제품 페이지: 별점 분포, "Customers say" AI 요약, 항목 태그(`Residue(25)`)는 **보인다**. 리뷰 본문은 **한 건도 없다.** 그 자리에 "Sign in to see customer reviews."가 나온다(Batiste, Death Wish, Jinx 3개 제품 모두 ✅). DOM에 `data-hook="review"` 요소가 0개다 ✅.
- `/product-reviews/B00OQKOO02`는 로그인 페이지(`/ap/signin?...`)로 리다이렉트된다 ✅. 로그인 벽이라 거기서 멈췄다.
- 후기 문구가 보이는 다른 공개 화면(`#cm-cr-dp-review-list`, "Top reviews from the United States", 리뷰 하이라이트)은 로그아웃 페이지에 **존재하지 않았다** ✅(HTML에 해당 id 0건).
- 리뷰 고유 주소 `/portal/customer-reviews/srp/-/R2PAMD6PD20P7R`(Apify가 준 `ReviewUrl`)도 로그아웃 상태에서는 로그인 페이지(`/ap/signin?...`)로 넘어간다 ✅. 거기서 멈췄다. 그래서 **리뷰 본문은 로그인하지 않으면 실제 사이트와 대조할 수 없다.** 대조하려면 로그인한 브라우저에서 리뷰 주소를 열어야 한다.
- 결론: **로그아웃으로 얻는 리뷰 정보는 별점 분포(퍼센트), AI 요약 1단락, 항목 태그와 언급 수까지다.**

#### (나) 로그인 상태 (사용자의 Chrome, "baro" 프로필) ✅
로그인 확인: 머리말이 "Hello, …"(계정 이름) 인사이고 배송지가 "Pacoima 91331"이었다. 계정 이름은 저장하지 않았다.

- **제품 페이지에 리뷰 8건이 바로 보인다.** `/product-reviews/…`가 열린다.
- 한 건이 가진 것(`data-hook`):
  - 별점(`review-star-rating`, "5 out of 5 stars"), 제목(`reviewTitle`), 본문(`reviewText`)
  - 날짜와 국가 줄(`review-date`: "Reviewed in the United States on November 24, 2023")
  - 구매 인증(`avp-badge`: "Verified Purchase")
  - 도움이 됨 수(`helpful-vote-statement`: "3 people found this helpful", "One person found…". 없으면 요소가 없다)
  - **리뷰한 변형**(`product-variation-attributes`: "Flavor Name: Dark Roast / Size: 1 Pound (Pack of 2)")
  - 리뷰 ID(`R2PAMD6PD20P7R` 형태, 요소 id)
  - DOM에는 작성자 이름, 프로필 링크, 아바타도 있다. 샘플에는 저장하지 않았다.
- **Death Wish 페이지의 변형 줄은 리뷰마다 다르다**(1 Pound Pack of 1, Pack of 2, 1.75 Pound). 이 페이지의 리뷰는 크기 변형 여러 개의 리뷰를 모은 것이다 ✅. Batiste 단일 제품은 변형 줄이 없었다 ✅.
- 본문에 Amazon이 넣은 표시 `Start of highlighted quote: … End of highlighted quote`가 문장 속에 섞여 나온다 ✅. 저장 전에 지워야 한다.
- 목록 페이지(`/product-reviews/B00OQKOO02`)와 `/portal/customer-reviews/B00OQKOO02`는 같은 화면이다. 둘 다 **고정 8건**이었다. 날짜가 뒤섞여 있다(2023-11, 2024-05, 2022-12, 2023-08, 2025-04, 2022-10, 2023-09, 2020-02 ✅). Apify 결과와 대조해 보니 이 순서가 Top reviews 순서였다 ✅(11절).
- **정렬, 별점 필터, 페이지 넘김이 없다.** `?pageNumber=2&sortBy=recent&filterByStar=one_star`를 붙여도 똑같은 8건이 나왔다(파라미터 무시 ✅). 화면에 정렬·필터 컨트롤이 없었다. "Load more" 버튼이 DOM에는 있지만 화면에 보이지 않았고, 누르지 않았다 ✅.
- 화면에 이런 문구가 있다: "We limit review access when we detect unusual activity on an account. Send a request so we can verify your account and restore the full reviews experience." ✅ 이 계정은 리뷰 접근이 제한된 상태로 보인다. 원인은 모른다(새 계정이어서인지, 자동화 접근 때문인지 ❓). 요청 버튼은 누르지 않았다.
- 그래서 이 계정으로 **도달할 수 있는 리뷰는 제품당 8건**이다(평점 1,014개 중).
- 리뷰 고유 주소(`/portal/customer-reviews/srp/-/<리뷰ID>`)는 로그인 상태에서 열렸고 리뷰 1건을 보여 준다 ✅. 제품 페이지의 "See more reviews"는 `/portal/customer-reviews/<ASIN>`으로 간다 ✅.
- 샘플: `samples/reviews_logged_in_sample.json`(Batiste 8건 요약 + Death Wish 8건, 이름 없음. 본문은 첫 문장과 길이만 저장).
- 이 경로는 쓰지 않기로 했다(10절). 수집기가 사람이 로그인해 둔 프로필에 의존하게 되고, 그 계정도 8건으로 제한돼 있기 때문이다.

#### (다) Apify 수집기 ✅
20건을 받았고, (나)에서 본 8건과 순서와 내용이 모두 일치했다. 자세한 내용은 11절에 있다.

## 5. 집중해서 볼 것과 원본의 대응
| 과제가 요구한 것 | 원본에서 얻는 방법 | 상태 |
|---|---|---|
| 순위 | 두 종류: 브랜드 필터 검색의 위치와 Best Sellers Rank. 6절 참고 | ✅ |
| 가격 | 제품 페이지 `priceToPay`. 검색 카드에도 있다 | ✅ USD |
| 평점 | 제품 페이지. 검색 카드에도 있다 | ✅ |
| 평점 수 | 제품 페이지의 정확한 값. 검색 카드는 `1.9K` 같은 근사값이다 | ✅ |
| 리뷰 본문 | Apify 수집기, 상품당 Top reviews 10건. 직접 짠 코드로는 로그인 없이 얻지 못한다. 실제 사이트와의 대조도 로그인해야 할 수 있다 | ✅ (11절, 규칙 위험 있음) |

## 6. 어떤 순위가 의미 있나
**한 제품의 두 순위를 나란히 놓으면 (✅):**

| 제품 | 검색 위치 (검색어 → 유기 순위) | Best Sellers Rank |
|---|---|---|
| Batiste B0BTVTH9CW (5.71oz) | "batiste dry shampoo" → 유기 2위 | Dry Shampoos **#11** (베스트셀러 목록 1페이지에서 읽음) |
| Batiste B00OQKOO02 (6팩) | 같은 검색 → 유기 6위 | Dry Shampoos **#149**, 큰 분류 #38,823 (제품 페이지) |
| Death Wish B006CQ1ZHI | "death wish coffee" → 유기 2위 | Ground Coffee **#15**, 큰 분류 #751 |
| Jinx B0F5LZXCDH | "jinx dog food" → 유기 1위 | Dry Dog Food **#38**, 큰 분류 #475 |

- **검색 위치**는 그 검색어에 대한 Amazon의 관련도, 광고, 재고가 섞인 값이다. 브랜드 필터 검색의 위치는 그 브랜드 상품 안에서의 정렬일 뿐 시장 순위가 아니다. 위 Batiste 두 제품은 검색 2위와 6위지만 카테고리 순위는 11위와 149위로 차이가 훨씬 크다.
- **Best Sellers Rank**는 판매량에 기반한 순위로, 시장 안에서의 위치를 나타낸다. 큰 분류 순위는 숫자가 커서(#38,823) 분류 사이 비교가 어렵다. **세부 분류 순위(Dry Shampoos #149)를 우선**으로 본다.
- 순위는 계속 바뀌므로 수집 시각과 함께 저장한다. 같은 날 몇 시간 사이에도 바뀌었다 ✅: Batiste B00OQKOO02는 #38,823 / #149에서 #38,059 / #150으로, Death Wish B006CQ1ZHI는 큰 분류 #751에서 #742로 바뀌었다. 갱신 주기는 모른다 ❓.
- 판매 순위는 맛이 다른 상품끼리 같은 값을 보여 줄 수 있다(4-2절). 같은 부모 아래 상품을 판매 순위로 서로 비교하면 안 된다.
- 그래서 상위 상품을 고르는 순서는 검색 위치로 정하고, 행마다 Best Sellers Rank를 함께 저장한다(12절).

## 7. 항목 식별과 재실행
- 상품 행의 키: 대표 ASIN(12절). 같은 상품 묶음을 알아보도록 부모 ASIN도 저장한다. "같은 상품"은 같은 변형 묶음(부모 ASIN, Apify에서는 `variantAsins`)에 속하고 정확한 평점 수도 같은 ASIN들이다(4-2절).
- 리뷰 행의 키: 리뷰 ID(`R2PAMD6PD20P7R` 형태) ✅.
- 대조용 주소: 상품 `https://www.amazon.com/dp/<ASIN>`, 리뷰 `https://www.amazon.com/portal/customer-reviews/srp/-/<리뷰ID>` ✅.
- 가격, 순위, 평점 수, 리뷰의 도움이 됨 수는 시점별 값이다. 같은 키의 행을 다시 만들지 않고, 시각과 함께 관측값으로 쌓는다.
- 상위 10에서 빠진 상품과 리뷰는 지우지 않고 ended로 표시한다. 뜻은 "이 브랜드의 상위 10(또는 그 상품의 Top reviews 10)에서 빠짐"이다. 상품이 사라졌다는 뜻이 아니다.
- 검색 결과 순서는 실행마다 달라질 수 있다. 같은 검색을 두 번 돌려 비교하지 않았다 ❓.

## 8. 이 소스에서 얻을 수 없는 것
- 직접 짠 코드, 로그아웃 상태: 개별 리뷰 본문 전부.
- 로그인(이 계정): 제품당 8건 이후의 리뷰, 정렬과 필터.
- 정확한 판매량. "600+ bought in past month" 같은 구간값만 있다.
- 검색 카드의 정확한 평점 수. 제품 페이지에서 얻어야 한다.
- 쿠폰: 이번 3개 제품과 4개 검색에서 본인 쿠폰을 못 봤다. 쿠폰 표시 형태는 모른다 ❓.
- 광고비, 입찰가. 광고 노출 여부만 안다.
- 과거 순위. 현재 시점 값뿐이다.

## 9. 이걸로 볼 수 있는 것
- **시장 안 위치:** Dry Shampoos 베스트셀러 상위 38위 안에 Batiste가 14개 있다. Living Proof는 Perfect hair Day Dry Shampoo가 8위(B0170GOCVO, $33.00, 평점 4.3, 14,812)이고 Advanced Clean이 34위(B09B16VRJ7)다 ✅.
- **가격과 크기 전략:** 같은 Jinx 사료가 4lb $8.59, 30lb $59.99(파운드당 $2.15 vs $2.00)로 나뉜다. Death Wish 분쇄 커피는 1lb $18.47에서 5lb $79.98까지 6개 크기다 ✅.
- **고객이 말하는 것:** 로그인 없이도 항목 태그 수로 비교할 수 있다. Batiste는 Effectiveness(88), Residue(25), Death Wish는 Coffee quality(15K), Value for money(2.3K), Jinx는 Taste(282), Digestibility(132)다 ✅. Apify 결과에는 항목별 긍정·부정 수도 있다(Batiste Residue 긍정 15, 부정 10 ✅).
- **리뷰 점수 분포:** 5점 비율이 Batiste 86%, Death Wish 82%, Jinx 83%다 ✅.
- **리뷰 본문:** 상품마다 Top reviews 10건으로 불만과 칭찬의 구체적인 내용을 읽는다. 예: Batiste 리뷰 20건 중 "Leaves residue", "False advertisement", "Not the same bottle as displayed" 같은 제목이 있다 ✅.
- 참고(저장하지 않음): 브랜드명 검색에는 경쟁사 광고가 보인다. Death Wish 검색 첫 화면에 자기 광고 4개와 Black Rifle·Bulletproof 광고, Jinx 검색에 Open Farm, ORIJEN, Purina, IAMS 광고가 나왔다 ✅. Black Rifle은 Death Wish 검색의 광고 1건(B0BLZKGWQ9)과 제품 페이지의 추천에서만 봤고, 직접 검색하지 않았다 ❓.

## 10. 정해야 할 것
정한 것 (2026-11-10, 사용자):
1. **리뷰 본문:** Apify `delicious_zebu/amazon-reviews-scraper-with-advanced-filters`로 받는다. 로그인 프로필은 쓰지 않는다. 리뷰어 이름은 받지 않는다(`include_personal_data: false`).
   - 규칙 위험은 사용자가 감수하기로 했다. 접근 방식이 공개되지 않아 "No borrowed accounts"와 충돌할 수 있다(11절). 이 위험은 notes에 그대로 적는다.
   - 검토했던 다른 길: (나) 로그인 프로필은 사람이 로그인해 둔 브라우저가 계속 필요하고 제품당 8건으로 제한돼 있다. 리뷰를 아예 받지 않으면 별점 분포, AI 요약, 항목 태그까지만 남는다.
2. **"상위 상품":** 브랜드명 검색의 일반 결과(광고 제외) 중 브랜드 줄이 그 브랜드인 상품을 순서대로 읽고, 서로 다른 상품 10개를 고른다. 용량·묶음만 다른 변형은 하나로 센다(12절). 처음에는 브랜드 필터 검색(3절 (c))으로 정했지만, 수집을 Apify로 옮기면서 (a)로 바꿨다. Apify 검색 수집기가 검색어만 받기 때문이다.
3. **리뷰 수:** 상품마다 Top reviews 순서로 10건을 받는다.
4. **광고 카드:** 저장하지 않는다. 이 소스는 상품과 리뷰를 본다.
5. **키:** 상품 행은 대표 ASIN 하나, 변형 묶음(처음에는 부모 ASIN, Apify로 옮긴 뒤에는 `variantAsins`)은 속성으로 둔다. 용량 변형을 하나로 묶기 때문에 같은 평점이 두 번 세어지지 않는다. 구현 전 확인에서 맛이 다른 상품도 같은 부모 아래 있다는 것이 드러났다. 그래서 묶는 기준을 "부모 ASIN이 같고 정확한 평점 수도 같음"으로 구체화했다. 용량·묶음만 다른 변형은 하나로 센다는 결정 내용은 그대로다.
6. **attribute 목록(12절):** 확정했다. 가격 없는 카드 건너뛰기와 ended 규칙(7절)도 포함한다. 수집을 Apify로 옮기면서 출처 열을 Apify 필드로 바꿨고, `parent_asin`은 `variant_family`로 바꿨다(두 수집기 모두 부모 ASIN 필드가 없다).
7. **상품 정보의 수집 경로:** Apify로 한다(사용자 결정, 2026-11-10). 첫 시험의 두 수집기는 막혔고, `apt_marble`(검색)과 `junglee`(상세)는 직접 본 값과 일치했다(13절). 수집기 3개(검색 `apt_marble`, 상세 `junglee`, 리뷰 `delicious_zebu`)를 그대로 쓰기로 사용자가 확정했다. 상세를 빼면 2개로 줄일 수 있지만, 판매 순위·판매자·재고·변형 묶음을 잃기 때문이다. 검색은 다른 수집기가 검색 위치와 광고 표시를 주지 않아서 뺄 수 없다.

8. **브랜드 검색어(12절):** `batiste`, `living proof`, `death wish coffee`, `black rifle coffee`, `jinx dog food`. Jinx만 범위를 좁혔다. "jinx"는 다른 상품이 많이 섞이기 때문이다. 그 대신 Jinx의 고양이 사료와 간식은 빠질 수 있다.

아직 정하지 않은 것:
9. **"직접 짠 코드" 규칙:** Amazon은 이제 모두 유료 서비스로 수집한다. "유료 스크래핑 서비스 없이 수집한 소스가 최소 1개"라는 규칙은 다른 소스에서 채워야 한다. 메인 스레드가 확인한다.

### 10-1. 구현 전 확인 (2026-11-10 08:04~08:06 UTC, 로그아웃 페이지 7회 + Apify 1회)
확인한 것:
1. **부모 ASIN 추출** ✅: 제품 페이지 HTML의 `"parentAsin":"<ASIN>"`에서 읽힌다. 3건 모두 값이 있었다. 변형이 없는 상품은 자기 자신이 부모다(4-2절).
2. **맛 변형도 같은 묶음인가** ✅: 같은 부모 아래 있지만 평점과 리뷰는 맛마다 따로다(Dark Roast 48,586개, Medium Roast 3,357개). 그래서 묶는 기준을 "부모 ASIN과 정확한 평점 수가 모두 같음"으로 정했다(12절). 판매 순위는 두 맛이 같은 값을 보여 줬다(4-2절).
3. **Living Proof 브랜드 필터 ID** ✅: 254796. 필터 결과 70개, 첫 쪽 60칸이 모두 Living Proof였다.
4. **필터 결과의 칸 수** ✅: Living Proof와 Batiste 필터는 60칸(유기 48 + 광고 12)이 모두 읽혔다. **브랜드 필터에도 광고가 나온다**(같은 브랜드 광고). Death Wish 필터에서 39칸만 읽힌 이유는 여전히 모른다 ❓. 유기 48칸이면 서로 다른 상품 10개를 채우기에 충분하다.
5. **재판매자 목록과 가격 없는 목록** ✅: 가격 없는 칸은 Batiste 1칸, Living Proof 0칸이었다. 제3자 판매자 목록은 걸러지지 않고 들어온다. 판매자는 거르지 않고 `seller`로 남긴다(3절).
6. **Apify 여러 상품 한 번에** ✅: 두 상품을 한 실행에 넣고 `max_reviews: 5`를 주니 상품마다 정확히 5건이 왔다. Death Wish의 `Variant`와 `VariantASIN`이 채워졌다(11절).
7. **리뷰 고유 주소** ✅: 로그아웃 상태에서는 로그인 페이지로 넘어간다. 리뷰 본문은 로그인하지 않으면 실제 사이트와 대조할 수 없다(4-4절).

아직 확인하지 못한 것:
8. **샘플 추출 오류:** 상품 샘플 3건 모두 `list_price`에 단가가 들어갔다(Batiste `$0.71`). 구현할 때 고쳐야 한다.
9. 화면 없는 실행(headless)이 되는지, 한국 IP에서 ZIP 설정이 필요한지, 같은 검색을 두 번 돌렸을 때 순서가 같은지 ❓.
10. 쿠폰과 "Best Seller" 배지의 표시 형태 ❓. 이번 Batiste 필터에서 "#1 Top Rated" 배지가 한 칸(B01CYDXMYQ)에 보였다 ✅.
11. 판매 순위가 부모 단위인지 ❓. 한 쌍에서만 같은 값을 봤다.

## 11. Apify 리뷰 수집기 시험 (`delicious_zebu/amazon-reviews-scraper-with-advanced-filters`, 2026-11-10) ✅
- 실행: run `uhEq1LM2ZFcZxDcjZ`, 07:45:46~07:45:56 UTC(9.8초), 1회, 오류 없음. 사용자가 이 스레드에서 직접 승인했다.
- 입력: ASIN `B00OQKOO02`, 국가 United States, `max_reviews: 20`, 정렬 `helpful`+`recent`, 별점·구매 인증·미디어 필터는 각각 "전체" 하나씩, `variant_scope: all_variants`, `unique_only: true`, `include_personal_data: false`.
- 상한: `maxTotalChargeUsd` $0.20. 이 수집기는 상한 최소값이 없다(`minimalMaxTotalChargeUsd: null`) ✅. Apify가 상한에 맞춰 `maxItems: 33`을 자동으로 붙였다 ✅.
- **차감액: $0.15** (`usageTotalUsd`: 시작 1건 $0.03 + 결과 20건 × $0.006) ✅. 시험 누계는 $0.62에서 $0.77이 됐다.

| 확인할 것 | 결과 |
|---|---|
| 8건을 넘는가 | ✅ 20건. Top reviews(`sortBy=helpful`) 순서의 1쪽 10건과 2쪽 10건이다. 제한 걸린 로그인 계정에서는 `pageNumber=2`가 무시됐지만, 여기서는 다른 10건이 왔다 |
| 미국 amazon.com의 그 상품인가 | ✅ `ReviewCountry`가 20건 모두 "United States"다. `PageUrl`은 `amazon.com/product-reviews/B00OQKOO02?...`, `ReviewUrl`은 `amazon.com/portal/customer-reviews/srp/-/<리뷰ID>`다 |
| 로그인 Chrome에서 본 8건과 같은가 | ✅ 8건이 모두 있고 **순서도 같다**(1~8위). 별점, 제목, 날짜, 구매 인증, 도움이 됨 수가 8건 모두 일치한다. 본문은 공백만 다르다(이쪽은 문장 사이 두 칸 공백을 그대로 둔다. 길이 차이 0~5자) |
| 리뷰어 이름이 비는가 | ✅ `Reviewer`, `ReviewerProfileUrl`, `ReviewerId`가 20건 모두 빈 문자열이다 |
| 정렬 기준 | ✅ 받은 20건은 모두 Top reviews 순서다. `recent`도 넣었지만 helpful에서 20건이 다 차서 recent는 읽지 않았다. Most recent 순서가 실제로 되는지는 모른다 ❓ |
| 전체 몇 건까지 | 이 상품에서 글이 있는 리뷰는 `RatingTypeTotalReviews` "131 customer reviews"다(평점 1,014개 중) ✅. README는 "필터 하나당 최대 100건이고, 정렬·별점·구매 인증·미디어 조합으로 더 받는다"고 한다. 100건 넘게 받아 보지는 않았다 ❓ |

- 한 행에 있는 것 ✅: `ReviewId`, `ReviewDate`(YYYY-MM-DD), `ReviewScore`, `ReviewTitle`, `ReviewContent`(전문, 63~1,402자), `Verified`, `HelpfulVotes`(숫자), `Images`(20건 중 1건에 1장), `Variant`, `VariantASIN`(이 단일 상품에서는 비어 있다. 변형이 많은 Death Wish에서는 확인하지 않았다 ❓), `PageUrl`(어느 정렬, 어느 쪽에서 왔는지).
- 상품 단위 값도 모든 행에 반복해서 온다: `AverageRating` 4.7, `TotalRatings` 1,014, `StarDistribution` 86/9/3/1/1, `CustomersSay`. 제품 페이지에서 직접 읽은 값과 같다 ✅.
- `ReviewAspects`에는 직접 읽은 화면에서 못 본 **측면별 긍정·부정 수**가 있다. 예: `Residue(25)`는 긍정 15, 부정 10이다 ✅.
- 본문에 `Start of highlighted quote` 표시가 섞인 경우는 20건 중 없었다 ✅.
- 대조하지 못한 것: 겹치지 않는 12건(9~20위)은 실제 사이트와 맞춰 보지 않았다 ❓. 리뷰 주소가 로그아웃 상태에서는 열리지 않아서, 대조하려면 로그인한 브라우저가 필요하다(4-4절).
- **규칙 위험 (사용자가 감수하기로 함):** 이 수집기가 읽는 `/product-reviews/<ASIN>`은 로그아웃 상태로 열면 로그인 페이지로 넘어가는 주소다(4-4절). 이 수집기는 그 주소의 2쪽까지 읽었다. 반면 우리 제한 계정은 2쪽을 받지 못했다. 소스 코드는 비공개이고(`isSourceCodeHidden: true`), 실행 로그에도 접근 방식이 나오지 않는다. README에는 "only reads publicly visible review pages"라고만 적혀 있다. 운영자의 로그인 계정으로 읽고 있을 가능성을 배제할 수 없다.
- 비용: 리뷰 1,000건에 약 $6.00, 여기에 실행 1회당 $0.03이 붙는다(무료 요금제 기준. 상위 요금제는 건당 $0.003~0.005) ✅ 단가는 수집기 정보에서 읽었다. 입력의 ASIN 칸은 목록이라 여러 상품을 한 번에 넣을 수 있고, 그러면 시작 요금은 한 번만 낸다(아래 2회째에서 확인).
- 원본: `samples/apify/`(입력, 결과 20건, 실행 기록 요약).

### 2회째: 두 상품을 한 실행에 (2026-11-10) ✅
- 실행: run `NsOurP6dBZOELcKMv`, 08:03:42~08:04:23 UTC(41초), 오류 없음. 사용자가 이 스레드에서 직접 승인했다.
- 입력: ASIN `B00OQKOO02`, `B006CQ1ZHI`, `max_reviews: 5`, 정렬 `helpful`만, 나머지는 1회째와 같다. 상한 $0.12(Apify가 `maxItems: 20`을 붙였다).
- **차감액: $0.09** (시작 1건 $0.03 + 결과 10건 × $0.006) ✅. 시험 누계는 $0.77에서 $0.86이 됐다.
- **상품마다 정확히 5건**이 왔다 ✅. 시작 요금은 한 번만 붙었다 ✅.
- Batiste 5건은 1회째의 1~5위와 같았다 ✅.
- Death Wish 5건은 로그인 Chrome의 제품 페이지에서 본 리뷰 1~5번째와 같았다 ✅. 리뷰 ID, 순서, 별점, 제목, 도움이 됨 수(84, 13, 46, 7, 1), 변형 줄이 모두 일치했다.
- `Variant`가 채워졌다 ✅. 예: `["Flavor Name: Dark Roast", "Size: 1 Pound (Pack of 2)"]`이고, `VariantASIN`은 B00TXTNL2S였다. 5건 모두 Dark Roast의 크기 변형이었다.
- Death Wish Dark Roast의 글 리뷰 총수는 21,740건이다(평점 48,586개 중) ✅.
- 리뷰어 이름, 프로필, ID는 10건 모두 비어 있었다 ✅.
- 원본: `samples/apify/input_2asins_5each.json`, `dataset_2asins_5each.json`, `run_NsOurP6dBZOELcKMv.json`.

## 12. "상위 상품"의 정의와 attribute
**정의, 개수, attribute 목록은 모두 사용자와 합의했다(2026-11-10).** 구현 전 확인(10-1절)으로 같은 상품을 묶는 기준을 구체화했다. 그 뒤 사용자가 수집을 모두 Apify로 옮기기로 해서, 고르는 순서와 attribute의 출처를 Apify 기준으로 다시 썼다(13절). ❓ 표시가 남은 항목은 구현하면서 확인한다.

### 상품 고르기 (브랜드당, Apify 3단계)
1. **검색:** `apt_marble/amazon-search-results-scraper`에 브랜드명을 검색어로 넣는다. 입력: `keywords: ["<브랜드 검색어>"]`, `maxResultsPerKeyword: 60`, `excludeSponsored: true`, `sortBy: "relevance"`, `marketplace: "us"`. 이 수집기는 검색 주소를 받지 않아서 브랜드 필터(`rh=p_123`)를 쓸 수 없다 ✅(입력 형식).
2. **거르기:** 브랜드 줄(`brand`)이 그 브랜드인 결과만 남긴다(대소문자 무시). 가격이 없는 결과는 건너뛰고, 건너뛴 수를 실행 기록에 남긴다. 순서는 `organicPosition`을 따른다.
3. **1차 묶기:** 평점과 정확한 평점 수(`rating`, `ratingsCount`)가 둘 다 같은 결과는 같은 상품의 용량 변형으로 보고, 가장 위의 것만 남긴다. 예: Living Proof B0BQ3YFRC5와 B0170GOCVO는 둘 다 4.3점, 14,811개다 ✅. 남은 후보를 위에서부터 15개 고른다.
4. **상세:** 후보 ASIN을 `junglee/Amazon-crawler`에 상품 주소(`https://www.amazon.com/dp/<ASIN>`)로 넣는다. 입력: `maxItemsPerStartUrl: 1`, `scrapeProductDetails: true`, `useCaptchaSolver: false`, `maxOffers: 0`, `scrapeSellers: false`. 판매 순위, 정확한 평점 수, 별점 분포, 같은 묶음의 변형 목록(`variantAsins`), 판매자, 재고가 온다.
5. **2차 묶기:** 한 후보가 다른 후보의 `variantAsins`에 들어 있고 평점 수(`reviewsCount`)도 같으면 같은 상품으로 본다. 위에 나온 것만 남긴다. 변형 목록에는 있지만 평점 수가 다르면(Death Wish의 맛) 다른 상품이다(4-2절).
6. 위에서부터 10개를 rank 1~10으로 저장한다. 10개가 안 되면 모인 만큼 저장하고, 그 사실을 표시한다.
- 브랜드 검색어(확정, 사용자 2026-11-10): `batiste`, `living proof`, `death wish coffee`, `black rifle coffee`, `jinx dog food`.
- 브랜드 줄 판정: 대소문자를 무시하고 **정확히 같을 때만** 그 브랜드로 본다. "포함"으로 비교하면 Jon Batiste 음반 같은 것이 섞일 수 있다. 허용값은 `batiste`, `living proof`, `death wish coffee`, `black rifle coffee company`, `jinx`다. 앞의 4개는 저장된 검색 결과의 브랜드 줄에서 확인했다 ✅(Living Proof는 "LIVING PROOF"와 "Living Proof" 두 표기). apt_marble의 `brand` 필드가 같은 값을 주는지는 Living Proof에서만 확인했다 ❓. 근거: `k=batiste` 브랜드 필터 화면(08:05 UTC)의 일반 결과 48개 중 47개가 제목에 "shampoo", 41개가 "dry shampoo"를 담고 있었다 ✅(나머지는 "Shampoo Dry …" 표기와 볼륨 스프레이). 즉 Batiste는 브랜드명만 넣어도 드라이 샴푸가 나온다. 필터 없는 `batiste` 검색은 직접 보지 않았다 ❓. Jon Batiste 음반 같은 다른 상품이 섞일 수 있지만, 브랜드 줄이 정확히 "Batiste"인 것만 남기면 빠진다. `k=living+proof`도 일반 결과 상위 25개가 트리트먼트, 샴푸, 드라이 샴푸, 스타일링 제품으로 브랜드 전체 제품군이 나왔다 ✅. "jinx"만 넣으면 다른 상품이 섞일 가능성이 크다. 브랜드 줄로 거르므로 검색어가 넓어도 다른 브랜드는 빠진다. 대신 그 브랜드 상품이 60칸 안에 10개 미만일 수 있다.
- 실행 수: 검색 1회(검색어 5개를 한 실행에), 상세 1회(후보 최대 75개), 리뷰 1회(상품 50개).

### 비용 (무료 요금제 단가 기준 계산값)
| 단계 | 수량 | 단가 | 합계 |
|---|---|---|---|
| 검색 `apt_marble` | 5 × 60건 | $0.001 | $0.30 |
| 상세 `junglee` | 최대 75건 | $0.005 | $0.375 |
| 리뷰 `delicious_zebu` | 최대 500건 | $0.006 + 시작 $0.03 | $3.03 |
| 1회 전체 | | | **약 $3.7** |

- 레코드 1,000개당: 리뷰 약 $6, 상품 약 $13.5(상품 1개에 검색 6건과 상세 1.5건이 든다고 보고 계산했다 ❓).

### 리뷰 받기
- 고른 상품 50개의 대표 ASIN을 Apify 실행 1회에 넣는다. 입력: `max_reviews: 10`, `sort_reviews_by: ["helpful"]`, 별점·구매 인증·미디어 필터는 각각 "전체" 하나, `variant_scope: all_variants`, `unique_only: true`, `include_personal_data: false`, `country: "United States"`.
- 비용: 최대 500건 × $0.006 + $0.03 = **약 $3.03**(계산값).
- 상품마다 받은 리뷰 수를 기록한다. 0건이면 "could not look", 10건 미만이면 그 상품의 글 리뷰 총수(`RatingTypeTotalReviewsCount`)와 비교해 부분 수집인지 표시한다.

### 상품 행 attribute (확정. 이름은 `attribute-candidates.md` 3-1절과 같다. 출처는 Apify 필드로 바꿨다(13절))
| attribute | 출처 (Apify 필드) | 확인 | 비고 |
|---|---|---|---|
| product_id | 대표 ASIN(`asin`) | ✅ | 키 |
| variant_family | junglee `variantAsins` | ✅ | **parent_asin 대신 둔다.** 두 수집기 모두 부모 ASIN 필드가 없어서, 같은 묶음의 ASIN 목록으로 대신한다. Death Wish 분쇄 커피는 41개다 |
| brand | 우리 브랜드 키. apt_marble `brand` 원문도 함께 둔다 | ✅ | |
| ★ rank | 6번 단계의 순서 1~10 | | 브랜드 상품 안에서의 순위 |
| search_keyword, search_position | apt_marble `keyword`, `organicPosition`, `position` | ✅ | 같은 검색어도 실행마다 순서가 조금씩 다르다(13절) |
| ★ bsr_sub, bsr_sub_category | junglee `bestsellerRanks[1]` | ✅ | 예: 150, Dry Shampoos. 같은 묶음끼리 같은 값을 보여 줄 수 있다(4-2절) |
| bsr_main, bsr_main_category | junglee `bestsellerRanks[0]` | ✅ | 예: 38,058, Beauty & Personal Care |
| title | junglee `title` | ✅ | |
| variant | junglee `variantAttributes` | ✅ | 예: Flavor Name Dark Roast, Size 1 Pound (Pack of 1) |
| ★ price | junglee `price.value` | ✅ | USD. apt_marble `price`와도 같았다 |
| unit_price | apt_marble `unitPrice` | ❓ | 이번 Living Proof 결과에는 없었다 |
| list_price | junglee `listPrice`, apt_marble `listPrice` | ✅ | 할인이 있을 때만 온다. 이번 3건에는 없었다 |
| ★ rating_avg | junglee `stars` | ✅ | |
| ★ review_count | junglee `reviewsCount` | ✅ | 정확한 평점 수 |
| written_review_count | 리뷰 수집기 `RatingTypeTotalReviewsCount` | ✅ | 글이 있는 리뷰 수(1,014 중 131) |
| rating_histogram | junglee `starsBreakdown` | ✅ | 비율(0.86 = 86%) |
| ai_review_summary | junglee `aiReviewsSummary.text`, 리뷰 수집기 `CustomersSay` | ✅ | 두 곳의 문장이 같았다(Batiste, Death Wish) |
| aspect_tags | 리뷰 수집기 `ReviewAspects` | ✅ | 긍정·부정 수 포함 |
| sales_signal | junglee `monthlyPurchaseVolume`, apt_marble `boughtInPastMonth` | ✅ | 구간값 |
| promo_badges | apt_marble `isAmazonsChoice`, `isBestSeller`, `badge`, `couponText`, `subscribeAndSaveText` | ❓ | Batiste B00OQKOO02의 Amazon's Choice가 junglee에서는 false였다. 첫날 직접 본 화면에는 있었다 |
| availability | junglee `inStockText` | ✅ | |
| seller | junglee `seller.name` | ✅ | Batiste B00OQKOO02의 "Deals 2 Grab"이 직접 본 값과 같았다 |
| url | `https://www.amazon.com/dp/<ASIN>` | ✅ | 대조용 |
| context | junglee `locationText` | ✅ | 수집기가 배송지를 실행마다 다르게 잡는다(Nashville 37217, Dallas 75270) |
| collected_at, run_id | 각 수집기의 실행 ID와 시각 | | 모든 행 공통 |

### 리뷰 행 attribute (확정. `attribute-candidates.md` 3-2절)
| attribute | Apify 필드 | 확인 | 비고 |
|---|---|---|---|
| review_id | `ReviewId` | ✅ | 키 |
| product_id | `ASIN` | ✅ | 상품 행과 연결 |
| rank | 받은 순서 1~10 | ✅ | Top reviews 순서. 로그인 화면 순서와 일치했다 |
| ★ rating | `ReviewScore` | ✅ | |
| ★ title | `ReviewTitle` | ✅ | |
| ★ body | `ReviewContent` | ✅ | 원문 그대로. 강조 표시가 있으면 지운다 |
| review_date | `ReviewDate` | ✅ | YYYY-MM-DD |
| review_country | `ReviewCountry` | ✅ | |
| verified_purchase | `Verified` | ✅ | |
| helpful_votes | `HelpfulVotes` | ✅ | 시점별 값 |
| reviewed_variant | `Variant`, `VariantASIN` | ✅ | 변형이 있는 상품에서만 채워진다(Death Wish ✅, Batiste는 빈 값) |
| image_count | `Images`의 개수 | ✅ | 사진 주소는 저장하지 않는다 |
| review_url | `ReviewUrl` | ✅ | 대조용. 로그인해야 열린다(4-4절) |
| source_page_url | `PageUrl` | ✅ | 어느 정렬, 어느 쪽에서 왔는지 |
| collected_via | 고정값 `apify:delicious_zebu/amazon-reviews-scraper-with-advanced-filters` | | 출처 표시 |
| collected_at, run_id | 수집기 | | |

- 저장하지 않는 것: 리뷰어 이름, 프로필 주소, 리뷰어 ID(빈 값으로 받는다), 리뷰 사진 주소, Apify가 행마다 반복해서 주는 상품 단위 값(제품 페이지 값을 쓴다).

## 13. 상품 정보 Apify 시험 (2026-11-10, 4개 수집기)
사용자가 상품 정보(순위, 가격, 평점)도 Apify로 받기로 했다. 그래서 수집기 4개를 시험했다. 실행은 모두 사용자가 이 스레드에서 직접 승인했다.

**결론:** 검색은 `apt_marble/amazon-search-results-scraper`, 상세는 `junglee/Amazon-crawler`로 한다. 둘 다 결과가 왔고, 직접 본 값과 일치했다. 첫 시험의 두 수집기는 결과 0건이었다.

### 첫 시험 (08:16 UTC, 실패)

후보 비교(Apify API의 수집기 정보와 README에서 읽음, 무료):

| 수집기 | 단가(무료 요금제) | 맞는 점 | 빠진 점 |
|---|---|---|---|
| `amazon-scraper/amazon-search-scraper` | 결과 1건 $0.0015, 시작 $0.0005, 배송지 지정 시 검색어당 $0.015 | `rh` 필터가 붙은 검색 주소를 그대로 받는다. 검색 위치 `position`과 광고 여부 `sponsored`를 준다 | 판매 순위, 정확한 평점 수, 변형 목록이 없다 |
| `delicious_zebu/amazon-product-details-scraper` | 결과 1건 $0.0025, 시작 $0.00005 | ASIN 목록을 받는다. 판매 순위, 평점 수, 별점 분포, 모든 변형(ASIN과 속성), 판매자, "Customers say" 항목별 긍정·부정 수를 준다. README에 "no login"이라고 적혀 있다 | 부모 ASIN 필드는 문서에 없다(변형 목록으로 대신할 수 있다 ❓) |
| `delicious_zebu/amazon-product-data-scraper` | 결과 1건 $0.0025 | 검색 주소와 상세를 한 번에 받는다 | 검색 위치와 광고 여부가 문서에 없다. 그래서 고르지 않았다 |
| `junglee/Amazon-crawler` | 결과 1건 $0.005, 배송지 지정 $0.06 | 가장 많이 쓰인다(최근 30일 사용자 3,566명) | 검색 위치와 광고 여부가 문서에 없다. 이 수집기에는 CAPTCHA 풀이 옵션(`useCaptchaSolver`)이 있다 |

실행 결과 ✅:

| 실행 | 입력 | 상태 | 결과 | 차감 |
|---|---|---|---|---|
| 검색 `ATUNHkiAjHrPm72Zx` | `https://www.amazon.com/s?k=batiste&rh=p_123%3A233425`, 20칸 | SUCCEEDED | **0건.** 로그: "Captcha challenge detected"(`MachineVerificationError`)가 두 번 나왔고, 세션을 바꿔 다시 시도한 뒤 검색을 포기했다 | $0.0005 |
| 상세 `uhQqd5Ryr25bc8dRo` | B006CQ1ZHI, B08VFVSBXM, B00OQKOO02 | SUCCEEDED | **0건.** 로그: "Failed to initialize session for website=amazon.com, deliverTo=US". 막힌 이유는 로그에 없다 ❓ | $0.00005 |

- 두 실행 모두 상태는 SUCCEEDED인데 결과가 0건이었다. 실행 상태만 보고 성공으로 판정하면 안 된다. 결과 건수를 함께 확인해야 한다.
- CAPTCHA가 나왔으므로 규칙대로 재시도하지 않고 멈췄다.
- 차감 합계 $0.00055. 시험 누계는 약 $0.86이다(남은 시험 예산 약 $0.14).
- 같은 날 직접 짠 코드(로그아웃 Chrome, 미국 IP, 요청 간격 4초 이상)로는 페이지 21회 동안 CAPTCHA가 한 번도 나오지 않았다(2절). 같은 Batiste 필터 주소를 08:05 UTC에 직접 열었을 때도 60칸이 정상으로 나왔다.
- 이번 실패가 일시적인 것인지, 이 수집기들이 늘 그런지는 모른다 ❓. 최근 30일 실행 기록은 검색 수집기가 성공 1,397회·실패 5회, 상세 수집기가 성공 25,944회·실패 1회였다. 다만 이번처럼 결과 0건이어도 성공으로 집계될 수 있다.
- 원본: `samples/apify/failed_search_ATUNHkiAjHrPm72Zx.json`, `failed_details_uhQqd5Ryr25bc8dRo.json`(입력, 실행 요약, 로그 줄).

### 검색: `apt_marble/amazon-search-results-scraper` (08:24 UTC) ✅
- 사용자가 제안한 수집기다. 최근 30일 사용자 637명, 실행 성공 4,656회, 실패 67회. 사용자 평가는 아직 없다. 단가는 결과 1건 $0.001이고 시작 요금이 없다. 상한 최소값도 없다.
- 입력은 검색어뿐이다(`keywords`). 검색 주소를 받지 않아서 브랜드 필터(`rh=p_123`)를 쓸 수 없다 ✅. 그래서 "상위 상품"을 브랜드명 검색 + 브랜드 줄 거르기로 바꿨다(10절 2번).
- 실행: run `1N8bni7NIcpBFHH6g`, 검색어 "living proof", 20건, 6.6초. 로그에 "0 challenged"(CAPTCHA 없음)가 찍혔다. **차감 $0.02** ✅.
- 주는 값 ✅: `position`(광고 포함 위치), `organicPosition`(광고 뺀 위치), `isSponsored`, `asin`, `title`, `price`, `listPrice`, `rating`, `ratingsCount`, `boughtInPastMonth`, `isAmazonsChoice`, `isBestSeller`, `brand`(브랜드 줄), 카드의 접근성 라벨 원문.
- 대조(08:05 UTC에 로그아웃 Chrome으로 직접 연 같은 검색 60칸과 비교):
  - 가격, 별점, 한 달 구매량: 수집기가 준 20건이 모두 직접 본 60칸 안에 있었고, 20건 모두 세 값이 같았다 ✅. 예: B0170GOCVO는 $33, 4.3, 8K+.
  - **평점 수는 정확한 정수다** ✅. 카드의 접근성 라벨("1,516 ratings")에서 읽는다. 직접 본 화면은 `(14.8K)`처럼 줄여 보여 줬다. B0170GOCVO의 14,811은 첫날 베스트셀러 목록의 14,812와 1 차이다.
  - 같은 평점 수를 가진 상품이 있다. B0BQ3YFRC5와 B0170GOCVO(둘 다 14,811), B0DB3M58J9와 B0DS6KDFS3(둘 다 1,046), B0DB3JCCHH와 B0DS6KMSS9(둘 다 705)다 ✅. 용량·묶음 변형으로 보인다(12절 1차 묶기에 쓴다).
  - **광고가 한 칸도 없었다.** 20칸 모두 `isSponsored: false`였다. 직접 본 화면은 상위 20칸 중 10칸이 광고였다. 수집기가 광고 없는 화면을 받았는지, 광고 표시를 놓쳤는지는 모른다 ❓. 실제 수집에서는 `excludeSponsored: true`로 둔다.
  - **순서가 조금 다르다.** 1~2위는 같았다. 20건 중 18건은 직접 본 화면의 일반 결과 22위 안에 있었다. 두 건은 크게 달랐다: B088WQHFR1(수집기 3위, 직접 본 화면 38위), B0DS6HF3QY(7위, 44위). 20분 차이와 접속 위치 차이 때문으로 보인다 ❓. 검색 위치는 세션마다 달라지는 값이므로 수집 시각과 함께 저장하고, 다른 사람이 다시 돌리면 순서가 달라질 수 있다고 notes에 적는다.
- 원본: `samples/apify/dataset_apt_marble_living_proof_20.json`(추적 속성 `tracking`은 뺐다), `run_apt_marble_1N8bni7NIcpBFHH6g.json`.

### 상세: `junglee/Amazon-crawler` (08:27 UTC) ✅
- 최근 30일 사용자 3,566명, 실행 성공 924,709회, 실패 1,856회, 사용자 평점 4.16(58건). 단가는 결과 1건 $0.005다. 배송지를 지정하면 $0.06이 추가되는데, 지정하지 않았다. 이 수집기에는 CAPTCHA 풀이 옵션(`useCaptchaSolver`)이 있다. 규칙에 따라 끄고(`false`) 돌렸다.
- 실행: run `viC6DyJHAGhoqVvOf`, 상품 주소 3개, 49초. "3 succeeded, 0 failed". **차감 $0.015** ✅.
- 대조(08:05 UTC에 직접 연 제품 페이지와 비교):

| 값 | Death Wish Dark Roast B006CQ1ZHI | Medium Roast B08VFVSBXM | Batiste B00OQKOO02 |
|---|---|---|---|
| 가격 | $18.47 ✅ | $17.48 ✅ | $28.80 ✅ |
| 평점 수 `reviewsCount` | 48,586 ✅ | 3,357 ✅ | 1,014 ✅ |
| 판매 순위 `bestsellerRanks` | #742 Grocery, #15 Ground Coffee ✅ | 같은 값 ✅ | #38,058 Beauty(직접 본 값 #38,059, 22분 차이), #150 Dry Shampoos ✅ |
| 별점 분포 `starsBreakdown` | 82/10/5/1/2 ✅ | 78/11/6/2/3 | 86/9/3/1/1 ✅ |
| 판매자 `seller.name` | Death Wish Coffee Co. ✅ | Death Wish Coffee Co. | Deals 2 Grab ✅ |
| 변형 `variantAttributes` | Dark Roast, 1 Pound (Pack of 1) | Medium Roast, 1 Pound (Pack of 1) | 없음 |
| 변형 묶음 `variantAsins` | 41개(두 맛이 같은 목록) | 41개 | 0개 |

- 부모 ASIN 필드는 없다(`parentAsin` 없음) ✅. 대신 `variantAsins`가 같은 묶음 전체를 준다. Dark Roast와 Medium Roast의 목록이 같다. 그래서 묶음은 `variantAsins`, 같은 상품 판정은 여기에 평점 수를 더해서 한다(12절 2차 묶기).
- `aiReviewsSummary.text`는 제품 페이지의 "Customers say" 문단과 같았다 ✅. `monthlyPurchaseVolume`("5K+ bought in past month")도 온다 ✅.
- `isAmazonChoice`는 세 상품 모두 false였다. 첫날 직접 본 Batiste 제품 페이지에는 Amazon's Choice가 있었다. 그 사이 바뀌었는지, 수집기가 놓쳤는지는 모른다 ❓.
- 배송지는 수집기가 상품마다 다르게 잡았다(Nashville 37217, Dallas 75270) ✅. 이번 3건의 가격은 직접 본 값(Miami 33166 기준)과 같았다. 지역에 따라 가격이 달라지는지는 확인하지 않았다 ❓.
- 원본: `samples/apify/dataset_junglee_3asins.json`(긴 설명, A+ 콘텐츠, 이미지 목록은 뺐다), `run_junglee_viC6DyJHAGhoqVvOf.json`.

### 시험 차감 합계 (이 소스)
- 리뷰 2회 $0.24 + 첫 상품 시험 $0.00055 + apt_marble $0.02 + junglee $0.015 = **$0.276**. 메인 스레드가 앞서 쓴 $0.62를 더한 누계는 약 **$0.90**이다.

## samples/
| 파일 | 내용 |
|---|---|
| `search_batiste_dry_shampoo.json` | 검색 카드 60개 추출 결과 (광고 12) |
| `search_death_wish_coffee.json` | 같은 형식, Death Wish 검색 |
| `search_jinx_dog_food.json` | 같은 형식, Jinx 검색 |
| `search_brand_filter_p_123_238605_deathwish.json` | 브랜드 필터 결과 39개 |
| `bestsellers_dry_shampoos_page1.json` | Dry Shampoos 베스트셀러 1~38위 |
| `product_B00OQKOO02_batiste.json`, `product_B006CQ1ZHI_deathwish.json`, `product_B0F5LZXCDH_jinx.json` | 제품 페이지 추출 결과 (로그아웃 상태) |
| `reviews_logged_in_sample.json` | 로그인 상태의 리뷰 구조 (이름 없음, 본문은 첫 문장·길이만) |
| `apify/input_B00OQKOO02_20.json`, `apify/dataset_B00OQKOO02_20.json`, `apify/run_uhEq1LM2ZFcZxDcjZ.json` | Apify 리뷰 수집기 1회째의 입력, 결과 20건(리뷰어 이름·프로필·ID는 빈 값으로 받음), 실행 기록 요약(계정 ID와 데이터셋 외 저장소 ID를 뺌) |
| `apify/input_2asins_5each.json`, `apify/dataset_2asins_5each.json`, `apify/run_NsOurP6dBZOELcKMv.json` | 2회째: 두 상품 × 5건 |
| `apify/failed_search_ATUNHkiAjHrPm72Zx.json`, `apify/failed_details_uhQqd5Ryr25bc8dRo.json` | 상품 정보 수집기 첫 시험 2건(결과 0건): 입력, 실행 요약, 로그 줄(13절) |
| `apify/dataset_apt_marble_living_proof_20.json`, `apify/run_apt_marble_1N8bni7NIcpBFHH6g.json` | 검색 수집기 시험: "living proof" 20건 |
| `apify/dataset_junglee_3asins.json`, `apify/run_junglee_viC6DyJHAGhoqVvOf.json` | 상세 수집기 시험: 상품 3개 |
| `check2_products_parent_asin.json` | 구현 전 확인: 제품 3건의 부모 ASIN, 평점 수, 가격, 판매 순위 추출값 |
| `check2_s_living_proof.json`, `check2_s_living_proof_filter_254796.json`, `check2_s_batiste_filter_233425.json` | 구현 전 확인: 검색 3건의 카드 60칸(위치, ASIN, 광고 여부, 가격, 평점 줄), 결과 수 문구, Brand 필터 링크 |
| `check2_review_permalink_logged_out.json` | 구현 전 확인: 리뷰 고유 주소가 로그인 페이지로 넘어간 기록 |
| `html_fragments/` | 페이지 종류별로 잘라낸 HTML 조각 14개 (카드 2, 베스트셀러 칸 1, 제품 영역 11). 스크립트·스타일·`svg`를 지웠고, 링크의 추적 쿼리와 토큰을 제거했다. 전체 페이지는 저장하지 않았다 |

주의:
- `product_*.json`에서 `coupon`은 null이고, `buybox_ships_sold`는 첫 줄만 담았다(Batiste의 "Sold by"는 본문 텍스트에서 확인했다).
- `product_*.json`의 `list_price`는 잘못 추출된 단가 값이다(10-1절 8번).
- `html_fragments/product_*_customer-reviews_feature_div.html`은 로그아웃 상태 HTML이며 40KB에서 잘랐다.
- 나머지 원본 전체 페이지는 임시 폴더에만 두었고 저장소에 넣지 않았다.
