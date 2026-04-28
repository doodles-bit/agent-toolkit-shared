# slack-channel

Slack 채널 폴링 + reply 도구를 노출하는 stdio MCP 서버. **clone-able / 환경변수 기반** — 토큰·채널·리액션 이모지·트리거 윈도우 모두 환경변수로 분기. Compass 생태계의 architect / 비서 / 새벽 / 노을 등 여러 페르소나가 *같은 코드베이스* 를 공유.

`architect/slack-channel/` 인스턴스를 base 로 추출. 기존 인스턴스는 그대로 운영 (이번 패키지는 신규 환경 — 회사 PC Codex CLI 등 — 셋업용).

## 도구

| 이름 | 입력 | 동작 |
|---|---|---|
| `reply` | `chat_id`, `text`, `thread_ts?` | Slack `chat.postMessage` 로 응답 전송. 호출 직후 큐를 드레인해 미처리 메시지 동봉. |
| `get_pending_messages` | (없음) | 큐에 쌓인 미처리 메시지 조회 + 큐 비움. |

큐 드레인 시 `SLACK_REACTION_EMOJI` 가 설정된 메시지에 자동 리액션 발사 (읽음 표시).

## 환경변수

| 키 | 필수 | 기본 | 설명 |
|---|:-:|---|---|
| `SLACK_BOT_TOKEN` | ✅ | — | Slack 봇 토큰 (`xoxb-...`). User scope 환경변수 권장. Windows 에선 `setx` 후 새 터미널 사용. **`.mcp.json` / `config.toml` 에 평문 하드코딩 금지.** |
| `SLACK_ALLOWED_CHANNELS` | △ | — | 폴링할 채널 ID 콤마 구분. 예: `C0AUCNQ3XHV,C0AU66G8TL1`. |
| `SLACK_CHANNEL_ID` | △ | — | 단일 채널 ID. `SLACK_ALLOWED_CHANNELS` 가 비어있을 때만 fallback 으로 사용. *둘 중 하나는 필수.* |
| `SLACK_ALLOWED_USERS` | ⬜ | — | 허용 사용자 ID 콤마 구분. 비어있으면 모든 사용자 메시지 폴링. |
| `SLACK_REACTION_EMOJI` | ⬜ | `triangular_ruler` | 읽음 리액션 이름 (콜론 제외). 빈 문자열이면 리액션 비활성. |
| `SLACK_CHANNEL_LABEL` | ⬜ | `(unspecified)` | 기본 instructions 의 채널 표기 라벨 (예: `#tech-desk`). 사람용. |
| `SLACK_POLL_INTERVAL_MS` | ⬜ | `3000` | 폴링 주기 (ms). 최저 1000. |
| `AGENT_NAME` | ⬜ | `slack-channel` | MCP 서버 이름 (식별자). |
| `AGENT_VERSION` | ⬜ | `1.0.0` | MCP 서버 버전. |
| `AGENT_INSTRUCTIONS_FILE` | ⬜ | — | 페르소나·운영 룰을 담은 파일 절대경로. 우선순위: 파일 > `AGENT_INSTRUCTIONS` > 기본 텍스트. |
| `AGENT_INSTRUCTIONS` | ⬜ | — | 짧은 instructions 직접 텍스트. 파일이 비어있을 때 사용. |
| `TRIGGER_SCRIPT_PATH` | ⬜ | — | Claude Code wt 탭 자가 알림용 PowerShell 스크립트 경로 (Compass 의 `task-broker/trigger.ps1` 류). 비면 트리거 비활성. |
| `TRIGGER_WINDOW` | ⬜ | — | 트리거 대상 wt 탭 제목. `TRIGGER_SCRIPT_PATH` 와 함께 둘 다 있어야 트리거 작동. |
| `TRIGGER_KEY` | ⬜ | `//slack` | 트리거가 클립보드 paste 할 키. |
| `TRIGGER_DEBOUNCE_MS` | ⬜ | `3000` | 트리거 디바운스 (ms). |
| `CODEX_ENABLED` | ⬜ | `false` | `true` 면 Codex MCP client 모드 활성. 메시지 수신 시 큐·트리거·MCP 노출 대신 codex 자식 프로세스를 호출해 응답을 Slack 채널에 reply. |
| `CODEX_BIN` | ⬜ | `codex` | codex 실행 파일 경로·이름. |
| `CODEX_CWD` | △ | — | codex `mcp-server` 의 cwd 절대경로. `CODEX_ENABLED=true` 일 때 *필수*. 새벽이용은 `dawn-dusk/saebyeok-codex/` 절대경로. |
| `CODEX_REQUEST_TIMEOUT_MS` | ⬜ | `60000` | codex JSON-RPC 요청 타임아웃. 최저 10000. |

`SLACK_APP_TOKEN` 은 *현 코드 미사용* — Socket Mode 또는 향후 확장 위한 placeholder. 필요 시 추후 별 라운드.

## 두 가지 운영 모드

본 서버는 *같은 코드베이스* 가 두 가지 모드로 동작:

| 모드 | 활성 조건 | Slack 메시지 도착 시 | 응답 주체 |
|---|---|---|---|
| **Claude Code MCP** | `CODEX_ENABLED` 미설정 또는 `false` (기본) | 큐 적재 + (옵션) wt 탭 트리거 + `mcp.notification` 발사 | Claude Code 가 `get_pending_messages` 도구로 꺼내 자율 응답 |
| **Codex MCP client** | `CODEX_ENABLED=true` + `CODEX_CWD` 설정 | `codex` 자식 프로세스의 `codex` / `codex-reply` 도구 호출 → 응답 텍스트를 Slack 채널 본문에 reply | codex 자식 (cwd 의 `AGENTS.md` 페르소나 + 메모리 자동 로드) |

Codex 모드는 Slack ⇄ codex agent 간 *자동 왕복* — 호출 측 Claude Code 세션이 필요 없음. *옵션 D 검증* (새벽이 GPT-5.5 마이그레이션) 의 핵심 토포지.

## 셋업 — Claude Code MCP 모드 (기본)

```bash
# 1) 패키지 받기
git clone https://github.com/doodles-bit/agent-toolkit-shared.git
cd agent-toolkit-shared/packages/slack-channel
npm install

# 2) 토큰 환경변수 등록 (Windows 예시)
setx SLACK_BOT_TOKEN "xoxb-XXXXXXXXXXXX-XXXXXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXX"
# (새 터미널부터 반영)

# 3) 동작 확인 — stdio 라 직접 실행 시 바로 input 대기 모드.
SLACK_ALLOWED_CHANNELS=C0AUCNQ3XHV npx tsx server.ts
```

## 셋업 — Codex MCP client 모드 (회사 PC 검증 시나리오)

새벽이 옵션 D 검증 흐름. 회사 PC 에서 격리된 Slack 봇 채널에 메시지 보내면 자동으로 `dawn-dusk/saebyeok-codex/` 의 페르소나 + 메모리를 로드한 codex agent 가 응답.

```powershell
# 1) 패키지 받기
git clone https://github.com/doodles-bit/agent-toolkit-shared.git
cd agent-toolkit-shared/packages/slack-channel
npm install

# 2) Codex CLI 설치 + 검증 봇 토큰 등록 (User scope)
#    (codex 설치는 OpenAI 공식 문서 참조 — 본 패키지 범위 밖)
setx SLACK_BOT_TOKEN "xoxb-..."   # 회사 PC 검증용 봇 토큰

# 3) 새벽이 시드 디렉토리 도달 (clone / zip / rsync 중 결정된 방식)
#    예: dawn-dusk/saebyeok-codex/ 가 C:/Users/<USER>/dawn-dusk/saebyeok-codex/ 에 위치
#    그 sibling 으로 dawn-dusk/memory/shared/ 도 함께 위치 — AGENTS.md 의 ../memory/shared/ 참조 작동.

# 4) 환경변수 설정 + 서버 시작
$env:CODEX_ENABLED       = "true"
$env:CODEX_CWD           = "C:/Users/<USER>/dawn-dusk/saebyeok-codex"
$env:SLACK_ALLOWED_CHANNELS = "C0XXXXXXXXX"   # 검증 봇 채널 ID
$env:SLACK_CHANNEL_LABEL = "#dawn-codex-test"
$env:AGENT_NAME          = "saebyeok-codex"
# 트리거는 Codex 모드에선 의미 없음 — 비워둠
npx tsx server.ts

# 5) 시작 로그에 다음 라인 보이면 통과:
#    [codex] connected. tools=[codex, codex-reply, ...]
#    [slack] Codex MCP server connected (agent mode, cwd=...)
#    [poll] Polling started (..., codex: on)

# 6) 검증 채널에 Slack 메시지 입력 → 새벽이 페르소나로 응답
#    첫 메시지: codex tool 호출 → conversation_id 생성 + 맵 등록
#    후속: codex-reply 호출 (같은 conversation_id) → 대화 이어짐
#    AGENTS.md 의 메모리 읽기 5개 (persona/recent/shared/{summary,schedule,contacts}) 가 적용되는지 확인.
```

**`conversation_id` 추출 — 라이브 검증 이전 추정**: 본 client 는 codex 응답 result 객체에서 `_meta.conversationId`, `conversationId`, `conversation_id`, `structuredContent.*`, content text JSON 안 등 *여러 후보 경로* 를 순회해 추출. 실제 codex 응답 구조 확인 후 (첫 라이브 호출의 stderr 로그) 추출 로직 조정 필요. 추정된 모든 경로에서 못 찾으면 후속 메시지가 *새 대화* 로 처리됨 (대화 맥락 유실) — 이때 server.log 의 `[codex] 응답에서 conversation_id 못 찾음 — result keys: ...` 라인의 keys 로 정확한 경로 파악 후 `codex-client.ts:extractConversationId()` 갱신.

## Codex CLI 등록 예시 (`~/.codex/config.toml`)

```toml
# ~/.codex/config.toml
[mcp_servers.slack-channel]
command = "npx"
args = ["tsx", "C:/Users/<USER>/agent-toolkit-shared/packages/slack-channel/server.ts"]
# 시크릿은 env 가 아닌 env_vars (이름만) 로 forward — 토큰 평문이 config 에 안 들어가게.
env_vars = ["SLACK_BOT_TOKEN"]
startup_timeout_sec = 30
tool_timeout_sec = 90

[mcp_servers.slack-channel.env]
SLACK_ALLOWED_CHANNELS = "C0AUCNQ3XHV"
SLACK_REACTION_EMOJI = "triangular_ruler"
SLACK_CHANNEL_LABEL = "#tech-desk"
AGENT_NAME = "architect-slack-channel"
# 트리거 비활성 (Codex 환경에선 wt 탭 자가 알림 미적용일 가능성):
# TRIGGER_SCRIPT_PATH = "C:/.../trigger.ps1"
# TRIGGER_WINDOW = "architect"
```

> `env` 블록은 평문이 config 에 박힘. 시크릿 (`SLACK_BOT_TOKEN`) 은 *반드시* `env_vars` 의 이름 forward 만. User scope `setx` 또는 shell 환경에서 끌어와짐.

> 위 예시의 정확한 TOML 키 이름·위치는 [OpenAI Codex MCP 문서](https://developers.openai.com/codex/mcp) 기준 (2026-04 시점). Codex 버전이 바뀌면 위 키 (`startup_timeout_sec`, `env_vars` 등) 가 재명명될 수 있음 — 회사 PC 첫 셋업 시 공식 docs 한 번 확인 권장.

## Claude Code 등록 예시 (`.mcp.json`)

```jsonc
{
  "mcpServers": {
    "slack-channel": {
      "command": "npx",
      "args": [
        "tsx",
        "C:/Users/pyeon/project_repo/agent-toolkit-shared/packages/slack-channel/server.ts"
      ],
      "env": {
        "SLACK_ALLOWED_CHANNELS": "C0AUCNQ3XHV",
        "SLACK_REACTION_EMOJI": "triangular_ruler",
        "SLACK_CHANNEL_LABEL": "#tech-desk",
        "AGENT_NAME": "architect-slack-channel",
        "TRIGGER_SCRIPT_PATH": "C:/Users/pyeon/project_repo/compass/task-broker/trigger.ps1",
        "TRIGGER_WINDOW": "architect"
      }
    }
  }
}
```

`SLACK_BOT_TOKEN` 은 `env` 블록에 *적지 않는다* — 부모 프로세스 (Claude Code) 가 User scope env 를 자동 상속해 자식 MCP 에게 전달.

## Codex CLI 모드 — `.mcp.json` 또는 `~/.codex/config.toml` (선택)

Codex MCP client 모드는 *Codex 자체* 를 자식으로 띄우는 자동 왕복 모드라 *외부 MCP host* (Claude Code, Codex CLI 등) 에 등록할 필요 *없음*. 단순히 OS 백그라운드 프로세스로 띄우면 됨:

```powershell
# Windows 서비스 또는 자동 시작 항목으로 등록 (선택)
Start-Process -NoNewWindow -FilePath "npx" -ArgumentList "tsx C:/Users/<USER>/agent-toolkit-shared/packages/slack-channel/server.ts"
```

또는 단순히 PowerShell 창 열어두고 `npx tsx server.ts` 직접 실행. server.lock 으로 단일 인스턴스 보장.

## 페르소나별 운영 예시

| 페르소나 | `SLACK_REACTION_EMOJI` | `SLACK_CHANNEL_LABEL` | `AGENT_NAME` | `TRIGGER_WINDOW` |
|---|---|---|---|---|
| architect | `triangular_ruler` | `#tech-desk` | `architect-slack-channel` | `architect` |
| 비서 (compass) | `inbox_tray` | `#investment-desk` | `compass-secretary-slack` | `compass-secretary` |
| 새벽 | `cherry_blossom` | `#일상` | `saebyeok-slack-channel` | `saebyeok` |
| 노을 | `fallen_leaf` | `#작업실` | `neul-slack-channel` | `neul` |

(현재 inbox/eyes 이중 시스템이나 trigger 코얼레싱 같은 *고급 분기* 는 본 패키지에 미포함 — 단일 리액션 + 단순 디바운스. 필요한 페르소나는 자기 인스턴스를 그대로 두거나 별 라운드에서 옵션 키 추가.)

## 관련

- 큐 영속화 (`processedTs`), 15분 룩백, 단일 인스턴스 락 (`server.lock`) 그대로.
- `node_modules/`, `server.lock`, `server.log`, `.state/`, `.cache/` 모두 git 추적 X.
- 시크릿 (`SLACK_BOT_TOKEN`) 코드·로그·README·commit 어디에도 평문 등장 0.

## 라이선스

`agent-toolkit-shared` 루트와 동일.
