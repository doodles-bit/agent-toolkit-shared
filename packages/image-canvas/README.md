# image-canvas

OpenAI `gpt-image-2` 기반 이미지 생성을 stdio MCP 서버로 노출하는 plain 패키지.

페르소나·도메인에 비종속이라 누구나 같은 도구를 쓰고, 그림의 색깔은 호출 측 CLAUDE.md
프롬프트 레이어가 결정한다. 새벽·노을 자매 페르소나가 첫 사용처지만, 이후 다른 팀·다른
페르소나도 그대로 재사용할 수 있게 만들었다.

## 도구

### `generate_image(prompt, size?, n?)`

| 파라미터 | 타입 | 기본 | 설명 |
| --- | --- | --- | --- |
| `prompt` | string | (필수) | 그릴 이미지에 대한 자연어 설명. 호출 측이 자유롭게 작성. |
| `size`   | string | `1024x1024` | `1024x1024` / `1024x1536` / `1536x1024` / `auto` 중 하나. |
| `n`      | number | `1` | 생성 매수, 1~10. |

반환: 저장된 PNG 의 절대 경로(들)를 줄단위 문자열로 묶어 반환.

파일명 규칙: `<YYYYMMDD-HHMMSS>_<6char-hash>.png` (`n>1` 일 때 뒤에 `_2`, `_3` … 인덱스).

## 환경변수

| 키 | 필수 | 설명 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 필수 | OpenAI 계정 API 키. **`.mcp.json` 등에 하드코딩하지 말고 부모 프로세스 (Windows User scope `setx`, `export` 등) 로 상속할 것.** |
| `IMAGE_CANVAS_OUTPUT_DIR` | 필수 | 생성된 PNG 가 저장될 절대경로. 디렉토리가 없으면 자동 생성. |

## 설치

루트에서:

```bash
cd packages/image-canvas
npm install
```

## 호출 측 등록 예 (Claude Code `.mcp.json`)

```jsonc
{
  "mcpServers": {
    "image-canvas": {
      "command": "npx",
      "args": [
        "tsx",
        "C:/Users/pyeon/project_repo/agent-toolkit-shared/packages/image-canvas/server.ts"
      ],
      "env": {
        "IMAGE_CANVAS_OUTPUT_DIR": "C:/Users/pyeon/project_repo/dawn-dusk/canvas"
      }
    }
  }
}
```

`OPENAI_API_KEY` 는 위 `env` 에 절대 적지 않는다. User scope 환경변수로만 흐르게 한다.

## 동작 검증

```powershell
$env:IMAGE_CANVAS_OUTPUT_DIR = "C:/tmp/image-canvas-test"
npx tsx server.ts
# 다른 창에서 MCP inspector 등으로 generate_image 호출
```

또는 호출 측 Claude Code 세션에서 `/mcp` 재연결 후 도구 호출.

## 라이선스

`agent-toolkit-shared` 루트와 동일.
