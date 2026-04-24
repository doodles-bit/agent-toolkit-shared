# analytics-leader 세션 메모리 자동 정리 — 설치 가이드

이 패키지는 KRAFTON 분석팀 팀장 에이전트(`analytics-leader`) 의 Claude Code 세션이
ctx 사용률 40% 를 상향 돌파하는 순간을 감지해 **자동 정리 사이클**(메모리 점검 →
체크포인트 저장 → `/export` + `/compact`) 을 주입하는 훅 한 세트다. Compass 쪽
Phase 2 자동 정리 시스템을 분석팀 환경에 맞춰 **Slack·비서 보고를 제거하고 로컬 완결형** 으로
간소화했다.

본 가이드는 설치·배포를 **분석팀장(Claude Code 기반 에이전트) 이 스스로** 수행할 수 있도록
작성됐다. 혼자 읽고 따라하면 된다.

---

## 0. 무엇이 달라지나

설치 전:
- 세션 ctx 가 70~80% 로 붇다가 오케스트레이션이 실패하는 일이 있었음 (2026년 4월 실제 사례).

설치 후:
- statusLine 스크립트가 매 턴 ctx 를 체크하다 40% 로 상향 돌파하는 순간 `cleanup-flag` 파일을 생성.
- 다음 프롬프트 제출 시 UserPromptSubmit 훅이 flag 를 읽어 정리 사이클 지시를 `additionalContext` 로 주입.
- 분석팀장이 그 지시를 읽고 로컬 메모리 점검 → 체크포인트 저장 → `/export` + `/compact` 를 수행.
- 정리 후 10분 내 다시 40% 재돌파하면 자동 정리는 중단되고 "수동 모드" 로 전환 (사용자 개입 요청).

---

## 1. 사전 조건

- 회사 PC 의 Windows 경로가 `C:/Users/doodles/` 기준 (`~` 는 `C:/Users/doodles/` 에 대응).
- Python 3 이 PATH 에 설치돼 있음. `python --version` 으로 확인.
- Claude Code 가 이미 설치·구동 중.
- 분석팀 레포: `C:/Users/doodles/project_repo/ai_agent_team`.
- task-broker trigger 스크립트: `C:/Users/doodles/project_repo/ai_agent_team/task-broker/trigger.ps1` (존재 확인).
- 팀원 세션(`palm`, `hifirush`, `verification`, `copperhead`, `editor`, `social-marketing`) 은 별도 터미널로 돌지만 이 훅은 cwd 검사로 `analytics-leader` 세션에서만 동작하므로 팀원 세션엔 영향 없음.

---

## 2. 설치 단계

### 2-1. 파일 복사

패키지 4개 파일을 `C:/Users/doodles/` 하위 표준 위치로 복사한다.

```bash
# 디렉토리 없으면 생성
mkdir -p ~/.claude/hooks
mkdir -p ~/.claude/state/analytics-leader
mkdir -p ~/project_repo/ai_agent_team/.claude/session-checkpoints

# 파일 복사 (이 패키지가 위치한 디렉토리에서 실행)
cp statusline.py ~/.claude/statusline.py
cp user-prompt-submit.py ~/.claude/hooks/user-prompt-submit.py
```

복사 직후 확인:

```bash
ls -la ~/.claude/statusline.py ~/.claude/hooks/user-prompt-submit.py
python ~/.claude/statusline.py < /dev/null   # 입력 없으면 "statusline: invalid input" 출력 — 정상
```

### 2-2. Claude Code settings 등록

`~/.claude/settings.json` 을 열고, `statusLine` · `hooks` 필드를 아래와 같이 설정한다.
이미 해당 필드가 있으면 **덮어쓰기** 또는 **기존 명령에 추가** 후 지침대로 병합한다.
`settings-snippet.json` 의 내용을 참고하면 된다.

```json
{
  "statusLine": {
    "type": "command",
    "command": "python \"C:/Users/doodles/.claude/statusline.py\""
  },
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:/Users/doodles/.claude/hooks/user-prompt-submit.py\""
          }
        ]
      }
    ]
  }
}
```

**기존 훅이 있을 경우**: 배열 안에 엔트리를 추가하면 둘 다 실행된다. 순서 영향은 없음 —
본 훅은 cwd 가 `analytics-leader` 가 아니면 즉시 종료한다.

### 2-3. 설정 반영

Claude Code 세션을 **새로 열어** settings.json 변경이 반영되도록 한다. 세션 중간에는
statusLine · hooks 설정이 즉시 리로드되지 않는다.

---

## 3. 동작 검증 체크리스트

아래를 **설치 직후** 순서대로 돌려 훅이 살아있는지 확인. 각 단계가 끝나면 다음 단계로.

### ✅ 3-1. statusLine 활성 확인

분석팀장 세션 상태줄에 다음 형식이 보여야 한다:

```
ai_agent_team | claude-opus-4-x | 12% | $0.04
```

보이지 않으면:
- `C:/Users/doodles/.claude/statusline.py` 존재 확인
- settings.json 의 `statusLine.command` 가 정확한 경로로 python 을 호출하는지 확인
- 세션 재시작

### ✅ 3-2. ctx 40% 도달 시 flag 생성 확인

실제로 ctx 를 40% 까지 밀기 전에 테스트로 수동 flag 를 만들어 훅 작동을 검증.

```bash
# (세션 종료 없이, 터미널에서 직접)
mkdir -p ~/.claude/state/analytics-leader
python -c "import json, time; open('/c/Users/doodles/.claude/state/analytics-leader/cleanup-flag','w').write(json.dumps({'trigger_time': time.time(), 'ctx_pct': 40.5, 'session_id': 'test-session', 'project': 'analytics-leader'}))"
```

그 다음 Claude Code 에 아무 프롬프트나 입력해본다 (예: "ping"). 분석팀장 응답에
`[자동 세션 컨텍스트 정리 트리거 — analytics-leader / ctx 41% 도달]` 으로 시작하는
가이드가 additionalContext 로 들어오면 정상.

검증 후:
```bash
ls ~/.claude/state/analytics-leader/   # cleanup-flag 가 사라져 있어야 한다 (훅이 삭제)
cat ~/.claude/state/analytics-leader/cleanup-history.log  # cleanup-start 이벤트 1줄 적혀있어야 함
```

### ✅ 3-3. 쿨다운/수동 모드 전환 검증

10분 쿨다운 로직 테스트.

```bash
# 쿨다운 시뮬레이션 — 방금 정리가 끝난 것처럼 timestamp 기록
date +%s > ~/.claude/state/analytics-leader/last-checkpoint.txt

# ctx 40% 미만 → 40% 이상 transition 모사하려면 statusline 을 2번 실행해야 하지만
# 간단히 수동으로 manual-mode 파일 생성해 훅 주입 동작만 확인:
python -c "import json, time; open('/c/Users/doodles/.claude/state/analytics-leader/manual-mode','w').write(json.dumps({'trigger_time': time.time(), 'ctx_pct': 40.5, 'last_checkpoint_ts': time.time()-120, 'session_id':'test-session','project':'analytics-leader'}))"
```

세션에 아무 프롬프트 입력 → `[수동 정리 모드 진입 — analytics-leader]` 메시지 확인.

복귀:
```bash
rm ~/.claude/state/analytics-leader/manual-mode
rm ~/.claude/state/analytics-leader/last-checkpoint.txt
```

### ✅ 3-4. history 로그 스키마 확인

```bash
tail -n 3 ~/.claude/state/analytics-leader/cleanup-history.log
```

각 줄은 JSON 이어야 하고 필드:
- `ts` (ISO8601 문자열)
- `event` ("cleanup-start" | "cleanup-done-pending" | "cleanup-fail" | "manual-mode")
- `project` ("analytics-leader")
- 이벤트별 부가 필드: `ctx_pct`, `session_id`, `stem`, `summary`, `step`, `reason` 등

### ✅ 3-5. 팀원 세션 비영향 확인 (선택)

`palm`, `hifirush`, `verification` 등 팀원 터미널에서도 훅이 실행은 되지만 cwd suffix 가
`/project_repo/ai_agent_team` 가 아니므로 (예: `~/project_repo/ai_agent_team` 가 아니라 다른 경로) no-op.
팀원 터미널 statusLine 이 영향 받지 않는지만 확인하면 된다.

> **참고**: 팀원 세션도 `ai_agent_team` 레포의 같은 디렉토리에서 띄운다면 훅이 동작할 수 있다.
> 현재 `TRACKED_PROJECTS` 와 `PROJECT_CONFIG` 는 analytics-leader 단일 엔트리. 팀원 세션에도
> 자동 정리가 필요하면 양쪽 파일에 엔트리를 추가하면 된다. 본 패키지 범위 밖.

---

## 4. 롤백 절차

설치가 문제를 일으키면 단계별 역순으로 해제.

### 4-1. 훅만 비활성

`~/.claude/settings.json` 에서 `statusLine` / `hooks.UserPromptSubmit` 의 본 훅 명령만 제거하거나
주석 처리. Claude Code 세션 재시작.

### 4-2. 파일 완전 제거

```bash
rm ~/.claude/statusline.py
rm ~/.claude/hooks/user-prompt-submit.py
rm -rf ~/.claude/state/analytics-leader/
```

`settings.json` 도 원상 복구.

### 4-3. 과거 설정 복원

설치 전 `settings.json` 백업을 남겨뒀다면 그걸로 복원. 남기지 않았으면 Claude Code 기본값으로
재시작하면 된다.

---

## 5. 설계 결정 메모

분석팀장이 훅을 고치거나 확장할 때 참고.

### 5-1. 새 agent_type `"terminal-only"`

Compass 프로젝트의 훅은 `secretary`(Slack 직접 응답), `teammate`(task-broker 비서 보고)
두 가지 분기를 썼다. 분석팀장은 **둘 다 해당 없음** — Slack 을 안 쓰고 비서 상위 에이전트도 없다.
그래서 `"terminal-only"` 라는 카테고리를 신설. 핵심 특징:
- 알림은 additionalContext 주입만 사용 (세션 자체가 가이드를 읽고 실행)
- 상태 이벤트는 로컬 JSONL 로그로 누적

### 5-2. cleanup-history.log 스키마

로그 파일 한 줄은 JSON 오브젝트 (JSON Lines):
```json
{"ts": "2026-04-24T17:05:12+0900", "event": "cleanup-start", "project": "analytics-leader", "ctx_pct": 41, "session_id": "abc123"}
{"ts": "2026-04-24T17:06:40+0900", "event": "cleanup-done-pending", "project": "analytics-leader", "stem": "2026-04-24_1705", "summary": "팀원 메모리 -27% / 체크포인트 저장"}
```
필드 `event` 가능 값:
- `cleanup-start` — 훅이 cleanup-flag 를 감지해 주입한 순간 (자동)
- `cleanup-done-pending` — 분석팀장이 5단계에서 append (수동)
- `cleanup-fail` — 실패 시 수동 append
- `manual-mode` — 쿨다운 내 재트리거 감지 (자동)

### 5-3. 트리거 포맷과 세션 정리의 관계

분석팀 `CLAUDE.md` 의 task-broker 트리거 포맷은 `//<sender> task:<8자리>` — P2P 태스크 통신용.
본 훅이 주입하는 `/export` + `/compact` 는 분석팀장 자신의 창(WindowTitle `analytics-leader`)
으로 가는 **Claude Code 슬래시 명령** 이며, task-broker 통신이 아니다. 따라서 task_id 포맷
규칙은 적용 안 함 — 다른 팀원·팀장 트리거 규약과는 채널이 다름.

### 5-4. 팀장 메모리 아카이브 기준

Compass 팀원은 10KB 초과면 아카이브 이동. 분석팀장은 `CLAUDE.md` 가이드를 따라:
- 10KB (≈5,000 토큰) 초과 → 다음 세션 시작 전 검토
- 15KB (≈7,500 토큰) 초과 → 즉시 분리 필수
- 한 번에 -25~30% 축소, 50% 이상 축소 금지

훅이 주입하는 지시 문구(`memory_archive_hint`) 는 위 기준을 반영한다.

### 5-5. 예외 케이스

| 상황 | 동작 |
|---|---|
| 화면 보호기·잠금 중 trigger 발동 | statusLine 은 잠금 중에도 동작 가능하지만 `/export`+`/compact` 주입은 활성 창에 key send 하므로 잠금 풀린 뒤 다음 턴에 가이드가 다시 등장 (cleanup-flag 가 생성되면 다음 프롬프트까지 유지됨) |
| 정리 중 새 위임 수신 | 가이드의 "예외 처리" 섹션대로 정리를 마칠 때까지 미룸. 팀원이 작업 중이면 트리거를 나중에 소화 |
| 40% 재진입 루프 (짧은 간격) | 쿨다운 10분 로직이 manual-mode 로 전환, 자동 루프 차단 |
| 세션 강제 종료 후 복귀 | `last-checkpoint.txt` + `cleanup-history.log` 가 남아있어 재시작 후에도 상태 추론 가능 |
| cleanup-flag 생성 시점에 사용자가 프롬프트 대신 응답 중 | flag 는 다음 UserPromptSubmit 훅 실행까지 디스크에 유지됨. 응답 완료 후 다음 입력 시 반영 |

### 5-6. 회사 PC 경로 (`C:/Users/doodles/`) vs 집 PC 경로 (`C:/Users/pyeon/`)

본 패키지는 **회사 PC 경로** (`C:/Users/doodles/...`) 로 하드코딩. 집 PC 등 다른 환경에
옮기려면 `user-prompt-submit.py` 의 `TRIGGER_SCRIPT` 와 `PROJECT_CONFIG["analytics-leader"]["project_root"]` 두 상수를 수정해야 한다.

---

## 6. 추가 운영 팁

- **로그 파일 용량**: `cleanup-history.log` 는 이벤트마다 1줄씩 추가되므로 증가 속도가 느리다.
  주기적으로 `tail -n 200 cleanup-history.log > cleanup-history.log.new && mv cleanup-history.log.new cleanup-history.log` 로 압축.
- **디버깅**: 훅이 이상 동작하면 수동으로 `python ~/.claude/hooks/user-prompt-submit.py < test.json` 으로 시뮬. test.json 에 `{"cwd": "C:/Users/doodles/project_repo/ai_agent_team"}` 등 넣어 로직 확인.
- **자주 만나는 질문**:
  - *Q: 왜 task-broker 비서 보고가 없나?* — 분석팀장 위에 비서가 없다. 팀장 자체가 최상위.
  - *Q: Slack 으로 Doodles 에게 알릴 수는 없나?* — 분석팀 봇·워크스페이스가 없어서 미지원. 필요시 추후 확장.
  - *Q: 팀원 세션(palm, hifirush 등) 도 같은 훅 쓰면 되나?* — `PROJECT_CONFIG` 에 엔트리만 추가하면 동작. 다만 팀원별 메모리 경로·아카이브 기준·체크포인트 디렉토리를 각각 맞춰줘야 한다. 본 패키지 범위 밖.

---

## 7. 문의

본 패키지는 Compass 유지보수 에이전트(maintenance) 가 작성했다. 동작 이상·개선 제안은
architect 에게 전달(→ maintenance 에게 재위임) 하거나, 분석팀장이 직접 코드를 고쳐도 된다.
각 파일은 독립적으로 읽고 실행 가능한 수준으로 주석이 달려있다.
