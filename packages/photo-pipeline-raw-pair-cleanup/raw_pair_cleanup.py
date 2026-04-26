#!/usr/bin/env python3
"""
RAW 페어 매칭 정리 — JPG 검수가 끝난 폴더의 살아남은 stem 기준으로
JPG stem 에 짝이 없는 .ARW 를 macOS 휴지통으로 이동한다.

사용
    python3 raw_pair_cleanup.py /path/to/folder

자동화: macOS Automator > Quick Action > "Folders" 에 Run Shell Script:
    /usr/bin/env python3 /path/to/raw_pair_cleanup.py "$1"

설계
- 완전 삭제 X. macOS 휴지통 이동만 (실수 안전망 — 와이프 손에서 복구 가능).
- 첫 라운드는 .ARW 만. 다른 brand 확장자 (.cr2/.cr3/.nef 등) 는 화이트리스트로 추후 확장.
- JPG 0장 안전 가드: ARW 만 있는 폴더에서 모두 휴지통 행이 되는 사고 방지.
- macOS native notification (osascript) 으로 결과 표시. Automator 우클릭에서 자연스러운 UI.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

# 첫 라운드 화이트리스트 — ARW 만. 추후 확장 시 이 set 에 추가.
RAW_EXTENSIONS = {".arw"}
JPG_EXTENSIONS = {".jpg", ".jpeg"}

NOTIFY_TITLE = "RAW 정리"


def notify(message: str) -> None:
    """macOS 기본 notification. osascript 가 없으면 stderr 로 fallback."""
    safe_message = message.replace('"', '\\"')
    safe_title = NOTIFY_TITLE.replace('"', '\\"')
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # macOS 가 아닌 환경 (개발·검증) 에선 stderr 로만 출력하고 계속 진행.
        print(f"[{NOTIFY_TITLE}] {message}", file=sys.stderr)


def collect_files(folder: Path) -> tuple[set[str], list[Path]]:
    """폴더 안 JPG stem set + ARW 파일 리스트를 추출. 하위 폴더는 보지 않음."""
    jpg_stems: set[str] = set()
    arw_files: list[Path] = []
    for entry in folder.iterdir():
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if ext in JPG_EXTENSIONS:
            jpg_stems.add(entry.stem)
        elif ext in RAW_EXTENSIONS:
            arw_files.append(entry)
    return jpg_stems, arw_files


def trash(path: Path) -> str | None:
    """send2trash 로 macOS 휴지통 이동. 실패 시 사유 문자열 반환."""
    try:
        from send2trash import send2trash
    except ImportError:
        return "send2trash 모듈 없음 — `pip3 install send2trash` 후 재시도"
    try:
        send2trash(str(path))
        return None
    except OSError as exc:
        return str(exc)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        notify("오류: 폴더 인자 누락 (사용: raw_pair_cleanup.py /폴더)")
        return 1

    folder = Path(argv[1]).expanduser().resolve()
    if not folder.exists():
        notify(f"오류: 폴더 없음 — {folder}")
        return 1
    if not folder.is_dir():
        notify(f"오류: 디렉토리 아님 — {folder}")
        return 1

    jpg_stems, arw_files = collect_files(folder)

    # 빈 폴더 / JPG 만 / ARW 만 분기
    if not jpg_stems and not arw_files:
        notify("정리할 파일 없음")
        return 0
    if not arw_files:
        notify(f"RAW 파일 없음 (JPG only, {len(jpg_stems)} 장)")
        return 0
    if not jpg_stems:
        # 안전 가드: JPG 0장이면 ARW 모두 살아남음. 와이프 실수 (검수 안 한 폴더 우클릭) 방지.
        notify(
            f"안전 가드 — JPG 0장. ARW {len(arw_files)} 장 그대로 보존 "
            f"(검수 안 한 폴더로 보임)"
        )
        return 0

    trashed = 0
    kept = 0
    failed: list[tuple[str, str]] = []
    for arw in arw_files:
        if arw.stem in jpg_stems:
            kept += 1
            continue
        reason = trash(arw)
        if reason is None:
            trashed += 1
        else:
            failed.append((arw.name, reason))

    if failed:
        sample = failed[0]
        notify(
            f"부분 완료 — {trashed} 장 휴지통, {kept} 장 보존, {len(failed)} 장 실패 "
            f"(예: {sample[0]} — {sample[1]})"
        )
        return 1

    notify(f"완료 — {trashed} 장 휴지통, {kept} 장 보존")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
