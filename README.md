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

## 환경 주의

본 repo 의 패키지는 **특정 실행 환경 기준 경로** 가 하드코딩돼 있을 수 있음. 예:

- `analytics-leader-session-cleanup/` 는 회사 PC `C:/Users/doodles/...` 기준.

다른 환경(다른 Windows 사용자명, macOS·Linux) 으로 이식하려면 각 패키지의 INSTALL.md 설계
결정 메모 섹션을 참조해 경로 치환 필요. 민감정보는 아니며 상정된 대상 환경이 반영된 것.

## 향후 확장

새 패키지가 생기면 repo root 직계 디렉토리로 추가. 각 패키지 내부에 자체 INSTALL.md /
README / 필요 파일을 둠. 다른 패키지 간 의존성 없이 독립 사용 가능하도록 유지.

## 라이선스

내부 운영 도구로 시작했으므로 공식 라이선스는 부여하지 않음 (기본 "저자권 보유"). 외부 팀이
자기 환경에 적용하는 용도로만 활용 가능하며, 재배포·2차 변경본 공개는 사전 합의 필요.
문의·이슈는 compass 운영팀(architect / maintenance) 경유.
