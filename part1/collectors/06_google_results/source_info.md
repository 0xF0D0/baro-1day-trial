# 소스 6: Google 검색 결과 (상위 20개 검색어의 순위와 광고)

- 확인일: 2026-11-10 (미국 IP, 화면이 뜨는 Chrome)
- 확인 대상: Google 검색 결과 페이지 직접 수집 1회(차단), 자동완성 공개 주소(브랜드 5개, 알파벳 확장 3개), 유료 SERP API 3곳의 공개 문서
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정이거나 문서에서 읽었거나 미확인
- **이 소스는 직접 수집이 막혀서 검색 결과 페이지의 실제 구조는 보지 못했다.** 4번 항목의 구조는 모두 문서에서 읽은 것이다 ❓.

## 1. 이 소스가 주는 것
브랜드의 상위 20개 검색어마다, 그 검색어를 Google에 쳤을 때 **누가 자연 검색(organic)에 나오고 누가 광고를 사는지**. **한 행은 (검색어, 순위 1개)**, 광고는 (검색어, 광고 1개)다.

## 2. 접근 방법
### 2-1. 직접 수집: 막혔다 ✅
- `https://www.google.com/search?q=batiste+dry+shampoo&gl=us&hl=en`을 미국 IP, 화면이 뜨는 Chrome에서 **한 번** 열었다. HTTP 200으로 열렸지만 곧바로 `https://www.google.com/sorry/index?continue=...` 화면으로 바뀌었다.
- 화면 내용: "Our systems have detected unusual traffic from your computer network. This page checks to see if it's really you sending the requests, and not a robot." 시각, IP, 요청 주소가 적혀 있다(`samples/google_search_captcha_sorry_page.html`, `.png`). reCAPTCHA다.
- 규칙대로 풀거나 우회하지 않았고 **더 시도하지 않았다**(검색 페이지 로드 총 1회). 두 번째 질의는 하지 않았다.
- 한국 IP에서의 사전 확인도 같은 화면이었다. 미국에서도 같다. 그러나 이번 IP는 데이터센터(VPN, `AS212238 Datacamp`)라서 **가정용 IP, 주거용 프록시라면 다를 수 있다** ❓. 이 소스는 그 경우를 시험하지 않았다.
- 결론: **자동 수집으로 검색 결과 페이지를 안정적으로 받는 방법을 찾지 못했다.**

### 2-2. 다른 길 (확인한 것)
- Google Custom Search JSON API: 새 고객에게 닫혀 있고 광고를 주지 않는다(사전 확인) ❓.
- 자동완성 `https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q=<검색어>`: 로그인과 키 없이 열린다 ✅. 6절에서 다룬다. 이것은 검색 결과가 아니라 **검색어 후보**만 준다.

### 2-3. 유료 SERP API (문서에서 읽은 것, 호출하지 않았다) ❓
5번 항목 참고.

## 3. 브랜드 매칭
- 검색어에 브랜드 이름이 들어 있는 것만 쓴다. 광고주 도메인은 소스 1과 같다.

| 브랜드 | 도메인 | 시드(자동완성 입력) |
|---|---|---|
| Batiste | batistehair.com | `batiste dry shampoo` |
| Living Proof | livingproof.com | `living proof` |
| Death Wish Coffee | deathwishcoffee.com | `death wish coffee` |
| Black Rifle Coffee | blackriflecoffee.com | `black rifle coffee` |
| Jinx | thinkjinx.com | `jinx dog food` |

- 단독 "batiste"와 "jinx"는 다른 뜻이 섞인다 ✅. `batiste` 알파벳 확장 261개 중 `batiste artist`, `batiste fabric`, `batiste jon`, `batiste guerra tennis`처럼 브랜드와 무관한 것이 많았다. `jinx`의 첫 10개 중 `jinx arcane`, `jinx build`, `jinx teen titans`, `jinx manhwa`는 게임/만화 캐릭터다. 그래서 위 시드처럼 **상품 단어를 붙인다**.
- 검색 결과에서 브랜드의 자연 검색 순위를 볼 때는 도메인으로 매칭한다(`domain == batistehair.com` 등). 아마존, 월마트 같은 리테일러에 나온 것은 브랜드 도메인이 아니라서 따로 표시해야 한다 ❓.

## 4. 원본 구조 (문서에서 읽은 것, 실제 응답은 보지 못했다) ❓
| 항목 | SerpApi | DataForSEO | Serper |
|---|---|---|---|
| 광고와 자연 검색 분리 | **분리됨.** `ads[]`와 `organic_results[]` | **분리됨.** 한 `items[]` 안에서 `type: "paid"`와 `type: "organic"` | 읽은 문서에 `ads` 키가 **없었다**. 응답 예시는 `organic`, `knowledgeGraph`, `peopleAlsoAsk`, `relatedSearches` ❓ |
| 순위 | `position` | `rank_group`, `rank_absolute`, `position`(left/right 정렬) | `position`(문서에서 확인하지 못함) |
| 도메인 | **`domain` 필드가 없다.** `displayed_link`, `source`로 직접 뽑아야 한다 | `domain` | 확인하지 못함 |
| 제목 | `title` | `title` | `title` |
| 요약문 | `snippet` | `description` | `snippet` |
| 주소 | `link` | `url` | `link` |
| 광고 위/아래 | `block_position`: `top`, `bottom`, `middle`, `right` | 문서에 **명시가 없다.** `rank_absolute`로 짐작하거나 `calculate_rectangles`(추가 $0.002)의 좌표를 쓴다 | 해당 없음 |
| 광고 필드 | `position`, `block_position`, `title`, `link`, `displayed_link`, `tracking_link`, `description`, `source` | `rank_group`, `rank_absolute`, `page`, `position`, `title`, `domain`, `website_name`, `url`, `breadcrumb`, `description`, `links`, `price`, `rating` 등 | 확인하지 못함 |
| 쇼핑 광고 | 읽은 페이지에 `shopping_results`가 없었다. `immersive_products`가 있다 | `type: "shopping"` | 별도 쇼핑 엔드포인트가 있다 |
| 다른 블록 | `related_questions`(People also ask), AI Overview는 별도 엔진 `udm=50` | `people_also_ask`, `ai_overview` | `peopleAlsoAsk`, `relatedSearches` |
| 미국 지정 | `gl=us`, `hl=en`, `google_domain=google.com`, `location`(예: "Austin, TX", 도시 단위 권장) | `location_code=2840`(미국), `language_code=en`, `device=desktop`, `depth`(기본 10, 최대 200) | `gl`, `hl`, `location` ❓ |

- 소스 1에서 본 Ads Transparency가 "광고 소재"를 준다면, 이 소스는 **"특정 검색어에 그 순간 노출된 광고"**를 준다. 검색어 단위 경쟁 구도는 이 소스에서만 나온다.
- 한계: Google은 위치, 기기, 시각마다 광고가 달라서 **같은 검색어도 호출마다 다를 수 있다** ❓.

## 5. 집중해서 볼 것과 원본의 대응 / 대안 비교
| 과제가 요구한 것 | 얻는 방법 | 상태 |
|---|---|---|
| 순위(누가 나오나) | SERP API의 `organic_results[]`/`organic` 항목 | ❓ 문서 |
| 광고(누가 사나) | SerpApi `ads[]` / DataForSEO `paid` | ❓ 문서. Serper는 미확인 |
| 광고주 도메인 | DataForSEO `domain`. SerpApi는 `displayed_link`에서 추출 | ❓ |
| 직접 수집 | 막힘 | ✅ |

### 가격표 (공개 가격 페이지에서 읽음, 2026-11-10) ❓
| 서비스 | 단가 | 최소 구입 |
|---|---|---|
| SerpApi | 월 정액. 무료 250건/월, Starter $25=1,000건($25/1,000), Developer $75=5,000건($15/1,000), Production $150=15,000건($10/1,000), Big Data $275=30,000건($9.17/1,000). 속도 옵션은 2배, 4배 | 가장 작은 유료가 월 $25 |
| DataForSEO | 건당 과금(SERP 1건=결과 10개). **Standard 큐 $0.0006(=$0.60/1,000, 대기 평균 약 5분), Priority $0.0012(=$1.20/1,000), Live $0.002(=$2.00/1,000)**. `depth`를 늘리면 늘린 만큼 추가 | 최소 충전액은 확인하지 못했다 ❓ |
| Serper | 선불 크레딧. Starter $50=5만 건($1.00/1,000), Standard $375=50만 건($0.75/1,000), 무료 2,500건. 성공한 응답만 차감, 크레딧 유효 6개월 | $50 |

### 전체 작업 비용: 5개 브랜드 × 20개 검색어 = 한 번에 SERP 100건
| 서비스 | 1회(100건) | 매일 돌리면(월 3,000건) | 비고 |
|---|---|---|---|
| DataForSEO Standard | **$0.06** | $1.80 | 대기 약 5분. 광고가 `paid`로 분리됨(문서) |
| DataForSEO Live | $0.20 | $6.00 | 6초 안에 응답 |
| Serper | $0.10 | $3.00(선불 $50 필요) | **광고가 나오는지 확인하지 못했다** |
| SerpApi | $2.50(Starter 기준) 또는 무료 한도 250건 안 | Big Data $275/월 | 광고 필드가 가장 상세하다(문서) |

- 이 비용은 모두 문서값이다. 실제 호출로 광고가 정말 분리되어 오는지는 **확인하지 못했다** ❓. 호출하기 전에 계정을 만들거나 키를 넣지 않았다.
- 검색어를 20개보다 더 늘려 2쪽까지 보면 건수가 곱절이 된다. "광고"는 보통 1쪽에만 있다 ❓.

## 6. "상위 20개 검색어"는 어디서 오나
**검색량을 주는 공개 소스는 없다.** 아래 세 방법 모두 검색량이 아니라 "이 검색어가 존재한다, 또는 인기 있다" 정도만 알려준다 ✅.

### 6-1. (a) Trends 연관 검색어 (소스 7)
- 비어 있거나 3~8개뿐이다 ✅. Batiste, Jinx는 모든 요청에서 0개였고 Death Wish는 3개, Black Rifle은 8개, Living Proof(토픽)는 5개였다. 20개를 채울 수 없다.
- 값은 그 목록 1위를 100으로 한 상대값이다.

### 6-2. (b) 자동완성 ✅ (`samples/suggest_*.json`)
- 응답 형식: `["입력",["제안1",...,"제안10"],[],{"google:suggestsubtypes":[...]}]`. **한 번에 최대 10개, 인기순(으로 보이는 순서)**. 건수나 점수는 없다. 다섯 브랜드 모두 200이었다.
- 첫 10개 예(`batiste`): `batiste dry shampoo`, `batiste`, `batiste dry shampoo dark hair`, `batiste fabric`, `batiste volumizing dry shampoo`, `batiste powder dry shampoo`, `batiste meaning`, `batiste blonde dry shampoo`, `batiste brunette dry shampoo`, `batiste bare dry shampoo`.
- 브랜드와 무관한 뜻(`batiste fabric`, `batiste meaning`, `jinx arcane`)이 섞여 있다 ✅.
- 순서가 곧 순위이므로 **순서를 저장한다.**

### 6-3. (c) 알파벳 확장 ✅ (`samples/alpha_*.json`)
- 시드 뒤에 공백과 `a`~`z`를 붙여 27번 호출한다(1.2초 간격). 요청 27번에 고유 검색어: `batiste` 261개, `batiste dry shampoo` 253개, `jinx dog food` 207개 ✅. 한 번의 확장으로 20개를 넘게 모은다.
- `batiste` 같은 짧은 시드는 `batiste a`에서 `batiste artist`, `bautista age`처럼 **엉뚱한 것이 섞인다.** 상품 단어를 붙인 시드(`batiste dry shampoo`)는 깨끗했다 ✅. 반대로 글자별 목록은 그 글자 단어가 나오는 대로 모이므로 **의미 있는 상위 20개라는 보장은 없다**.
- 가끔 일부 호출이 네트워크 오류를 냈다(`No route to host`). 재시도 후 성공했다 ✅.

### 6-4. 권장 레시피 (정확히 20개)
1. 시드 = 3절 표의 시드. (브랜드 이름이 모호하면 상품 단어를 붙인다)
2. 시드 자체의 자동완성 10개를 순서대로 담는다.
3. 부족하면 `<시드> a`~`z` 각각의 1위, 2위, 3위를 순서대로 돌려가며(1위 26개 → 2위 26개 …) 담는다.
4. 검색어에 브랜드 단어(`batiste`, `jinx` 등)가 없는 것은 버린다. 중복을 버린다.
5. 20개가 되면 멈춘다. 순서와 "시드 / 알파벳(`a`)" 출처를 저장한다.
6. 호출 횟수는 브랜드당 최대 27번. 시드 + 알파벳 26번.
- 시험 결과(`samples/recipe_sketch.py`, 같은 방식을 코드로 만든 스케치) ✅: `batiste dry shampoo` 시드로 20개 완성(예: `batiste dry shampoo dark hair`, `...7.62 oz`, `...review`, `...sweat activated`, `...amazon`, `...gluten free`, `...kroger`). `jinx dog food` 시드로도 20개 완성(`...reviews`, `...near me`, `...recall`, `...walmart`, `...topper`, `...coupons`, ...). 두 번째는 알파벳 단계 첫 글자들(`at walmart`, `big bag`, `coupons`)로 채워졌다.
- 한계: 알파벳 단계는 `a`~`k` 글자에 치우친다. 이건 의도가 아니라 "먼저 20개가 차는" 결과다.
- 또는 사람이 20개를 한 번 정하고 고정하는 방법도 있다(제안, 10절).

## 7. 항목 식별과 재실행
- 검색어 단위 키: 브랜드 + 검색어 문자열 + 수집일. 광고는 검색어 + 광고주 도메인 + 제목 + 수집일(같은 광고가 여러 번 나올 수 있다).
- 자동완성 순서는 호출마다 바뀔 수 있다. 두 번 호출해서 비교하지는 않았다 ❓. 20개 목록은 **한 번 정해서 저장하고 그 목록으로 계속 조회**하는 편이 안전하다(제안).
- SERP 호출은 같은 검색어라도 매번 결과가 다를 수 있다 ❓. 수집 시각과 위치(US), 기기(desktop)를 같이 저장한다.

## 8. 이 소스에서 얻을 수 없는 것
- 검색량. (자동완성, Trends 모두 상대값이거나 순서뿐이다)
- 직접 수집으로는 아무것도 얻지 못했다(CAPTCHA).
- 광고비, 노출량, 입찰가.
- 가정용 IP로 직접 수집했을 때 되는지: 시험하지 않았다.

## 9. 이걸로 볼 수 있는 것
이번에 실제 데이터로 본 것은 자동완성뿐이다.
- **소비자가 브랜드에 붙이는 말**: Death Wish는 `caffeine content`, `k cups`, `near me`, `mugs`; Black Rifle은 `menu`, `stock`, `owner`, `energy drink`; Jinx는 `reviews`, `recall`, `walmart`, `topper` ✅. 제품, 가격, 구매처, 불만이 보인다.
- **브랜드 이름 혼동**: Batiste와 Jinx는 다른 뜻과 섞인다. 그 자체가 브랜드 관리 이슈다.
- 순위와 광고 분석(누가 광고를 사는지, 경쟁사가 브랜드 검색어에 광고하는지)은 유료 SERP API를 써야 얻는다 ❓.

## 10. 정해야 할 것
> 2026-11-10 정리: 1·2·6은 12절, 3·4는 13절, 7은 14절에서 정했다. 5는 메인 스레드가 정한다.

1. **검색 결과를 어떻게 얻을지.** (제안: DataForSEO Standard 큐. 1회 $0.06. 단, 실제로 `paid` 항목이 오는지 소량으로 먼저 확인한다. 안 되면 SerpApi 무료 한도 250건으로 확인한다)
2. 직접 수집을 포기할지. (제안: 포기. 한 번 만에 막혔다)
3. 20개 검색어를 자동 레시피로 매번 만들지, 한 번 정해 고정할지. (제안: 자동 레시피로 한 번 만들고 사람이 훑어본 뒤 고정)
4. Batiste와 Jinx의 시드에 상품 단어를 붙이는 것에 동의하는지. (제안: 붙인다)
5. 광고만 필요하면 소스 1(Ads Transparency)과 겹친다. 이 소스에서 광고를 꼭 따로 볼지. (제안: 검색어별 순위가 필요하면 둔다)
6. 광고 추출(`focusOnPaidAds`, 쪽당 $0.0065)을 계속 켤지. 시험 3회에서 광고가 0건이었다(11-5). (제안: 11-7의 1회 확인 뒤 정한다)
7. 소셜 결과의 `websiteTitle`(`Facebook · <페이지 이름>`)과 `displayedUrl`을 저장할지. 개인 제작자 이름이 들어갈 수 있다. (제안: 저장하지 않고 도메인만 둔다)

## 11. Apify 시험 (2026-11-10): 순위는 왔고, 광고는 세 검색어 모두 0건이었다
유료 경로는 Apify 한 곳으로 모으기로 했다(메인 스레드 결정). 수집기는 공식 `apify/google-search-scraper`(빌드 0.0.482)다.

- 실행 1회 ✅: 검색어 3개(`batiste dry shampoo`, `death wish coffee`, `jinx dog food`), 미국, 영어, 데스크톱, 검색어당 1쪽, 광고 추출 켬, 부가 기능 전부 끔. 2026-11-10 07:09~07:11 UTC, 91초, 3건 성공 0건 실패.
- **실제 차감액 $0.03305** ✅ = 검색 3쪽 × $0.0045 + 광고 추출 3쪽 × $0.0065 + 시작 1회 $0.00005(`samples/apify/trial_run_summary.json`). 재실행은 하지 않았다.
- 결론: **"누가 순위에 있는지"는 이 응답으로 채울 수 있다. "누가 광고를 사는지"는 채우지 못했다**(11-5).

### 11-1. 단가 ✅ (수집기 정보의 `pricingInfos`, 무료 요금제 기준)
| 과금 항목 | 단가 | 붙는 조건 |
|---|---|---|
| `search-page-scraped` | $0.0045 / 쪽 | 항상 |
| `ads-scraped` | **$0.0065 / 쪽** | `focusOnPaidAds`를 켜면 광고가 없어도 붙는다 |
| `apify-actor-start` | $0.00005 / GB | 실행 1회(기본 메모리 1 GB) |
| AI Overview, AI Mode, Gemini, Perplexity, ChatGPT, Copilot, 리드, 사이트 본문 | $0.003~$0.2 / 건 | 입력에서 켰을 때만. 시험 입력에서는 전부 껐다 |

- 광고까지 보면 **검색 1회 = $0.011**이다(처음 들은 $0.0045가 아니다). 검색 3회 시험은 약 $0.033, 전체(5개 브랜드 × 20개 = 100회)는 **1회 실행에 약 $1.10**이다. 무료 요금제의 월 크레딧은 $5다.
- 광고를 끄면 100회에 $0.45지만 "누가 광고를 사는지"를 못 본다.

### 11-2. 실행당 상한의 최솟값 ✅
- 실행 요청에 `maxTotalChargeUsd=0.05`를 붙였더니 HTTP 400 `max-total-charge-usd-below-minimum`("Maximum cost per run is less than the allowed minimum of $0.50")이 왔다. 이 수집기는 **실행당 상한을 $0.50 아래로 걸 수 없다**(`minimalMaxTotalChargeUsd: 0.5`). 거절된 요청은 실행되지 않았고 차감도 없었다.
- 사용자 승인을 받아 상한 $0.50, 제한 시간 300초로 실행했다. 실행 중 과금 항목 수를 20초마다 읽어 $0.05를 넘으면 중단하도록 했고, 넘지 않았다.
- 수집기를 만들 때도 같다. 상한은 $0.50 이상으로만 걸 수 있으므로, 비용은 입력(검색어 수 × 쪽 수, 부가 기능 끔)으로 고정해야 한다.

### 11-3. 입력 형식 ✅ (`samples/apify/trial_input.json`)
- `queries`: 줄바꿈으로 구분한 검색어 문자열. `maxPagesPerQuery`: 검색어당 쪽 수(1쪽에 약 10개). `countryCode`(`gl`), `languageCode`(`hl`), `mobileResults`(기본 false = 데스크톱), `locationUule`(정확한 위치).
- `focusOnPaidAds`: 광고 전용 프록시로 검색어당 최대 3번 다시 시도해 광고를 찾는다고 적혀 있다 ❓(설명문).
- `saveHtmlToKeyValueStore`(기본 true): 결과 화면 HTML을 저장하고 `htmlSnapshotUrl`로 준다. 대조용으로 켜 둔다.

### 11-4. 결과: 자연검색 ✅ (`samples/apify/trial_run_dataset.json`)
- **검색어 1쪽이 항목 하나**다. 최상위 키: `searchQuery`, `url`, `hasNextPage`, `organicResults[]`, `paidResults[]`, `paidProducts[]`, `relatedQueries[]`, `peopleAlsoAsk[]`, `suggestedResults[]`, `aiOverview`(있을 때만), `htmlSnapshotUrl`, `#debug`, `#error`.
- `searchQuery`: `term`, `url`(예: `http://www.google.com/search?q=batiste+dry+shampoo&gl=us&hl=en`), `device`(`DESKTOP`), `page`, `type`, `domain`, `countryCode`(`US`), `languageCode`, `locationUule`, `resultsPerPage`.
- 자연검색 한 건: `type`(`organic`), `position`, `title`, `url`, `displayedUrl`, `description`, `emphasizedKeywords`, `siteLinks[]`, `productInfo`, `websiteTitle`, `date`(일부만).
- **`domain` 필드는 없다.** `url`에서 뽑아야 한다. `displayedUrl`은 소셜 결과에서 `130+ comments · 5 years ago`, `343.8K+ followers` 같은 글자가 와서 도메인으로 쓸 수 없다.
- 브랜드 사이트 `url`에는 `?srsltid=...`가 붙어 온다(deathwishcoffee.com, thinkjinx.com). 호출마다 바뀌는 값으로 보이므로 ❓ 식별 키에서는 떼야 한다.
- **1쪽의 자연검색은 10개가 아니다.** `resultsPerPage`는 10인데 실제로는 7개, 6개, 9개가 왔다.
- `websiteTitle`은 소셜 결과에서 `Facebook · <페이지 이름>`, `YouTube · <채널 이름>` 형태다. 계정 이름이 들어 있으므로 저장할지 정해야 한다(10절).

| 검색어 | 자연검색 순위(도메인) |
|---|---|
| `batiste dry shampoo` | 1 batistehair.com, 2 amazon.com, 3 ulta.com, 4 batiste-hair.eu, 5 facebook.com, 6 allure.com, 7 ebay.com |
| `death wish coffee` | 1 deathwishcoffee.com, 2 amazon.com, 3 reddit.com, 4 instagram.com, 5 walmart.com, 6 en.wikipedia.org |
| `jinx dog food` | 1·2·5·6 thinkjinx.com, 3 thedodo.com, 4 reddit.com, 7 tractorsupply.com, 8 chewy.com, 9 youtube.com |

- 다른 블록: `relatedQueries` 16개(같은 8개가 두 번 들어 있다), `peopleAlsoAsk` 4개(질문만 있고 답은 비어 있다), `aiOverview`는 `death wish coffee`에만 왔고 따로 과금되지 않았다.
- 실제 브라우저 화면과 순위를 나란히 대조하지는 않았다 ❓. 같은 날 사용자의 Chrome에서 본 `batiste dry shampoo` 화면은 결과 10개였고 여기서는 7개다.

### 11-5. 결과: 광고는 받지 못했다
- 세 검색어 모두 `paidResults: []`, `paidProducts: []`였다 ✅. 광고 추출 요금은 세 쪽 모두 차감됐다.
- 항목마다 `#debug.retryCount: 3`이고 오류 기록에 `Didn't get any paid results, retrying 1/3` ~ `3/3`이 있다 ✅. 수집기가 세 번 다시 시도했지만 광고를 받지 못했다는 뜻이다.
- 수집기가 저장한 결과 화면 HTML을 열어 보면 위쪽 광고 자리(`#tads`)와 아래쪽 광고 자리(`#tadsb`)는 있는데 **내용이 비어 있고**, 화면 글자 `Sponsored`는 0개다 ✅(`samples/apify/trial_html_ad_slots.md`). 수집기가 광고를 놓친 것이 아니라 받은 화면에 광고가 실리지 않았다.
- 같은 날 사용자의 Chrome으로 `batiste dry shampoo`를 열었을 때는 `Sponsored` 표시가 2개 보였다(메인 스레드 관찰). 그래서 이 0건은 **"광고가 없다"가 아니라 "이 경로로는 광고를 받지 못했다"일 수 있다** ❓. 원인은 확인하지 못했다.
- 광고 한 건의 필드는 여전히 README로만 안다 ❓: `type: "paid"`, `position` 대신 `adPosition`, 광고 순위는 자연검색과 따로 센다.
- 기록 규칙(제안): `paidResults`가 비어 있어도 "광고 없음"으로 적지 않는다. 광고는 "could not look"으로 적고, 한 건이라도 온 검색어만 광고 행을 만든다.

### 11-6. 과제 요구와 대조
| 요구 | 이 응답으로 채울 수 있나 |
|---|---|
| 누가 순위에 있나 | ✅ `organicResults[]`의 `position`과 `url`에서 뽑은 도메인 |
| 누가 광고를 사나 | ❌ 이번 시험에서는 0건. 받을 수 있는 경우가 있는지도 모른다 ❓ |

### 11-7. 남은 확인
- 광고를 받는 다른 액터를 브랜드 검색어 1개로 시험한다(11-8). 이 스레드 몫($0.05)의 잔액은 $0.017이다.
- 한 검색어를 실제 브라우저 화면과 나란히 놓고 순위가 맞는지 대조한다.

### 11-8. 광고를 준다고 적은 다른 Apify 액터 (스토어 정보와 README에서 읽음, 호출하지 않았다) ❓
- 공식 액터의 스토어 설명에도 광고를 준다고 적혀 있다. 우리 실행에서 0건이었던 것과 설명은 어긋나지 않는다. 광고 칸은 응답에 있었고 비어 있었다.
- `southern-data/google-search-ads-monitor`의 README에 따르면 **Google은 매번 광고를 싣지 않는다.** 출시 전 시험에서 나라 단위로는 페이지 로드의 33~58%, **도시를 지정하면 50~94%**에 광고가 있었다고 한다. 우리 시험은 도시를 지정하지 않았다(`locationUule` 비움).

| 액터 | 30일 실행(성공/전체), 사용자 | 단가(무료 요금제) | 광고 | 특징 |
|---|---|---|---|---|
| `cheapapi/google-serp-scraper` | 239/261, 36명 | 쪽당 $0.0015 + 실행 시작 $0.002 | 쪽 요금에 포함, `paidResults` | 자연검색과 광고를 함께 준다. 입력에 `location`, `device`, 화면 크기가 있다. 무료 요금제에서는 이 액터에 **월 $0.25까지만** 쓸 수 있다 |
| `southern-data/google-search-ads-monitor` | 8/8, 1명 | 검색 1회 $0.007 | 광고 전용 | 검색어마다 여러 번(`checksPerKeyword`, 기본 2) 열어 광고주별 한 행을 준다. `advertiserDomain`, 위치(top/bottom), 순위가 있다. 실행 사이에 `new_advertiser`, `advertiser_gone`을 표시한다. 자연검색은 주지 않는다 |
| `santamaria-automations/google-search-scraper` | 7,195/7,508, 108명 | 쪽당 $0.006 + 광고 시도 $0.006 | `extractAds` | 공식 액터와 방식이 비슷하다(프록시를 바꿔 최대 2번 더 시도) |
| `clearpath/dataforseo` | 2,525/2,541, 54명 | 1,000크레딧에 $0.99 | DataForSEO SERP | 무료 요금제는 평생 10회, 실행당 10행. **Google Ads 검색량**도 준다(6절의 "검색량이 없다"를 풀 수 있다) |

- 이 표의 수치와 기능은 모두 각 액터의 스토어 정보와 README에서 읽은 것이다. `cheapapi`만 11-9에서 실제로 호출했다.

### 11-9. `cheapapi/google-serp-scraper` 시험 (2026-11-10 08:14~08:17 UTC): 광고 0건, 순위는 공식 액터와 크게 달랐다 ✅
- 입력(`samples/apify/cheapapi_input.json`): `batiste dry shampoo` 1개, 미국, **도시 지정 `New York,New York,United States`**, 데스크톱, 1쪽, 부가 기능 끔, 처리 속도 standard. 실행 상한 `maxTotalChargeUsd=0.05`가 그대로 받아들여졌다(이 액터는 최솟값이 없다). 186초 걸렸다.
- **차감액 $0.00601** = 액터 요금 $0.0035(실행 시작 $0.002 + 결과 1쪽 $0.0015) + Apify 플랫폼 사용료 약 $0.0025. 이 액터는 플랫폼 사용료가 따로 붙는다(공식 액터는 붙지 않았다).
- 결과(`samples/apify/cheapapi_run_dataset.json`): 쪽 행 1개 + 자연검색 행 8개. `searchUrl`에 `uule`(위치)이 들어간다.
- **광고: `paidResults: []`** ✅. 쇼핑 블록 3개(`In stores nearby`, `Popular products`, `More products`)는 `popular_products` 형식이고, Sponsored 표시가 없는 무료 상품 목록으로 보인다 ❓.
- **자연검색: 공식 액터와 결과가 크게 달랐다** ✅.

| 순위 | 공식 액터(07:10, 미국 전체) | cheapapi(08:15, 뉴욕) |
|---|---|---|
| 1 | batistehair.com | target.com |
| 2 | amazon.com | allure.com |
| 3 | ulta.com | themomedit.com |
| 4 | batiste-hair.eu | sallybeauty.com |
| 5 | facebook.com | sallybeauty.com |
| 6 | allure.com | walgreens.com |
| 7 | ebay.com | ebay.com |
| 8 | 없음 | amazon.com |

- cheapapi에서는 **batistehair.com이 1쪽에 없다**(`rankTracking`: `found: false`, 광고와 지역 목록에도 없음). 위치 차이(미국 전체 / 뉴욕) 때문인지, 한쪽의 해석이 틀린 것인지는 가릴 수 없다 ❓. cheapapi는 결과 화면 HTML을 남기지 않는다.
- 이 차이는 정확도에 직접 걸린다. 같은 검색어도 위치 설정에 따라 순위가 달라지므로, 행마다 위치와 요청 URL을 남기고 실제 화면과 대조할 때도 같은 위치로 봐야 한다.
- 출력 형식은 공식 액터보다 쓰기 좋다 ✅: 자연검색에 `domain`, `position`(자연검색 순위), `absolutePosition`(AI Overview와 상품 블록을 포함한 화면상 순서)이 있고, `rankTracking`이 브랜드 도메인의 순위를 따로 준다.
- 그 밖에 연관 검색어에 `Batiste dry shampoo lawsuit`, `recall`이, People also ask에 "How safe is Batiste dry shampoo?"가 있었다.

### 11-10. 광고 결론 (제안)
- 방식이 다른 두 액터(공식: HTTP 요청 + 광고 전용 프록시 3회 재시도, cheapapi: 브라우저 흉내 + 도시 지정)로 브랜드 검색어를 열었고, **광고는 모두 0건**이었다. 같은 날 사용자 Chrome에서는 `batiste dry shampoo`에 Sponsored 2개가 있었다.
- 그래서 **"누가 광고를 사나"는 이 경로들로는 "could not look"으로 기록**하자는 것이 이 스레드의 제안이다. 광고 전용 액터(`southern-data`, 2회 확인 $0.014)가 남은 시도지만, 이 스레드 몫의 잔액($0.0109)을 넘는다.
- 이 스레드의 Apify 차감 합계: $0.03305 + $0.00601 = **$0.03906**.

## 12. 결정 (2026-11-10, 사용자)
- **순위 수집기: 공식 `apify/google-search-scraper`.** 이유: 받은 결과 화면 HTML을 남겨(`htmlSnapshotUrl`) 행마다 대조할 근거가 있고, 브랜드 검색어에서 브랜드 사이트 1위라는 그럴듯한 결과를 냈으며, Apify가 직접 관리한다. `cheapapi`는 더 싸지만 HTML을 남기지 않고, 브랜드 사이트가 1쪽에 없는 결과를 냈다.
- **광고 추출(`focusOnPaidAds`)은 끈다.** 두 액터 모두 브랜드 검색어에서 광고를 받지 못했다. 광고는 수집하지 않고 검색어마다 "could not look"으로 기록한다.
- 비용: 검색 1회 $0.0045. 5개 브랜드 × 20개 = 1회 실행 약 $0.45. 실행 상한은 $0.50 이상만 걸 수 있다(11-2).
- 위치: 미국 전체(`countryCode: us`, 도시 지정 없음), 영어, 데스크톱, 1쪽. 행마다 요청 URL(`searchQuery.url`)과 수집 시각을 남긴다.
- 남은 확인: 같은 검색어를 미국 IP의 일반 브라우저로 열어 순위가 맞는지 사람이 대조한다(11-9의 두 결과 중 어느 쪽이 맞는지).

## 13. 검색어 20개: 고정 (2026-11-10) ✅
- 파일: `samples/keywords.json`(브랜드별 20개, 순서, 출처 `seed#n`/`<글자>#<순위>`, 뺀 검색어와 이유). 6-4 레시피를 그대로 썼다. 수집기는 이 파일만 읽고 목록을 다시 만들지 않는다.
- 나머지 3개 브랜드의 알파벳 확장을 새로 받았다: `samples/alpha_living_proof.json`, `alpha_death_wish_coffee.json`, `alpha_black_rifle_coffee.json`. 요청 81번, 1.5초 간격, 모두 200.
- **뺀 것: 브랜드가 아닌 다른 대상과 채용 검색.** Living Proof에서 노래와 교회(`gregory alan isakov lyrics`, `katy nichole`, `ministries`, `of a loving god`), 세 브랜드에서 `jobs`. 기업 관련 검색(`stock`, `owner`, `headquarters`)은 시드 자체의 상위 제안이라 남겼다.
- **자동완성 순서는 몇 시간 만에 바뀐다** ✅. `death wish coffee`의 시드 제안 10개 중 4개가 14:17과 17:24 사이에 바뀌었다(`k cups`, `mugs`, `power surge`, `near me`가 빠지고 로스트별 `caffeine content` 4개가 들어왔다). Living Proof도 1개가 바뀌었고 Black Rifle은 같았다. 그래서 **목록은 한 번 정해 파일로 고정하고 수집기는 그 파일만 읽는다**(제안).
- 한계: 11~20위는 알파벳 앞쪽 글자(a~k 근처)의 1위 제안으로 채워진다. 그래서 `walmart`, `ulta`, `near me`, `recall` 같은 판매·평판 검색어가 뒤 글자라는 이유로 빠진다(예: Batiste의 `walmart`, `ulta`, `near me`, `recall`). 손으로 고르지 않고 기계적 규칙을 그대로 쓴 것은 누가 다시 만들어도 같은 목록이 나오게 하기 위해서다.

## 14. attribute 안 (이 스레드 제안, 한 테이블 스키마는 메인 스레드가 정한다)
`part1/docs/attribute-candidates.md` 3-3의 "자연검색 결과"를 이 소스의 실제 응답(11-4)에 맞췄다.

**한 행 = (브랜드, 검색어, 수집 실행, 자연검색 결과 1개).**

| attribute | 원본(공식 액터) | 비고 |
|---|---|---|
| brand | 입력 | |
| keyword, keyword_rank, keyword_origin | `samples/keywords.json` | 순위 1~20, 출처 `seed#n` / `<글자>#<순위>` |
| result_type | `organicResults[].type` | 지금은 `organic`만 |
| position | `organicResults[].position` | 자연검색 안의 순위 |
| url | `organicResults[].url` | 원본 그대로 저장 |
| url_key | `url`에서 `srsltid` 등 추적 파라미터를 뗀 것 | 재실행 중복 판단에 쓴다 |
| domain | `url`의 호스트(`www.` 제거) | 응답에 `domain` 필드가 없다 |
| domain_class | 도메인 대응표(사람이 관리) | brand / retailer / marketplace / media / community / social / reference / other. 브랜드 도메인에는 batiste-hair.eu 같은 지역 사이트도 넣는다 |
| title, description | `title`, `description` | |
| source_url | `searchQuery.url` | 예: `http://www.google.com/search?q=batiste+dry+shampoo&gl=us&hl=en` |
| context | `searchQuery.countryCode`, `device`, `languageCode`, `page` | US / DESKTOP / en / 1 |
| observed_at | 실행 종료 시각(UTC) | 공식 액터는 항목별 시각을 주지 않는다 |
| run_id, html_snapshot_url | 실행 ID, `htmlSnapshotUrl` | 대조용. 스냅샷 보관 기간은 확인하지 못했다 ❓ |

- **광고**: 검색어마다 `could_not_look`으로 한 번 기록한다(12절). `paidResults`가 비었다는 이유로 "광고 없음"으로 적지 않는다.
- **재실행**: 같은 (브랜드, 검색어, url_key)는 같은 항목이다. 지난 실행에 1쪽에 있었는데 이번에 없으면 삭제하지 않고 ended로 표시한다. 순위는 실행마다 관측값으로 쌓는다.
- **빈 결과**: 검색어 하나가 실패하면 그 검색어만 `could_not_look`으로 적는다. 응답을 받았는데 결과가 0개일 때만 "nothing found"다.
- **저장하지 않는 것**: `websiteTitle`(소셜 결과에 `Facebook · <페이지 이름>`처럼 계정 이름이 들어 있다), 소셜 결과의 `displayedUrl`(`343.8K+ followers` 같은 글자), People also ask의 답, 연관 검색어(필요하면 별도 행으로 메인 스레드가 정한다).

### 14-1. 이 소스로 정리할 수 있는 것: 검색어별 매장 노출 순서
- 검색어마다 `domain_class`가 brand / retailer / marketplace인 행을 `position` 순으로 늘어놓으면 "이 검색어를 치면 어느 매장이 몇 위로 나오는지"가 된다. 20개 검색어를 모으면 매장별 등장 횟수와 평균 순위가 나온다.
- 시험 응답(11-4, 공식 액터)으로 만든 예 ✅:

| 검색어 | 매장 노출 순서(자연검색 순위) |
|---|---|
| `batiste dry shampoo` | 1 batistehair.com(브랜드) → 2 Amazon → 3 Ulta → 4 batiste-hair.eu(브랜드 EU) → 7 eBay |
| `death wish coffee` | 1 deathwishcoffee.com(브랜드) → 2 Amazon → 5 Walmart |
| `jinx dog food` | 1·2·5·6 thinkjinx.com(브랜드) → 7 Tractor Supply → 8 Chewy |

- `domain_class` 대응표 시작안(사람이 관리, 처음 보는 도메인은 other로 두고 채운다):
  - brand: batistehair.com, batiste-hair.eu, livingproof.com, deathwishcoffee.com, blackriflecoffee.com, thinkjinx.com
  - retailer: walmart.com, target.com, ulta.com, sephora.com, sallybeauty.com, walgreens.com, cvs.com, kroger.com, chewy.com, petsmart.com, petco.com, tractorsupply.com
  - marketplace: amazon.com, ebay.com
  - community: reddit.com / social: instagram.com, facebook.com, youtube.com, tiktok.com / reference: wikipedia.org

## samples/
| 파일 | 내용 |
|---|---|
| `apify/trial_input.json` | Apify 시험 입력(검색어 3개, 미국, 1쪽, 광고 켬, 부가 기능 전부 끔) |
| `apify/trial_run_dataset.json` | 시험 실행의 원본 응답(항목 3개). `htmlSnapshotUrl`의 서명 값만 `REDACTED`로 바꿨다 |
| `apify/trial_run_summary.json` | 실행 기록에서 상태, 시각, 과금 항목 수, 차감액, 단가만 옮긴 것(계정 식별값은 뺐다) |
| `apify/trial_html_ad_slots.md` | 결과 화면 HTML 3개에서 광고 자리 마크업만 뽑은 것. HTML 전체(각 1.1~1.7 MB)는 저장하지 않았다 |
| `apify/cheapapi_input.json`, `cheapapi_run_dataset.json`, `cheapapi_run_summary.json` | `cheapapi/google-serp-scraper` 시험의 입력, 원본 응답(행 9개), 실행 요약(11-9) |
| `google_search_captcha_sorry_page.html`, `.png` | 직접 수집 시 나온 CAPTCHA 화면. 본문의 IP 주소는 이 컴퓨터의 VPN 출구 주소다 |
| `suggest_batiste.json`, `suggest_living_proof.json`, `suggest_death_wish_coffee.json`, `suggest_black_rifle_coffee.json`, `suggest_jinx.json` | 자동완성 원본. 끝에 상태 코드(`200`)가 한 줄 붙어 있다 |
| `alpha_batiste.json`, `alpha_batiste_dry_shampoo.json`, `alpha_jinx_dog_food.json`, `alpha_living_proof.json`, `alpha_death_wish_coffee.json`, `alpha_black_rifle_coffee.json` | 알파벳 확장. 키는 호출한 입력, 값은 제안 목록 |
| `keywords.json` | 고정한 검색어 목록(5개 브랜드 × 20개, 13절) |
| `recipe_sketch.py` | 6-4 레시피의 스케치(참고용, 구현이 아님) |

용량 약 100 KB. 줄인 것: 없음. 저장하지 못한 것: 실제 검색 결과 페이지(차단).
