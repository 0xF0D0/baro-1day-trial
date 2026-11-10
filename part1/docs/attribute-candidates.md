# Part 1 광고 / 비광고 분리와 attribute 후보

표기:
- ★ 과제 명세가 요구하는 항목
- ✅ 2026-11-10 접근 조사에서 실제로 확인함
- ○ 있을 것으로 예상하지만 미확인
- ✕ 제공되지 않음
- EU: EU 노출 광고에만 제공됨

## 1. 분류

**광고 여부는 소스가 아니라 행(row)의 속성으로 둔다.** #4, #5, #6, #8은 한 소스 안에 광고와 비광고가 섞여 있다.

| # | 소스 | 분류 | 섞여 있는 부분 |
|---|---|---|---|
| 1 | Google Ads Transparency | 광고 | |
| 2 | TikTok Ad Library | 광고 | |
| 3 | Meta Ad Library | 광고 | |
| 6 | Google 검색 결과 | **혼합** | "who buys ads"는 검색광고 = 광고, "who ranks"는 자연검색 = 비광고 |
| 4 | Amazon | 비광고(매대) | 검색 결과의 Sponsored 슬롯은 광고 ○ |
| 5 | 리테일 매대 | 비광고(매대) | Sponsored 슬롯 있음. Target 검색 API가 `include_sponsored=true` 사용 ✅ |
| 7 | 검색 관심도 | 비광고(수요) | |
| 8 | TikTok 게시물 | 비광고(소셜) | "Paid partnership" 라벨이 붙은 게시물은 광고성 ○ |
| 9 | TikTok Shop | 비광고(매대) | |
| 10 | 자사몰과 환영 메일 | 비광고(자사 채널) | 유료 매체는 아니지만 프로모션 메시지임 |

비광고 하위 그룹:
- **매대**: #4, #5, #9, #10 상품
- **리뷰**: #4, #5
- **검색 수요**: #6 자연검색, #7
- **소셜**: #8
- **자사 채널**: #10 오퍼와 메일

---

## 2. 광고 attribute 후보

열 머리: G = Google ATC, T = TikTok Library, M = Meta Library, S = Google 검색광고

### 2-1. 식별과 출처
| attribute | G | T | M | S | 비고 |
|---|---|---|---|---|---|
| ad_id | ○ 소재 ID | ○ | ✅ Library ID | ✕ | S는 키워드+광고주+헤드라인 해시로 대체 |
| advertiser_name | ✅ Church & Dwight Co., Inc. | ✅ | ○ 페이지 이름 | ○ 표시 도메인 | 모회사 명의와 브랜드가 다를 수 있음 |
| advertiser_id | ○ AR… | ○ | ○ page_id | ✕ | 브랜드 프로필의 매핑 키 |
| advertiser_verified | ✅ | ✕ | ○ | ✕ | |
| brand_match_method | 도메인 | 이름 | page_id | 키워드 | 우리가 붙이는 값: 어떻게 이 브랜드로 판정했는지 |
| detail_url | ○ | ○ | ○ | ✕ | 원본 퍼머링크(where) |

### 2-2. 크리에이티브
| attribute | G | T | M | S | 비고 |
|---|---|---|---|---|---|
| ★ format | ✅ 텍스트/이미지/영상 필터 | 영상 | ○ 이미지/영상/캐러셀 | 텍스트 | |
| ★ headline, body_text | ○ | ○ 캡션 | ✅ | ○ | |
| cta_text | ○ | ○ | ○ | ✕ | "Shop now" 등 |
| landing_url, landing_domain | ○ | ○ | ○ | ○ | 자사몰로 가는지 리테일러로 가는지 |
| ★ media_file | ○ 이미지, YouTube 영상 | ★ ○ 영상 | ★ ○ | ✕ | 경로, sha256, mime, 길이, 크기 |
| variant_count | ✕ | ✕ | ✅ "4 ads use this creative and text" | ✕ | 같은 소재 묶음 |
| language | ○ | ○ | ○ | ○ | |

### 2-3. 노출과 기간
| attribute | G | T | M | S | 비고 |
|---|---|---|---|---|---|
| ★ platform_first_shown | ○ | ✅ | ✅ "Started running on" | ✕ | 플랫폼이 보고한 값 |
| ★ platform_last_shown | ○ | ✅ | ○ 종료된 광고만 | ✕ | |
| platforms | ✅ 필터 있음(Search/YouTube/Display…) | TikTok | ✅ FB/IG/Messenger/AN | Search | |
| country | ✅ US | ✅ EU 범위 | ✅ US | ○ gl=us | |
| reach | ✕ | ✅ "Unique users seen: 0-1K" | EU | ✕ | |
| targeting (연령/성별/지역) | ✕ | EU ○ | EU | ✕ | |
| spend | ✕ | ✕ | ✕ | ✕ | 정치 광고에만 공개됨. 수집 대상 아님 |

### 2-4. 검색광고(S)에만 있는 것
- ★ query: 어떤 검색어에서 나왔는지
- ad_position: 상단 1~4, 하단
- is_brand_owner: 브랜드 본인 광고인지, 경쟁사가 브랜드 키워드에 입찰한 것(conquesting)인지
- display_url, sitelinks

### 2-5. 우리 쪽 관측값 (모든 행 공통)
- first_seen_by_us, last_seen_by_us, status(active/ended), run_id
- 플랫폼이 보고한 기간(`platform_first/last_shown`)과 **우리가 본 기간은 별도 컬럼으로 둔다.** 둘은 다르다

### 2-6. 파생 후보 (나중에 LLM이나 비전 모델로 추출. 원본을 저장해 두면 재처리 가능)
- offer: % 할인, 무료배송, 번들
- 등장 제품
- 핵심 메시지/주장: 예) "no white residue"
- 첫 3초 훅
- UGC 스타일인지 스튜디오 촬영인지, 크리에이터 출연 여부
- 시즌성: 홀리데이 등

---

## 3. 비광고 attribute 후보

### 3-1. 매대 (#4 Amazon, #5 리테일, #9 TikTok Shop, #10 자사몰 상품)
| attribute | Amazon | 리테일 | TT Shop | 자사몰 | 비고 |
|---|---|---|---|---|---|
| product_id | ✅ ASIN | ○ SKU/TCIN | ○ | ✅ Shopify id | |
| gtin/upc, sku | ○ | ○ | ✕ | ○ sku | 채널 간 같은 상품을 묶는 키. 없으면 제목+용량으로 매칭 |
| title, variant/size | ✅ | ✅ | ○ | ✅ | |
| ★ price | ✅ $28.79 (ZIP 10001) | ✅ Sephora | ★ ○ | ○ variants | 위치(ZIP)에 따라 달라짐 |
| list_price, compare_at, discount_pct | ○ | ○ | ○ | ○ compare_at_price | |
| unit_price ($/oz) | ○ | ○ | ✕ | ✕ | |
| promo_badges | ○ 쿠폰, 정기배송(S&S) | ○ | ○ | ○ | |
| availability | ○ | ○ | ○ | ○ | |
| seller (1P/3P) | ○ | ✕ | ○ 샵 이름 | 브랜드 | |
| ★ rating_avg | ✅ 4.7 | ○ | ○ | ✕ | |
| ★ review_count | ✅ 1,014 | ○ | ○ | ✕ | |
| rating_histogram | ✅ | ○ Bazaarvoice | ✕ | ✕ | |
| ai_review_summary, aspect_tags | ✅ "Customers say", Residue(25) 등 | ✕ | ✕ | ✕ | 리뷰 본문의 대체재 |
| ★ rank (검색 순위) | ○ 자연/광고 구분 | ○ | ○ | ✕ | 검색어와 함께 저장 |
| ★ rank (카테고리 순위) | ✅ BSR #149 in Dry Shampoos | ✕ | ✕ | ✕ | |
| ★ sales_signal | ○ "N+ bought in past month" | ✕ | ★ ○ "N sold" | ✕ | |
| context | ✅ 검색어, ZIP | ○ 매장/ZIP | ○ | ✕ | 같은 상품도 조건에 따라 값이 다름 |
| launched_at | ✕ | ✕ | ✕ | ✅ published_at, created_at | 신제품 감지 |

### 3-2. 리뷰 (#4, #5)
- ★ 수집: review_id, rating, ★ body, title, date, verified_purchase, helpful_votes, 리뷰 대상 옵션, syndicated 여부(Bazaarvoice "originally posted on…")
- **수집하지 않음**: 리뷰어 이름, 프로필, 위치(일반인 개인정보)
- Amazon 리뷰 본문: `could_not_look`(로그인 필요) ✅ 확인. 리테일 리뷰는 Bazaarvoice 경유로 ○

### 3-3. 검색 수요 (#6 자연검색, #7 Trends)
- **키워드 집합**
  - keyword
  - keyword_source: 어디서 뽑았는지(Trends 연관 검색어 / 자동완성 / 수동)
- ★ **자연검색 결과** (who ranks)
  - query, position
  - result_type: organic / shopping / video / People Also Ask / AI Overview
  - url, domain, title, snippet
  - domain_class: 브랜드 / 리테일러 / 경쟁사 / 미디어
  - AI Overview에 브랜드가 언급되는지
- ★ **Trends**
  - week ✅, value(0~100) ✅
  - is_partial: 마지막 주 미완성 여부 ○
  - geo ✅, timeframe ✅, comparison_set ✅: 요청 조건. 값이 상대값이라 필수
  - related_queries(top/rising) ✅, related_topics ○, 하위 지역 관심도 ✅

### 3-4. 소셜 (#8 TikTok 게시물과 브랜드 계정)
- **게시물**
  - post_id, url, ★ posted_at
  - ★ creator_handle, creator_is_brand, creator_verified
  - ★ views, ★ likes, comments, shares, saves
  - caption, hashtags, sound, duration
  - paid_partnership: 광고성 플래그 ○
  - linked_shop_product: #9와 연결
  - surfaced_by: 어떤 검색어나 해시태그로 찾았는지, rank
- **브랜드 계정 스냅샷** (시계열로 쌓음)
  - followers ✅ 371.9K, total_likes ✅ 2.1M, video_count
- **개인정보**: 크리에이터는 공개 핸들과 공개 지표만 저장

### 3-5. 자사 채널 (#10)
- ★ **자사몰 오퍼**
  - 사이트 전체 배너 문구, 프로모 코드, % 할인
  - 무료배송 기준 금액, 정기구독 할인, 가입 팝업 오퍼, 번들
  - 신제품 ✅ published_at
- **Batiste**: 직판이 없으므로 where-to-buy 리테일러 목록(Swaven JSON ✅)으로 대체
- ★ **환영 메일**
  - signup_at, signup_url
  - received_at, hours_since_signup, sequence_no
  - from_name, from_address, subject, preheader
  - offer(%, 코드, 만료일), 등장 제품, CTA 링크 도메인
  - 본문(html/text) 원본

---

## 4. one table 설계에 주는 시사점
1. **`is_paid`(또는 `media_class`: paid / owned / earned / shelf / demand)를 행 단위 컬럼으로 둔다.** 소스 단위로 두면 #4, #5, #6, #8을 표현할 수 없다.
2. **여러 소스에 반복되는 attribute는 공통 컬럼으로 승격하고, 나머지는 JSON에 둔다.**
   - 광고 쪽: format, text, landing_url, media_path, platform, platform_first/last_shown
   - 비광고 쪽: product_ref, price, rating, review_count, rank, sales_count, views, likes
3. **플랫폼이 보고한 기간과 우리가 관측한 기간을 분리한다.**
4. **가격, 순위, 조회수, 팔로워는 시계열이다.** 아이템 정체성(중복 판단 키)과 측정 스냅샷을 어떻게 분리할지 스키마에서 결정해야 한다.
5. **같은 값이라도 조건(검색어, ZIP, 지역, 비교 키워드 묶음)이 다르면 다른 관측이다.** 조건을 `context` 컬럼으로 남긴다.
