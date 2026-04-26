# 설치 절차 (최초 1회)

와이프 시점. macOS 기준. 5~10분 소요.

## 1) Python 의존성 설치

터미널 (Spotlight 에서 "Terminal" 검색) 에서:

```bash
cd /path/to/agent-toolkit-shared/packages/photo-pipeline-raw-pair-cleanup
pip3 install -r requirements.txt
```

`pip3` 가 없다고 하면 `python3 -m pip install -r requirements.txt`.

## 2) 스크립트 경로 확인

터미널에서:

```bash
realpath raw_pair_cleanup.py
```

출력된 절대경로를 메모해 둔다. 예: `/Users/wife/work/agent-toolkit-shared/packages/photo-pipeline-raw-pair-cleanup/raw_pair_cleanup.py`. 이 경로가 다음 단계에서 필요.

## 3) Automator Quick Action 등록 — 두 갈래 중 택일

### A. 동봉된 워크플로우 사용 (권장)

`automator/RAW Pair Cleanup.workflow` 디렉토리를 통째로 `~/Library/Services/` 로 복사:

```bash
mkdir -p ~/Library/Services
cp -R "automator/RAW Pair Cleanup.workflow" ~/Library/Services/
```

그리고 `~/Library/Services/RAW Pair Cleanup.workflow/Contents/document.wflow` 를 텍스트 에디터로 열어 `__SCRIPT_PATH_PLACEHOLDER__` 부분을 2단계에서 메모한 절대경로로 교체:

```bash
WF=~/Library/Services/"RAW Pair Cleanup.workflow"/Contents/document.wflow
SCRIPT_ABS="$(cd /path/to/agent-toolkit-shared/packages/photo-pipeline-raw-pair-cleanup && pwd)/raw_pair_cleanup.py"
sed -i '' "s|__SCRIPT_PATH_PLACEHOLDER__|$SCRIPT_ABS|" "$WF"
```

Finder 다시 띄우면 폴더 우클릭 → 빠른 동작 → "RAW Pair Cleanup" 메뉴 확인.

### B. 동봉 워크플로우가 안 먹으면 (Automator.app 으로 직접)

1. **Automator.app 열기** — Spotlight 에서 "Automator"
2. **새 문서 → 빠른 동작(Quick Action)** 선택
3. 상단 영역:
   - "워크플로우가 다음 항목을 받음" 을 **`folders`(폴더)** 로
   - "위치" 는 **Finder.app**
4. 좌측 라이브러리에서 **셸 스크립트 실행(Run Shell Script)** 액션을 우측 영역으로 드래그
5. 액션 박스의 **"입력 전달 방식"** 을 **`인자로(as arguments)`** 로 변경
6. 셸 스크립트 박스에 입력 (2단계에서 메모한 경로로 교체):

   ```bash
   /usr/bin/env python3 "/Users/wife/.../raw_pair_cleanup.py" "$1"
   ```

7. **⌘S** 로 저장. 이름 입력란에 **`RAW Pair Cleanup`** (또는 와이프 마음대로) 입력
8. Finder 에서 폴더 우클릭 → 빠른 동작 → 방금 저장한 메뉴 확인

## 4) 첫 사용 검증

검수 거의 안 끝난 더미 폴더 (JPG·ARW 페어 몇 장) 만들어 우클릭 한 번:

- 정상 동작 → notification "완료 — N 장 휴지통, M 장 보존"
- 알림 안 뜸 → "시스템 환경설정 → 알림" 에서 "Script Editor" 또는 "AppleScript" 알림 권한 허용

## 트러블슈팅

**`send2trash 모듈 없음` 알림** → 1단계의 `pip3 install` 다시. 시스템 Python 과 Automator 가 쓰는 Python 이 다를 수 있어 `/usr/bin/python3 -m pip install send2trash` 또는 Automator 셸 스크립트의 `/usr/bin/env python3` 를 정확한 Python 절대경로로 변경.

**우클릭 메뉴에 안 보임** → "시스템 환경설정 → 키보드 → 단축키 → 서비스" 에서 "RAW Pair Cleanup" 체크. Finder 재시작 (`killall Finder`).

**파일 이동은 됐는데 알림이 안 뜸** → 권한 문제. 첫 실행 시 macOS 가 권한 묻는 다이얼로그 띄우니 허용. 이미 거부했다면 "시스템 환경설정 → 보안 및 개인정보 보호 → 자동화" 에서 Finder/Automator 가 Script Editor 제어할 수 있도록 다시 허용.

## 제거

```bash
rm -rf ~/Library/Services/"RAW Pair Cleanup.workflow"
```

또는 Automator.app 에서 빠른 동작 라이브러리 열어 삭제.
