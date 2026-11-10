# 소스 7: 검색 관심도 (Google Trends)

- 확인일: 2026-11-10 (미국 IP, 화면이 뜨는 Chrome)
- 확인 대상: 다섯 브랜드, 미국, 최근 12개월. 주 단위 시계열, 연관 검색어, 자동완성
- 표기: ✅ 실제 응답에서 확인함 / ❓ 추정이거나 미확인
- 참고: 이 IP는 데이터센터(VPN) 대역이다(`AS212238 Datacamp`). 가정용 IP에서의 동작은 보지 못했다 ❓
- 갱신(2026-11-10 15:10 KST): 검색어 방향 결정(3-3), 샘플 재분석(3-4), 10번째 요청도 429(2-1), attribute 제안(11번)

## 1. 이 소스가 주는 것
브랜드 이름의 검색 관심도를 **0~100 사이 상대값**으로, 주 단위로 준다. **한 행은 (검색어, 지역, 기간, 주) 1개**다. 검색량(건수)은 어디에도 없다 ✅.

## 2. 접근 방법
- 로그인이 필요 없다 ✅. 화면 상단에 "Sign in"만 보이고 데이터는 그대로 나온다.
- **헤드리스는 429**였다(사전 확인). 화면이 뜨는 Chrome으로 `https://trends.google.com/trends/`를 먼저 열고, 이어서 아래 주소를 열면 된다 ✅.
  `https://trends.google.com/trends/explore?date=today%2012-m&geo=US&q=<검색어 또는 토픽ID>`
- 검색어를 쉼표로 이어 붙이면 비교 요청이 된다(최대 5개) ✅. 토픽은 `q=%2Fg%2F113ltsfhl`처럼 ID를 넣는다 ✅.
- 화면에 "Classic Explore is expiring soon. Switch to the new Explore page"라는 안내가 떠 있다 ✅. 이 explore 화면과 `/trends/api/*`는 곧 바뀔 수 있다 ❓.
- 응답 본문 맨 앞에 `)]}',` 한 줄이 붙어 있다 ✅. 첫 줄을 버리고 JSON으로 읽는다. (예외: `explore` 응답은 `)]}'`로 끝나고 줄바꿈 뒤에 JSON이 온다. 같은 방식으로 첫 줄을 버리면 된다 ✅)
- 페이지를 열면 페이지가 스스로 아래 요청을 보낸다. 가로채서 저장한다(소스 1과 같은 방식).

| 요청 | 담긴 것 | 파일 |
|---|---|---|
| `/trends/api/explore` | 아래 위젯들의 요청 조건과 토큰 | `explore_batiste_term.txt` |
| `/trends/api/widgetdata/multiline` | **시계열** | `multiline_*.txt` |
| `/trends/api/widgetdata/relatedsearches` | 연관 검색어(검색어용, 토픽용 2번) | `related_queries_*.txt` |
| `/trends/api/widgetdata/comparedgeo` | 주(state)별 관심도 | `comparedgeo_batiste_term.txt` |
| `/trends/api/autocomplete/<검색어>?hl=en-US&tz=300` | 검색어에 대응하는 토픽 후보 | `autocomplete_*.txt` |

- 자동완성은 trends.google.com을 연 페이지 안에서 `fetch`로 불렀다(페이지 로드가 아니다) ✅. 다섯 브랜드 모두 200.
- `explore` 응답의 `widgets[]`가 `multiline`, `relatedsearches` 요청에 필요한 `token`을 준다. 토큰을 직접 만들 수는 없으므로 **페이지를 열어서 가로채는 방식**이 가장 단순하다 ✅(우리가 쓴 방식). `explore`를 직접 불러 토큰을 받는 방식은 시도하지 않았다 ❓.
- 요청 조건에 `"userType":"USER_TYPE_SCRAPER"`가 찍혀 있다 ✅. Google이 이 세션을 자동화로 분류하고 있다는 뜻으로 보인다 ❓.

### 2-1. 요청 횟수와 429
이번 세션의 페이지 로드: `trends/` 홈 4번(세션마다 1번), explore 9번. 사이 간격은 6~15초.
- **explore 8번은 연속으로 성공했다**(홈 열기 후 7번 한 세션에서, 앞선 1번은 다른 세션). 9번째(`batiste dry shampoo`)가 **HTTP 429**였고 `https://www.google.com/sorry/index?continue=https://trends.google.com/trends/explore...`로 넘어갔다 ✅. reCAPTCHA 화면이다. 풀거나 우회하지 않고 거기서 멈췄다.
- **차단은 한 시간 가까이 지나도 풀리지 않았다** ✅. 첫 429는 14:12 KST 무렵이었고, 15:08 KST에 새 브라우저 세션으로 홈(200)을 연 뒤 explore를 1번 열자 다시 429와 `sorry` 화면이 나왔다. 거기서 멈췄다. 두 번 모두 새 브라우저 세션이었으므로 차단은 브라우저가 아니라 IP에 걸려 있다 ✅.
- 15:08의 요청은 수식어를 붙인 검색어 5개 비교(3-3)였고 주소의 기간을 고정 날짜(`date=2025-11-10%202026-11-10`)로 썼다. 막혀서 둘 다 확인하지 못했다 ❓.
- 정확한 한도는 알 수 없다. 이 IP가 데이터센터 대역이라 낮을 수 있다 ❓.
- Trends의 지역은 주소의 `geo=US`가 정한다. 미국 IP가 아니어도 같은 데이터를 요청할 수 있다(VPN 없이 직접 해 보지는 않았다 ❓). 수집기를 다시 돌리는 사람의 IP는 이 VPN이 아니므로, 여기서 본 한도가 그대로 적용된다고 볼 수 없다.
- 5개 비교 요청 한 번이 연관어 위젯 5개를 같이 준다. **한 브랜드씩 따로 부르는 것보다 비교 요청 1회가 페이지 로드가 적다.**
- 한 번의 explore 로드에서 응답 전체가 약 9초 안에 도착했다 ✅.

권장 예산: 일일 수집은 5개 비교 요청 1회 + 연관어(같은 응답에 포함) = 페이지 로드 2~3회(홈 포함). 429를 만나면 그날은 멈추고 다음 날 재시도한다.

## 3. 검색어 대 토픽: 브랜드 매칭
Batiste와 Jinx는 흔한 단어라서 같은 이름의 다른 것이 섞인다.

### 3-1. 자동완성이 주는 토픽 ID (`samples/autocomplete_*.txt`) ✅
| 입력 | 토픽 ID | 제목 / 종류 | 메모 |
|---|---|---|---|
| Batiste | `/g/113ltsfhl` | Batiste / Topic | 첫째 후보. 종류가 "Topic"이라 무엇인지 알 수 없다. 둘째는 `Cambric`(천) |
| Batiste dry shampoo | `/g/11z_tx12yc` | Batiste Dry Shampoo / Topic | 제품 토픽 |
| Living Proof | `/g/11hv8hfy7` | Living Proof / Topic | |
| Death Wish Coffee | `/m/0wk9gm_` | Death Wish Coffee / **Company** | 종류가 명확하다 |
| Black Rifle Coffee | `/g/11nnz4l0bv` | Black Rifle Coffee Company / Topic | 같은 이름의 매장 토픽도 있다(`/g/11sczvvfrx` 버지니아 비치) |
| Jinx | `/g/11l8lp95mq`, `/m/01lby8`, `/m/05hb_m` | Jinx / League of Legends, Jinx / Topic, Jinx / DC 캐릭터 | **개 사료 회사는 첫 화면에 없다** |
| Jinx pet food | `/g/11nnztr_by` | Jinx / Topic | 개 사료 회사일 가능성이 높지만 종류 표기가 없다 ❓ |
| Jinx dog food | (제품 토픽들, 예 `/g/11zgbr3l2_`) | Jinx Salmon Brown Rice... / Dog food | 회사가 아니라 제품 |

### 3-2. 결과가 얼마나 다른가 ✅ (`samples/multiline_*.txt`, 각각 단독 요청, 53주)
| 비교 | 평균값 | 두 계열의 상관 | 읽는 법 |
|---|---|---|---|
| Batiste 검색어 vs 토픽 `/g/113ltsfhl` | 52.5 vs 71.8 | -0.05 | **전혀 다른 곡선**이다. 어느 쪽이 드라이샴푸를 보는지 이 데이터만으로는 알 수 없다 ❓ |
| Jinx 검색어 vs 토픽 `/g/11nnztr_by` | 74.7 vs 62.3 | -0.56 | 정반대로 움직인다 |
| Jinx 검색어 vs "Jinx dog food" 검색어 | 74.7 vs 24.6 | 0.54 | |
| Jinx 토픽 vs "Jinx dog food" 검색어 | | -0.08 | 토픽 `/g/11nnztr_by`가 개 사료와 같은 것인지 확인되지 않는다 ❓ |

- 화면의 Batiste 단독 곡선은 5월 17일 주(100), 8월 9일 주(100), 10월 11일 주(89)에 솟는다 ✅. 이 날짜가 드라이샴푸 행사인지, 다른 뜻의 Batiste(가수 Jon Batiste, 천)인지 구분할 방법이 없다 ❓.
- "Jinx" 검색어는 최근 값이 60~71로 높다 ✅. 비교 요청(아래)에서 다른 네 브랜드를 압도한다. 개 사료가 아니라 게임/애니메이션 캐릭터 때문일 가능성이 크다 ❓.

### 3-3. 결정과 제안 (브랜드별)
**사용자 결정(2026-11-10):** Batiste와 Jinx는 인물이나 일반 주제에도 쓰이는 단어이므로, 수식어를 붙인 일반 검색어로 본다. 규칙으로 쓰면 "브랜드 이름 + 카테고리 단어"다. 토픽은 쓰지 않으므로 Batiste, Jinx 토픽 ID의 정체 확인은 더 필요하지 않다.

| 브랜드 | 검색어(일반 검색어) | 상태 | 근거와 남은 것 |
|---|---|---|---|
| Batiste | `Batiste dry shampoo` | 결정 | 단독 "Batiste"는 주별 값이 루이지애나 100, 중앙값 26이다(3-4). **이 검색어의 시계열은 아직 한 번도 받지 못했다**(두 번 모두 429) ❓ |
| Jinx | `Jinx dog food` | 결정 | 단독 요청 샘플이 있다(53점, 최소 9, 0값 없음) ✅. 3월 22일~5월 17일 주에 크게 솟는다(3-4) |
| Death Wish Coffee | `Death Wish Coffee` | 제안 | 이름에 카테고리 단어가 이미 있다. 같은 규칙에 맞는다 |
| Black Rifle Coffee | `Black Rifle Coffee` | 제안 | 위와 같다 |
| Living Proof | `Living Proof shampoo` | 제안(미확정) | "Living Proof"는 일반 영어 표현이다. 단독 검색어는 연관 검색어가 비어 있고 토픽 곡선과 상관이 0.06이다 ✅. 토픽의 연관 검색어 1위가 `living proof shampoo`(100)다 ✅. 이 검색어의 시계열은 받지 못했다 ❓ |

**어떤 검색어로 수집했는지를 행에 같이 저장**한다.

### 3-4. 샘플 재분석에서 나온 것 (2026-11-10, 새 요청 없이 `samples/`만으로) ✅
- **단독 요청과 비교 요청은 모양이 같다.** 같은 계열의 단독 값과 5개 비교 안의 값의 상관은 Batiste 검색어 1.0, Jinx 검색어 1.0, Jinx 토픽 1.0, Batiste 토픽 0.99였다. 척도와 정수 반올림만 다르다.
- **비교 요청에서는 작은 계열의 단계 수가 줄어든다.** 검색어 5개 비교에서 Death Wish는 3~10 사이 7단계뿐이었다.
- **일반 검색어들이 2026-03-29~05-17 주에 함께 솟는다.** 이 8주의 평균을 나머지 주의 평균으로 나눈 값은 "Jinx dog food" 4.73, Living Proof 2.41, Death Wish Coffee 1.75, Batiste 1.51, Black Rifle Coffee 1.21, Jinx 1.20이다. 같은 계산을 토픽 5개에 하면 0.84~1.01이다. 계열 간 상관도 높다(Living Proof와 "Jinx dog food" 0.91, Living Proof와 Death Wish Coffee 0.89). 서로 관계없는 브랜드가 같은 주에 같이 오르는 이유는 확인하지 못했다 ❓. 실제 수요가 아니라 Trends 쪽 집계 변화나 자동화 검색일 수 있다(추정). **검색어로 수집하면 이 구간이 그대로 들어온다**는 점을 노트에 적어야 한다.
- **"Batiste" 단독 검색어의 주별 값**은 루이지애나 100, 와이오밍 63, DC 47이고 중앙값은 26이다(`comparedgeo_batiste_term.txt`). 루이지애나에 흔한 성이라 인물 검색이 섞였다고 본다(추정).

## 4. 원본 구조 (시계열)
### 4-1. `multiline` 응답 ✅
`default.timelineData[]`: 12개월 요청에 **53개**, **주 단위**(`resolution: "WEEK"`).

| 필드 | 뜻 | 예시 |
|---|---|---|
| `time` | 주 시작 시각(초). **일요일 00:00 UTC** | `"1762646400"` = 2025-11-09 |
| `formattedTime` | 주 범위 표시 문자열 | `Nov 9 – 15, 2025` (사이에 얇은 공백 문자가 섞여 있다) |
| `formattedAxisTime` | 축 라벨 | `Nov 9, 2025` |
| `value[]` | 값. **검색어 수만큼 배열**. 비교 요청이면 순서대로 | `[40]` |
| `formattedValue[]` | 값을 문자열로 | `["40"]` |
| `hasData[]` | 데이터 있음 | `[true]` |
| `isPartial` | **마지막 점에만 있다.** 아직 끝나지 않은 주 | `true` |

- 첫 점은 2025-11-09, 마지막 점은 2026-11-08~14 주다. 오늘(11-10)이 그 주 중간이라 `isPartial: true` ✅.
- `isPartial`은 **마지막 점에만** 붙는다. 다른 52개에는 필드 자체가 없다 ✅.
- 12개월(`today 12-m`) 요청은 항상 주 단위로 왔다. 일 단위는 기간이 짧을 때(대략 9개월 이하로 알려져 있다) 나온다 ❓.
- 수집한 시계열 전부(단독 요청 7건, 비교 요청 2건)에서 0값은 없었다 ✅. 값이 너무 작으면 0이나 `hasData: false`가 나올 수 있다 ❓.

### 4-2. `comparedgeo` (주별) ✅
`default.geoMapData[]`: 51개(50개 주 + DC). 필드 `geoCode`(`US-LA`), `geoName`, `value[]`(0~100), `hasData[]`. Batiste는 루이지애나가 100이었다. 시장별 분석에 쓸 수 있으나 과제는 시계열만 요구한다.

### 4-3. 연관 검색어 (`relatedsearches`)
`default.rankedList[0]` = TOP, `[1]` = RISING. 항목은 `query`, `value`, `formattedValue`, `link`. 두 번 부른다: `keywordType: ENTITY`(연관 토픽, 이번에는 모두 비어 있었다)와 `QUERY`(연관 검색어).

| 브랜드(검색어) | TOP 수 | RISING 수 | 예 |
|---|---|---|---|
| Death Wish Coffee | 3 | 1 | `death wish coffee caffeine content`(100), `death by coffee`(43), `deathwish coffee`(25). RISING: `death by coffee` +200% ✅ |
| Black Rifle Coffee | 8 | 3 | `black rifle company`(100), `black rifle coffee near me`(13), `...pods`(6) 등. RISING: `black rifle coffee tucson` +500% ✅ |
| Living Proof (토픽) | 5 | 2 | `living proof shampoo`(100), `living proof conditioner`(20), `living proof bond complex`(7), `k18`(4) ✅ |
| Living Proof (검색어) | **0** | **0** | 같은 브랜드가 검색어로는 비어 있다 ✅ |
| Batiste (검색어·토픽 모두, 단독·비교 모두) | **0** | **0** | 3번 확인했다 ✅ |
| Jinx (검색어, 토픽, "Jinx dog food") | **0** | **0** | ✅ |
| Death Wish (토픽) | 0 | 0 | ✅ |

- **가장 큰 발견: 연관 검색어는 비어 있는 경우가 많고, 있어도 3~8개뿐이다.** 20개를 채울 수 없다 ✅. 어떤 요청에서 비는지는 규칙을 찾지 못했다. 같은 브랜드가 토픽으로는 나오고 검색어로는 비는 경우(Living Proof), 반대인 경우(Death Wish, Black Rifle은 검색어에서만)가 있었다 ✅.
- 비어 있는 이유가 검색량 부족인지, 자동화 세션에 대한 제한인지 구분하지 못했다 ❓. 
- 값은 **그 목록의 1위를 100으로 한 상대값**이다. 검색량이 아니다. RISING의 `+200%`는 이전 기간 대비 증가율이다(`formattedValue` 문자열, 값은 `200`).
- 연관 검색어에는 브랜드와 무관한 것이 섞인다(`k18`, `death by coffee`) ✅.

## 5. 값은 상대값이다: 무엇을 같이 저장하나
**한 요청 안에서 가장 높은 점이 100이다.** 요청이 바뀌면 같은 주의 같은 브랜드 값이 달라진다 ✅.

| 요청 | Batiste 5월 17일 주 | Batiste 마지막 주 |
|---|---|---|
| Batiste 혼자 | **100** | 34 |
| 다섯 브랜드를 한 요청(검색어) | **36** | 12 |
| 비율 | 0.36 | 0.35 |

- 다섯 개를 같이 요청하면 모두 가장 큰 "Jinx"(평균 74.7)에 눌린다. 다섯 계열의 평균은 Batiste 18.7, Living Proof 28.1, Death Wish 4.6, Black Rifle 21.7, Jinx 74.7이다 ✅.
- 토픽 5개를 같이 요청하면 Black Rifle 토픽이 100이 된다(평균 Batiste 16.8, Living Proof 43.1, Death Wish 13.2, Black Rifle 65.7, Jinx 10.1) ✅.
- **같은 요청 안의 계열끼리만 비교할 수 있다.** 비율은 요청이 달라도 거의 유지된다(0.36/0.35) ✅.

저장해야 하는 것(각 행마다):
1. 값(`value`)과 **함께 요청한 검색어/토픽 전체 목록**과 그 순서(또는 요청 ID)
2. 검색어 문자열이나 토픽 ID, 어느 쪽인지(`ENTITY`/`QUERY` 구분)
3. 지역(`geo=US`), 기간(`time` 문자열 `2025-11-10 2026-11-10`), 카테고리(0), 검색 유형(Web Search)
4. 주 시작일(`time`), `isPartial`
5. 수집 시각

권장: **브랜드 5개를 항상 같은 한 요청으로 묶어 수집한다.** 그래야 브랜드 간 비교가 된다. 단, "Jinx"는 단독 검색어면 나머지를 눌러버리므로 3-3의 권장 검색어("Jinx dog food")로 묶는다(이 조합은 직접 돌려보지 않았다 ❓). 5개 한 요청의 단점은 작은 브랜드의 값이 1~3으로 뭉개진다는 것이다(Death Wish 최고 10).

## 6. 마지막 점의 판정
- 마지막 점(`isPartial: true`)은 진행 중인 주라서 값이 낮게 나온다. **분석에서는 빼거나 "진행 중"으로 표시한다**(제안). 이번 12개월 요청에서 해당하는 점은 53개 중 1개(2026-11-08 주)였다 ✅.

## 7. 항목 식별과 재실행
- 고유 키: 검색어/토픽 + 요청에 함께 들어간 목록 + 지역 + 기간 문자열 + 주 시작일(`time`)
- 같은 요청을 다시 보내면 **53개 값이 모두 같았다** ✅ (Batiste 검색어, 첫 실행과 두 번째 실행 사이 약 20분, 다른 브라우저 세션). 한 주 이상 지난 값이 바뀌는지는 보지 못했다 ❓.
- 마지막 주(`isPartial: true`)는 주가 끝나면 값이 바뀔 수 있다. 다음 수집 때 덮어쓴다.
- 기간 창이 매일 이동한다(`2025-11-10 2026-11-10`). 창이 바뀌면 최고점이 창 밖으로 빠져 **전체 값의 척도가 달라질 수 있다** ❓. 그래서 척도 정보가 필요 없다고 믿지 말고 요청 조건을 같이 저장한다.

## 8. 이 소스에서 얻을 수 없는 것
- 검색량(건수)
- 비교가 아닌 시점 간 척도 통일(요청마다 100이 바뀐다)
- 브랜드의 전체 검색어 목록(연관어는 0~8개뿐)
- 단어 뜻 구분이 필요 없는 깨끗한 브랜드 신호(Batiste, Jinx)

## 9. 이걸로 볼 수 있는 것
- **관심도의 시간 흐름**: Batiste는 5월 중순과 8월 초에 정점(100)을 찍고 마지막 주에 34다. 작년 11월 값(40)과 비슷하다 ✅.
- **브랜드 간 상대 규모**(같은 요청 안에서만): 토픽 기준으로 Black Rifle > Living Proof > Batiste > Death Wish > Jinx 순이다 ✅(평균값).
- **어떤 이벤트가 있었는지**: 급등 주를 광고/가격 행사 시점과 맞춰볼 수 있다(Batiste 5월 17일 주).
- **연관 검색어**: Black Rifle의 `near me`, `pods`, `tucson`처럼 소비자가 붙이는 말을 볼 수 있다. 일부 브랜드만 나온다.

## 10. 정해야 할 것
1. 브랜드별 검색어. **Batiste와 Jinx는 결정됨**(3-3). 남은 것: Living Proof를 `Living Proof shampoo`로 할지, 나머지 둘을 이름 그대로 둘지.
2. 한 요청에 몇 개를 묶을지. (제안: 5개 한 요청. 척도가 공유되고 페이지 로드가 1번이다. 모양은 단독 요청과 같다(3-4). 단, 수식어를 붙인 5개 조합에서 작은 계열이 얼마나 뭉개지는지는 보지 못했다 ❓. 최고값이 20 미만인 계열이 나오면 그 브랜드만 단독 요청을 더한다)
3. 연관 검색어를 "상위 20개 검색어"의 재료로 쓸지. (제안: 쓰지 않는다. 비거나 3~8개다. 소스 6의 자동완성 방식을 쓴다)
4. 연속 수집 주기와 429 대응. (제안: 하루 1회, 429면 중단하고 그 실행을 "could not look"으로 기록한다)
5. 척도 표기: 화면에 "상대값, 같은 요청 내에서만 비교"라고 적을지. (제안: 적는다)
6. 차단이 풀린 뒤 확인할 것(요청 1회면 된다): 수식어를 붙인 5개 비교가 값을 주는지, 고정 날짜 주소(`date=2025-11-10%202026-11-10`)가 `today 12-m`과 같은 응답을 주는지.

## 11. attribute 제안 (사용자와 합의 전)
한 행은 **(검색어, 지역, 비교 묶음, 주)의 관측 1개**다. 12개월이면 브랜드당 53행, 5개 브랜드 265행이다.

| attribute | 예시 | 원본 | 비고 |
|---|---|---|---|
| brand | `Batiste` | 우리가 정함 | |
| keyword | `Batiste dry shampoo` | 요청의 `keyword[].value` | 화면에 넣은 문자열 그대로 |
| keyword_type | `term` | 요청의 `type`(`BROAD`) | 토픽을 쓰게 되면 `topic`과 토픽 ID |
| week_start | `2025-11-09` | `time`(초) | 일요일 00:00 UTC |
| value | `40` | `value[i]` | 0~100 정수. 상대값 |
| is_partial | `false` | `isPartial` | 마지막 주만 `true` |
| has_data | `true` | `hasData[i]` | `false`면 값 0과 구분한다 |
| geo | `US` | 요청의 `geo.country` | |
| timeframe | `2025-11-10 2026-11-10` | 요청의 `time` | 척도가 이 창 안에서 정해진다 |
| comparison_set | 검색어 5개의 순서 있는 목록 | 요청의 `comparisonItem[]` | 값은 이 묶음 안에서만 비교할 수 있다 |
| source_url | 고정 날짜를 넣은 explore 주소 | 우리가 만듦 | 같은 화면을 다시 열어 대조할 수 있게 한다(고정 날짜 주소는 미확인 ❓) |
| collected_at | 수집 시각 | 우리 쪽 | |

- 고유 키(제안): keyword + keyword_type + geo + comparison_set + week_start. timeframe은 키에 넣지 않는다. 넣으면 창이 매일 움직여서 날마다 53행이 새로 생긴다.
- 재실행: 같은 키의 행은 value, is_partial, timeframe, collected_at을 덮어쓴다. 12개월 창 밖으로 나간 주는 지우지 않고 ended로 둔다. 그 행의 값은 마지막으로 본 timeframe의 척도다.
- 넣지 않는 것(제안): 연관 검색어(대부분 비어 있다), 주(state)별 관심도(과제 요구 밖), 검색량(존재하지 않는다).
- 실행 단위로 남길 것: 페이지 로드 수, 소요 시간, 429 여부(막히면 "could not look").

## samples/
| 파일 | 내용 |
|---|---|
| `explore_batiste_term.txt` | explore 응답(위젯과 토큰). 첫 줄은 요청 주소, 둘째 줄은 상태 코드, 이후는 본문 원본 |
| `explore_compare5_terms.txt` | 5개 비교의 explore 응답 |
| `multiline_batiste_term.txt` | Batiste 검색어 시계열 53점 |
| `multiline_batiste_term_rerun.txt` | 위와 같은 요청 재실행 |
| `multiline_batiste_topic.txt` | Batiste 토픽 시계열 |
| `multiline_jinx_term.txt`, `multiline_jinx_topic.txt`, `multiline_jinx_dog_food_term.txt` | Jinx 세 가지 |
| `multiline_compare5_terms.txt`, `multiline_compare5_topics.txt` | 5개 비교 (`value`에 5개씩) |
| `comparedgeo_batiste_term.txt` | 주별 관심도 |
| `related_queries_*.txt` | 연관 검색어 (`_EMPTY`는 빈 응답 예시) |
| `autocomplete_*.txt` | 자동완성 토픽 후보. 브랜드 5개와 추가 5개(`Jinx_dog_food` 등) |
| `trends_page_batiste.png` | 화면 캡처 |

용량 276 KB. 줄인 것: `explore/pickers/category`와 `pickers/geo`(합계 약 190 KB, 카테고리/지역 목록이라 제외). 주별 응답은 하나만 두었고, 같은 브랜드의 반복된 비교 응답과 비교 요청의 주별 위젯(5개씩)은 제외했다. 429 화면(`sorry` 페이지)은 저장하지 않았다.
