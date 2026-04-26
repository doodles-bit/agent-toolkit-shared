# photo-pipeline-raw-pair-cleanup

JPG 검수가 끝난 폴더의 *살아남은 stem* 기준으로 짝 없는 .ARW(Sony RAW) 를 macOS 휴지통으로 이동하는 batch 스크립트. Finder 우클릭 → "RAW 정리" 한 번이면 끝.

본 패키지는 본식 사진 워크플로우의 *첫 라운드* 페인포인트만 제거한다. USB 자동 인식·자동 복사·AI 검수·FTP 업로드·Slack 알림 통합 같은 후속 토픽은 *별 라운드* 로 분리.

## 핵심 정책

- **완전 삭제 X — 휴지통 이동**. 와이프 손에서 복구 가능. macOS Finder 의 휴지통 비우기 시점이 진짜 삭제.
- **첫 라운드는 .ARW 만**. Canon `.cr2`/`.cr3`, Nikon `.nef` 등은 화이트리스트 항목으로 추후 확장.
- **JPG 0장 안전 가드**. 검수 안 한 폴더(JPG 미생성)에서 우클릭한 케이스에 ARW 가 모두 휴지통 행이 되는 사고를 차단. JPG 0장이면 처리 중단 + "검수 안 한 폴더로 보임" 알림.
- **macOS 만 대상**. Windows 호환 X (osascript / `~/Library/Services` 의존).
- **plain·페르소나 비종속**. 와이프·노을 prompt·동작 무수정.

## 동작

1. 와이프가 macOS 사진 뷰어에서 JPG 검수 → 마음에 안 드는 JPG 휴지통 이동 (현재 흐름 그대로).
2. Finder 폴더 우클릭 → "RAW 정리" Quick Action 클릭.
3. 스크립트가 폴더 안 *JPG stem set* 과 *ARW 리스트* 비교. JPG stem 에 짝이 없는 ARW 만 macOS 휴지통으로 이동.
4. macOS native notification: `RAW 정리 완료 — N 장 휴지통, M 장 보존`.

엣지 케이스 처리:

| 폴더 상태 | 결과 |
|---|---|
| 비어있음 | "정리할 파일 없음" |
| JPG 만 (ARW 없음) | "RAW 파일 없음 (JPG only, X 장)" |
| ARW 만 (JPG 0장) | **안전 가드** — "JPG 0장. ARW X 장 그대로 보존 (검수 안 한 폴더로 보임)" |
| stat / 휴지통 이동 일부 실패 | "부분 완료 — N 장 휴지통, M 장 보존, X 장 실패 (예: ...)" |

## 파일

- `raw_pair_cleanup.py` — 본체 스크립트 (CLI: 폴더 절대경로 인자)
- `requirements.txt` — `send2trash`
- `automator/RAW Pair Cleanup.workflow/` — Quick Action 등록용 macOS Automator workflow
- `INSTALL.md` — 와이프 시점 *최초 1회 설치* 절차

## 미래 확장 (별 라운드)

- 다른 brand RAW 확장자 (`.cr2`/`.cr3`/`.nef`/`.dng` 등) 화이트리스트 추가
- Sidecar 파일 (`.xmp`/`.jpg.xmp`) 동시 정리
- 휴지통 이동 전 *덜 위험한* 격리 폴더 (예: `_review_trash/`) 옵션
- 폴더 *재귀* 순회 옵션
- Slack 통합 (작업 진행 상황 채널 푸시)

## 라이선스

`agent-toolkit-shared` 루트와 동일.
