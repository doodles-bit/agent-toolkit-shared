# Windows 회사 PC Ollama + Gemma 4 설치/검증 매뉴얼

작성일: 2026-05-14
대상: Windows 회사 PC에서 커뮤니티 댓글/자막 materials 추출용 Gemma 4 smoke test를 준비하는 분석 에이전트

## 목적

이 문서는 "Gemma 설치법"이 아니라 다음 순서의 현장 복구 매뉴얼이다.

```text
Windows 회사 PC에서 Ollama 설치/검증
-> Gemma 4 모델 설치
-> GPU/오프로딩 확인
-> materials 추출 옵션 적용
-> 댓글 1개, 10개, 50개 순서로 smoke test
```

Gemma 4는 최종 리포트 작성자가 아니라 `translation_ko`, `sentiment`, `targets`,
`key_points`, `evidence`, `uncertainty` 같은 materials를 뽑는 로컬 전처리기로 쓴다.
최종 요약, 번역 보정, 센티멘트 해석, 리포트 작성은 validator warning을 함께 받은 강한
모델이 담당한다.

## 빠른 의사결정표

| 막힌 지점 | 확인 명령 | 가능 원인 | 다음 조치 |
|---|---|---|---|
| PowerShell 한 줄 설치 실패 | `irm https://ollama.com/install.ps1 \| iex` 실행 오류 원문 확인 | 회사 보안 정책이 원격 스크립트 실행 또는 `irm` 다운로드를 차단 | PowerShell 우회 시도보다 공식 Windows 설치 파일을 사용한다. 계속 막히면 오류 원문과 차단 URL을 IT에 전달한다. |
| 설치 파일 다운로드 실패 | 브라우저에서 `https://ollama.com/download/windows` 접속 | 회사망/프록시/보안 제품이 다운로드 도메인 또는 실행 파일을 차단 | IT에 Ollama 다운로드 도메인 허용을 요청한다. 임의 미러나 비공식 파일은 쓰지 않는다. |
| 설치 후 `ollama` 명령어를 못 찾음 | `ollama --version`, `where.exe ollama`, `$env:Path -split ';' \| Select-String Ollama` | 설치 직후 기존 터미널 PATH 미갱신, 사용자 PATH 반영 지연, 설치 경로 변경 | 새 PowerShell을 열고 재시도한다. 필요하면 재로그인 후 `%LOCALAPPDATA%\Programs\Ollama`가 사용자 PATH에 있는지 확인한다. |
| Ollama 서버/API가 응답 안 함 | `Invoke-RestMethod http://localhost:11434/api/version` | Ollama tray app 미실행, 서버 초기화 실패, 회사 보안 제품의 localhost 차단, 포트 충돌 | Start menu에서 Ollama를 실행한다. `%LOCALAPPDATA%\Ollama\server.log`와 `app.log`를 확인한다. |
| `gemma4:e2b` 다운로드 실패 | `ollama pull gemma4:e2b` | 모델 저장 공간 부족, 회사망이 모델 registry 다운로드 차단, 프록시/SSL 검사 문제 | `OLLAMA_MODELS`를 큰 디스크로 옮기고 새 터미널/앱 재시작. 네트워크 차단이면 오류 원문을 IT에 전달한다. |
| 실행은 되지만 너무 느림 | `ollama ps`, 작업 관리자 CPU/GPU/메모리 확인 | CPU fallback, VRAM 부족, context가 너무 큼, 너무 큰 모델 사용 | `gemma4:e2b`, `num_ctx 4096`, `thinking off`로 낮춘다. 4k -> 8k -> 16k 순서로만 올린다. |
| GPU를 안 쓰고 CPU만 씀 | `ollama ps`의 `PROCESSOR` 컬럼 확인 | GPU/드라이버 미지원, VRAM 부족, Windows 지원 카드 범위 밖, Vulkan 실험 경로 미사용 | 최신 GPU 드라이버와 공식 지원 목록을 확인한다. `PROCESSOR`가 CPU/GPU 혼합이면 모델/ctx를 낮춘다. Vulkan은 기본 운영 경로로 쓰지 않는다. |

## 1. Windows Ollama 설치

### 1.1 요구사항 확인

공식 Windows 문서 기준:

- Windows 10 22H2 이상, Home 또는 Pro.
- NVIDIA GPU는 Windows 문서상 452.39 이상 드라이버가 언급되지만, GPU 지원 문서에서는
  compute capability 5.0+ 및 531 이상 드라이버를 기준으로 한다. 실무에서는 최신 안정
  드라이버를 권장한다.
- AMD Radeon은 AMD Radeon Driver가 필요하다.
- Ollama Windows는 기본적으로 관리자 권한 없이 사용자 홈 디렉터리에 설치된다.
- 바이너리 설치에 최소 4GB가 필요하고, 모델은 수십 GB 이상까지 커질 수 있다.

### 1.2 PowerShell 한 줄 설치

공식 다운로드 페이지의 PowerShell 설치 명령:

```powershell
irm https://ollama.com/install.ps1 | iex
```

회사 PC에서 이 명령이 막히면 보안 정책상 정상적인 차단일 수 있다. 이때는 execution policy를
무리하게 우회하지 말고 설치 파일 방식으로 넘어간다.

### 1.3 설치 파일 방식

브라우저에서 공식 Windows 다운로드 페이지를 연다.

```text
https://ollama.com/download/windows
```

다운로드한 `OllamaSetup.exe`를 실행한다. 기본 설치는 사용자 홈 아래에 들어가며 관리자 권한이
필요하지 않다.

설치 위치를 바꿔야 하면 설치 파일을 다음처럼 실행한다.

```powershell
.\OllamaSetup.exe /DIR="d:\some\location"
```

### 1.4 설치 후 확인

설치가 끝난 뒤 기존 터미널이 아니라 새 PowerShell을 연다.

```powershell
ollama --version
Invoke-RestMethod http://localhost:11434/api/version
```

`ollama --version`이 실패하면 먼저 새 터미널/재로그인을 확인한다. 그래도 실패하면 설치
경로가 PATH에 들어갔는지 확인한다.

```powershell
where.exe ollama
$env:Path -split ';' | Select-String -SimpleMatch 'Ollama'
```

### 1.5 설치/로그 위치

Windows Ollama 공식 문서 기준 주요 위치:

```text
%LOCALAPPDATA%\Ollama
%LOCALAPPDATA%\Programs\Ollama
%HOMEPATH%\.ollama
%TEMP%\ollama*
```

로그 확인:

```powershell
explorer $env:LOCALAPPDATA\Ollama
Get-Content "$env:LOCALAPPDATA\Ollama\server.log" -Tail 80
Get-Content "$env:LOCALAPPDATA\Ollama\app.log" -Tail 80
```

### 1.6 모델 저장 위치 변경

홈 디렉터리 용량이 부족하면 사용자 환경변수 `OLLAMA_MODELS`를 큰 디스크로 지정한다.

PowerShell에서 현재 값 확인:

```powershell
[Environment]::GetEnvironmentVariable('OLLAMA_MODELS', 'User')
```

GUI 방식:

1. Windows Settings 또는 Control Panel에서 `environment variables`를 검색한다.
2. 사용자 계정의 환경변수 편집으로 들어간다.
3. `OLLAMA_MODELS`를 만들거나 수정해 큰 디스크 경로를 지정한다.
4. Ollama tray app을 종료 후 Start menu에서 다시 실행하고, 새 터미널을 연다.

예:

```text
D:\ollama-models
```

## 2. 회사 PC에서 자주 막히는 지점

### PowerShell 원격 스크립트 차단

`irm https://ollama.com/install.ps1 | iex`가 실패하면 공식 다운로드 설치 파일을 쓴다. 회사
환경에서는 원격 스크립트 실행 차단이 보안 정책상 맞을 수 있다.

### 다운로드/모델 pull 차단

설치 파일 다운로드나 `ollama pull gemma4:e2b`가 실패하면 회사망/프록시/SSL 검사 정책을 먼저
의심한다. 이 경우 필요한 정보는 다음 세 가지다.

- 실행한 명령
- 원문 오류 메시지
- 실패한 URL 또는 도메인

비공식 mirror를 쓰기보다 IT에 공식 도메인 허용 또는 수동 다운로드 정책을 확인한다.

### 홈 디렉터리 용량 부족

Gemma 4 모델은 작은 태그도 GB 단위다. 홈 디렉터리 quota가 작으면 `OLLAMA_MODELS`를 큰
디스크로 지정한 뒤 Ollama를 재시작한다.

### PATH 미반영

설치 직후 기존 PowerShell에서는 `ollama`가 안 잡힐 수 있다. 새 PowerShell, 재로그인,
`%LOCALAPPDATA%\Programs\Ollama` PATH 반영 순서로 확인한다.

## 3. Gemma 4 모델 선택과 설치

### 공식 Ollama library 기준 모델

| 용도 | 태그 | 공식 library 기준 크기/컨텍스트 | 판단 |
|---|---|---|---|
| 기본 smoke | `gemma4:e2b` | 약 7.2GB, 128K context | 댓글/자막 materials 추출 첫 후보 |
| 조금 더 강한 edge 후보 | `gemma4:e4b` | 약 9.6GB, 128K context | e2b 품질이 부족하고 PC 여유가 있을 때 |
| 워크스테이션 후보 | `gemma4:26b` | 약 18GB, 256K context | 로컬 고성능 PC에서만 후보 |
| 워크스테이션 후보 | `gemma4:31b` | 약 20GB, 256K context | VRAM/메모리 여유가 큰 PC에서만 후보 |
| 제외 | `gemma4:31b-cloud` | Ollama cloud tag | 로컬 설치/검증 기준에서는 제외 |

우리 기준 추천:

```powershell
ollama pull gemma4:e2b
ollama run gemma4:e2b "한 문장으로 답해"
```

`pull` 없이 `run`을 먼저 실행해도 모델이 없으면 다운로드를 시작한다.

architect 로컬 검증값:

- 집 PC에서 `gemma4:e2b`는 Ollama `0.23.2` 기준 약 7.2GB로 설치 확인.
- 이 값은 참고값이다. 정확한 크기와 동작은 Ollama library tag, quantization, 설치 시점에 따라
  달라질 수 있다.

## 4. GPU 확인과 오프로딩

### 지원 범위

공식 문서 기준:

- Windows Ollama는 NVIDIA와 AMD Radeon GPU를 지원한다.
- NVIDIA는 GPU 지원 문서 기준 compute capability 5.0+ 및 531 이상 드라이버가 기준이다.
  Windows 문서의 최소 드라이버 문구와 다를 수 있으므로 실무에서는 최신 안정 드라이버를 쓴다.
- AMD Windows 지원은 ROCm v6.1 기준 Radeon RX 7900/7800/7700/7600/6900/6800 계열과
  Radeon PRO W7900/W7800/W7700/W7600/W7500/W6900X/W6800 계열 및 V620 범위로 제한된다.
- Vulkan GPU 지원은 실험 기능이다. 회사 운영 기본 경로로 권하지 않는다.

### 실제 GPU 사용 확인

모델을 한 번 실행한 뒤 확인한다.

```powershell
ollama ps
```

`PROCESSOR` 컬럼을 본다.

```text
NAME            SIZE     PROCESSOR       CONTEXT
gemma4:e2b      7.2 GB   100% GPU        4096
gemma4:e2b      7.2 GB   CPU/GPU         4096
gemma4:e2b      7.2 GB   CPU             4096
```

판단:

- `100% GPU`: 가장 좋은 상태.
- `CPU/GPU`: VRAM이 부족해 일부가 CPU로 내려갔을 수 있다. 속도 저하 가능.
- `CPU`: GPU 미지원, 드라이버 문제, VRAM 부족, 또는 fallback 가능성.

속도가 너무 느리면 모델 크기와 context를 먼저 낮춘다. GPU 설정을 억지로 만지기보다
`gemma4:e2b`, `num_ctx 4096`, `thinking off`로 smoke를 통과시키는 것이 우선이다.

## 5. 실행 옵션 매뉴얼

### 우리 materials 추출 기본값

댓글/자막 materials 추출 smoke의 시작값:

```text
model: gemma4:e2b
runtime: Ollama native API
thinking: off
temperature: 0.2
top_p: 0.95
top_k: 64
num_ctx: 4096
num_predict: 800~2000
output: compact JSON
```

Ollama `/api/chat`에서는 top-level `think: false`를 명시한다. `think`는 `options` 안이 아니라
요청 body의 top-level 필드다.

### 일반 Gemma 권장값과 다른 이유

Ollama Gemma 4 library의 best practice는 일반 대화/추론 성능 기준으로 `temperature=1.0`,
`top_p=0.95`, `top_k=64` 계열을 제시한다. 하지만 materials 추출은 창의성보다 재현성,
JSON 안정성, quote 보존이 중요하다.

따라서 우리 기본값은 다음처럼 낮춘다.

```text
temperature: 1.0 -> 0.2
top_p: 0.95 유지
top_k: 64 유지
```

### context length 올리는 순서

Ollama 공식 문서는 context length가 커질수록 더 많은 메모리/VRAM이 필요하다고 설명한다.
회사 PC에서는 한 번에 128K를 쓰지 말고 다음 순서로 올린다.

```text
4096 -> 8192 -> 16384
```

각 단계마다 확인:

```powershell
ollama ps
```

`PROCESSOR`가 `100% GPU`에서 `CPU/GPU` 또는 `CPU`로 바뀌면 context가 너무 크거나 VRAM이
부족할 수 있다.

## 6. PowerShell API smoke test

아래 예제는 Windows PowerShell에서 그대로 붙여 넣을 수 있게 작성했다. 실패하면 오류 원문을
저장해서 보고한다.

### 6.1 API version 확인

```powershell
$ErrorActionPreference = "Stop"

try {
  Invoke-RestMethod -Uri "http://localhost:11434/api/version"
} catch {
  $_ | Out-String | Set-Content -Encoding UTF8 ".\ollama-version-error.txt"
  throw
}
```

### 6.2 댓글 1개 JSON materials 추출

```powershell
$ErrorActionPreference = "Stop"

$comment = @"
comment_id: c_001
author: user123
language_hint: en
text: The product is much faster now, but the pricing is confusing.
"@

$system = @"
You are a compact JSON materials extractor for comment and transcript analysis.
Return only valid JSON.
Extract:
- comment_id
- language
- translation_ko
- sentiment: positive, neutral, negative, mixed, or unclear
- sentiment_score: number from -1.0 to 1.0
- targets
- key_points
- evidence with exact source quotes
- uncertainty
Do not write the final report.
"@

$body = @{
  model = "gemma4:e2b"
  stream = $false
  think = $false
  format = "json"
  messages = @(
    @{ role = "system"; content = $system },
    @{ role = "user"; content = $comment }
  )
  options = @{
    temperature = 0.2
    top_p = 0.95
    top_k = 64
    num_ctx = 4096
    num_predict = 1000
  }
} | ConvertTo-Json -Depth 10

try {
  $response = Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:11434/api/chat" `
    -ContentType "application/json" `
    -Body $body

  $response.message.content
  $response.message.content | ConvertFrom-Json
} catch {
  $_ | Out-String | Set-Content -Encoding UTF8 ".\ollama-chat-error.txt"
  throw
}
```

성공 후 확인:

```powershell
ollama ps
```

보고할 것:

- `ollama --version` 결과
- `/api/version` 결과
- `/api/chat` 실행 시간 체감
- `ollama ps`의 `PROCESSOR`와 `CONTEXT`
- JSON parse 성공 여부
- quote가 원문에 실제로 있는지

## 7. Modelfile wrapper 예시

wrapper는 품질 향상 카드가 아니라 system prompt와 options를 고정하는 운영 정리용이다.
architect 집 PC 실험에서는 wrapper로 옮겨도 `prompt_eval_count`가 사라지지는 않았다.

`Modelfile` 예:

```text
FROM gemma4:e2b

PARAMETER temperature 0.2
PARAMETER top_p 0.95
PARAMETER top_k 64
PARAMETER num_ctx 4096

SYSTEM """
You are a compact JSON materials extractor for Korean/English comment and transcript analysis.
Return only valid JSON.

Extract:
- translation_ko
- sentiment
- sentiment_score
- targets
- key_points
- evidence with exact source quotes
- uncertainty

Do not write the final report.
If the source text and metadata conflict, preserve the source text and leave uncertainty.
"""
```

생성:

```powershell
ollama create ai-briefing-materials-gemma4:thinkoff -f Modelfile
ollama run ai-briefing-materials-gemma4:thinkoff "한 문장으로 답해"
```

API 호출 시 모델 이름만 바꾼다.

```powershell
model = "ai-briefing-materials-gemma4:thinkoff"
```

주의:

- wrapper는 호출 코드의 system/options 중복을 줄인다.
- wrapper가 JSON 안정성이나 품질을 자동으로 올린다고 보지 않는다.
- source conflict는 wrapper가 아니라 validator warning과 후속 강한 모델에서 해결한다.

## 8. 최종 smoke 성공 기준

회사 PC에서 성공으로 볼 최소 기준:

1. `ollama --version` 통과.
2. `Invoke-RestMethod http://localhost:11434/api/version` 통과.
3. `ollama run gemma4:e2b "한 문장으로 답해"` 통과.
4. PowerShell `/api/chat` JSON 예제 통과.
5. `ollama ps`에서 모델 로드 상태와 `PROCESSOR` 확인.
6. 댓글 10개 materials 추출 통과.
7. 댓글 50개 materials 추출 통과.
8. 결과에서 evidence quote가 원문에 실제로 있는지 확인.
9. 고유명사/숫자/source conflict warning이 얼마나 나는지 기록.

성공 판단은 "모델이 답했다"가 아니라 다음 세 가지다.

- JSON이 parse된다.
- quote가 원문에 있다.
- 후속 강한 모델이 사용할 수 있는 materials가 보존된다.

## 9. 실패 보고 템플릿

실패하면 아래 형식으로 보고한다.

```text
OS:
GPU:
ollama --version:
설치 방식: PowerShell / 설치 파일
실패 단계:
실행 명령:
원문 오류:
ollama ps:
로그 위치:
  %LOCALAPPDATA%\Ollama\server.log
  %LOCALAPPDATA%\Ollama\app.log
추가 메모:
```

토큰, 개인 계정, 회사 내부 URL, 민감 파일 경로는 보고에 포함하지 않는다.

## 참고 링크

공식 문서:

- Ollama Windows: https://docs.ollama.com/windows
- Ollama Download Windows: https://ollama.com/download/windows
- Ollama Hardware support: https://docs.ollama.com/gpu
- Ollama Context length: https://docs.ollama.com/context-length
- Ollama API Chat: https://docs.ollama.com/api/chat
- Ollama API Generate: https://docs.ollama.com/api/generate
- Ollama Modelfile: https://docs.ollama.com/modelfile
- Ollama Gemma4 library: https://ollama.com/library/gemma4
- Google DeepMind Gemma 4: https://deepmind.google/models/gemma/gemma-4/

로컬 검증값:

- architect 집 PC: Ollama `0.23.2`, `gemma4:e2b` 약 7.2GB 설치 확인.
- 이 값은 공식 스펙이 아니라 2026-05-13 로컬 실험 참고값이다.
