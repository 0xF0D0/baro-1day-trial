# 소스 10: 브랜드 자사 사이트 (가격, 오퍼, 가입 이메일)

- 확인일: 2026-11-10 (미국 IP, 화면이 뜨는 Chrome. 이메일은 UTC 05:25 기준)
- 확인 대상: 5개 브랜드 사이트 홈, Shopify 4곳의 `products.json` 전부, 상품 페이지 4곳, Klaviyo 폼 목록 4곳, Batiste where-to-buy 위젯, 가입 메일 3통
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정이거나 미확인

## 1. 이 소스가 주는 것
브랜드가 자기 사이트와 자기 이메일로 내보내는 가격, 오퍼, 환영 메일이다. 행은 세 종류다.
- **가격 행:** 상품(또는 변형) 1개의 그날 가격. Batiste는 사이트에 가격이 없어서 리테일러별 가격으로 대신한다(4-1 참고).
- **오퍼 행:** 홈페이지에 걸린 문구 1개(공지 띠, 배너, 가입 팝업, 푸터 폼, 무료배송 기준 등).
- **이메일 행:** 가입 후 받은 메일 1통.

## 2. 접근 방법

### 가격
| 브랜드 | 플랫폼 | 가져오는 곳 | 상태 |
|---|---|---|---|
| Living Proof | Shopify | `https://www.livingproof.com/products.json?limit=250&page=N` | ✅ 200 JSON (Chrome) |
| Death Wish | Shopify | `https://www.deathwishcoffee.com/products.json?...` | ✅ 200 JSON (Chrome) |
| Jinx | Shopify | `https://www.thinkjinx.com/products.json?...` | ✅ 200 JSON (Chrome) |
| Black Rifle | Shopify | `https://www.blackriflecoffee.com/products.json?...` | ✅ 200 JSON (화면 있는 일반 브라우저) |
| Batiste | ASP.NET, 상점 없음 | where-to-buy 위젯이 부르는 `wtb-api-hub.swaven.com` | ✅ 상품 페이지에서 "SHOP NOW" 누르면 나감 |

- 페이지 크기: `limit`을 안 주면 30개, `limit=250`을 주면 250개가 왔다 ✅. 250 초과는 시험하지 않았다 ❓(Shopify 상한이 250으로 알려져 있다).
- 넘기기: `page=1,2,...`를 올리다가 250개 미만이 오면 끝이다 ✅. Black Rifle은 250 + 197 = 447개였다. 나머지 셋은 한 번에 끝났다(66, 165, 73).
- 사이트마다 상품 목록은 요청 1~2회면 된다.
- 한국 IP는 이번에 시험하지 않았다. 미국 IP였다.
- **Black Rifle은 까다롭다.**
  - curl(일반 User-Agent)은 403 "Attention Required! | Cloudflare" 페이지를 받았다 ✅.
  - Playwright로 띄운 Chrome은 홈이 200으로 열리지만 약 3초 뒤 사이트의 스크립트가 `blackriflecoffee.com/url?q=https://www.google.com/`로 보내서 Google 첫 화면이 된다 ✅(두 번 모두 재현). Cloudflare `cdn-cgi/challenge-platform/scripts/jsd` 스크립트가 같이 돌았다. 원인은 자동화 감지로 보이나 확정은 못 했다 ❓.
  - **판정: 직접 짠 코드로는 막힘(blocked).** 소유자 규칙에 따라 이 경로는 더 시도하지 않았다. 소유자는 유료 경로(Apify)를 골랐고, 시험 결과는 11번에 있다(차단을 넘어 가격이 왔다).
  - 규칙이 오기 전에 Claude 앱 안의 일반 브라우저로 한 번 열어 `products.json`(447개)과 홈 오퍼를 읽었다 ✅. 이 데이터는 그 한 번의 수동 확인이다. 반복 수집이 된다는 뜻이 아니다. 이 경로가 다시 되는지는 확인하지 않았다 ❓.
- 브리프에서 "curl은 429, Chrome은 200"이라던 Death Wish와 Jinx는 이번에 curl을 다시 보내지 않았다 ❓. Chrome으로 200은 확인했다 ✅.

### 오퍼
- 홈페이지를 열어 DOM에서 읽는다. 서버가 처음 주는 HTML에 이미 들어 있는 것과, 스크립트가 나중에 끼우는 것이 섞여 있다(4-2).
- Klaviyo 팝업 정의는 따로 공개 주소로도 받을 수 있다 ✅: `https://static-forms.klaviyo.com/forms/api/v7/<회사ID>/full-forms` (인증 없이 200). 회사 ID는 사이트가 스스로 노출한다: Living Proof `H99sYH`, Death Wish `Q6RhjR`, Black Rifle `XU3JTE`, Jinx `V2u2jn`. 이 목록에는 팝업이 화면에 안 뜬 경우의 문구와 코드(예: `DWC20`)도 들어 있다.

### 이메일
- 시험용 받은편지함에 가입해 둔 메일을 읽는다. Claude 세션의 Gmail 커넥터로 원문을 받아, 가린 .eml로 저장하고 수집기는 그 파일을 읽는다(12번).

## 3. 브랜드 매칭
브랜드마다 사이트가 하나라서 도메인으로 그냥 정해진다.

| 브랜드 | 사이트 | 보낸 사람 도메인 | 주의 |
|---|---|---|---|
| Living Proof | livingproof.com | livingproof.com | |
| Death Wish Coffee | deathwishcoffee.com | deathwishcoffee.com | 머치 상품의 vendor가 `Sportiqe`, `Planet Apparel`(제조사)로 따로 있다 ✅ |
| Black Rifle Coffee | blackriflecoffee.com | blackriflecoffee.com | vendor 철자가 두 가지다: `Black Rifle Coffee Company`와 끝에 공백이 붙은 것 ✅. `BRCC Staging` 상품이 1개 새어 있다 ✅ |
| Jinx | thinkjinx.com | (가입 없음) | `jinx.com`은 다른 회사다 |
| Batiste | batistehair.com | (가입 없음) | Church & Dwight 소유. 위젯 설정에 운영자가 `Batiste`, 계정이 `Church & Dwight`로 나온다 ✅ |

## 4. 원본 구조

### 4-1. 가격

#### Shopify `products.json` (`samples/products_*_trimmed.json`)
최상위는 `{"products": [...]}`이다 ✅. 샘플은 상품 2~3개로 줄였다(변형은 3개까지, 이미지는 첫 주소만, 설명은 200자).

| 키 | 뜻 | 예시 | 상태 |
|---|---|---|---|
| `id` | 상품 ID | `7780999069792` | ✅ |
| `title`, `handle` | 이름, 주소 조각 | `Gothic Serpent 3.0, 12oz, Whole Bean` | ✅ 상품 주소는 `/products/<handle>` |
| `vendor` | 제조/판매자 | `Black Rifle Coffee Company` | ✅ 브랜드 구분용으로 믿으면 안 된다(3번) |
| `product_type` | 분류 | `Coffee`, `Bundle`, `Dog Kibble` | ✅ 비어 있는 상품이 있다(Jinx 18개, Black Rifle 3개) |
| `tags` | 태그 | `["12oz","coffee","subscriber_store"]` | ✅ 행사 표시가 섞여 있다: `flash-sale`, `clearance`, `free-gift-with-purchase`, `GWP_threshold:13` |
| `published_at`, `updated_at` | 공개, 수정 시각 | `2026-11-09T22:11:19-07:00` | ✅ 시차가 상점 현지 시간이다: Living Proof -04:00, Death Wish -05:00, Jinx -08:00, Black Rifle -07:00(또는 -06:00) |
| `options[]` | 옵션 이름과 값 | `Size`, `Format` | ✅ |
| `variants[]` | 변형 | 아래 | ✅ |
| `images[]` | 이미지 | `src`, `width`, `height`, `variant_ids` | ✅ 주소는 `cdn.shopify.com` |
| `body_html` | 설명 HTML | | ✅ |

변형(`variants[]`) 키:
| 키 | 뜻 | 예시 | 상태 |
|---|---|---|---|
| `id` | 변형 ID | `43069582082144` | ✅ |
| `title` | `option1 / option2` | `Whole Bean / 12oz` | ✅ 옵션이 없으면 `Default Title` |
| `sku` | 재고 코드 | `3F-269-12W` | ✅ 비어 있을 수 있다(Black Rifle 135개, Jinx 4개) |
| `price` | 현재 판매가, **문자열** | `"30.00"` | ✅ 달러. 응답에 통화 필드는 없다 ✅ |
| `compare_at_price` | 할인 전 가격, 없으면 `null` | `"131.97"` | ✅ 있으면 할인 중이라고 읽을 수 있다 |
| `available` | 지금 살 수 있나 | `true` | ✅ 재고 수량은 없고 참/거짓만 있다 |
| `grams` | 무게 | `340` | ✅ 값이 0인 변형이 많다(번들) |
| `created_at`, `updated_at` | | | ✅ |
| `featured_image`, `option1~3`, `position`, `product_id`, `requires_shipping`, `taxable` | | | ✅ |

수집한 규모(2026-11-10):
| 브랜드 | 상품 | 변형 | 살 수 있는 변형 | `compare_at_price`가 있는 변형 | 가격 범위 |
|---|---|---|---|---|---|
| Living Proof | 66 | 108 | 100 | 13 | $0 (1건, 사은품 추정 ❓) ~ $168 |
| Death Wish | 165 | 450 | 398 | 240 | $5 ~ $149.95 |
| Jinx | 73 | 142 | 113 | 7 | $1 ~ $249 |
| Black Rifle | 447 | 1,837 | 1,066 | 635 | 계산 안 함 |

Black Rifle의 `product_type` 분포: Apparel 214, Gear 143, Coffee 55, Bundle 23, 기타. 커피는 55개뿐이고 대부분이 옷과 장비다 ✅. Death Wish도 커피 38개에 옷 39개 등이다 ✅. 브랜드끼리 가격을 비교하려면 `product_type`으로 커피/제품만 골라야 한다.

#### 상품 하나가 변형 여러 개가 되는 모양
- **크기 변형:** Living Proof `Perfect hair Day™ Style Refresh Mist` 변형 2개(`Size`) ✅.
- **수량 변형(Death Wish):** `Peppermint Mocha Coffee`의 변형이 `1 BAG / 2 BAGS / 5 BAGS`이고 가격이 1399 / 2798 / 6995센트다 ✅. 개당 단가는 13.99로 같고 5개 묶음은 개당 13.99다. 이런 변형은 단가로 나눠야 비교가 된다.
- **옷 변형:** 색 x 사이즈로 최대 36개(Black Rifle), 8개(Death Wish) ✅. 가격은 같은 경우가 많다.
- **번들:** `The Espresso Upgrade`(Black Rifle) 12개 변형. 가격 `125.37`, `compare_at_price` `131.97` ✅.

#### 통화와 지역
- 페이지의 `Shopify.currency.active`는 4곳 모두 `USD`, `Shopify.country`는 `US`였다 ✅(미국 IP).
- 방문자 국가에 따라 달라지는지는 시험하지 못했다 ❓. 미국에서만 열었다. 해외 IP에서 열면 Shopify Markets가 통화와 가격을 바꿀 수 있다 ❓.
- `products.json`은 통화를 알려주지 않는다 ✅. 수집기는 미국 IP에서 돌리고 `USD`를 직접 적어야 한다.

#### 구독 가격
- 세 상품의 `/products/<handle>.js`를 열어 봤다(Black Rifle `gothic-serpent...`, Death Wish `peppermint-mocha-coffee`, Jinx `senior-cage-free-chicken-dog-food`). `selling_plan_groups`가 모두 빈 배열이고 변형의 `selling_plan_allocations`도 비어 있다 ✅. 즉 Shopify 표준 구독 가격은 없다.
- Jinx는 Recharge 스크립트가 있고 상품 페이지에 `subscription-widget--container`가 있지만 텍스트가 비어 있다 ✅. 구독이 걸린 다른 상품이 있는지는 보지 않았다 ❓.
- Death Wish는 홈 배너에 "SUBSCRIBE AND SAVE 30% OFF YOUR ORDER"가 있고 `/pages/subscription`이 있다 ✅(링크만). 그 페이지의 구독 가격은 열어 보지 않았다 ❓. Black Rifle은 `subscriber_store` 태그와 "Subscribe" 메뉴가 있다 ✅(구독 가격은 확인 못 함 ❓). Living Proof는 구독 여부를 보지 않았다 ❓.
- 정리하면 구독 할인은 가격 표에 안 잡히고, 오퍼 문구(4-2)로만 잡힌다.

#### Jinx: 자기 사이트에서 파는가
- **판다.** 상품 페이지에 `form[action*="/cart/add"]`가 있고 버튼이 `Add to cart`다 ✅. 변형 142개 중 113개가 `available: true`, 상품 73개 중 56개가 하나 이상 구매 가능이다 ✅.
- 그런데 홈은 "Shop Now at Walmart"(`walmart.com/brand/jinx/cat-food/20035686` 링크 ✅)와 공지 띠 "Get Jinx shipped fast from Walmart, Chewy, Amazon or pick up in store! Explore Now" ✅를 앞세운다. 자기 사이트 가격은 그대로 있지만 브랜드가 밀고 있는 곳은 리테일러다.
- 자기 사이트 가격이 Walmart/Chewy보다 비싼지는 비교하지 않았다 ❓.

#### Batiste: 사이트에는 가격이 없다. 위젯 응답이 대신한다
- 사이트에서 가격 문자열이 보이지 않는다 ✅(상품 페이지에서 `$` 숫자 요소 없음, JSON-LD 없음).
- 상품 페이지는 "SHOP NOW" 버튼(`a.swn-awe-btn-enabled`, `id=SHOP_NOW_<제품>`, `data-mm-ids`에 EAN 목록)을 만들고 누르면 MikMak(Swaven) 팝업이 열린다 ✅. 팝업 화면은 Target, Walmart, CVS, Walgreens, Ulta의 **BUY** 버튼만 보여주고 가격은 안 보여준다 ✅.
- **그런데 응답에는 가격이 있다.** 설정 `conf` 응답에 `"displayprices": false`가 있다 ✅. 그래도 `availabilities` 응답의 매장 행마다 `pr`(가격, 숫자), `currency` `USD`, `av` `true`가 온다 ✅. 요약 필드도 있다: `minp` 8.99, `maxp` 13.49, `avgp` 11.2 ✅.

위젯이 부르는 주소(상품 페이지 `.../products/dry-shampoo/fragrance-bare`):
| 순서 | 주소 | 담긴 것 |
|---|---|---|
| 1 | `wtb-api-hub.swaven.com/cache/tag/v1/app/679a82f096a96e0f672b1fc9?&h=<도메인 base64>` | 앱 설정: 국가 `US` |
| 2 | `.../cache/tag/v1/app/<앱ID>/page/<경로>` | 페이지 키만 `{"appId","key"}` |
| 3 | `.../cache/wtb/v2/api/conf/679a839e96a96e0f672b1fcc` | 위젯 설정: 통화 `USD`, `displayprices:false`, 리테일러 우선순위 번호 목록 |
| 4 | `.../wtb/v2/api/search/products/<EAN4개>?wtbid=...&lang=en&av=false&country=` | 제품 4개(EAN, 이름, 이미지) |
| 5 | `.../wtb/v2/api/search/availabilities/<EAN>?wtbid=...&lang=en&country=US&nextEndpointV2=true&applyTiedHouseLaw=true` | 리테일러/매장별 가격과 재고 |

4번 응답의 제품 4개 EAN은 `5010724526705`(3.81 oz), `5010724527146`, `5010724538333`(7.62 oz), `5010724532133`(미니)다 ✅. 5번은 첫 EAN 하나만 불렀다(팝업이 처음 고른 제품).

5번 응답(`samples/batiste_wtb_availabilities_trimmed.json`, 행 7개 중 3개만 저장):
| 키 | 뜻 | 예시 |
|---|---|---|
| `d[]` | 리테일러/매장 행 | 7개 ✅ |
| `d[].rname`, `rid` | 리테일러 이름, 번호 | `Target`, `257` ✅ |
| `d[].sid`, `sname` | 매장 ID, 이름 | `257_WEB`(온라인), `257_2259`(`Columbia Heights`, 오프라인 매장) ✅ |
| `d[].pr`, `currency` | 가격, 통화 | `8.99`, `USD` ✅ |
| `d[].av` | 재고 있음 | `true` ✅ |
| `d[].carturl` | 장바구니 직행 주소 | `https://www.target.com/occ/p/51006733?afid=mikmak-attach&q=1` (제휴 파라미터 포함) ✅. CVS, Walgreens, Ulta는 `null` ✅ |
| `d[].shd` | 배송(home delivery) 가능 | 온라인 행은 `true` ✅ |
| `loc` | 위치 | 워싱턴 D.C.(`Source: auto`, `IsDefaultLocation: true`) ✅ |

온라인 5곳의 가격: Target 8.99, Walmart 9.68, CVS 10.49, Walgreens 13.49, Ulta 12.99 ✅. 같은 제품이 리테일러마다 8.99~13.49로 다르다. 가까운 Target 매장 2곳은 11.39로 온라인(8.99)보다 높았다 ✅.
- 위치는 IP 기반의 기본값(워싱턴 D.C.)이다 ✅. 다른 도시나 우편번호로 바뀌면 매장 행과 가격이 달라질 것이다 ❓(시험 안 함).
- 이 제품 하나만 봤다 ❓. 제품 목록 전체는 이 위젯에서 얻을 수 없다(8번).
- 가격은 "사이트가 보여주는 값"이 아니라 위젯 API가 내려주는 값이다. 브랜드가 의도적으로 안 보여주는 값(`displayprices:false`)을 가져오는 셈이므로 쓸지는 정해야 한다(10번).

### 4-2. 오퍼
홈페이지 DOM에서 읽는다. 각 오퍼가 서버 HTML에 처음부터 있는지(`raw`), 스크립트가 끼우는지(`script`)는 저장한 원본 HTML을 스크립트 없이 열어 확인했다 ✅. 문구와 선택자와 HTML 조각은 `samples/offers_blackrifle.json`, `samples/offers_homepage_other_brands.json`에 있다.

| 브랜드 | 위치 | 문구(원문) | 선택자 | 출처 |
|---|---|---|---|---|
| Living Proof | 공지 띠 | Easy gifting, exclusive savings. Save up to 33% + get free shipping on limited edition [kits] | `div.announcement__text > p` | raw ✅ |
| Living Proof | 번들 배너 | Choose 4 full-size products and save 15%. | `div.banner-image__heading` | raw ✅ |
| Living Proof | 가입 팝업 | 15% off your first order / Join our email list today for exclusive offers | `div.kl-private-reset-css-*` (Klaviyo 폼 `StXUHd`) | script ✅ |
| Living Proof | 푸터 폼 | Subscribe | `form#NewsletterForm--newsletter_*` (Shopify 기본 폼, POST /contact) | raw ✅ |
| Living Proof | 무료배송 | Spend $50 more for FREE shipping | 장바구니 서랍 `[data-left-to-spend]` | raw ✅ (빈 장바구니 기준 $50이라 기준액이 $50이라고 읽음 ❓) |
| Death Wish | 공지 띠 | BUILD YOUR OWN COFFEE BUNDLE AND SAVE UP TO 15% OFF | `div.announcement-bar > a > p.announcement-bar__message` | raw ✅ |
| Death Wish | 히어로 배너 | SUBSCRIBE AND SAVE 30% OFF YOUR ORDER. Start a coffee subscription to save 30% off your first shipment... | `h2.banner__heading` + `div.banner__text` | raw ✅ |
| Death Wish | 푸터 폼 | STAY BOLD, STAY CAFFEINATED. SIGN UP AND SAVE 20% OFF YOUR FIRST ORDER | `h2.inline-richtext` + `div.klaviyo-form-RpC5ka` | 제목 raw, 폼 본체 script ✅ |
| Death Wish | 팝업(홈에서 12초 안에 안 뜸) | 20% OFF YOUR FIRST ORDER  CODE: DWC20 | Klaviyo 폼 `SyWkJC` | Klaviyo 목록에만 있음 ✅ |
| Black Rifle | 공지 띠 | Free Shipping on orders over $75! | `announcement-bar .swiper-slide` (캐러셀 가능성 ❓) | ✅ DOM |
| Black Rifle | 가입 팝업 | WANT THE LATEST INTEL? Get exclusive deals and drops! [EMAIL ME] | `form.needsclick` (Klaviyo, 쿠키 배너 위) | script ✅ |
| Black Rifle | 번들 카드 | 예: WRAPPED AND LOADED BUNDLE $104.46 (정가 $109.96), FREE PATCH! FIRST RESPONDER BUNDLE $80.96 (정가 $90.96) | `product-carousel product-card` | ✅ DOM |
| Black Rifle | 구독 메뉴 | Every month, you'll get a new exotic roast shipped to your door... Sign up today! | 메뉴 항목(호버 때만 보임) | ✅ DOM |
| Jinx | 공지 띠 | Get Jinx shipped fast from Walmart, Chewy, Amazon or pick up in store! Explore Now | `[class*=announcement]` | ✅ 상품 페이지 DOM |
| Jinx | 히어로 버튼 | Shop Now at Walmart | `a.btn--primary` href walmart.com | raw ✅ |
| Jinx | 무료배송 | Congratulations! Your order qualifies for free shipping | `div.drawer__message[data-free-shipping-limit="65"]` | raw ✅ (기준 $65) |
| Jinx | 문구 | 1% with Every Purchase (개와 보호소에 기부) / 100% money-back guaranteed | `h2.column__heading`, `em.cart__note` | raw ✅ |
| Batiste | 커뮤니티 | Join Batiste Nation / JOIN NOW | `div#footer-signup a.homepage-new-cta` (제3자 사이트로 연결) | raw ✅ |

- **스크립트가 끼우는 것(진짜 브라우저가 필요):** Klaviyo 가입 팝업(Living Proof, Black Rifle), Death Wish 푸터 폼 본체, Batiste의 SHOP NOW 버튼과 팝업. 단순 HTTP 요청으로는 안 보인다.
- **서버 HTML에 처음부터 있는 것:** 공지 띠, 배너, 번들 문구, 무료배송 기준(Living Proof, Death Wish, Jinx), 푸터 폼 제목. 이것들은 브라우저 없이도 읽힌다(Black Rifle은 raw HTML을 못 받아서 확인 못 함 ❓).
- **Klaviyo 폼 목록(`samples/klaviyo_forms_*.json`)이 가장 단단하다.** 팝업이 안 뜨는 경우에도 문구와 코드를 받을 수 있다. 개수: Living Proof 5개, Death Wish 16개, Black Rifle 16개, Jinx 0개(`enabled:false`) ✅. Black Rifle 목록에는 "Join email & SMS for 20% off your first order plus free shipping on $75+."(`V77uVu`)와 "Join our email list for 20% off your 1st order!"(`XUpvid`)가 있고, 일부는 끝난 행사(`This giveaway has ended.`, `BRCC 2026 SHOT SHOW`)다 ✅. 목록에는 켜진 폼과 꺼진 폼의 구분 필드를 읽지 못했다 ❓(`status` 키 없음). 문구가 있다고 지금 노출 중이라는 뜻은 아니다.
- Living Proof에는 사은품 팝업(`div.gwp-block.gwp-popup`: "Please choose your free gift from the following")과 상품 태그 `GWP_threshold:*`가 있다 ✅. 기준 금액이 무엇인지는 풀지 못했다 ❓.

### 4-3. 이메일
가입한 3곳에서 각각 1통이 왔다(`samples/email_livingproof.json`, `email_deathwish.json`, `email_blackrifle.json`). 받는 사람 주소는 `TRIAL_INBOX`로 바꿨고 수신 취소 링크의 토큰은 지웠다.

| | Living Proof | Death Wish | Black Rifle |
|---|---|---|---|
| 보낸 사람 | `Living Proof <whatsnew@livingproof.com>` | `Death Wish Coffee Co. <hey@deathwishcoffee.com>` | `Black Rifle Coffee Company <brcc@blackriflecoffee.com>` |
| 제목 | Welcome to Living Proof. | START STRONG 🤘 | Buckle up, buttercup. |
| 받은 시각(UTC) | 04:48:29 | 04:47:45 | 04:56:27 |
| 가입 시각(UTC) | 04:47:06 | 04:47:48 | 04:54:53 |
| 가입 후 | 83초 | -3초(가입 기록이 클릭 후에 찍혀 늦다) | 94초 |
| 미리보기(preheader) | Enjoy 15% off. | Here's 20% off your first order | Welcome to America's Coffee 🦅 |
| 할인 | 15%, 코드 `WC-TM5JN7LG`, 첫 구매 | 20%, 코드 `DWC20`, 첫 주문 | 20%, 코드 `BEANS20`, 첫 주문 |
| 유효기간 | 본문에 "Valid through 12-09-2026", 약관에는 "30 days from signup date" | 없음 | 없음 |
| 주 링크 | `livingproof.com/collections/all` (HTML에서는 `ctrk.klclick.com/l/...`로 감쌈) | `deathwishcoffee.com` | `blackriflecoffee.com/discount/beans20/?redirect=/collections/coffee` (할인 자동 적용 주소) |
| 보낸 서비스 | Klaviyo | Klaviyo | Klaviyo |
| 라벨 | 프로모션, 안 읽음 | 프로모션, 안 읽음 | 프로모션, 안 읽음 |

- 모두 ✅ 실제 메일에서 읽었다. 세 메일의 제목, 미리보기, 보낸 사람, 코드, 링크는 커넥터가 돌려준 값이다.
- **Living Proof 코드는 가입자별로 만들어지는 것으로 보인다**(`WC-` + 8자리) ❓. 메일이 한 통뿐이고 Klaviyo 폼 목록에도 코드 종류를 알려 주는 필드가 없어, 형식만 보고 판단했다. 나머지 두 곳은 모두에게 같은 코드로 보인다 ✅(코드가 사이트 팝업 문구와도 같다. `DWC20`은 Klaviyo 폼 목록에도 있다).
- Living Proof 날짜 형식은 `MM-DD-YYYY`(12-09-2026)다 ✅. 가입일 + 29일이라 약관의 "30일"과 하루 어긋난다 ✅(둘 다 본문에 있는 그대로).
- **Black Rifle 첫 메일은 도착했다.** 가입 응답에 확인 문구가 없었지만 94초 뒤에 왔다 ✅. 사이트 폼 문구에 있던 "free shipping on $75+"는 메일에는 없다 ✅.
- 지금까지 메일 수: Living Proof 1, Death Wish 1, Black Rifle 1 (가입 후 약 37분, 37분, 30분 시점인 05:25 UTC). 받은편지함 검색(`from:` 세 도메인)에서 이 3통만 나왔다 ✅. Batiste와 Jinx는 가입하지 않았다.
- 본문은 plain text와 HTML 두 부분이다. 처음 조사 때 `email_*.json` 샘플에는 Living Proof HTML의 구조 요약만 넣었다. 지금은 세 통 모두 HTML 전체가 `samples/eml/`에 있다 ✅(12번).
- Living Proof 메일은 내용 대부분이 이미지(`alt`만 있음)다 ✅. 이미지 속 글자는 기계가 읽지 못한다.
- Black Rifle plain text 샘플은 긴 약관 줄을 줄임표로 줄였다(원문은 커넥터 응답에 있다).

### 4-4. 메일을 행으로 바꾸는 규칙 (2026-11-10, 소유자 승인. 가린 .eml 3통으로 시험)
**판정: 일부만 정규화한다.** 세 통 모두 Klaviyo가 보냈고 plain text 부분도 Klaviyo가 같은 방식으로 만든다. 그래서 헤더와 오퍼는 브랜드가 달라도 같은 규칙으로 뽑힌다. 본문 블록 구성은 브랜드마다 달라서 컬럼으로 나누지 않고 원문으로 둔다.

| 층 | 세 통 비교 | 처리 |
|---|---|---|
| 헤더 | `From`, `Subject`, `Date`, `X-Kmail-Flow`, `X-Kmail-Message`가 세 통 모두 있다 ✅ | 그대로 컬럼 |
| 미리보기(preheader) | 세 통 모두 HTML에서 `<body>` 다음에 오는 첫 `display:none` `div`에 있다. plain text에는 없다 ✅ | 컬럼. 못 찾으면 빈칸 |
| 할인 코드, 할인율 | 아래 정규식으로 세 통 모두 뽑혔다: `BEANS20` 20%, `DWC20` 20%, `WC-TM5JN7LG` 15% ✅ | 컬럼. 못 뽑으면 빈칸으로 두고 "추출 실패"로 표시하며, 추측하지 않는다 |
| 만료일 | Living Proof만 있다(`Valid through 12-09-2026`, `MM-DD-YYYY`) ✅ | 있을 때만 날짜로 |
| 조건 | Black Rifle은 긴 제외 목록, Living Proof는 약관, Death Wish는 없음 ✅ | 원문 텍스트 한 칸 |
| 링크 | plain text에 실제 목적지가 있다 ✅. HTML 링크는 추적 주소라 가렸다(12번) | 링크 목록으로 따로 |
| 본문 블록 구성 | 브랜드마다 다르다 | 정규화하지 않는다. plain text 통째로 |

시험한 정규식(Python, plain text 부분):
- 코드: `(?i:\bcode)\s*:?\s+([A-Z0-9][A-Z0-9-]{3,})\b`. 코드 부분은 대소문자를 구분한다. 그래야 Black Rifle 약관의 "Code not valid"를 코드로 잡지 않는다.
- 할인율: `(\d{1,2})\s*%\s*off` (대소문자 무시)
- 만료일: `valid through (\d{2}-\d{2}-\d{4})` (대소문자 무시)
- 링크 주소: `\]\(((?:https?://)?[^)\s]+)\)`. Living Proof의 소셜 링크는 `www.`로 시작하고 스킴이 없다.

**링크를 읽을 때 주의할 점** ✅
- **`[문구](주소)` 짝으로 읽지 않는다.** Black Rifle 본문에는 `[… | [ SHOP NOW ]](주소)`처럼 대괄호 안에 대괄호가 있다. 짝으로 읽었더니 Black Rifle 자사 링크 12개 중 6개만 잡혔다. 주소만 뽑으면 12개가 다 잡힌다.
- **상품은 주소의 핸들로 판단한다.** Black Rifle의 "Gunship Roast" 링크는 `/products/tactisquatch-roast`로 간다. 링크 문구를 믿으면 상품이 틀린다.
- **Black Rifle 링크는 할인 자동 적용 주소를 거친다.** `/discount/beans20/?redirect=/products/<handle>` 모양이다. 종류와 핸들은 `redirect` 값에서 읽는다.
- 자사 링크 수(주소만 뽑은 경우): Black Rifle 12개(컬렉션 5, 상품 4, 페이지 3), Death Wish 13개(홈 4, 컬렉션 4, 페이지 5), Living Proof 6개(컬렉션 4, 블로그 1, 페이지 1). 메일에서 상품을 직접 거는 곳은 Black Rifle뿐이다.

**메일 행 컬럼(제안)**
| 컬럼 | 출처 |
|---|---|
| 브랜드 | `From` 도메인 |
| `gmail_id` (중복을 거르는 키) | `X-Trial-Gmail-Id` |
| 받은 시각 / 보낸 시각 | `X-Trial-Received-At` / `Date` |
| 가입 후 경과(분) | 받은 시각 − `part1/data/email_signups.json`의 가입 시각. 가입 시각은 클릭보다 늦게 찍혀 Death Wish는 −3초가 나온다(4-3). 분 단위로만 쓴다 |
| 보낸 사람, 제목, 미리보기 | 헤더, HTML의 첫 숨은 `div` |
| 흐름 ID, 메일 ID | `X-Kmail-Flow`, `X-Kmail-Message`. 같은 흐름의 두 번째 메일을 가를 때 쓴다 |
| 할인 코드, 할인율, 만료일 | 위 정규식 |
| 코드 종류 | 공용 / 개별 / 모름. Living Proof는 지금 "모름"이다(4-3 ❓). 개별 코드로 확정되면 표에는 코드 값을 빼고 "개별 코드"라고만 적는 것도 고려한다 |
| 조건 원문 | plain text에서 `*`로 시작하는 약관 줄 |
| 본문 원문 | plain text 전체 |
| 원본 파일 | `samples/eml/<파일명>` |
| 링크 목록 (자식 행 또는 JSON) | 주소, 종류(상품/컬렉션/페이지/블로그/홈/외부), 핸들 |

- 첫날 메일은 브랜드마다 몇 통 되지 않는다. 그래서 컬럼은 이 정도로 두고, 나머지는 원문을 보고 답한다.
- 최종 한 테이블 스키마는 메인 스레드에서 정한다. 이 표는 그때 쓸 재료다.

## 5. 집중해서 볼 것과 원본의 대응

### 5-1. 가격
| 과제가 요구한 것 | 원본에서 얻는 방법 | 상태 |
|---|---|---|
| 상품 가격 | `variants[].price` | ✅ 4개 Shopify 사이트 |
| 정가와 할인 | `compare_at_price` | ✅ 있으면 할인 중. 없으면 `null` |
| 품절 | `variants[].available` | ✅ |
| 새 상품, 변경 | `published_at`, `updated_at` | ✅ 상점 현지 시간대 |
| 구독 가격 | 표준 경로에는 없음 | ❓ 확인한 3개 상품에서 없음 |
| Batiste 가격 | 위젯 `availabilities`의 `pr` | ✅ 단 8번의 한계 있음 |
| 통화/지역 | 응답엔 없음. 미국 IP면 USD | ✅ 미국에서만 확인 |

### 5-2. 오퍼
| 과제가 요구한 것 | 원본에서 얻는 방법 | 상태 |
|---|---|---|
| 공지 띠, 배너 | 홈 DOM 선택자(4-2 표) | ✅ |
| 가입 팝업 | 브라우저에서 DOM, 또는 Klaviyo `full-forms` JSON | ✅ 둘 다 확인 |
| 무료배송 기준 | Jinx `data-free-shipping-limit`(65), Living Proof(50, 읽어서 추정), Black Rifle 공지 띠(75) | ✅ / ❓ |
| 번들 | Black Rifle 홈 카드(가격 두 개), Death Wish 공지 띠, Living Proof 배너 | ✅ |
| 구독 할인 | 문구로만(Death Wish "30% off your first shipment") | ✅ 문구 / ❓ 실제 가격 |
| 오퍼의 시작/끝 | 없다. 수집한 날의 스냅샷만 있다 | 매일 돌려서 만든다 |

### 5-3. 이메일
| 과제가 요구한 것 | 원본에서 얻는 방법 | 상태 |
|---|---|---|
| 가입 첫날 받은 메일 전부 | 받은편지함 읽기 | ✅ 3통(가입 후 30~37분 시점까지만) |
| 발신자, 제목, 시각 | 메일 헤더 | ✅ |
| 오퍼(할인율, 코드, 기한) | plain text 정규식(4-4) | ✅ 코드/할인율 / 기한은 Living Proof만 |
| 주 행동 유도 링크 | plain text의 주소(4-4) | ✅ |
| 본문 원문 | `samples/eml/`의 plain text, HTML | ✅ 세 통 모두 |

## 6. 지금 유효한 항목의 판정
- **가격:** 이번에 받은 `products.json`에 있고 `available: true`면 지금 팔고 있다. 다음 수집에서 안 보이면 내린 것이다. `published_at`이 미래거나 아주 오래전인 것도 있다(Death Wish 최소 2014-03-12) ✅. 공개일 순서로 신상품을 가르면 된다.
- **오퍼:** 날짜가 없다. 오늘 홈 DOM에 있으면 "오늘 노출", 어제는 있고 오늘은 없으면 "내림"으로 보는 수밖에 없다(제안).
- **Klaviyo 폼:** 목록에 있다고 켜져 있는 것은 아니다(4-2). 노출 여부는 홈을 열어 DOM에서 확인해야 한다.
- **이메일 쿠폰:** Living Proof만 기한이 있다(12월 9일). 나머지는 기한 없음으로 적는다.

## 7. 항목 식별과 재실행
- **가격 행의 고유 키(제안):** `브랜드 + 변형 ID`(`variants[].id`). 이 ID는 안 바뀐다 ✅(상품 ID, 변형 ID 모두 큰 숫자).
- **오퍼 행:** 브랜드 + 위치 종류 + 문구(해시) + 수집일.
- **이메일 행:** Gmail 메시지 ID(.eml의 `X-Trial-Gmail-Id`). 메일이 올 때마다 새 행이다. 받은 시각은 `X-Trial-Received-At`(Gmail `internalDate`)이다.
- 대조용 주소: 상품 `https://<사이트>/products/<handle>`, 변형 `?variant=<ID>`.
- 다시 돌리면 같은 키의 가격 행은 값과 `updated_at`을 갱신하고, 가격이 바뀌면 이력을 남긴다. 목록에서 사라지면 내림으로 표시한다.
- 공손하게 호출한다: 사이트당 페이지 로드 8회 이하, 3초 이상 간격. 이번 조사에서 사이트당 요청은 홈 1~2회, `products.json` 1~2회, 상품 페이지 1회 정도였다.

## 8. 이 소스에서 얻을 수 없는 것
- 판매량, 매출, 재고 수량(`available`은 참/거짓뿐)
- 오퍼가 언제 시작해서 언제 끝나는지(오퍼에는 날짜 필드가 없다)
- 구독 가격(표준 경로에는 없다)
- Batiste: 자기 사이트의 가격, 전체 제품 목록(위젯은 한 제품씩만 묻는다), 리테일러의 실제 진열대 가격(위젯이 가져온 값 하나다)
- Jinx: 가입 이메일(가입 폼이 없다), 리테일러 가격(Walmart, Chewy, Amazon은 이 소스의 범위가 아니다)
- 이메일 안의 이미지에 든 글자(이미지만 있는 배너)
- 가입 후 24시간 동안 오는 후속 메일: 이번에는 가입 후 약 30~37분까지만 봤다 ❓. 환영 메일 뒤에 장바구니 포기, 후속 할인, 두 번째 환영 메일이 올지는 아직 모른다.

## 9. 이걸로 볼 수 있는 것
수집일 하루치 기준이다. 아래는 이번에 실제로 본 것이다.
- **가입 혜택 비교:** Living Proof 15%, Death Wish 20%, Black Rifle 20%. Living Proof만 기한을 쓰고, 코드도 가입자별로 보인다(❓). Black Rifle은 할인 자동 적용 주소를 쓰고 Death Wish는 홈으로 보낸다.
- **사이트 문구와 메일의 차이:** Black Rifle 폼 문구에는 "free shipping on $75+"가 붙지만 메일에는 없다.
- **할인 방식:** Death Wish는 상품 240개 변형이 정가 대비 할인 표시(`compare_at_price`)다(450개 중). Black Rifle은 1,837개 중 635개다. 둘 다 상시 할인에 가깝다.
- **제품 구성:** Black Rifle 상품 447개 중 커피는 55개, 옷과 장비가 357개다. 커피 회사이면서 머치 비중이 크다.
- **Jinx의 채널 전략:** 자기 사이트에서도 팔지만 홈의 첫 버튼과 공지 띠가 리테일러(Walmart, Chewy, Amazon)로 간다.
- **Batiste의 리테일러 가격 차:** 같은 제품이 8.99(Target)에서 13.49(Walgreens)까지 퍼져 있다(한 제품, D.C. 기준).
- **무료배송 기준:** Jinx $65, Black Rifle $75, Living Proof $50(추정).

## 10. 정해야 할 것
1. **행 단위:** 상품이냐 변형이냐. (제안: **변형 1개 = 가격 행 1개**. 상품 정보는 같이 저장한다. 크기, 수량 묶음, 색상 변형의 가격이 서로 다르고 `available`도 변형마다 다르다. 상품 단위로 가면 대표 가격 하나만 남아서 정보가 사라진다. 비교용으로는 상품 최저가와 `compare_at_price` 유무를 파생 값으로 만든다. Death Wish 수량 변형은 개당 단가를 따로 계산해야 한다.)
2. **어떤 상품을 볼지:** 전부(Black Rifle 1,837행) 받을지, `product_type`이 커피/반려동물 사료/헤어케어인 것만 받을지. (제안: 전부 받아서 저장하고 분석할 때 걸러낸다. 요청 수는 같다.)
3. **Black Rifle 접속 방식(막힘):** curl은 Cloudflare 403, Playwright Chrome은 3초 뒤 Google로 이동한다. **정한 것(2026-11-10, 소유자): ① Black Rifle 가격은 Apify로 받는다(11번). ② 소유자가 브라우저에서 직접 저장한 `products.json`도 "수동 스냅샷"으로 표시해 넣는다.** 자동 실행이 막히면 "못 봄"으로 기록하고 기존 행은 ended로 바꾸지 않는다.
4. **Batiste 위젯 가격을 쓸지:** 브랜드가 `displayprices:false`로 숨긴 값이다. 쓰려면 제품마다 EAN이 필요하고(4번 응답으로 제품 4개 얻음) 위치(기본 워싱턴 D.C.)를 정해야 한다. (제안: 쓰되 "리테일러 가격, 사이트 가격 아님"으로 표시하고 위치를 고정한다.)
5. **통화와 위치:** 미국 IP로만 돌리고 USD로 적는다(제안).
6. **받은편지함을 읽는 방법: 정함(2026-11-10, 소유자).** Gmail 커넥터로 원문을 내보낸다. IMAP과 Gmail API는 쓰지 않는다(12번).
7. **받은편지함 권한이 없는 사람이 다시 돌리는 방법: 정함.** 수집기는 저장소의 가린 .eml을 읽는다(12번).
8. **가입 후 24시간 관찰:** 2026-11-11 04:55 UTC(13:55 KST) 이후 내보내기를 다시 한다(12번). 아직 안 했다.
9. **Klaviyo 목록을 오퍼 소스로 쓸지:** 공개 주소이고 문구와 코드가 한 번에 오지만 켜진 것/꺼진 것이 안 갈린다. (제안: 홈 DOM 스냅샷을 정답으로, Klaviyo 목록을 보조로 쓴다.)

### 받은편지함을 코드로 읽는 두 가지 방법 (❓ 이번에 설정하지 않았고 일반 지식이다. 쓰지 않기로 했다. 12번 참고)
| | Gmail API (OAuth) | IMAP (앱 비밀번호) |
|---|---|---|
| 주인이 한 번 손으로 할 일 | ① Google Cloud 프로젝트를 만들고 Gmail API를 켠다 ② OAuth 동의 화면을 만든다(테스트 모드면 시험용 계정을 "테스트 사용자"로 추가) ③ OAuth 클라이언트 ID(데스크톱 앱)를 만들어 `credentials.json`을 받는다 ④ 처음 한 번 브라우저에서 로그인해 동의하고 `token.json`(refresh token)을 저장한다. 범위는 `gmail.readonly` | ① 계정에서 2단계 인증을 켠다 ② 앱 비밀번호(16자리)를 만든다 ③ Gmail 설정에서 IMAP을 켠다(요즘은 기본 켜짐인 경우가 많다) |
| 받는 원본 | `users.messages.get?format=raw`가 base64url로 인코딩된 **RFC 822(MIME) 원문**을 준다. 디코딩하면 .eml과 같다. `format=full`은 JSON으로 헤더와 본문 조각을 준다 | `FETCH <번호> (RFC822)`가 **RFC 822(MIME) 원문**을 그대로 준다. 저장하면 .eml이다 |
| 쓰는 단위 | 메시지 ID, `internalDate`, 라벨, 검색(`q=from:livingproof.com`) | UID, `INTERNALDATE`, `SEARCH FROM "livingproof.com"` |
| 먼저 설정하기 쉬운 쪽 | 설정이 4단계라 더 걸린다. 테스트 모드의 refresh token은 7일 만에 끝나는 경우가 있다 ❓ | **더 빠르다.** 앱 비밀번호만 있으면 몇 분이다. 단 계정에 2단계 인증이 필요하고 일부 Workspace 계정은 앱 비밀번호가 막혀 있다 ❓ |
| 장단점 | 읽기 전용 범위가 분명하고 비밀번호가 새도 계정 전체가 열리지 않는다 | 비밀번호가 새면 메일 전체가 열린다. 읽기 전용으로 좁힐 수 없다 |

- **제안: IMAP으로 시작.** 시험용 계정이고 가장 빠르다. 비밀번호는 환경 변수로만 받고 저장소에 넣지 않는다. 오래 쓸 거면 Gmail API로 옮긴다.
- 두 방법 모두 받는 것은 MIME 원문이라 파서는 하나로 합칠 수 있다(Python `email` 모듈). 헤더(`From`, `Subject`, `Date`), `text/plain`, `text/html` 부분을 꺼내고, 링크는 `ctrk.klclick.com` 같은 추적 주소를 따라가지 않고 plain text 부분의 실제 주소를 쓴다.
- **자격 없이 다시 돌리기:** 주인이 메일 3통을 .eml로 저장하고(Gmail "원본 보기 → 다운로드") 저장소 `part1/data/emails/*.eml` 같은 곳에 둔다. 수집기는 받은편지함 모드와 디스크 모드를 둘 다 지원하고, 자격이 없으면 디스크의 .eml을 읽는다. 올리기 전에 `To:`와 수신 취소 링크의 토큰을 `TRIAL_INBOX`와 `REDACTED`로 바꾼다. 이번 조사의 샘플 JSON도 같은 방식으로 만들었다.

## 11. Apify 시험: Black Rifle 가격 (2026-11-10, 실행 1회)
메인 스레드가 정한 시험이다: `apify/e-commerce-scraping-tool`로 `blackriflecoffee.com`에서 상품 5개.

- **결정(2026-11-10, 소유자): Black Rifle 가격은 Apify로 받는다.** 소유자 지시로 조사 세션이 실행했다.
- **결과 요약:** 차단을 넘어 상품 5개가 모두 왔다 ✅. 이전 스냅샷에 있는 2개는 가격이 맞다 ✅. 정가와 용량별 가격은 목록에서 찾은 상품에만 오고, 변형 ID와 용량별 품절 여부는 어느 쪽에도 없다 ✅. **차감액 $0.0258** ✅.
- 계정: 무료 요금제, 월 한도 $5 ✅.

### 실행 내용 ✅
| 항목 | 값 |
|---|---|
| 실행 ID | `mq7tThgHbN3DRebqB` |
| 시각(UTC) | 07:15:21 시작, 07:19:53 끝(272초) |
| 입력 | 상품 페이지 2개(이전 스냅샷에 있는 Gothic Serpent 3.0과 The Espresso Upgrade. 대조하려고 넣었다) + 목록 `/collections/coffee` 1장, `maxProductResults: 5`, `additionalProperties: true` (`samples/apify/blackrifle_run1_input.json`) |
| 상한 | `maxTotalChargeUsd=1`(쿼리 파라미터. 최소 상한이 $1이라 그 아래로는 걸 수 없다) |
| 결과 | 상품 5개, 오류 0건. 목록 페이지에서 상품 10개를 찾아 3개를 받은 뒤 개수 상한에서 멈췄다 |
| 걸린 시간 | 상품 페이지 2개는 7초, 13초. 목록 페이지 1장에 3분 11초. 목록에서 고른 상품 3개에 약 1분 |
| 차감 | `push-product` 3건, `residential-proxy-per-product` 2건, `browser-rendering-per-product` 2건, `product-search` 1건, `start-actor` 1건 = **$0.0258** (`eventUsage` 합계와 `usageTotalUsd`가 같다) |

- 상품은 5개가 왔는데 청구된 `push-product`는 3건이다. `chargedEventCounts`는 4건(브라우저 3건)이고, 실제 금액과 맞는 `accountedChargedEventCounts`는 3건(브라우저 2건)이다. 차이가 나는 이유는 모른다 ❓.
- 수집기가 residential 프록시와 브라우저 렌더링을 스스로 붙였다 ✅. 어느 상품에 붙었는지는 응답에 없다 ❓. unblocker는 쓰지 않았다 ✅.

### 상한과 접근 방식
- 수집기 요금 정보에 `minimalMaxTotalChargeUsd: 1`이 있다 ✅. Apify 문서는 이 값을 "사용자가 실행 상한을 너무 낮게 잡지 못하게 개발자가 정하는 최솟값"으로 설명하고, 실행 API의 400 오류 종류에 `max-total-charge-usd-below-minimum`이 있다 ✅. 그래서 상한은 $1로 걸고 비용은 개수(`maxProductResults`)로 묶었다. 0.10을 넣으면 실제로 거절되는지는 시험하지 않았다 ❓.
- 수집기는 막힌 상점에서 프록시를 자동으로 올린다(datacenter → residential → unblocker). 요금표가 이를 "to overcome bot detection"이라고 적는다 ✅. 즉 이 경로는 사이트의 차단을 유료 프록시로 넘는 방식이다. 노트의 접근 방법에 그대로 적는다.

### 단가 (무료 요금제, `samples/apify/actor_pricing_current.json`) ✅
| 과금 항목 | 단가 | 붙는 조건 |
|---|---|---|
| `start-actor` | $0.0001 | 실행 1회 |
| `product-search` | $0.0005 | 목록 페이지 1장(상품 수와 무관) |
| `push-product` | $0.006 | 상품 1개(HTTP + datacenter 프록시) |
| `residential-proxy-per-product` | + $0.003 | 사이트가 residential 프록시를 요구할 때 |
| `browser-rendering-per-product` | + $0.0006 | 브라우저 렌더링이 필요할 때 |
| `unblocker-proxy-per-product` | + $0.0015 | residential도 막힐 때 |

- 상품 1개: $0.006(추가 없음) ~ $0.0111(추가 3종 모두). 추가 3종이 한꺼번에 붙는지는 모른다 ❓.
- 계산한 예상 비용(실측 아님 ❓): 상품 5개 $0.031 ~ $0.057 / **상품 1,000개 $6.0 ~ $11.1** / Black Rifle 전체 447개 $2.7 ~ $5.0(무료 한도 $5를 한 번에 거의 다 쓴다) / 커피 55개만 $0.33 ~ $0.61.
- 과금 단위는 상품이다. 용량별 행(1,837개)마다 과금되는지는 모른다 ❓.
- 같은 계정에서 다른 소스 스레드가 돌린 실행 3건(2026-11-10 07:10 UTC, Black Rifle 대상 아님)의 차감액이 이 요금표와 맞는다 ✅: 상품 10개 + 목록 1장 + 시작 1회 = $0.0606, residential이 1개 붙은 실행은 $0.0636. 세 실행 모두 상한이 $1로 걸려 있었다 ✅(최소 상한과 같은 값).
- **실측(이 시험 1회):** 상품 5개에 $0.0258, 개당 $0.0052 ✅. 요금표대로 상품마다 모두 청구되면 개당 $0.006~$0.0111이므로 **상품 1,000개 $5~$11**로 적는다. Black Rifle 전체 447개는 $2.3~$5.0이다(계산값 ❓).

### 입력 형식 (빌드 0.0.137, `samples/apify/actor_input_schema.json`) ✅
- `listingUrls`: 목록(카테고리) 페이지 주소 배열 `[{"url": ...}]`. `detailsUrls`: 상품 페이지 주소 배열.
- `maxProductResults`: 실행 전체의 상품 수 상한(정수, 1 이상). 개수 제한은 이 값으로 건다.
- `scrapeMode`: `AUTO`(기본) / `BROWSER` / `HTTP`. `additionalProperties`: 추가 속성 포함 여부.
- 숨은 입력 `disableFallbacks`의 설명에 "skip Zyte/Shopify/Oxylabs fallbacks"가 있다 ✅. Shopify용 대체 경로가 내장돼 있다는 뜻이다. 그 경로가 `products.json`을 읽는지는 모른다 ❓.
- 금액 상한 `maxTotalChargeUsd`는 입력이 아니라 실행 주소의 쿼리 파라미터다 ✅(Apify API 문서).

### 응답 모양: 한 실행 안에서 두 가지로 갈린다 ✅ (`samples/apify/blackrifle_run1_items.json`)
| 필드 | 상품 페이지 주소로 받은 2개 | 목록에서 찾은 3개 |
|---|---|---|
| `name`, `url`, `scrapedAt` | 있음 | 있음 |
| `offers.price` | 숫자(`30`, `125.37`) | **문자열**(`"45.87"`) |
| `offers.priceText`, `offers.availability` | 있음(`"InStock"`) | 없음 |
| `gtin` | Gothic Serpent만(`840461224665`) | 없음 |
| `additionalProperties` | **없음**(요청했는데도) | 있음 |
| 정가 `additionalProperties.regularPrice` | 없음 | Dark Roast Bundle에만 `50.97`(할인 중인 상품에만 붙는 것으로 보인다 ❓) |
| 상품 ID | 없음 | `additionalProperties.sku`에 Shopify 상품 ID(`7762549899360`) |
| 용량별 `additionalProperties.variants[]` | 없음 | `name`(예: `Tactisquatch Roast - Ground / 12oz`), `price`(문자열), `currency`, `sku` |
| 용량별 `sku`의 정체 | | 커피 2개는 실제 SKU(`30-109-12G`), 번들은 Shopify 변형 ID(`42986248175712`) |
| 용량별 품절, 용량별 정가, 변형 ID | 없음 | 없음 |
| 상품 분류 | 없음 | `additionalProperties.extraProperties`의 `type`(`Coffee`, `Bundle`) |

- 상품 페이지 주소로 넣으면 대표 가격 하나만 오고, 목록에서 찾은 상품에는 용량별 가격이 온다 ✅. 왜 갈리는지는 모른다 ❓.
- `products.json`에 있는데 여기에 없는 것: 변형 ID(항상), 용량별 `available`, 용량별 `compare_at_price`, `published_at`, `updated_at`, `tags`. 상품 페이지 경로는 용량 목록도 없다.

### 이전 스냅샷과 대조
이전 스냅샷은 같은 날 05시경(UTC) 일반 브라우저로 받은 `products.json`이다. 전체 447개는 저장하지 않았고 샘플 2개만 남아 있다.

| 상품 | 스냅샷 | Apify(07:15~07:19 UTC) | 판정 |
|---|---|---|---|
| Gothic Serpent 3.0, 12oz, Whole Bean | 30.00, 정가 없음, 구매 가능 | 30, `InStock` | ✅ 일치 |
| The Espresso Upgrade | 125.37, 정가 131.97, 변형 12개 | 125.37, 정가 없음, 변형 없음 | ✅ 가격 일치 / 정가와 변형은 안 옴 |
| Dark Roast Bundle | 샘플에 없음 | 45.87(정가 50.97), 용량 3개(45.87, 45.87, 35.07) | ❓ 대조할 원본 없음 |
| Pumpkin Spice Roast | 샘플에 없음 | 17.99, 용량 2개(17.99, 21.99) | ❓ 대조할 원본 없음 |
| Tactisquatch Roast | 샘플에 없음 | 16.99, 용량 8개(12.99~79.99) | ❓ 대조할 원본 없음 |

- 대조할 수 있는 2개는 둘 다 가격이 맞았다. 나머지 3개는 맞는지 확인하지 못했다. 이 세션에서는 사이트를 직접 열 수 없다(2번).

### 표에 넣을 때의 뜻
- 이 응답으로는 다른 세 Shopify 브랜드(`products.json`)와 같은 행 모양을 만들 수 없다. 변형 ID가 없어서, 재실행 때 같은 행을 찾는 키를 `상품 주소 + 용량 이름`으로 써야 한다. 용량별 품절과 정가는 비워 두고 비어 있다고 표시한다.
- 목록 경로만 쓰면 용량별 가격은 온다. 상품 페이지 주소 경로는 쓰지 않는 편이 낫다(대표 가격만 온다).
- 가격이 문자열과 숫자로 섞여 온다. 수집기에서 숫자로 바꿔야 한다.
- 447개를 다 받는 데 걸리는 시간은 모른다 ❓. 이번 속도(목록 1장에 3분, 상품마다 수 초~수십 초)로는 수십 분 이상일 수 있다.

### 재실행 관점
- 다른 사람이 수집기를 다시 돌리려면 자기 Apify 토큰과 잔액이 필요하다. 토큰이 없으면 Black Rifle 가격은 "못 봄"으로 기록되어야 한다.
- 비용은 실행마다 든다. 하루 한 번 447개를 다 받으면 $2.3~$5.0이라 무료 한도($5)로는 한두 번이다.

## 12. 메일 원문 내보내기: Gmail 커넥터 (2026-11-10, 3통 시험)
- **결정(2026-11-10, 소유자): 수신함은 Claude 세션의 Gmail 커넥터로 읽고, 원문을 가린 .eml로 저장한다. 수집기는 저장된 .eml을 읽는다.** IMAP과 Gmail API는 쓰지 않는다.
- 이유: 소유자가 설정할 것이 없고 비밀번호를 다루지 않는다. 첫날 메일은 24시간이 지나면 늘지 않는 묶음이라, 저장한 파일이 재실행 때 그대로 쓰는 원본이 된다. 수신함 권한이 없는 사람도 같은 결과를 얻는다.
- 한계: 수집기 코드가 수신함을 직접 읽지 않는다. 새 메일을 넣으려면 세션에서 내보내기를 다시 해야 한다. 노트에 그렇게 적는다.

### 순서 ✅ (3통으로 시험함)
1. `search_threads`로 세 브랜드 도메인만 찾는다: `{from:livingproof.com from:deathwishcoffee.com from:blackriflecoffee.com}`. 다른 메일은 열지 않는다.
2. 메시지마다 `get_message`를 `messageFormat: RAW`로 부른다. 응답은 `{id, threadId, internalDate, labelIds, raw, sizeEstimate, ...}`이고, `raw`는 base64url로 인코딩한 RFC 822 원문이다 ✅. 응답이 커서(약 6만 자) 하네스가 파일로 저장해 준다 ✅. 원문을 손으로 옮겨 적지 않는다.
3. `tools/redact_eml.py <출력 폴더> <응답 파일...>`로 가린 .eml을 만든다. 주소나 지운 토큰이 출력에 남으면 파일을 쓰지 않고 멈춘다.
4. `tools/verify_eml.py <출력 폴더> <응답 파일...>`로 원본과 따로 대조한다.

### 가리는 규칙
| 대상 | 처리 | 이유 |
|---|---|---|
| 수신 경로 헤더(`Received`, `Delivered-To`, `Return-Path`, `ARC-*`, `DKIM-Signature`, `Authentication-Results`, `Received-SPF`, `X-Received`) | 버림 | 수신 주소가 들어 있다 ✅(주소 3회, 계정 이름 최대 9회) |
| 수신자나 발송 건을 가리키는 헤더(`X-Kmail-Ops`, `X-SG-ID`, `X-SG-EID`, `X-Entity-ID`, `CFBL-Address`, `X-Mailer-Info*`) | 버림 | |
| `To` | `TRIAL_INBOX <trial_inbox@redacted.invalid>` | |
| `List-Unsubscribe` | 쿼리를 `REDACTED`로 바꾸고 mailto 형식은 버림 | 수신 취소 토큰 |
| 남기는 헤더 | `From`, `Reply-To`, `Subject`, `Date`, `Message-ID`, `MIME-Version`, `Feedback-ID`, `List-Unsubscribe-Post`, `X-Kmail-Account`(회사 ID), `X-Kmail-Flow`(흐름 ID), `X-Kmail-Message`(메일 ID), `X-Report-Abuse` | 브랜드와 흐름을 가르는 데 쓴다 |
| 남기는 헤더 안의 수신자별 토큰 | `REDACTED` | Black Rifle은 `Message-ID`에 지운 토큰과 같은 값이 있었다 ✅ |
| 본문 클릭 추적 `…/l/<토큰>`, 열람 픽셀 `…/o/<토큰>` | `/l/REDACTED`, `/o/REDACTED` | 누르면 시험 계정의 클릭으로 기록된다. 추적 주소는 Living Proof와 Death Wish가 `ctrk.klclick.com`, Black Rifle이 `trk.send.blackriflecoffee.com` ✅ |
| 본문 `manage.kmail-lists.com/...?…` | 쿼리를 `REDACTED`로 | 수신 취소, 구독 설정 토큰 |
| 쿠폰 코드(Living Proof `WC-TM5JN7LG`는 가입자별로 보임 ❓) | 남김 | 오퍼 자료다 |
| 추가 헤더 | `X-Trial-Gmail-Id`, `X-Trial-Received-At`(Gmail `internalDate`, UTC), `X-Trial-Gmail-Labels`, `X-Trial-Redaction`(가린 개수) | 받은 시각과 중복 제거 키 |

- 본문은 plain text와 HTML을 디코딩한 글자에서 바꾸고 quoted-printable로 다시 인코딩한다. 인코딩된 상태에서 바꾸면 quoted-printable 줄바꿈이 토큰을 끊어 놓칠 수 있다.
- 본문의 실제 상품 주소는 plain text 부분에 그대로 있다 ✅(Living Proof와 Death Wish는 HTML의 링크가 모두 추적 주소라, 가린 뒤에는 HTML에서 목적지를 알 수 없다).
- DKIM 서명은 버렸으므로 이 파일로 서명 검증은 안 된다.

### 시험 결과 ✅ (`samples/eml/`)
| 파일 | 원본 | .eml | 가린 것 | 쿠폰 코드 |
|---|---|---|---|---|
| `livingproof_20261110T044829Z_1a1c3c946076193d.eml` | 44,737 B | 38,065 B | 추적 9, 수신 취소 2 | `WC-TM5JN7LG` |
| `deathwish_20261110T044745Z_1a1c3c89e9e9cf7d.eml` | 48,813 B | 41,917 B | 추적 18, 수신 취소 2 | `DWC20` |
| `blackrifle_20261110T045627Z_1a1c3d099d8be175.eml` | 48,920 B | 41,557 B | 추적 20, 수신 취소 1, `Message-ID` 1 | `BEANS20` |

따로 짠 검사(`verify_eml.py`)를 3통 모두 통과했다 ✅.
- 수신 주소와 계정 이름이 헤더, 원문, 디코딩한 본문 어디에도 없다.
- 원본에서 따로 모은 수신자별 토큰(30~46개)이 하나도 남지 않았다.
- 주소를 뺀 본문 글자가 원본과 같고, 주소 개수도 같다. 다른 점은 각 부분 끝에 줄바꿈 하나가 붙는 것뿐이다.
- 수신 경로 헤더가 없다.
- 처음 만든 스크립트는 `ctrk.klclick.com`을 못 잡아 Living Proof와 Death Wish의 추적 토큰을 남겼다. 따로 짠 검사로 찾아 고쳤고 파일을 덮어썼다(커밋된 적 없다).

### 24시간 시점 재수집 (아직 안 함)
- 가입 24시간: Living Proof 2026-11-11 04:47:06 UTC, Death Wish 04:47:48 UTC, Black Rifle 04:54:53 UTC. **04:55 UTC(13:55 KST) 이후** 1~4단계를 다시 돌린다.
- "첫날 메일"의 기준(제안): 받은 시각(`X-Trial-Received-At`)이 브랜드별 가입 시각부터 24시간 안인 메일. 그 뒤에 온 메일은 넣지 않는다.
- 스팸함: 커넥터 검색은 기본으로 스팸을 빼고, 도구 설명상 `in:anywhere`도 스팸은 거른다. 스팸으로 간 메일이 있는지는 그때 `in:spam`으로 따로 확인한다 ❓.
- 지금까지 메일 수(2026-11-10 07:2x UTC 검색): 브랜드마다 1통 ✅.

## samples/
| 파일 | 내용 |
|---|---|
| `eml/*.eml` | 가입 메일 3통의 원문(가린 것). 수집기가 읽을 원본 |
| `apify/actor_pricing_current.json` | Apify 수집기의 현재 요금표와 최소 상한(무료 조회 응답에서 현재 항목만) |
| `apify/actor_input_schema.json` | Apify 수집기 입력 형식(빌드 0.0.137) |
| `apify/blackrifle_run1_input.json` | Black Rifle 시험 실행의 입력 |
| `apify/blackrifle_run1_run.json` | 실행이 끝난 뒤의 실행 객체(차감 내역 포함. 계정 ID와 서명된 결과 주소는 지움) |
| `apify/blackrifle_run1_items.json` | 결과 상품 5개 원본 |
| `apify/blackrifle_run1_errors.json` | 오류 목록(빈 배열) |
| `apify/blackrifle_run1_log.txt` | 실행 로그 |
| `products_livingproof_trimmed.json` | `products.json` 66개 중 3개 (변형 3개까지, 이미지 1개) |
| `products_deathwish_trimmed.json` | 165개 중 3개 (수량 변형 `1/2/5 BAGS` 포함) |
| `products_jinx_trimmed.json` | 73개 중 3개 |
| `products_blackrifle_trimmed.json` | 447개 중 2개 (커피와 번들. 손으로 줄였다) |
| `batiste_wtb_availabilities_trimmed.json` | Batiste 위젯 `availabilities` 응답(7행 중 3행) |
| `klaviyo_forms_livingproof.json`, `klaviyo_forms_deathwish.json`, `klaviyo_forms_blackrifle.json`, `klaviyo_forms_jinx.json` | Klaviyo `full-forms` 응답 원본(Jinx는 빈 목록) |
| `offers_blackrifle.json`, `offers_homepage_other_brands.json` | 홈 오퍼 문구, 선택자, HTML 조각 |
| `email_livingproof.json`, `email_deathwish.json`, `email_blackrifle.json` | 가입 메일 1통씩(수신자와 수신 취소 토큰 삭제, HTML 본문은 저장 안 함). 처음 조사 때 커넥터 응답을 요약한 것이고, 원문은 `eml/`에 있다 |

## tools/
조사용 스크립트다. 수집기 코드가 아니다.
| 파일 | 내용 |
|---|---|
| `redact_eml.py` | 커넥터 RAW 응답 파일을 가린 .eml로 바꾼다(12번 규칙) |
| `verify_eml.py` | 가린 .eml을 원본과 따로 대조한다 |
