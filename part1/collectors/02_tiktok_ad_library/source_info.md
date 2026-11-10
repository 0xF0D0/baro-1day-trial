# 소스 2: TikTok 광고: Creative Center Top Ads(미국)를 Apify로 수집

> **결정 (사용자, 2026-11-10):** 이 소스는 **Creative Center Top Ads(미국)만** Apify `fetch_cat`으로 수집한다. 수집 방법과 attribute는 9-1절, 근거와 한계는 12절에 있다. EU Ad Library(1~8절, 10절)는 미국 광고를 담지 않아 **쓰지 않는다.** 그 절들은 조사 기록으로만 남긴다.

- 확인일: 2026-11-10 (미국 IP, 화면이 뜨는 Chrome을 Playwright로 실행)
- 확인 대상: 다섯 브랜드 이름·키워드 검색 약 30회, Batiste 광고 상세 1건, 영상 내려받기 1건, Creative Center 목록 1회
- 2차 확인: 2026-11-10 06:09~06:20 UTC. 페이지 열기 5회(상세 1, 목록 1, 목록 카드를 눌러 연 상세 3), 검색 요청 2회, 손으로 만든 상세 요청 1회(421로 거절, 2절). CAPTCHA·로그인 화면은 없었다. 접속 IP 지역은 이번에 확인하지 않았다.
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정이거나 미확인
- 요약: **미국 광고는 이 소스에 없다.** 유럽 등 지원 지역에 나간 광고만 있다. 다섯 브랜드 중 Batiste만 잡혔다. 본인 계정(스페인 5건)과 모회사 Church & Dwight 계정이 있고, 모회사 UK 계정의 광고는 올린 TikTok 계정(`batiste_hair`)으로 Batiste임을 가를 수 있다(3절). 나머지 넷은 찾지 못했다.

## 1. 이 소스가 주는 것
TikTok이 공개하는 상업 광고 라이브러리(EU 디지털서비스법 때문에 만든 것)다. **한 행은 광고 1개**이고, 영상 파일 주소·표지 이미지·광고 문구·노출 지역별 도달 수까지 준다. 단 지원 지역은 아래 목록뿐이다.

- 지원 지역 34곳 ✅ (`api/v1/support-regions`, `samples/support_regions.json`): EEA 국가 + CH, GB, TR, BR. **US는 없다.**
- 화면의 검색 조건 "Ad target country"를 "All countries"로 둬도 이 34곳 안에서만 찾는다 ✅.

## 2. 접근 방법
- 주소: `https://library.tiktok.com/ads?region=all`. 로그인이 필요 없다 ✅. CAPTCHA나 확인 화면은 한 번도 뜨지 않았다 ✅.
- 헤드리스 실행은 확인하지 않았다 ❓ (화면이 뜨는 Chrome으로만 했다).
- 페이지가 스스로 보내는 요청을 가로채서 저장한다.

| 요청 | 언제 나가나 | 담긴 것 |
|---|---|---|
| `GET api/v1/support-regions?lang=en-US` | 페이지 열 때 | 지원 지역 목록 |
| `GET api/v1/location` | 페이지 열 때 | 접속자 지역(`US`) |
| `POST api/v1/suggestion` | 검색창에 글자를 칠 때 | 광고주 이름 후보와 광고주 ID |
| `POST api/v1/search?region=all&type=1&start_time=<초>&end_time=<초>` | Search 버튼을 누를 때 | 광고 목록(12개씩) |
| `GET api/v1/items/<광고ID>/details?lang=en-US` | 상세 페이지(`/ads/detail/?ad_id=<광고ID>`)를 열 때 | 광고 1개의 전체 정보 |
| `GET api/v1/cdn/<시각>/video/<인코딩>/<uuid>?...` | 상세 페이지가 영상을 불러올 때 | 302로 CDN 영상 주소 안내 |

- 페이지 열기는 약 10번 했다(검색은 페이지 안에서 반복했다). 광고 상세 페이지는 목록에서 링크(`a href`)로 이어진다 ✅.
- 검색창에서 Enter를 눌러도 검색이 나가지 않는다. **Search 버튼을 눌러야 한다** ✅.

### 2-1. 광고주 ID로 바로 여는 주소 (2차 확인)
- 상세 화면의 "See all ads" 링크가 이 형식이다 ✅: `https://library.tiktok.com/ads?adv_name=<광고주 이름>&region=all&query_type=2&adv_biz_ids=<광고주 ID>`
- 이 주소를 열면 검색창에 광고주가 채워지지만 **검색은 나가지 않는다** ✅. Search 버튼을 한 번 눌러야 `query_type:"2"`, `adv_biz_ids:"<ID>"`로 요청이 나간다 ✅ (C&D UK로 확인, 이름을 쳐서 후보를 고르는 동작이 필요 없다).
- **주의:** Search를 누르기 전 화면에 이미 "Total ads: 0 / No ads found"가 떠 있다 ✅. 화면 글자가 아니라 **검색 응답을 실제로 받았을 때만** 0건으로 기록해야 한다.
- 날짜를 주지 않으면 기간은 **지금부터 31일 전까지**(초 단위 현재 시각 기준)다 ✅. 검색 뒤 주소창은 `...&start_time=<밀리초>&end_time=<밀리초>&adv_name=...&adv_biz_ids=...&query_type=2&sort_type=create_time,desc&ad_type=0&ad_status=1&ages=all&ad_reach=all&gender=ALL`로 바뀐다 ✅. 이 주소에 `start_time`/`end_time`을 직접 넣어 열면 기간이 그대로 잡히는지는 확인하지 않았다 ❓.
- 목록 카드는 `a[href="/ads/detail/?ad_id=<ID>"][target=_blank]`이고, 누르면 새 탭에서 상세가 열리며 상세 요청이 나간다 ✅ (3건 모두 200).

### 2-2. 손으로 만든 요청은 거절된다 (2차 확인)
- 페이지가 보내는 상세 요청에는 `x-ccl-str`라는 전용 헤더가 붙는다 ✅ (헤더 이름만 확인했고 값은 남기지 않았다).
- 같은 페이지 안에서 `fetch('/api/v1/items/<ID>/details?lang=en-US')`를 직접 부르면 **421 `system busy`**가 온다 ✅ (1회 시도, 재시도하지 않았다). 이 헤더를 흉내 내는 일은 하지 않는다.
- 따라서 **수집은 페이지를 조작해서(주소 열기 → Search → View more → 카드 누르기) 페이지가 스스로 보낸 응답을 받는 방식만 쓴다.** 영상 파일 주소만 예외로 일반 GET이 된다(5절).
- 새 탭을 만들어 상세 주소를 직접 `goto`했을 때 한 번 `net::ERR_ABORTED`로 이동이 취소됐다 ✅ (서버 응답이 아니라 브라우저 쪽 취소였고, 원인은 모른다 ❓). 첫 탭에서 상세 주소를 직접 여는 것과 카드를 누르는 것은 됐다 ✅.

## 3. 브랜드 매칭
검색 방법이 세 가지이고, **결과의 성격이 전혀 다르다.**

| 방법 | 요청 본문 | 성격 |
|---|---|---|
| (가) 키워드 | `query_type:"1"`, `query:"<글자>"` | 광고 문구(제목)에서 **단어 하나라도** 맞으면 잡는다. 점수순이다 ✅ |
| (나) 정확한 문구 | 후보 목록의 "Search this exact phrase"를 고르면 `search_clause:{search_terms:["<문구>"],search_type:1}` | 문구 전체가 같아야 한다 ✅ |
| (다) 광고주 | 후보 목록에서 광고주를 고르면 `query_type:"2"`, `adv_biz_ids:"<광고주ID>"` | 그 광고주 계정의 광고만 ✅. **브랜드를 찾는 방법은 이것뿐이다.** |

### 3-1. 브랜드별 결과 (기간: 2025-11-09 ~ 2026-11-10, 지역 전체)
기간은 화면 달력이 허용하는 가장 넓은 범위다. 2025-11-09보다 앞 날짜는 눌러지지 않는다 ✅. 처음 열면 기본값은 최근 30일(10/10~11/10)이다 ✅.

| 브랜드 | 광고주 계정(다) | (나) 정확한 문구 | (가) 키워드 | 판단 |
|---|---|---|---|---|
| Batiste | `Batiste` (ID `7078634489555092225`, 등록지 스페인): **5건** ✅ | `Batiste` 957건 | `Batiste` 957건 | 본인 계정 5건이 확실하다. 나머지는 대행사·재판매자 광고다(아래) |
| Church & Dwight (Batiste 모회사) | `CHURCH & DWIGHT UK LIMITED`(`6876491804275901185`) **181건**, `Church & Dwight Deutschland GmbH`(`6880429141854782210`) **120건**, `CHURCH & DWIGHT DEUTSCHLAND GmbH`(`7355423739376418832`) **10건** ✅ | 311건 | 5,000건 | 모회사 이름으로 집행한다. 독일 쪽 제목에 Batiste와 다른 브랜드(Hero 여드름 패치 등)가 섞여 있다 ✅ |
| Living Proof | 후보 없음 ✅ | 160건 (모두 일반 문구 "living proof"가 든 남의 광고) | 5,000건 (쓸모없음) | 못 찾음 |
| Death Wish Coffee | 후보 없음 ✅ | **0건** | 5,000건 (쓸모없음: "death wish" 단어가 든 드라마·게임 광고) | 못 찾음 |
| Black Rifle Coffee | `blackriflee`(`7618943895874846721`)가 후보로 뜨나 광고 **0건**. 이 계정이 브랜드 것인지는 모른다 ❓ | 3건 (개인 제작자 영상 1계정, 브랜드 아님) | 5,000건 (쓸모없음: "Sniper Rifle" 게임 광고) | 못 찾음 |
| Black Rifle Coffee Company / BRC | 후보 없음 (`BRC`는 무관한 계정만 뜬다) | 3건 (위와 같은 개인 계정) | 5,000건 / `BRC` 52건 | 못 찾음 |
| Jinx | `thinkjinx`(`7572734655321866248`)가 후보로 뜨고 광고 **0건** ✅. `JINX GmbH`는 다른 회사다 | `Jinx` 2,332건 (게임·웹툰 광고), `thinkjinx` 0건 | 2,329건 / `thinkjinx` 0건 | 못 찾음 |

- 키워드 결과의 5,000은 **상한**으로 보인다 ❓ (서로 다른 검색어 여럿이 정확히 5,000을 냈다).
- 후보 목록(`suggestion`)은 TikTok의 모든 계정 이름을 대상으로 한다. 일반 개인 계정(`batiste.47` 등)도 뜬다 ✅. 그래서 후보에 이름이 있다는 것이 광고를 낸다는 뜻이 아니다.
- **Batiste의 다른 광고는 본인 이름이 아니다.** 같은 상품을 판 광고가 `PUBLICITARII INVEST SERVICES S.R.L.`("Pass the Batiste!")과 포르투갈 대행사 `Media DuYes`(포르투갈어 Batiste 문구)의 이름으로 나온다 ✅. 광고주 이름만으로는 브랜드를 가를 수 없다.
- Church & Dwight UK의 181건(최근 31일로는 91건 ✅)은 제목이 비어 있어서 어떤 브랜드인지 목록만으로는 모른다 ✅.
- **C&D UK 광고는 상세의 "올린 계정"으로 브랜드를 가를 수 있다** ✅ (2차 확인, `samples/detail_cd_uk_3ads_summary.json`). 상세 3건 모두 `advertiser.tt_user.username`이 `batiste_hair`(표시 이름 `Batiste_hair`, `account_type:"BLUEV_BA"`, 팔로워 107.7K)였다. 비용 부담자는 `re:act Marketing` / `RE:ACT MARKETING LTD`였다.
  - 이 3건에는 제목·랜딩 주소·CTA·광고 목표가 **아예 없다** ✅ (`display_mode:"standard"`, 4-2). 랜딩 주소로 가르는 방법은 UK에서는 쓸 수 없다.
  - 3건만 본 것이다. 91건 전체가 `batiste_hair`인지, C&D의 다른 브랜드 계정이 섞여 있는지는 모른다 ❓. 광고마다 상세를 열어 판정해야 한다.
  - Batiste 스페인 계정의 상세에서는 `tt_user`가 `null`이었다 ✅. 올린 계정이 없는 광고도 있다.
  - 독일 계정 2곳(130건)의 상세는 열어 보지 않았다 ❓.
- 미국 브랜드가 EU에 광고를 내지 않으면 아예 안 나온다. Death Wish, Black Rifle, Living Proof, Jinx가 그 경우로 보이나, "EU에 광고를 안 낸다"와 "이 라이브러리가 못 잡는다"를 구분할 방법은 없다 ❓.

## 4. 원본 구조
JSON이고 필드 이름이 그대로 있다.

### 4-1. 목록 응답 `search` (`samples/search_advertiser_batiste.json`, `samples/search_keyword_church_dwight.json`)
응답 최상위: `data[]`, `total`(전체 개수, 키워드 검색은 5000이 상한으로 보임 ❓), `has_more`, `search_id`, `code`.

| 키 | 뜻 | 예시 | 근거 |
|---|---|---|---|
| `id` | 광고 ID | `"1880286032506130"` | ✅ 상세 주소에 쓰인다 |
| `name` | 광고주 이름 | `Batiste` | ✅ |
| `type` | 광고 종류 | `"2"` (본 광고 전부 2) | ❓ 뜻 모름 |
| `first_shown_date`, `last_shown_date` | 처음/마지막 노출일. 밀리초 단위, 하루 단위(00:00 UTC) | `1793145600000` = 2026-10-28, `1794096000000` = 2026-11-08 | ✅ 상세 화면의 "First shown 10/28/2026, Last shown 11/08/2026"과 일치 |
| `videos[].video_url` | 영상 주소(아래 5절) | | ✅ |
| `videos[].cover_img`, `image_urls[]` | 표지 이미지. 같은 주소 | | ✅ 내려받기 확인 (37 KB JPEG, `samples/batiste_cover.jpg`) |
| `estimated_audience` | 본 사람 수 구간 | `900K-1M` | ✅ 화면의 "Unique users seen"과 같다 |
| `title` | 광고 문구. 비어 있는 광고가 많다 | `Batiste refresca tu pelo...` | ✅ |
| `subject` | 광고 분류 | `Beauty & Personal Care` | ✅ |
| `spent`, `impression` | 빈 문자열, 0 | | ✅ 값이 없다 (광고비·노출 수는 안 준다) |
| `audit_status`, `sor_audit_status`, `show_mode`, `rejection_info` | 심사·표시 상태 | `"1"`, `"1"`, `1`, `null` | ❓ 뜻 모름 |

### 4-2. 상세 응답 `details` (`samples/detail_batiste_spain.json`)
`data.ad`는 목록의 필드에 더해 아래를 준다 ✅.

| 키 | 뜻 | 예시 |
|---|---|---|
| `external_url` | 연결된 사이트. 추적 인자 포함 | `https://www.batistehair.es/?utm_source=tiktok&...` |
| `call_to_action` | 행동 유도 문구(CTA) | `Watch now` |
| `advertising_objective` | 광고 목표 | `Reach` |
| `data.advertiser.name`, `adv_biz_ids`, `registry_location`, `sponsor` | 광고주 이름, ID, 등록 국가, 비용 부담자("Ad paid for by") | `Batiste`, `7078634489555092225`, `Spain`, `BE A TIGER` |
| `data.targeting.location.data[]` | 노출 국가별 도달 수와 나이·성별 분해 | `{"region":"ES","impressions":"981K","breakdowns":[{"age":"18-24","gender":"FEMALE","impressions":"327K"},...]}` |
| `targeting.countries[]`, `languages[]`, `age[]`, `gender[]` | 타깃 국가·언어·나이대·성별 | `["ES"]`, 언어 없음, 전 연령, 여성만 |
| `targeting.target_audience_size` | 타깃 모수 | `14.2M-17.4M` |
| `targeting.audience`, `interest`, `high_spending_power`, `operating_systems` 등 | 맞춤 타깃 사용 여부 | 이 광고는 모두 "Not used"/`No`/`ALL` |

**상세는 두 가지 형태로 온다** ✅ (2차 확인, `samples/detail_cd_uk_standard.json`).

| `data.display_mode` | 본 곳 | 있는 것 | 없는 것 |
|---|---|---|---|
| `enhanced` | Batiste 스페인 1건 | 위 표 전부. 도달 수의 나이·성별 분해 | `tt_user`(null) |
| `standard` | C&D UK 3건 | 광고주, 비용 부담자, 노출일, 도달 수(국가별 합계만), 영상, 분류, 타깃 나이·성별·관심사, `tt_user` | `title`, `external_url`, `call_to_action`, `advertising_objective` 키 자체가 없다. 나이·성별 분해는 빈 배열, `targeting.countries`도 빈 배열 |

- 무엇이 두 형태를 가르는지는 모른다 ❓ (EU 회원국 광고와 영국 광고의 차이일 수 있다. 4건만 봤다).
- `advertiser.tt_user` ✅: `username`, `display_name`, `account_type`, `follower_count`, `avatar_url`, `profile_web_link`. 광고를 올린 TikTok 계정이다. **개인 제작자 계정일 수도 있으므로**(본 3건은 기업 인증 계정) 브랜드 계정 목록과 맞을 때만 저장한다(10절).
- `standard`에서도 노출 국가는 `targeting.location.data[].region`으로 알 수 있다 ✅ (`GB`). `targeting.countries`는 비어 있으므로 국가는 `location`에서 읽어야 한다.

- **노출 국가는 상세에서만 알 수 있다.** 목록에는 국가가 없다 ✅.
- 도달 수(`impressions`)가 국가·나이·성별로 나뉘어 오는 것은 이 소스의 큰 강점이다.
- 나이·성별 분해 값이 `0-1K`처럼 구간이거나 `327K`처럼 숫자인 두 형태가 섞여 있다 ✅.

## 5. 영상 파일 (과제의 핵심)
`videos[0].video_url`을 **그냥 GET하면 받아진다** ✅ (쿠키·헤더 없이 curl로 확인).

1. `https://library.tiktok.com/api/v1/cdn/<시각>/video/<Base64 인코딩 주소>/<uuid>?a=...&signature=...` → **302**.
2. `Location`이 `https://v16m.tiktokcdn.com/.../video/tos/.../?...&mime_type=video_mp4&signature=...` → **200**, `video/mp4`, **784,974바이트**(확인한 1건, 약 0.8 MB).
- 같은 주소로 HEAD를 보내면 404가 온다 ✅. **GET으로 받아야 한다.**
- 만료: CDN 주소 경로 안에 16진수 시각(`6af2fec0` = 2026-11-10 11:23 UTC)이 있고, 이는 조회 시각(05:23 UTC)보다 약 6시간 뒤다. 검색 응답의 한 영상 주소에는 `VExpiration=1794309991`(11:26 UTC)이 있었다 ✅. 표지 주소도 `x-expires`(11:00 UTC)가 있다 ✅. **약 6시간짜리 서명 주소로 보이고, 만료 뒤 실제로 막히는지는 시험하지 않았다 ❓.** 수집 즉시 받아야 한다.
- 해상도 ✅ (2차 확인, 상세 화면의 재생기에서 읽음): Batiste 스페인 640×360, 15.0초. C&D UK 2건은 576×1024(세로), 7.0초와 32.7초. 해상도 선택 필드는 없고 한 가지 파일만 온다.
- 영상 파일은 저장소에 넣지 않았다(0.8 MB라 한도 안이지만 폴더 크기 때문). 표지 JPEG만 `samples/`에 있다.

## 6. 지금 돌고 있는 광고의 판정
- 요청 본문의 `ad_status:1`은 화면 Filters의 **"Ad status: Active"**(기본값)다 ✅ (2차 확인, 패널 글자만 읽었고 바꿔 보지 않았다). 그러나 이 상태로도 마지막 노출이 2주 넘게 지난 광고가 목록에 나온다 ✅ (C&D UK 2쪽은 전부 10/26~10/27). **"Active"는 "지금 노출 중"이라는 뜻이 아니다.** 정확한 뜻은 모른다 ❓. 지금 도는지는 마지막 노출일로 직접 판정해야 한다.
- 기간 조건은 "마지막 노출일"이 기준이다 ✅. 즉 목록에는 그 기간 안에 마지막으로 노출된 광고, 곧 끝난 광고도 섞여 있다.
- 노출일은 **하루 단위**이고, 페이지에 "업데이트가 최대 48시간 늦을 수 있다"고 적혀 있다 ✅. Batiste 5건의 마지막 노출은 11월 8~9일이었다 ✅.
- 제안: **마지막 노출이 수집일 기준 3일 이내이면 active, 아니면 ended.** (소스 1과 같은 기준)

## 7. 항목 식별과 재실행
- 고유 키: 광고 ID(`id`). 숫자 문자열이다.
- 대조용 주소: `https://library.tiktok.com/ads/detail/?ad_id=<광고ID>`
- 광고주 단위 수집: 광고주 ID(`adv_biz_ids`)와 이름을 설정에 고정해 두고, 2-1의 주소로 열어 Search를 누른다 ✅. 새 광고주 ID를 찾을 때만 이름 후보 검색(`suggestion`)이 필요하다. 요청을 손으로 만드는 방법은 쓸 수 없다(2-2).
- 다시 돌리면 같은 광고 ID의 행을 갱신한다.

### 쪽 넘김 (2차 확인 ✅, `samples/search_advertiser_cd_uk_pages.json`)
- 목록 아래의 **"View more"**(`span.loading_more_text`)를 누르면 다음 쪽 요청이 나간다 ✅. 문서 전체가 아니라 안쪽 영역이 스크롤되는 구조라, 창을 스크롤하는 것으로는 나가지 않는다(1차에서 실패한 이유).
- 2쪽 요청 본문 ✅: 1쪽과 같고 `offset:1`, `search_id:"<1쪽 응답의 search_id>"`만 다르다. **`offset`은 항목 수가 아니라 쪽 번호(0부터)다.** `limit`은 12 그대로다.
- `search_id`를 풀면 `{"last_sort":[<정렬값>],"next_cursor":12}` → 2쪽 응답에서는 `next_cursor:24` ✅.
- **쪽 사이에 같은 광고가 겹친다** ✅. 1쪽의 마지막 광고(`1880166457820562`)가 2쪽의 첫 광고로 다시 왔다. 광고 ID로 중복을 걸러야 하고, 다 넘긴 뒤 **고유 ID 수를 `total`과 비교**해 모자라면 "일부만 수집"으로 표시한다. 끝까지 넘겨서 수가 맞는지는 확인하지 않았다 ❓.
- 정렬은 등록일 최신순(`create_time,desc`)이다 ✅. 마지막 노출일 순이 아니라서, 앞쪽만 보고 "지금 도는 광고"를 다 찾았다고 할 수 없다. C&D UK 1쪽 12건 중 수집일 기준 3일 이내는 5건이었고 2쪽은 0건이었다 ✅. 정렬 메뉴의 다른 선택지는 열어 보지 않았다 ❓.
- C&D UK는 최근 31일 91건으로 8쪽 정도다(`total`÷12).

## 8. 이 소스에서 얻을 수 없는 것
- **미국에 나간 광고** (가장 큰 한계)
- 광고비, 정확한 노출 수 (구간뿐; `spent`는 비어 있다)
- 광고 문구·랜딩 주소·CTA·광고 목표가 없는 광고가 있다(C&D UK는 상세에도 없다, 4-2)
- 다섯 브랜드 중 넷은 이 라이브러리에 없다(3-1)
- 영상 속 말·자막 (영상을 받아서 따로 처리해야 한다)

## 9. 이걸로 볼 수 있는 것
Batiste 스페인 계정 5건과 Church & Dwight 유럽 계정 기준이다.
- **영상 소재:** 영상 파일과 표지가 그대로 온다. 확인한 상세 1건과 목록 3건은 영상이었다 ✅.
- **타깃과 도달:** 스페인 한 나라, 여성만, 전 연령. 도달 `900K-1M`, 18~24세 여성이 327K로 가장 많다 ✅.
- **집행 구조:** 같은 광고 문구를 여러 소재로 올린다. Batiste 스페인에서 같은 문구가 광고 ID 여럿으로 나왔다 ✅. 집행은 대행사(`BE A TIGER`)가 한다 ✅.
- **유럽 시장의 브랜드 구성:** C&D 독일 광고 제목에서 Batiste와 Hero를 나란히 집행하는 것이 보인다 ✅. 미국 전략과는 다를 수 있다.
- 미국 브랜드 간 비교에는 쓸 수 없다.

## 9-1. 정해진 것
- **이 소스는 Creative Center Top Ads(미국)만 Apify로 수집한다** (사용자 결정, 2026-11-10). 한계를 인정하고 쓴다. 근거와 한계는 12절에 있다. EU Ad Library는 쓰지 않는다.
  - 공백 기록: 상위 광고 목록에서 찾지 못한 브랜드(지금은 Batiste, Death Wish, Black Rifle)는 "상위 광고 목록에 없음"으로 적는다. "nothing found"로 적지 않는다. 미국 전체 광고는 볼 방법이 없으므로 "could not look"으로 적는다.
  - 액터: `fetch_cat/tiktok-ads-library-scraper`. 같은 조건에서 data_xplorer보다 1건 더 찾았고, 키워드를 한 번에 여러 개 받으며 더 싸다(12-1).
  - 입력: 브랜드 이름과 변형을 키워드로, `regions:["US"]`, `period:"180"`, `sortBy:"for_you"`, `maxItems` 300 안팎.
  - 브랜드 판정: 광고 문구나 브랜드 이름 칸에 브랜드 이름, 도메인, 공식 계정(@Jinx 등)이 있을 때만 남긴다. 나머지 행은 버리고 건수만 실행 기록에 남긴다.
  - 영상은 수집 즉시 받는다(`mediaExpiresAt`이 약 6시간 뒤다).
  - 지금 도는지는 판정할 수 없다. 행에는 "최근 180일 상위 광고 목록에 있음"만 적는다.
  - 다시 돌렸을 때 목록에서 빠진 광고는 지우지 않는다. "목록에서 빠짐"으로 표시한다. 광고가 끝났다는 뜻은 아니다.
  - 비용(확정 금액 기준, 2026-11-10 정정): 실행 1회에 $0.005가 들고, 행마다 $0.00020537(무료 등급)이 붙는다. 296행 실행은 $0.066이었다. 원시 행 1,000개당 약 $0.21이다. 브랜드 광고만 세면 3건이라 1,000건당 약 $22이다. 처음에 적은 $0.03은 실행 직후 아직 확정되지 않은 금액이었다(12-1).
  - 수집기 spec: `part1/collectors/02_tiktok_ad_library/spec.md`(2026-11-10). 빌드 `0.1.30`으로 고정, 비용 상한 $0.25, 브랜드마다 실행 1회.
  - 브랜드를 언급하지 않는 행은 버리고 광고 ID만 남긴다. 사용자가 그 행들이 무엇인지 확인한 뒤 다시 정했다(2026-11-10). 그 행들은 키워드와 단어만 겹치는 다른 광고주의 광고였다. Death Wish 키워드에는 숏드라마와 다른 커피 브랜드 21건이, Black Rifle 키워드에는 "Black Hole" 게임 등이 섞여 왔다. 남는 공백도 있다. 문구와 브랜드 이름 칸 어디에도 브랜드가 없는 실제 브랜드 광고가 있다면 함께 버려진다(샘플에서 버린 행 중 브랜드 이름이 빈 행이 104개였다).
  - 노트에 적을 한계: 광고주가 허락한 상위 광고뿐이다. 노출 수, 광고비, 날짜가 없다. 상세 화면은 로그인해야 열려서 하나씩 대조할 수 없다. 액터는 화면이 로그인을 요구하는 범위 너머의 목록을 가져온다.
- **attribute (확정, 사용자 2026-11-10):** `ad_id`(Creative Center 소재 ID), `brand`, `match_basis`, `ad_text`, `brand_name_raw`, `likes`, `ctr_percentile`(예: 상위 32%, **클릭률 아님**), `budget_tier`(low/medium/high), `objective`, `industry`, `duration_sec`, `video_file`(경로·크기·해시), `cover_image`, `detail_url`, `region`=US, `lookback_days`=180, `search_keyword`, `rank`, `collected_via`="apify:fetch_cat", `collected_at`, `is_active`=판정 불가.

## 10. (해당 없음) EU Ad Library를 쓸 경우의 결정 사항
> EU Ad Library를 쓰지 않기로 해서(맨 위 결정) 아래 항목은 열려 있지 않다. 조사 기록으로만 둔다.
1. **수집 범위.**

   | 안 | 내용 | 걸리는 점 |
   |---|---|---|
   | A | Batiste 본인 계정(스페인)만 | 5건뿐이다. 영국 광고가 통째로 빠진다 |
   | B | A + C&D 유럽 계정 3곳의 광고 중 Batiste로 판정되는 것 | 광고마다 상세를 열어야 한다. 독일 계정의 판정 근거는 아직 못 봤다 ❓ |
   | C | B + 문구에 Batiste가 든 대행사·재판매자 광고 | 브랜드가 낸 광고가 아닌 것이 섞인다 |

   제안: **B.** UK 계정은 올린 계정(`batiste_hair`)으로 판정할 수 있음이 확인됐다(3절). 판정하지 못한 광고는 넣지 않고 건수만 실행 기록에 남긴다.
2. **브랜드 판정 규칙(B안일 때).** 제안: 아래 중 하나가 맞으면 Batiste로 보고, 어느 것으로 맞았는지 행에 남긴다.
   - 광고주 계정이 브랜드 본인 계정이다(`7078634489555092225`).
   - 올린 계정 `tt_user.username`이 브랜드 계정 목록에 있다(`batiste_hair`).
   - 랜딩 주소 도메인이나 광고 문구에 브랜드 이름이 있다(`enhanced` 형태에서만 가능).
3. **올린 계정 저장 범위.** 제안: 브랜드 계정 목록과 맞을 때만 계정 이름을 저장하고, 맞지 않으면 저장하지 않는다(개인 제작자 계정일 수 있다).
4. **"지금 도는 광고"의 범위와 active 기준.** 제안: 마지막 노출일이 수집일 기준 3일 이내인 광고만 수집하고 active로 둔다(갱신이 최대 48시간 늦다). 다음 실행에서 이 조건을 벗어난 기존 행은 지우지 않고 ended로 바꾼다.
5. **공백의 기록.** 제안: Ad Library 기준으로 미국은 다섯 브랜드 모두 "could not look(이 라이브러리는 미국을 담지 않는다)"로 적는다. 유럽은 네 브랜드에 "찾아봤고 광고주 계정이 없거나 0건"이라고 적되, 검색 응답을 실제로 받은 경우에만 그렇게 적는다. Creative Center(미국)는 Batiste·Death Wish·Black Rifle에 "상위 광고 목록에 없음"으로 적는다. 이는 미국 광고가 없다는 뜻이 아니다(9-1).
6. **영상 저장.** 서명 주소가 약 6시간이라 수집 때 바로 받아야 한다(0.8 MB급). 제안: 파일로 받고 경로·크기·해시를 행에 남긴다.
7. ~~Creative Center(11절)를 뺄지~~ → 9-1에서 Apify로 쓰기로 정했다.

## 10-1. (해당 없음) EU Ad Library에서 확인하지 못한 것
- 독일 계정 2곳 상세의 형태와 판정 근거(제목, 랜딩 주소, 올린 계정).
- 주소에 `start_time`/`end_time`을 넣어 기간을 좁힐 수 있는지, 정렬을 마지막 노출일 순으로 바꿀 수 있는지. 되면 넘길 쪽 수가 크게 준다.
- 끝까지 넘겼을 때 고유 광고 수가 `total`과 맞는지.
- 영상 주소가 약 6시간 뒤 실제로 막히는지(1차에 받은 주소는 11:23 UTC 이후에 시험할 수 있다).
- 헤드리스 실행.

## 11. 보조: TikTok Creative Center Top Ads (미국 광고 샘플)
**막힌 부분이 있다. 아래에 쓴 것이 전부다.**

- 주소: `https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?period=30&region=US`
- 로그인 없이 열린다 ✅. 그러나 화면에는 카드 4개만 보이고 그 아래에 **"View More  Log in to access all Top Ads and more. Log in or sign up"**이 떴다 ✅. 스크롤해도 더 나오지 않았다 ✅. 이 길은 **여기서 멈췄다.** 로그인하지 않았고, 2쪽·검색·다른 방법을 시도하지 않았다.
- 페이지가 스스로 부른 목록 응답은 받아졌다 ✅: `GET creative_radar_api/v1/top_ads/v2/list?period=30&page=1&limit=20&order_by=for_you&country_code=US` → 200, 광고 20개, `pagination:{has_more:true, page:1, size:20, total_count:134}` (`samples/creative_center_top_ads_US_list.json`, 20개 중 2개만 남김). 화면은 4개만 보여 주는데 응답에는 20개가 들어 있었다는 점은 확인한 사실이다. 그 이상 쓰는 것이 허용되는지는 판단하지 않았다.
- 필드 ✅: `id`, `ad_title`, `brand_name`(대부분 빈 값), `cost`(예산 등급 1~3으로 보임 ❓), `ctr`(비율, 화면의 "Top 12% CTR"과 관련 ❓), `like`, `industry_key`, `objective_key`, `is_search`, `video_info{vid, duration, cover, width, height, video_url{360p,480p,540p,720p,1080p}}`.
- **없는 것** ✅: 광고주 ID, 노출 시작·종료일, 노출 수, 타깃, 랜딩 주소, CTA. 한 행이 "성과가 좋은 광고 샘플"이며 전체 목록이 아니다. 광고주가 공개를 승인한 것만 나온다(화면 하단 문구).
- 받은 20개의 제목에 우리 브랜드는 없었다 ✅ (눈으로 확인한 20개 제목 기준).
- **키워드 검색은 시험하지 못했다.** 검색어 후보 요청(`query_suggestion`)은 빈 목록이었다 ✅. 브랜드 이름 검색이 되는지는 ❓.
- 결론: 미국 보조 소스로 쓰려면 로그인이 필요해 보이고, 광고주별 수집은 구조상 어렵다 ❓.

## 12. 미국 광고를 Apify로 볼 수 있나 (2026-11-10, 스토어 공개 정보만 확인, 실행 안 함)
Apify 스토어 API(`api.apify.com/v2/store`, `v2/acts/<액터>`, `builds/default`)로 TikTok 광고 액터의 설명·입력·가격을 읽었다. 액터는 돌리지 않았다.

| 갈래 | 미국 | 예 | 메모 |
|---|---|---|---|
| EU Ad Library 수집 | 안 됨 | `s-r/tiktok-ads-library`(설명에 "region=US is unsupported"), `lexis-solutions/tiktok-ads-scraper`, `jmlp/tiktok-ad-library-scraper` | 1~10절에서 본 것과 같은 데이터 ✅ |
| Creative Center Top Ads 수집 | 됨 | `fetch_cat/tiktok-ads-library-scraper`, `azzouzana/tiktok-creative-center-top-ads-scraper`, `datapeak/tiktok-creative-center`, `doliz/tiktok-creative-center-scraper` | 아래 |
| 브랜드 계정 게시물 + 광고 표시 | 계정 기준 | `unseenuser/TikTok-posts`(`is_ad`, 유료 협찬 표시) | 소스 8 영역이다. README가 "TikTok의 원래 `is_ad`는 일반 상업 게시물에서도 켜진다"고 적었다 ✅. 광고 판정은 추정이다 |

Creative Center 액터로 얻는 것 (README·입력 스키마 기준 ✅, 실제 출력은 확인 안 함 ❓)
- 광고별: 문구, 좋아요, CTR, 예산 등급(cost index), 업종, 광고 목표, Spark 광고 여부, 영상 MP4(360~720p), 표지. 상세 모드에서 댓글·공유·랜딩 주소·노출 국가.
- 정렬 기준으로 노출, 2초·6초 시청률, CVR이 있다. 이 값이 행에 숫자로 오는지는 모른다 ❓.
- 없는 것: 노출 수·도달·광고비, 처음/마지막 노출일, 광고주 ID. fetch_cat README가 "광고주·브랜드·랜딩·미디어 필드는 자주 빈다", "TikTok의 전체 광고 기록이 아니다"라고 직접 적었다 ✅.
- 범위: TikTok이 고른 성과 상위 광고 모음이다. datapeak README는 "로그인 없이 필터 조합당 보통 20~100건"이라고 적었다 ✅. 브랜드 키워드로 찾을 수 있지만, 다섯 브랜드가 실제로 잡히는지는 돌려 봐야 안다 ❓.

깨끗한 수집 기준으로 본 액터
- `doliz`: 사용자의 Creative Center 로그인 쿠키가 필요하다 ✅. 제외.
- `datapeak`: 서명 헤더를 자체 생성하고, 주거용 프록시가 사실상 필수라고 적었다("TikTok blocks datacenter IPs aggressively") ✅. 탐지 회피 성격이라 제외 제안.
- `fetch_cat`: "No login is required", 프록시 기본 꺼짐, 키워드 20개/실행, 상세는 6건 이하 ✅. 가격: 실행 $0.005 + 건당 약 $0.0002(무료 등급). 가장 깔끔하다.
- `azzouzana`: "No login", 실행당 최대 3,000건 ✅. 가격: 실행 $0.005 + 건당 $0.001 + 상세 건당 $0.002. 무료 등급은 실행당 5건.
- **판단할 점:** Creative Center 화면은 카드 4개 뒤에서 로그인을 요구했고 이 조사는 거기서 멈췄다(11절). 위 액터들은 화면 뒤의 공개 API를 쪽 단위로 불러 그 이상을 가져온다. 로그인은 쓰지 않지만, 화면이 막은 범위를 넘는 것이다.
- 저장소 `.env`에 `APIFY_TOKEN` 키가 있다(값은 보지 않았다).

### 12-1. 실제로 돌린 결과 (2026-11-10 07:50~08:00 UTC, 사용자 승인 후, 확정 합계 $0.234)
> **비용 정정 (2026-11-10):** 처음 표에 적은 금액은 실행 직후에 읽은 값이었다. Apify는 과금을 실행이 끝난 뒤 10~25초에 걸쳐 확정한다. 확정 금액은 fetch_cat $0.066, data_xplorer 5회 $0.1675로, 합계 $0.234이다. 이후 spec을 확인하려고 승인받아 한 Jinx 실행은 $0.006이었다(누계 $0.240).
조건: 미국(`US`), 기간 180일. 결과 요약은 `samples/apify_creative_center_us_2026-11-10.json`에 있다.

| 액터 | 실행 | 비용 | 돌려받은 행 | 브랜드 광고 |
|---|---|---|---|---|
| `fetch_cat` (키워드 9개 한 번에, `for_you` 순, 최대 300) | 1회, 38초 | $0.066 (확정) | 296 | 3건 |
| `data_xplorer` Top Ads 모드 (키워드 1개씩, `like` 순, 각 최대 30) | 5회, 각 3~12초 | $0.1675 (확정) | 95 (고유 63) | 2건 (fetch_cat 3건 중 2건과 같음) |

**브랜드별 결과** ✅ (광고 문구와 브랜드 이름에 브랜드가 나오는 것만 셌다)
| 브랜드 | 결과 | 내용 |
|---|---|---|
| Batiste | 0건 | 두 액터 모두 검색 결과 0행 |
| Living Proof | 1건 (`7531018269878140936`) | 브랜드 이름 `Living Proof`, 문구에 `livingproof.com`. 목표 Traffic, 좋아요 822, CTR 상위 32%, 예산 등급 0, 8초. data_xplorer는 좋아요 순 상위 30건 안에 들지 않아 놓쳤다 |
| Death Wish Coffee | 0건 | 59~165행이 왔지만 전부 무관한 광고(숏드라마·게임 등) |
| Black Rifle Coffee | 0건 | 38행 전부 무관 |
| Jinx | 2건 (`7609180755211075600`, `7619486503161118737`) | 제작자가 만든 협찬 광고다(`#JinxPartner`, "@Jinx … available only at Walmart"). 브랜드 이름 칸은 비어 있다. 목표 Reach, 좋아요 1,183 / 237, 예산 등급 1 |

**알게 된 것** ✅
- **키워드 검색이 느슨하다.** 브랜드 이름을 넣어도 무관한 광고가 대부분이다(fetch_cat 296행 중 브랜드 광고 3건). 문구와 브랜드 이름으로 다시 걸러야 한다.
- **`ctr`은 클릭률이 아니라 순위 구간이다.** data_xplorer가 같은 값을 `ctr: 0.39` → `ctr_readable: "Top 39%"`로 풀어 준다. `cost`도 금액이 아니라 예산 등급(0~2 → Low/Medium/High)이다.
- 노출 수, 광고비, 처음·마지막 노출일, 광고주 ID는 두 액터 모두 없다. 그래서 **"지금 도는 광고"인지 판정할 수 없다.** 시간 정보는 검색 기간(180일)뿐이다. 광고 ID를 시각으로 풀면 2025-07-25, 2026-02-21, 2026-03-20이다. 다만 이는 영상이 만들어진 시각으로 보이고 광고 기간이 아니다 ❓.
- 랜딩 주소는 상세 모드를 켜지 않아 비어 있었다(fetch_cat 0/296). 영상 주소는 전부 있었고 약 6시간 뒤 만료된다(`mediaExpiresAt`).
- data_xplorer README의 "impressions and spend estimates"는 EU 라이브러리 모드의 이야기다. Top Ads 모드의 행에는 없다.
- 두 액터의 차이: fetch_cat은 키워드를 한 번에 여러 개 받고 `detailUrl`, `rank`, `mediaExpiresAt`을 준다. data_xplorer는 키워드를 실행당 1개만 받고, 등급을 읽기 쉬운 글자로 풀어 주며, `brand_name`이 더 자주 채워진다(61/95). 정렬에 `for_you`가 없다.
- **이 3건을 Creative Center 화면과 대조하지는 않았다 ❓** (상세 주소가 로그인 벽에 걸릴 수 있어 열지 않았다).
- **Creative Center에 없다고 해서 광고를 안 낸다는 뜻은 아니다.** Creative Center Top Ads는 TikTok이 고른 성과 상위 광고 모음이다. 화면 하단 문구로는 광고주가 공개를 허락한 것만 나온다(11절). fetch_cat README도 "curated Top Ads … not a complete archive"라고 적었다 ✅. Batiste 0건은 "상위 광고 모음에 없음"이지 "미국 TikTok 광고 없음"이 아니다.

### 12-1a. Top Ads에 무엇이 올라가나 (2026-11-10)
- TikTok 공식 도움말 ✅ ([top ads](https://ads.tiktok.com/help/article/top-ads?lang=en)): Top Ads에 나오는 광고는 모두 광고주가 Ads Manager에서 공개를 허락한 것이다. 성과 기준은 "high-performing creatives"라고만 하고 구체적으로 밝히지 않는다. 광고비 기준은 언급이 없다.
- Creative Center 화면 문구 ✅: "See high-performing auction ads on TikTok."와 "ads displayed here are limited to those that have been authorized by advertisers and may not reflect all top-performing auction ads."
- 실제 데이터도 광고비순이나 바이럴순이 아니다 ✅. 예산 등급 Low에 좋아요 822인 Living Proof 광고가 들어 있고, 화면 첫 카드 4개 중 3개도 Low였다.
- 따라서 **"효과가 좋으면 잡힌다"가 아니다.** 경매형 광고 중에서 광고주가 공개를 허락했고, 동시에 TikTok이 성과가 좋다고 본 것만 나온다. 허락하지 않은 브랜드의 광고는 아무리 잘돼도 나오지 않는다.

### 12-1b. 실제 사이트와 대조할 수 있나 (2026-11-10, 페이지 1회)
- Living Proof 광고의 상세 주소(`https://ads.tiktok.com/business/creativecenter/topads/7531018269878140936`)를 로그인 없이 열었다. 상세는 뜨지 않고 Top Ads 목록 첫 화면으로 이동했다 ✅. 목록은 카드 4개 뒤에 "Log in to access all Top Ads and more."를 띄웠다 ✅. 로그인 벽이므로 이 경로는 여기서 멈췄다.
- 페이지의 `creative_radar_api/v1/user/info`는 `code 40000 "invalid user"`(비로그인)였다 ✅.
- **결론: 미국 행은 로그인 없이는 Creative Center 화면과 하나씩 대조할 수 없다.** 대조 근거로는 수집 때 받은 영상 파일, 광고 문구, `detailUrl`을 남긴다.

### 12-2. Apify에 다른 대안이 있나 (2026-11-10, 스토어 검색만)
검색어 8개를 더 넣었다(`tiktok ad spy`, `pipiads`, `tiktok spark ads`, `tiktok branded content`, `tiktok paid partnership`, `tiktok feed ads`, `tiktok advertiser`, `ad intelligence tiktok`). 처음 검색에 없던 광고 관련 액터 39개가 더 나왔고, 원천별로 나누면 아래뿐이다 ✅.

| 원천 | 미국 | 예 |
|---|---|---|
| EU Commercial Content Library | 안 됨 | 대부분(설명에 EU/EEA/UK/CH/TR만 적힘) |
| Creative Center Top Ads | 상위 광고만 | 12-1과 같은 원천 |
| 위 둘을 묶은 여러 플랫폼 도구 | 위와 같음 | `seibs.co/ad-library-intel`, `capable_cauldron/multi-channel-ad-intelligence` |
| 크리에이터 협찬 게시물(유료 협찬 표시, `#ad`, `#partner`) | 됨 | `dami_studio/tiktok-hashtag-scraper`, `church_of_loujess/tiktok-brand-sponsor-spy`, `unseenuser/TikTok-posts` |

- 앱 피드의 광고를 모으는 유료 광고 탐색 서비스(PiPiAds 류)를 긁는 액터는 없었다.
- 마지막 갈래는 광고 기록이 아니라 **브랜드가 돈을 낸 일반 게시물**이다. 조회 수와 좋아요는 있지만, 그 게시물을 광고로 돌렸는지(Spark 광고)는 알 수 없다. 노출 수와 광고비도 없다. 소스 8(TikTok 게시물)의 영역이다.
- 연결점: 12-1에서 찾은 Jinx 광고 2건이 바로 이런 크리에이터 협찬 게시물(`#JinxPartner`)이었다 ✅. 협찬 해시태그로 게시물을 모으면 미국 Jinx 협찬 콘텐츠의 조회 수를 볼 수 있다. 시험하지는 않았다 ❓.

## samples/
| 파일 | 내용 |
|---|---|
| `support_regions.json` | 지원 지역 34곳 |
| `suggestion_batiste.json` | `Batiste` 후보 요청과 응답 |
| `search_advertiser_batiste.json` | 광고주 검색 요청 본문과 응답(5건 중 2건) |
| `search_keyword_church_dwight.json` | 키워드 검색 요청 본문과 응답(12건 중 3건) |
| `keyword_counts_plain.json` | 키워드 검색 10건의 요청·건수·광고주 이름 |
| `detail_batiste_spain.json` | Batiste 광고 상세 응답 |
| `detail_page.png` | 그 상세 화면 |
| `batiste_cover.jpg` | 표지 이미지 (37 KB) |
| `creative_center_top_ads_US_list.json` | Creative Center 목록 응답(20건 중 2건) |
| `search_advertiser_cd_uk_pages.json` | 2차: C&D UK 광고주 목록 1쪽·2쪽의 요청 본문, `search_id`, 광고 ID, 겹친 ID (data는 2건만) |
| `detail_cd_uk_standard.json` | 2차: C&D UK 광고 상세 1건(`display_mode:"standard"`, `tt_user` 포함)과 요청 헤더 이름 |
| `detail_cd_uk_3ads_summary.json` | 2차: C&D UK 상세 3건 요약(올린 계정, 없는 필드, 도달 수) |
| `apify_creative_center_us_2026-11-10.json` | 12-1: Apify 두 액터의 실행 정보(비용·행 수)와 미국 브랜드 광고 3건(영상 주소 제외, 제작자 계정 이름 가림) |
