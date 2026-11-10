# baro-1day-trial

1일 트라이얼 과제. Part 1은 "Market Radar"로, 브랜드를 넣으면 10개 소스(광고, 매대, 검색, 소셜)를 한 테이블로 모으는 수집기를 만든다.

## 작업 방식: superpowers를 그대로 따른다

이 프로젝트는 superpowers 플러그인(프로젝트 범위로 설치됨)의 흐름을 바꾸지 않고 쓴다.
전역 스킬 `build-plan` / `execute-plan`은 역할이 겹치므로 이 프로젝트에서는 쓰지 않는다.

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
4. **깨끗한 수집.** 공개 페이지만 본다. 남의 계정을 쓰지 않는다. 일반인 개인정보(리뷰어 이름 등)를 저장하지 않는다. 요청 간격을 둔다.
5. **CAPTCHA와 로그인 벽은 우회하지 않는다.** 막히면 3번 규칙대로 기록한다.

## 아직 정하지 않은 것
- 테이블 스키마. 확정 전에는 구현 계획을 쓰지 않는다.
- 미국 IP 사용 여부, 유료 서비스 사용 여부, 환영 메일 수신함.

## 참고 문서
- `part1/docs/access-analysis.md`: 소스별 접근 조사 결과(2026-11-10, 한국 IP). 계획에 소스별 사실을 옮길 때 여기서 가져온다.
- `part1/docs/attribute-candidates.md`: 광고/비광고 분류와 attribute 후보.
