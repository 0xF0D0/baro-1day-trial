# 소스 9: TikTok Shop

- 확인일: 2026-11-10 (미국 IP, 화면이 뜨는 Chrome, 로그인 없음). 같은 날 Apify 수집기 시험 1회.
- 확인 대상: 직접 접근은 `shop/s/death-wish-coffee` 1건, `shop.tiktok.com` 1건이고 두 곳 모두 퍼즐에서 멈췄다. Apify 시험은 검색어 `death wish coffee`로 상품 10건이다.
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정, 문서에서 읽음, 또는 미확인
- 요약: **직접 수집은 퍼즐로 막혀 있다.** Apify 수집기 `lurkapi/tiktok-shop-scraper` 시험(상품 10건, 0.01995달러)에서는 상품, 가격, 판매 수, 샵 정보가 왔다(11절). **다만 이 값들을 실제 TikTok Shop 화면과 대조하지는 못했다.** 우리 쪽에서는 퍼즐 때문에 화면을 열 수 없다.

## 1. 이 소스가 주는 것 (브리프)
"리스팅, 가격, 판매 수". 직접 수집으로는 리스팅을 한 건도 보지 못했다. 실제 응답으로 본 필드는 11절(Apify 시험)에만 있다.

## 2. 접근 방법과 막힌 곳
| 시도 | 결과 |
|---|---|
| `https://www.tiktok.com/shop/s/death-wish-coffee` | HTTP 200, 주소 유지. 한국 IP 때의 `not_supported_region` 리디렉션은 **없었다** ✅. 화면 글자: "Verify to continue: Drag the puzzle piece into place" ✅. 페이지가 부른 리스팅 API `/api/shop/brandy_desktop/death-wish-coffee/page_data`는 본문 `{"code":10000}`만 돌려줬다 ✅ |
| `https://shop.tiktok.com/` | `https://shop.tiktok.com/us`로 이동. 같은 퍼즐 "Verify to continue: Drag the puzzle piece into place" ✅. 다른 내용 없음 |

- 퍼즐은 `api-verification.tiktokshops.us`에서 불러온다 ✅. 규칙에 따라 **풀지도, 끌지도 않고 즉시 멈췄다.** 이 경로를 우회하는 시도는 하지 않았다.
- `batiste dry shampoo` 검색은 **시도하지 않았다.** 같은 `shop/s/` 경로에서 퍼즐이 떴기 때문이다.
- 로그아웃 상태에서 상품 상세가 열리는지는 모른다 ❓. (소스 8의 TikTok 해시태그 페이지 상단에는 "TikTok Shop is now available on web!" 배너가 있었다 ✅.)
- 증거: `samples/shop_search_puzzle.png`, `shop_root_puzzle.png`, `shop_search_text_and_api.txt`.

## 3. 브랜드의 TikTok Shop 존재 여부 (간접 단서)
다섯 브랜드 프로필(소스 8에서 열었다)의 `ttSeller` 값이다. 이 값이 **TikTok Shop 판매자 계정 표시**로 보이지만 의미는 확정하지 못했다 ❓.

| 브랜드 | 핸들 | `ttSeller` | 프로필 `commerceUserInfo.category` |
|---|---|---|---|
| Death Wish Coffee | `@deathwishcoffee` | true ✅ | Shopping & Retail |
| Living Proof | `@livingproofinc` | true ✅ | Shopping & Retail |
| Black Rifle Coffee | `@blackriflecoffee` | true ✅ | Shopping & Retail |
| Batiste | `@batiste` | false ✅ | Others |
| Jinx | `@jinx` | false ✅ | Others |

- Death Wish Coffee는 Apify 시험에서 같은 이름의 샵이 나왔고, 그 샵의 팔로워 수가 프로필 팔로워 수와 거의 같았다(11절). `ttSeller: true`가 "샵이 있다"는 뜻이라는 해석과 맞는다. 나머지 네 브랜드는 확인하지 않았다 ❓.
- Jinx 프로필 소개글은 Walmart, Chewy, Amazon, PetSmart, Publix에서 판다고 적혀 있다 ✅. TikTok Shop은 언급이 없다.
- Death Wish Coffee가 리포스트한 크리에이터 영상 하나의 캡션에는 "Shop now on Death Wish Coffee's website"라는 문구가 있다 ✅.

## 4. 원본 구조
**직접 수집한 원본 없음.** 목록 API는 `/api/shop/brandy_desktop/<검색어 슬러그>/page_data`로 보이고 ✅, 퍼즐 통과 전에는 `{"code":10000}`만 온다 ✅. Apify 응답은 수집기가 가공한 형태이고 TikTok 원본 구조가 아니다.

## 5. 집중해서 볼 것과 원본의 대응
| 과제가 요구한 것 | 직접 수집 | Apify 시험 응답 (10건 중 값이 있는 건수) |
|---|---|---|
| 리스팅(제목, 주소) | ❌ 못 봄 | `productId`, `title`, `productUrl` ✅ 10/10 |
| 가격 | ❌ | `currentPrice`, `currency`, `priceDisplay` ✅ 10/10. `originalPrice`는 1/10 |
| 판매 수 | ❌ | `soldCount` ✅ 10/10 (값 0~28) |
| 평점, 리뷰 수 | ❌ | `rating`, `reviewCount` ✅ 10/10 (리뷰가 없으면 둘 다 0) |
| 샵 이름/ID | ❌ | `sellerId`, `sellerName`, `sellerUrl`, `sellerSold`, `sellerProductCount` ✅ 10/10 |
| 공식 샵 여부 | ❌ | `sellerIsOfficial`이 오지만 10건 모두 false라 쓸 수 없다 |
| 검색 순위 | ❌ | `rank` ✅ 10/10 |
| 수집 시각 | ❌ | `scrapeTimestamp` ✅ 10/10 |

## 6. 지금 파는 상품의 판정
직접 판정할 수 없다. Apify 응답에서는 `status: "Success"`인 행을 판매 중으로 볼 수 있을 것이다 ❓. 설명서는 내려간 상품이 `status`에 사유와 함께 표시되고 과금되지 않는다고 적는다 ❓. 이번 10건은 모두 `Success`였다 ✅.

## 7. 항목 식별과 재실행
- 고유 키: `productId`(19자리 숫자) ✅. 샵은 `sellerId`(19자리 숫자) ✅.
- 대조용 주소: 응답의 `productUrl`은 `https://www.tiktok.com/shop/pdp/_/<productId>` 형태로 온다 ✅. 슬러그 자리가 `_`다. 이 주소가 실제로 열리는지는 **확인하지 못했다** ❓.
- 검색어로 모으면 상위 N개가 실행마다 달라질 수 있다 ❓. 사라진 항목을 ended로 표시하려면 샵 ID로 샵 전체를 받는 쪽이 맞다(수집기가 `shopIds` 입력을 받는다 ✅, 시험은 안 함).

## 8. 이 소스에서 얻을 수 없는 것
- 직접 수집: 전부.
- Apify 응답에서도 비어 있던 것(10건 모두 null): 상품 설명, 옵션별 가격·옵션명·재고, 상세 속성, 출고지, 총재고, 사업자명, 할인율.
- 신뢰할 수 있는 공식 샵 표시와 상품 브랜드명(11절).

## 9. 이걸로 볼 수 있는 것
- 브랜드 이름으로 검색했을 때 **누가 파는지**: Death Wish Coffee는 상위 10건 중 4건이 브랜드 이름의 샵, 6건이 재판매 샵 4곳이었다 ✅(응답 값).
- 브랜드 샵의 규모: 상품 23개, 샵 전체 판매 301 ✅(응답 값, 대조 못 함).
- 상품별 가격과 판매 수 ✅(응답 값, 대조 못 함).
- 판매자 표시(`ttSeller`)는 세 브랜드가 참, Batiste와 Jinx는 거짓 ✅.

## 10. 정해야 할 것
1. **대조 없이 테이블에 넣을지.** 응답 값은 왔지만 실제 화면과 맞는지 모른다. 사용자가 자기 Chrome에서 퍼즐을 직접 풀고 2~3건을 눈으로 대조하면 판단할 수 있다. 대조 없이 넣으려면 "공급자가 준 값이고 직접 대조하지 못했다"는 표시가 필요하다.
2. **수집 단위.** 검색어(브랜드 이름)로 상위 N개를 받을지, 브랜드 샵 ID로 샵 전체를 받을지, 둘 다 할지. 재판매 샵의 상품을 포함할지.
3. **브랜드별 샵 ID.** Death Wish Coffee는 `7495749272480024998`로 보인다. 나머지 네 브랜드는 검색 시험을 해야 안다.
4. **판매 수의 정밀도.** 이번 값은 모두 28 이하라 큰 값이 반올림되는지 알 수 없다. 많이 팔린 상품으로 한 번 더 시험할지.
5. **직접 수집.** 로그인이나 퍼즐 우회는 하지 않는다. 직접 수집은 "could not look"으로 남는다. 이 소스는 "유료 서비스 없이 수집"한 소스로 셀 수 없다.

이전에 문서로만 읽은 다른 공급자(가입/호출 안 함 ❓): Bright Data는 1,000건당 1.5달러에 `url`, `title`, `initial_price`, `final_price` 등을 준다고 적혀 있었고 판매 수 필드는 확인하지 못했다. 유료 경로는 Apify 한 곳으로 정해졌다.

## 11. Apify 시험 (2026-11-10)
수집기는 `lurkapi/tiktok-shop-scraper`다. 이 절의 ✅는 Apify API의 메타데이터나 실제 실행 응답에서 본 것이고, ❓는 수집기 설명서에만 적혀 있거나 확인하지 못한 것이다.

### 수집기와 단가
- 빌드 0.0.34(2026-10-26) ✅. 누적 사용자 91명, 최근 30일 사용자 17명 ✅. 최근 30일 실행 5,016건 중 성공 4,977건, 시간 초과 39건 ✅. 사용자 수가 적어서 결과를 그대로 믿지 않는다.
- 건당 과금이다 ✅. 무료 요금제 단가: 미국 상품 1개 0.00199달러, 시작 1회 0.00005달러 ✅. 부가 옵션: 해시태그 상품 0.005달러, 크리에이터 수 0.02달러, 6번째부터의 리뷰 0.002달러 ✅.
- 입력 종류: 검색어, 상품/샵 주소, 상품 ID, 샵 ID, 카테고리, 해시태그 ✅. 샵 단위 수집은 숫자 샵 ID가 있어야 하고 `@핸들/shop` 주소는 받지 않는다 ✅.

### 실행 내역
- 입력(`samples/apify/run_input.json`): 검색어 `death wish coffee`, 미국, 정렬 기본값, 상품 10개, 부가 옵션 3개 모두 끔. 실행 상한 `maxTotalChargeUsd=0.05`.
- 실행 ID `EXHk3uNv40Lsip1gL`, 2026-11-10T07:09:47Z 시작, **21.4초**, 상태 `SUCCEEDED` ✅. 재실행 없음.
- 우리 쪽 요청 수: 실행 시작 1회, 결과 받기 1회.
- **차감액: 0.01995달러** ✅ (상품 10건 × 0.00199 + 시작 1회 0.00005, 실행 기록의 `usageTotalUsd`).
- **레코드 1,000개당 약 1.99달러** ✅.

### 응답 10건 (`samples/apify/search_death_wish_coffee_items.json`)
| 순위 | 제목(앞부분) | 가격(USD) | 판매 수 | 샵 |
|---|---|---|---|---|
| 1 | Death Wish Coffee, Dark Roast, Instant Coffee, 300mg Natural Caffeine, (8) Single Serve Packets Per Box | 51.99 | 28 | Death Wish Coffee |
| 2 | Power Surge Ground Bundle | 52.99 | 0 | Death Wish Coffee |
| 3 | Call of the Wild Mug | 43.00 | 1 | Death Wish Coffee |
| 4 | Fight or Flight Sampler Kit | 49.00 | 0 | Death Wish Coffee |
| 5 | Death Wish Coffee, Organic and Fair Trade, Dark Roast, Ground… | 18.78 | 0 | Shine Nest |
| 6 | Death Wish Coffee, Organic and Fair Trade, Dark Roast, Medium… | 27.17 | 0 | Love Cosmetic Shop |
| 7 | Death Wish Coffee, Valhalla Java Odinforce Blend - Whole Bean… | 11.40 (정가 25.38) | 1 | Salus University |
| 8 | Death Wish Coffee, Organic and Fair Trade Medium Roast Ground… | 41.00 | 2 | AurumLine |
| 9 | Death Wish Coffee, Organic and Fair Trade, Espresso Roast, Ground… | 26.50 | 0 | Love Cosmetic Shop |
| 10 | Death Wish Coffee Instant Dark Roast Coffee Packets… | 20.08 | 5 | Salus University |

- 10건 모두 `status: "Success"`이고, 제목이나 샵 이름으로 볼 때 모두 Death Wish Coffee 상품이다 ✅(응답 값 기준). 4건은 브랜드 이름의 샵, 6건은 재판매 샵 4곳이다.
- 결과 파일의 행 순서는 순위 순이 아니다 ✅. `rank`로 정렬해야 한다.

### 판매 수는 정확한 숫자인가
- `soldCount` 값은 0, 0, 0, 0, 0, 1, 1, 2, 5, 28이다 ✅. 모두 작은 정수라서 **큰 값이 반올림되는지는 판단할 수 없다** ❓.
- 0이 5건이다. 실제로 0개인지, 값이 없어서 0으로 온 것인지 구분할 수 없다 ❓.
- 샵 전체 판매 수(`sellerSold`)는 1, 32, 301, 1470, 7400이다 ✅. 큰 값은 반올림된 것처럼 보인다(내 해석 ❓).
- 설명서는 판매 수가 TikTok이 공개하는 근삿값이라고 적는다 ❓.

### 샵 이름과 공식 샵 여부
- `Death Wish Coffee` 샵: `sellerId` `7495749272480024998`, 상품 23개, 샵 전체 판매 301, 팔로워 371,948, 주소 `https://shop.tiktok.com/us/store/death-wish-coffee/7495749272480024998` ✅(응답 값).
- `sellerIsOfficial`은 이 샵을 포함해 **10건 모두 false**다 ✅. 공식 여부 판정에 쓸 수 없다.
- `brand`는 10건 모두 `sellerName`과 같은 값이다 ✅. 재판매 샵 이름이 브랜드로 들어오므로 브랜드 판정에 쓸 수 없다.
- `businessName`은 10건 모두 null이다 ✅.
- 그래서 "브랜드 샵인가"는 브랜드별로 `sellerId`를 정해 두고 우리가 판정해야 한다.

### 간접 대조 (TikTok Shop 화면이 아닌 다른 소스와)
- 샵 팔로워 371,948 ✅ ↔ 소스 8에서 같은 날 본 `@deathwishcoffee` 프로필 팔로워 371,950 ✅. 이 샵이 브랜드 본계정에 연결된 샵이라는 근거다.
- "Power Surge Ground Bundle" 52.99달러 ✅ ↔ 소스 10의 자사몰 샘플에 같은 이름의 상품이 52.99달러로 있다 ✅.
- 이 두 가지는 샵이 브랜드 것이라는 점을 뒷받침할 뿐이다. **판매 수와 TikTok Shop 화면의 가격은 검증하지 못했다.**

### 대조하지 못한 것
- 실제 TikTok Shop 화면과는 **한 건도 대조하지 못했다.** 퍼즐 때문에 화면을 열 수 없다.
- `productUrl`(`/shop/pdp/_/<productId>`)과 `sellerUrl`이 열리는지 확인하지 못했다 ❓.
- 순위 1번은 "8개입" 제목에 51.99달러다. 묶음 옵션의 가격일 수 있으나 옵션 정보가 비어 있어 확인할 수 없다(내 해석 ❓).

### 비어 있거나 조심할 필드
- `variants`: `skuId`만 있고 가격, 옵션명, 재고가 모두 null ✅. 설명서 예시와 다르다.
- `description`, `specifications`, `shippingOrigin`, `totalStock`, `freeShipping`, `discountPercent`: 10건 모두 null ✅. 정가가 있는 1건에서도 할인율은 null이다. 무료 배송 여부는 `tags`의 "Free shipping"으로만 보인다 ✅.
- `originalPrice`: 1건만 있다 ✅. "Limited time deal" 태그가 3건인데 그중 1건에만 정가가 있다 ✅.
- `rating`: 리뷰가 0건이면 0으로 온다 ✅. 0은 "평점 없음"으로 처리해야 한다.
- `gmvContribution`, `commentRate`: 수집기가 계산한 값이다(가격 × 판매 수, 리뷰 수 ÷ 판매 수와 일치) ✅. TikTok의 값이 아니므로 저장하지 않는다.
- 가격: 설명서는 `currentPrice`가 로그아웃 방문자 기준이고 로그인 화면보다 5~15% 낮을 수 있으며 수시로 바뀐다고 적는다 ❓. 화면과 대조할 때 어긋날 수 있다.

### 개인정보
- 부가 옵션을 껐는데도, 리뷰가 있는 상품 1건에 리뷰 5건이 딸려 왔다 ✅. 리뷰에는 작성자 이름, 작성자 ID, 프로필 사진 주소, 국가가 들어 있었다 ✅.
- 저장한 샘플에서는 `reviews`를 통째로 빼고 건수와 키 이름만 남겼다. 수집기를 만들 때도 `reviews`는 저장하지 않는다.

### 수집기가 어떻게 접근하는가
- 응답의 `inputUrl`은 `https://shop.tiktok.com/us/s?q=death%20wish%20coffee`다 ✅. 우리가 퍼즐을 만난 것과 같은 사이트다.
- 수집기가 퍼즐을 어떻게 지나는지는 공개되어 있지 않다 ❓. 설명서는 카테고리 입력에서 CAPTCHA를 푼다고 적는다 ❓. 카테고리 입력은 쓰지 않았다.
- notes에는 "직접 접근은 퍼즐에서 멈췄고, 유료 서비스가 대신 가져온 값"이라고 적어야 한다.

## samples/
| 파일 | 내용 |
|---|---|
| `shop_search_puzzle.png` | `shop/s/death-wish-coffee`의 퍼즐 화면 |
| `shop_root_puzzle.png` | `shop.tiktok.com/us`의 퍼즐 화면 |
| `shop_search_text_and_api.txt` | 화면 글자와 리스팅 API 응답(`{"code":10000}`) 기록 |
| `apify/actor_pricing_and_stats.json` | Apify API에서 읽은 수집기 단가와 사용 통계 |
| `apify/actor_input_schema.json` | 수집기 입력 형식 |
| `apify/run_input.json` | 시험 입력 |
| `apify/run_summary.json` | 실행 ID, 시각, 소요 시간, 과금 건수, 차감액 |
| `apify/search_death_wish_coffee_items.json` | 응답 10건. `reviews`는 개인정보 때문에 빼고 건수와 키 이름만 남김 |

직접 수집한 리스팅 원본 샘플은 없다.
