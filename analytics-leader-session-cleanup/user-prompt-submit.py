"""
UserPromptSubmit 훅 (Claude Code용) — analytics-leader 전용.

statusline.py 가 ctx 40% 상향 돌파 시 만든 `cleanup-flag` / `manual-mode` 파일을 읽어서
정리 사이클 지시를 `additionalContext` 로 세션에 주입한다.

Compass 팀원 버전과의 차이:
- 분석팀장(analytics-leader) 은 **Slack 을 쓰지 않는다**: Slack 호출 코드 없음.
- 분석팀장은 compass 비서 같은 상위 관리 에이전트가 없다: **task-broker 보고도 없음**.
- 모든 상태 알림은 (a) additionalContext 로 세션 터미널에 한국어 메시지로 주입,
  (b) 로컬 로그 파일 `~/.claude/state/analytics-leader/cleanup-history.log` 에 JSONL 누적.

상태 파일:
  ~/.claude/state/analytics-leader/cleanup-flag         — statusline 이 생성, 본 훅이 삭제
  ~/.claude/state/analytics-leader/manual-mode          — 쿨다운 내 재트리거 감지 시 생성
  ~/.claude/state/analytics-leader/last-checkpoint.txt  — 직전 정리 완료 Unix timestamp
  ~/.claude/state/analytics-leader/cleanup-history.log  — JSONL 이벤트 로그 (본 훅이 append)
"""

import json
import os
import sys
import time

STATE_DIR = os.path.expanduser("~/.claude/state")

# 회사 PC 분석팀 환경 전용 — trigger.ps1 은 task-broker 루트에 있음.
TRIGGER_SCRIPT = "C:/Users/doodles/project_repo/ai_agent_team/task-broker/trigger.ps1"

PROJECT_CONFIG = {
    # analytics-leader 는 새로운 agent_type="terminal-only" 카테고리.
    # Compass 의 "secretary"(Slack 직접 응답) / "teammate"(task-broker 비서 보고) 어느 쪽도
    # 아니라서 정리 사이클을 단순화했다: 로컬 메모리·체크포인트·export·compact 만 수행.
    "analytics-leader": {
        "agent_type": "terminal-only",
        "cwd_suffix": "/project_repo/ai_agent_team",
        "terminal": "analytics-leader",
        "project_root": "C:/Users/doodles/project_repo/ai_agent_team",
        "memory_archive_hint": (
            "`.claude/memory/team-lead.md` 가 10KB 초과면 완료된 작업·검증 결과·피드백을 "
            "`.claude/memory/team-lead-archive.md` 로 이동 (아카이브 인덱스도 갱신). "
            "할루시네이션 대응 3층 체계·자율 판단 우선 원칙 같은 원칙 섹션은 남긴다. "
            "15KB 초과면 강제 분리 필수 — CLAUDE.md '아카이브 규칙' 참조."
        ),
    },
}


def _history_log_path(project_key):
    return os.path.join(STATE_DIR, project_key, "cleanup-history.log")


def _append_history(project_key, event, extra=None):
    """정리 사이클 이벤트 로그에 한 줄 JSON 추가.

    스키마: {"ts": iso8601, "event": str, "project": str, **extra}
    event 종류: "cleanup-start" | "cleanup-done-pending" | "cleanup-fail" | "manual-mode"
    """
    try:
        path = _history_log_path(project_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z") or str(time.time()),
            "event": event,
            "project": project_key,
        }
        if extra:
            record.update(extra)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def build_cleanup_context(data, project_key, cfg):
    agent_type = cfg.get("agent_type", "terminal-only")
    if agent_type == "terminal-only":
        return _build_cleanup_terminal_only(data, project_key, cfg)
    # 패키지 범위 밖 — 분석팀엔 다른 agent_type 없음. 안전장치로 terminal-only 로 폴백.
    return _build_cleanup_terminal_only(data, project_key, cfg)


def _build_cleanup_terminal_only(data, project_key, cfg):
    """분석팀장용 정리 사이클 — Slack·비서 호출 없이 터미널 + 로컬 로그만 사용.

    분석팀장이 실행해야 할 6단계 사이클을 additionalContext 로 안내한다. Compass 팀원의
    `[cleanup-start] → task-broker 보고` 패턴 대신, 로컬 `cleanup-history.log` 에 이벤트를
    누적하고 필요 시 분석팀장이 직접 열람하는 구조.
    """
    ctx_pct = round(data.get("ctx_pct") or 0)
    _append_history(
        project_key,
        "cleanup-start",
        {"ctx_pct": ctx_pct, "session_id": data.get("session_id")},
    )
    return (
        f"[자동 세션 컨텍스트 정리 트리거 — {project_key} / ctx {ctx_pct}% 도달]\n\n"
        f"프로젝트: {project_key} | 터미널: {cfg['terminal']} | 에이전트 유형: terminal-only "
        f"(Slack 없음, task-broker 비서 보고 없음 — 로컬 완결형).\n\n"
        f"아래 순서로 정리를 수행. `<stem>` 은 `YYYY-MM-DD_HHMM` 형식 (모든 단계에서 동일).\n\n"
        f"1. **시작 기록** — 본 훅이 이미 `cleanup-history.log` 에 `cleanup-start` 이벤트를 "
        f"append 했음. 추가 보고 불필요.\n\n"
        f"2. **로컬 메모리 점검** — {cfg['memory_archive_hint']}\n\n"
        f"3. **체크포인트 요약 저장** — 현재 세션의 주요 위임·검증·판단·미해결 항목을 "
        f"`{cfg['project_root']}/.claude/session-checkpoints/<stem>.md` 에 저장. "
        f"분석 결과 디테일은 팀원 메모리에 있으므로 여기에는 팀장 판단/결정/진행 상태만 3~5줄씩.\n\n"
        f"4. **쿨다운 타임스탬프 기록** (필수 — 재트리거 방지):\n"
        f"   ```\n"
        f"   date +%s > ~/.claude/state/{project_key}/last-checkpoint.txt\n"
        f"   ```\n\n"
        f"5. **완료 로그 append** — `/compact` 직전에 미리 기록.\n"
        f"   ```bash\n"
        f"   python -c \"import json, time, os; "
        f"p=os.path.expanduser('~/.claude/state/{project_key}/cleanup-history.log'); "
        f"open(p,'a',encoding='utf-8').write(json.dumps({{\\\"ts\\\": time.strftime('%Y-%m-%dT%H:%M:%S%z'), "
        f"\\\"event\\\": 'cleanup-done-pending', \\\"project\\\": '{project_key}', "
        f"\\\"stem\\\": '<stem>', \\\"summary\\\": '<한줄요약>'}}, ensure_ascii=False)+chr(10))\"\n"
        f"   ```\n"
        f"   (요약 예: '팀원 메모리 -28% / 체크포인트 2026-04-24_1600.md')\n\n"
        f"6. **`/export` + `/compact` 순차 주입** (마지막 단계, 한 PowerShell 세션·5초 지연):\n"
        f"   ```\n"
        f"   MSYS_NO_PATHCONV=1 powershell.exe -NoProfile -Command \"& '{TRIGGER_SCRIPT}' "
        f"-WindowTitle '{cfg['terminal']}' "
        f"-Key '/export {cfg['project_root']}/.claude/session-checkpoints/<stem>-full.md'; "
        f"Start-Sleep -Seconds 5; "
        f"& '{TRIGGER_SCRIPT}' -WindowTitle '{cfg['terminal']}' -Key '/compact'\"\n"
        f"   ```\n"
        f"   `/export` 가 원본 대화 전체를 `<stem>-full.md` 로 저장 → 5초 후 `/compact` 가 세션 압축.\n\n"
        f"**예외 처리:**\n"
        f"- 어느 단계든 실패하면 수동으로 `cleanup-fail` 이벤트를 로그에 append:\n"
        f"  ```bash\n"
        f"  python -c \"import json, time, os; "
        f"p=os.path.expanduser('~/.claude/state/{project_key}/cleanup-history.log'); "
        f"open(p,'a',encoding='utf-8').write(json.dumps({{\\\"ts\\\": time.strftime('%Y-%m-%dT%H:%M:%S%z'), "
        f"\\\"event\\\": 'cleanup-fail', \\\"project\\\": '{project_key}', "
        f"\\\"step\\\": <번호>, \\\"reason\\\": '<원인>'}}, ensure_ascii=False)+chr(10))\"\n"
        f"  ```\n"
        f"- 사이클 도중 새 위임 요청이 들어와도 정리를 마칠 때까지 미뤄라 "
        f"(팀원이 이미 작업 중이면 `//<팀원> task:<8자리>` 트리거를 나중에 소화).\n"
    )


def build_manual_context(data, project_key, cfg):
    agent_type = cfg.get("agent_type", "terminal-only")
    if agent_type == "terminal-only":
        return _build_manual_terminal_only(data, project_key, cfg)
    return _build_manual_terminal_only(data, project_key, cfg)


def _build_manual_terminal_only(data, project_key, cfg):
    """쿨다운(10분) 내 재트리거 감지 — 자동 정리 중단 안내."""
    ctx_pct = round(data.get("ctx_pct") or 0)
    last_ts = data.get("last_checkpoint_ts") or 0
    elapsed_min = round((time.time() - last_ts) / 60, 1) if last_ts else 0
    _append_history(
        project_key,
        "manual-mode",
        {
            "ctx_pct": ctx_pct,
            "last_checkpoint_ts": last_ts,
            "elapsed_min": elapsed_min,
            "session_id": data.get("session_id"),
        },
    )
    return (
        f"[수동 정리 모드 진입 — {project_key}]\n\n"
        f"직전 정리({elapsed_min}분 전) 로부터 10분 이내 재트리거 발생. 자동 정리가 중단됐다.\n\n"
        f"1. **로그 확인** — 본 훅이 이미 `~/.claude/state/{project_key}/cleanup-history.log` "
        f"에 `manual-mode` 이벤트를 append 했다. 필요 시 `tail -n 5 "
        f"~/.claude/state/{project_key}/cleanup-history.log` 로 최근 흐름 확인.\n\n"
        f"2. **수동 판단** — ctx {ctx_pct}% 상태지만 자동 정리는 비활성. 정말 정리가 필요하면 "
        f"이번 응답 처리 후 직접 2~6단계(로컬 메모리 점검 → 체크포인트 저장 → 쿨다운 타임스탬프 → "
        f"완료 로그 → /export+/compact) 를 수행.\n\n"
        f"3. **자동 모드 복귀** — 수동 모드는 `~/.claude/state/{project_key}/manual-mode` 파일이 "
        f"존재하는 한 유지된다. 다음 정리를 자동으로 돌리고 싶으면:\n"
        f"   ```\n"
        f"   rm ~/.claude/state/{project_key}/manual-mode\n"
        f"   ```\n"
        f"   로 파일을 삭제하면 다음 40% 재돌파부터 자동 트리거 재개.\n"
    )


def detect_project(cwd_norm):
    for key, cfg in PROJECT_CONFIG.items():
        if cwd_norm.endswith(cfg["cwd_suffix"]):
            return key, cfg
    return None, None


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return

    cwd = (d.get("cwd") or "").replace("\\", "/").rstrip("/")
    project_key, cfg = detect_project(cwd)
    if not project_key:
        return

    project_dir = os.path.join(STATE_DIR, project_key)
    cleanup_flag = os.path.join(project_dir, "cleanup-flag")
    manual_mode = os.path.join(project_dir, "manual-mode")

    parts = []

    if os.path.exists(cleanup_flag):
        try:
            with open(cleanup_flag, "r") as f:
                flag_data = json.load(f)
            parts.append(build_cleanup_context(flag_data, project_key, cfg))
            os.remove(cleanup_flag)
        except (OSError, json.JSONDecodeError):
            pass

    if os.path.exists(manual_mode):
        try:
            with open(manual_mode, "r") as f:
                mm_data = json.load(f)
            if not mm_data.get("notified"):
                parts.append(build_manual_context(mm_data, project_key, cfg))
                mm_data["notified"] = True
                with open(manual_mode, "w") as f:
                    json.dump(mm_data, f)
        except (OSError, json.JSONDecodeError):
            pass

    if parts:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n\n---\n\n".join(parts),
            }
        }
        sys.stdout.buffer.write(
            json.dumps(output, ensure_ascii=False).encode("utf-8")
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
