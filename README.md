# agent-toolkit-shared

Compass 생태계에서 외부 팀에 공유하는 에이전트 운영 패키지·도큐먼트 저장소.

본 repo 는 **외부 팀 (분석팀 등) 전달용 패키지의 영구 허브**. Compass 내부 운영 레포는
private 이지만, 외부 팀은 그쪽 접근 권한이 없어서 브라우저만으로 열람·clone 가능한 공간이
따로 필요함. 이 repo 에 디렉토리별로 각 패키지를 배치한다.

## 수록 패키지

### `analytics-leader-session-cleanup/`
KRAFTON 분석팀 팀장 에이전트(`analytics-leader`) 용 자동 세션 메모리 정리 시스템.
Claude Code 세션의 ctx 사용률이 40% 를 상향 돌파하는 순간을 감지해 체크포인트 저장 +
`/export` + `/compact` 사이클을 자동 주입한다. Compass Phase 2 구조를 분석팀 환경에
맞춰 Slack·task-broker 비서 보고를 제거하고 로컬 완결형 (`terminal-only` agent_type) 으로
간소화한 버전.

설치는 `analytics-leader-session-cleanup/INSTALL.md` 를 읽고 분석팀장이 스스로 수행.

### `analytics-gemma-materials-guide/`
커뮤니티 댓글 요약·번역·센티멘트 분석에 로컬 Gemma를 적용할 때의 운영 가이드.
Gemma를 최종 리포트 작성자가 아니라 `translation_ko`, `sentiment`, `targets`,
`key_points`, `evidence`, `uncertainty` 같은 materials 추출기로 두고, validator warning과
강한 모델을 후속 단계에 배치하는 구조를 설명한다.

집 PC 기준 실험 결과는 참고값이며, 회사 PC에서는 실제 댓글 50~100개 shadow run으로 처리
시간·부하·품질을 별도 재검증해야 한다.

### `packages/image-canvas/`
OpenAI `gpt-image-1` 기반 이미지 생성 stdio MCP 서버. 도구 1개 (`generate_image`).
페르소나·도메인 비종속 plain 패키지로, 호출 측 CLAUDE.md 가 프롬프트 톤·페르소나를
얹는다. 첫 사용처는 Compass 외부의 새벽·노을 자매 페르소나(공유 출력 폴더 사용)지만,
이후 다른 팀·페르소나가 같은 도구를 그대로 재사용할 수 있도록 설계했다.

`packages/image-canvas/README.md` 의 `.mcp.json` 등록 예와 환경변수
(`OPENAI_API_KEY`, `IMAGE_CANVAS_OUTPUT_DIR`) 안내를 따라 호출 측에서 설정.

### `packages/x-observed-search-collection/`
X.com 공개 검색 화면에 노출되는 포스트를 주제별로 수집할 때 쓰는 운영 매뉴얼.
full archive API 없이 브라우저 검색 surface를 날짜 window로 나누어 관측하고,
`tweet_url` dedupe, gap 재검색, AI 분석 guard, 보고서 한계 문구까지 포함한다.
집이나 개인 환경에서 다른 주제의 소셜 반응을 모을 때 `README.md` 절차를 기준으로 사용.

## 활용처 요약

본 repo 가 다루는 패키지는 크게 네 갈래로 묶인다 (현 시점):

1. **외부 팀(분석팀) 세션 정리 자동화** — `analytics-leader-session-cleanup/`.
   private 운영 레포에 직접 접근 못 하는 외부 팀이 브라우저로 clone 해서 자기 환경에
   설치할 수 있도록 패키지화한 첫 사례.
2. **분석 에이전트 로컬 전처리 가이드** — `analytics-gemma-materials-guide/`.
   OpenAI/Anthropic API 비용을 줄이기 위해 로컬 Gemma를 댓글 materials 추출기로 쓰는
   패턴을 정리한다. thinking off 기본값, wrapper 모델의 한계, source conflict validator
   처리, 회사 PC shadow run 필요성을 포함한다.
3. **maintenance 이중화·공유 로그** — 본 repo 자체가 Compass 운영 중 안전 사고 후속으로
   maintenance 가 작업 산출물을 공개 가능한 형태로 외부에 노출하는 *공식 허브* 가 됨
   (메모: `t-20260424-bfb551`, public repo `doodles-bit/agent-toolkit-shared`).
4. **페르소나·팀 간 공유 도구** — `packages/image-canvas/`. 새벽·노을 자매가 같은 도구를
   페르소나 색깔별로 호출하는 패턴을 시작으로, 향후 다른 팀에서도 동일한 plain 도구를
   재사용 가능하게 둔다.
4. **공개 검색 기반 소셜 수집 운영 매뉴얼** — `packages/x-observed-search-collection/`.
   X.com full archive가 아닌 observed search dataset을 만들 때 필요한 query 설계, 1일
   window 재수집, union/dedupe, gap check, 보고서 표현 원칙을 공유한다.

## 환경 주의

본 repo 의 패키지는 **특정 실행 환경 기준 경로** 가 하드코딩돼 있을 수 있음. 예:

- `analytics-leader-session-cleanup/` 는 회사 PC `C:/Users/doodles/...` 기준.
- `analytics-gemma-materials-guide/` 의 시간·부하 수치는 집 PC 실험 기준. 회사 PC에서는
  실제 댓글 샘플로 smoke test 후 batch 크기와 동시성을 정해야 함.
- `packages/image-canvas/` 의 사용 예시 경로는 Compass 운영 PC `C:/Users/pyeon/...`
  기준. 다른 환경에서는 `IMAGE_CANVAS_OUTPUT_DIR` 절대경로만 환경에 맞게 바꿔주면 됨.

다른 환경(다른 Windows 사용자명, macOS·Linux) 으로 이식하려면 각 패키지의 INSTALL.md 설계
결정 메모 섹션을 참조해 경로 치환 필요. 민감정보는 아니며 상정된 대상 환경이 반영된 것.

## 향후 확장

새 패키지가 생기면 repo root 직계 디렉토리로 추가. 각 패키지 내부에 자체 INSTALL.md /
README / 필요 파일을 둠. 다른 패키지 간 의존성 없이 독립 사용 가능하도록 유지.

## 라이선스

내부 운영 도구로 시작했으므로 공식 라이선스는 부여하지 않음 (기본 "저자권 보유"). 외부 팀이
자기 환경에 적용하는 용도로만 활용 가능하며, 재배포·2차 변경본 공개는 사전 합의 필요.
문의·이슈는 compass 운영팀(architect / maintenance) 경유.
