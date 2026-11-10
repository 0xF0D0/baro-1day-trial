# Part 1 소스별 접근성 분석

- 조사일: 2026-11-10
- 조사 환경: 한국 IP(서울), Playwright 1.65 + 로컬 Google Chrome(`channel="chrome"`), 사이트당 요청 1~5회
- 방법: 실제 페이지를 열어서 상태 코드, 봇 차단 표식, 페이지가 스스로 호출하는 XHR/JSON 엔드포인트를 기록함

## 요약: 4단계

| 단계 | 의미 | 소스 |
|---|---|---|
| **A. 바로 가능** | 일반 브라우저 자동화로 열림 | #1 Google Ads Transparency, #3 Meta Ad Library(웹), #10 Shopify 자사몰 3곳, #5 Ulta·Sephora, #7 Trends(헤드풀만) |
| **B. 되지만 범위 제약** | 열리긴 하지만 원하는 데이터 일부가 구조적으로 없음 | #2 TikTok Ad Library(미국 광고 없음), #4 Amazon(리뷰 본문 로그인 필요), Batiste 자사몰(직판 없음) |
| **C. 미국 IP 필요** | 한국 IP라서 막힘 | Black Rifle 자사몰, Target, TikTok Shop |
| **D. 봇 차단/CAPTCHA** | 직접 코드로는 불가(CAPTCHA 우회 금지) → 유료 서비스 또는 `could_not_look` | #6 Google 검색 결과, #8 TikTok 게시물, Chewy |

## 소스별 상세

### 1. Google Ads Transparency Center: A
- `?region=US&domain=<도메인>`가 한국 IP에서도 미국 기준으로 동작함
- Batiste 도메인: 광고 65개, 전부 **Church & Dwight Co., Inc.** 명의
- Death Wish 도메인: 광고 39개
- 광고주 이름으로 "Church & Dwight"를 검색하면 약 3.1K개(모회사 전체 브랜드)가 나옴. 브랜드 단위로는 **도메인 검색이 정확함**
- 데이터 경로: 페이지가 호출하는 `anji/_/rpc/SearchService/SearchCreatives`의 응답을 가로챔
- 남은 확인: 소재 상세의 first/last shown 필드, 영상 소재 형식(YouTube 링크 여부)

### 2. TikTok Ad Library: B (범위 제약)
- 로그인 없이 접근 가능
- 지원 지역(`/api/v1/support-regions` 응답): EEA 30개국, 스위스, 영국, 튀르키예, 브라질. **미국은 없음**
- Black Rifle Coffee, Jinx 모두 0건
- 기록 원칙: `none_found`, 범위 = "EEA/CH/GB/TR/BR". 이 결과로 "TikTok 광고를 하지 않는다"고 결론내면 안 됨
- 보완책: TikTok Creative Center Top Ads(`region=US`)는 로그인 없이 열림. 다만 "전체 광고"가 아니라 "성과 상위 광고" 샘플임
- 남은 확인: 광고 상세 페이지의 영상 파일 URL

### 3. Meta Ad Library: A
- 로그인 없이 `country=US`, `active_status=active`로 동작함
- 문서 응답 코드는 **403인데 본문은 정상 렌더링**됨. 상태 코드가 아니라 내용으로 성공 여부를 판정해야 함
- 키워드 검색("death wish coffee")은 약 7,600건이 나와서 노이즈가 큼. **페이지 ID(`view_all_page_id`) 기준 검색**이 필요함
- 데이터 경로: `/api/graphql/` 응답을 가로챔
- 미디어 URL은 서명된 CDN 주소라 만료됨. 수집할 때 바로 다운로드해야 함

### 4. Amazon: B (리뷰 본문 불가)
- 검색과 상품 페이지가 한국 IP에서 낮은 빈도로는 열림(약 5회 요청, CAPTCHA 없음)
- 그냥 열면 가격이 KRW로 나옴. "Deliver to" UI에서 ZIP 10001을 입력하니 USD $28.79로 바뀜
- 수집 가능: 제목, 가격, 별점 4.7, 리뷰 수 1,014, BSR(#149 in Dry Shampoos), 별점 분포, AI 요약("Customers say"), 측면 태그(Effectiveness(88), Residue(25) …)
- **리뷰 본문은 비로그인 상태에서 0개**("Sign in to see customer reviews."). `/product-reviews/`는 로그인 페이지로 리다이렉트됨
- 기록 원칙: 리뷰 본문은 `could_not_look`(로그인 필요)으로 남기고, AI 요약과 분포로 대체한 사실을 명시함
- 리스크: 요청 수가 늘면 CAPTCHA가 뜸. 상위 상품 N개만, 요청 사이 간격을 둠

### 5. 리테일 매대: 브랜드별로 다름
| 리테일러 | 결과 | 비고 |
|---|---|---|
| Ulta (Batiste) | A: 29개 상품 | `/dxl/graphql` |
| Sephora (Living Proof) | A: 57개, 가격 노출 | `/gway/v1/browsegraph/graphql` |
| Target (커피 2종, Jinx 후보) | C: "This page is currently unavailable", redsky API 435 | 한국 IP 차단으로 추정, PerimeterX 있음 |
| Chewy (Jinx 후보) | D: 헤드풀 Chrome에서도 429와 Kasada(KPSDK) 챌린지 | |
| (참고) Walmart | A: 열림, PerimeterX를 1회 통과 | 과제가 허용한 4곳에 포함되지 않음 |

결론: 커피 2종과 Jinx는 사실상 **Target(미국 IP 필요)** 이 유일한 현실적 선택지임

### 6. Google 검색 결과: D
- 첫 자동화 검색부터 `/sorry/` reCAPTCHA가 뜸. CAPTCHA 우회는 금지
- Custom Search JSON API는 신규 고객을 받지 않고 2027-01-01 종료 예정. 광고 결과도 주지 않음
- 현실적 경로: 유료 SERP API(5개 브랜드 × 20개 검색어 = 100쿼리). 규칙상 "최소 1개 소스만 직접 코드"면 되므로 허용 범위임
- "상위 20개 검색어"는 #7 Trends의 `relatedsearches`(동작 확인)와 자동완성에서 뽑을 수 있음

### 7. Google Trends: A (헤드풀 조건)
- 헤드리스는 첫 요청부터 429
- 헤드풀 Chrome으로 홈을 먼저 열고 explore를 여니 정상 동작함
- 페이지가 호출하는 위젯 응답을 가로챔: `widgetdata/multiline`(12개월 주간), `relatedsearches`, `comparedgeo`
- 값은 0~100 상대값임. 요청 조건(키워드 묶음, 지역, 기간)을 함께 저장해야 함

### 8. TikTok 게시물: D
- 검색(`/search/video`)과 해시태그(`/tag/`) 페이지에 슬라이더 CAPTCHA("Drag the slider to fit the puzzle")가 뜸
- 브랜드 프로필(`@deathwishcoffee`)은 열림: 팔로워 371.9K, 좋아요 2.1M. 영상 그리드는 렌더링되지 않음
- Research API는 학술 연구용이라 사용할 수 없음
- 현실적 경로: 유료 서비스, 또는 직접 코드로는 `partial`/`could_not_look`

### 9. TikTok Shop: C (그 다음 D 가능성)
- `/shop/s/...`가 `enter_method=not_supported_region`으로 리다이렉트됨. 한국에서는 지역 미지원
- 미국 IP로도 TikTok 본체와 같은 봇 차단이 있을 가능성이 높음(미확인)

### 10. 자사몰과 환영 메일
| 브랜드 | 도메인 | 결과 |
|---|---|---|
| Living Proof | livingproof.com | Shopify. curl로도 `products.json` 응답 200 |
| Death Wish | deathwishcoffee.com | Shopify. curl은 429, **브라우저로는 200** |
| Jinx | **thinkjinx.com** | Shopify, 브라우저로 200. `jinx.com`은 2023년에 폐업한 다른 회사(J!NX 의류)임 |
| Black Rifle | blackriflecoffee.com | C: curl, 헤드리스, 헤드풀 모두 Cloudflare "Sorry, you have been blocked". 한국 IP 차단으로 추정 |
| Batiste | batistehair.com | IIS/ASP.NET 브랜드 사이트, 직판 없음. Where-to-buy(Swaven JSON)와 Bazaarvoice만 있음 |

- 환영 메일: 직접 관리하는 수신함에서 Gmail API나 IMAP으로 수집(미검증). Batiste는 뉴스레터 가입 폼이 있는지부터 확인해야 함

## 전체에 걸친 결론
1. **미국 IP가 가장 큰 변수.** Black Rifle 자사몰, Target, TikTok Shop이 여기서 막힘. 미국 리전 클라우드 VM이나 VPN으로 해결할 수 있음. 레지덴셜 프록시는 유료 서비스라 회색 지대임
2. **헤드풀 Chrome이 필요함.** Trends는 헤드리스에서 막힘. 서버에서 돌리면 xvfb 같은 가상 디스플레이가 필요함
3. **응답 가로채기 패턴을 씀.** 내부 API를 키로 직접 호출하지 않고, 실제 페이지를 열어서 페이지가 받는 JSON을 가로챔. 사이트 입장에서 일반 방문과 같아서 더 깨끗함
4. **상태 코드는 진실이 아님.** Meta는 403인데 정상이었고, jinx.com은 200인데 엉뚱한 회사 페이지였음. `coverage` 판정은 콘텐츠 검증으로 해야 함
5. **브랜드 프로필이 필요함.** 도메인, 광고주 명의, Meta 페이지 ID, TikTok 핸들, 리테일러를 브랜드마다 명시함
