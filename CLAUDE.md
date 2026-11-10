# baro-1day-trial

1일 트라이얼 과제. Part 1은 "Market Radar"로, 브랜드를 넣으면 10개 소스(광고, 매대, 검색, 소셜)를 한 테이블로 모으는 수집기를 만든다.

## 작업 방식: superpowers를 그대로 따른다

이 프로젝트는 superpowers 플러그인(프로젝트 범위로 설치됨)의 흐름을 바꾸지 않고 쓴다.

| 단계 | 스킬 | 담당 | 산출물 |
|---|---|---|---|
| 설계 | `superpowers:brainstorming` | 메인 세션 | `docs/superpowers/specs/YYYY-MM-DD-<주제>-design.md` |
| 계획 | `superpowers:writing-plans` | 메인 세션 | `docs/superpowers/plans/YYYY-MM-DD-<기능>.md` |
| 구현 | `superpowers:subagent-driven-development` | Sonnet 서브에이전트 | 작업별 커밋 |
| 마무리 | `superpowers:finishing-a-development-branch` | 메인 세션 | PR |

### 모델 분담
- 메인 세션(상위 모델)은 스펙, 계획, 판정, 최종 리뷰만 한다. 구현 코드를 직접 쓰지 않는다. 예외는 전역 CLAUDE.md와 같다(한두 줄 수정, 빌드 오류 즉시 수정, 설정·문서 편집).
- 구현 서브에이전트는 항상 `model: "sonnet"`을 명시해서 띄운다. 모델을 생략하면 세션 모델을 물려받으므로 생략하지 않는다.
- 작업별 리뷰는 Sonnet으로 한다. 수정이 4회차 이상으로 가거나 설계 판단이 걸린 작업만 상위 모델로 올린다.
- 브랜치 전체 최종 리뷰는 가장 상위 모델로 한다.

### 브랜치와 PR
- 계획 하나 = 브랜치 하나 = PR 하나. main에서 직접 구현하지 않는다.
- 계획 실행 방식은 항상 Subagent-driven을 고른다.
- 마무리는 항상 "Push and Create PR"을 고른다. 로컬 머지는 하지 않고, 머지는 사용자가 한다.
- 계획은 작게 나눈다. 공통(스키마와 실행기) 계획을 먼저 하나 만들고, 그 뒤로 소스마다 하나씩 만든다.
- worktree는 superpowers 기본 위치인 `.worktrees/`를 쓴다.

## 모든 계획의 Global Constraints (과제 규칙)
계획을 쓸 때 아래를 Global Constraints에 그대로 옮긴다.

1. **직접 짠 코드.** 최소 1개 소스는 유료 스크래핑 서비스 없이 수집한다.
2. **재실행 안전.** 두 번 돌려도 중복이 생기지 않는다. 사라진 항목은 삭제하지 않고 ended로 표시한다.
3. **정직한 공백.** 접근하지 못한 소스는 "could not look"으로 기록하고, "nothing found"로 기록하지 않는다. 일부만 수집했으면 그 사실을 표시한다.
4. **깨끗한 수집.** 남의 계정을 쓰지 않는다. 일반인 개인정보(리뷰어 이름 등)를 저장하지 않는다. 요청 간격을 둔다.

## 확인된 가정
- VPN(미국 IP) 사용과 CAPTCHA 우회는 BARO 측에서 허용한다고 사용자가 확인했다(2026-11-10).
- 결과를 한 테이블로 묶지 않아도 된다고 BARO 측에서 확인했다고 사용자가 전했다(2026-11-10). 성격별로 테이블을 나눈다.
- 환영 메일은 사용자가 이미 가입해 둔 수신함에서 읽는다. Amazon 계정도 같은 주소로 만든다.
- Part 1과 Part 2는 별개 과제다. 데이터와 키를 공유하지 않는다.

## 정해진 순서 (2026-11-10)
1. 소스별 원본 수집기를 먼저 구현한다. 수집기는 소스의 원본을 그대로 저장하는 데까지만 한다.
2. 원본 수집기가 다 구현된 뒤에, 여러 소스를 가로지르는 인사이트와 테이블 스키마를 메인 스레드에서 정한다.

## 정해진 것 (2026-11-10)
- 유료 경로는 Apify 한 곳으로 모은다. 토큰은 저장소 루트 `.env`의 `APIFY_TOKEN`에 있다. `.env`는 커밋하지 않는다. 토큰이 없으면 그 소스는 "could not look"으로 기록한다.
- 소스별 접근 경로, attribute, 남은 결정은 `part1/collectors/<번호_이름>/source_info.md`에 있다. 소스마다 스레드가 따로 있다.
- "직접 짠 코드" 규칙은 유료 서비스 없이 받는 소스로 채운다: Google Ads Transparency, Meta Ad Library, 검색 관심도, Ulta, Shopify 자사몰.
- Google 검색 결과의 광고는 수집하지 않고 검색어마다 "could not look"으로 기록한다.
- 원본 수집기는 `part1/collectors/<번호_이름>/`에서 구현한다. 조사 결과(`source_info.md`)와 테스트가 읽는 샘플(`samples/`)도 같은 폴더에 둔다. 모든 수집기가 따르는 공통 약속은 `part1/collectors/README.md`에 있고, 소스별 요구는 각 폴더의 `spec.md`에 있다.
- BARO에 넘기는 문서는 영어로 쓴다: `part1/collectors/` 아래의 `README.md`와 `spec.md`, 그리고 앞으로 쓸 노트와 설계 문서. 사용자와의 대화는 한국어로 한다.
- 수집기는 시간 범위를 받지 않고 실행 시점의 스냅샷만 쓴다. 새 항목 추가와 ended 표시는 테이블에 넣는 단계에서 이전 상태와 비교해 처리한다. ended 표시는 그 범위의 실행이 `ok`일 때만 한다.
- 테이블은 네 성격으로 나눈다.
  - ads: 1, 2, 3번의 광고와 10번의 오퍼·가입 폼·메일. 유료 채널과 자사 채널을 구분한다.
  - product page: 4, 5, 9, 10번의 상품. 리뷰는 상품의 자식 행으로 둔다.
  - search: 6번의 검색 순위와 7번의 관심도.
  - social post: 8번의 게시물.
- TikTok 크리에이터 계정명(`posts.creator_handle`)과 TikTok Shop 판매자명(`products.seller_name`)은 컬럼에 저장한다. 표시 이름, 아바타, 위치는 저장하지 않는다.

## 아직 정하지 않은 것
- 테이블별 컬럼과 인사이트. 메인 스레드에서 정하는 중이다.
- 수집기를 돌릴 네트워크(VPN 사용 여부). 사용자가 정한다.

## 참고 문서
- `part1/collectors/<번호_이름>/source_info.md`: 소스별 조사 결과와 결정. 소스 계획을 쓸 때 여기서 가져온다.
- `part1/docs/access-analysis.md`: 초기 접근 조사(2026-11-10 오전, 한국 IP). 이후 내용은 소스별 문서가 우선한다.
- `part1/docs/attribute-candidates.md`: 광고/비광고 분류와 attribute 후보.
- `part1/docs/paid-services-ads-search.md`, `part1/docs/paid-services-commerce-social.md`: 유료 서비스 조사.
- `part2/docs/analysis.md`: Part 2 요구사항, 데이터 측정값, 설계를 바꾸는 함정, deep dive 비교(2026-11-10). Part 2 계획은 여기서 사실을 가져온다.
