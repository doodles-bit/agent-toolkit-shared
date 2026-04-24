"""
statusLine 스크립트 (Claude Code용) — analytics-leader 전용.

추적 대상 프로젝트(`~/project_repo/ai_agent_team`) 에서 ctx 사용률이 40% 상향 돌파하는
순간을 감지해 `~/.claude/state/analytics-leader/cleanup-flag` (혹은 쿨다운 중이면
`manual-mode`) 파일을 생성한다. 이 flag 는 UserPromptSubmit 훅이 다음 프롬프트 시
읽어서 정리 사이클 지시를 additionalContext 로 주입한다.

경로:
  ~/.claude/state/ctx-<session_id>.json       : 세션별 직전 ctx (격리)
  ~/.claude/state/analytics-leader/cleanup-flag      : 정리 트리거 flag (훅이 감지 후 삭제)
  ~/.claude/state/analytics-leader/manual-mode       : 수동 모드 flag (사용자가 수동 삭제)
  ~/.claude/state/analytics-leader/last-checkpoint.txt : 직전 정리 완료 Unix timestamp

Compass 원본(`github.com/doodles-bit/compass/.claude/memory/...` 참조)의 로직을 그대로
따르되, 분석팀 환경에 맞춰 TRACKED_PROJECTS 를 analytics-leader 단일 엔트리로 축소.
"""

import json
import os
import sys
import time

STATE_DIR = os.path.expanduser("~/.claude/state")

THRESHOLD = 40.0
COOLDOWN_SEC = 600
CTX_FILE_MAX_AGE_SEC = 86400  # 24h 이상 갱신 안 된 ctx-*.json 정리

# 분석팀 환경 — cwd 가 `/project_repo/ai_agent_team` 로 끝나면 analytics-leader 세션으로 간주.
# 다른 팀원(palm, hifirush, verification, copperhead, editor, social-marketing)은 본 훅의
# 적용 범위 밖. 팀원 세션도 정리가 필요해지면 별도 엔트리 추가 검토.
TRACKED_PROJECTS = [
    ("/project_repo/ai_agent_team", "analytics-leader"),
]


def detect_project(cwd_norm):
    for suffix, key in TRACKED_PROJECTS:
        if cwd_norm.endswith(suffix):
            return key
    return None


def project_paths(project_key):
    project_dir = os.path.join(STATE_DIR, project_key)
    return {
        "dir": project_dir,
        "cleanup_flag": os.path.join(project_dir, "cleanup-flag"),
        "manual_mode": os.path.join(project_dir, "manual-mode"),
        "last_checkpoint": os.path.join(project_dir, "last-checkpoint.txt"),
    }


def cleanup_stale_ctx_files():
    try:
        now = time.time()
        for name in os.listdir(STATE_DIR):
            if not (name.startswith("ctx-") and name.endswith(".json")):
                continue
            path = os.path.join(STATE_DIR, name)
            try:
                if now - os.path.getmtime(path) > CTX_FILE_MAX_AGE_SEC:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        print("statusline: invalid input", end="")
        return

    cwd = (d.get("workspace") or {}).get("current_dir") or d.get("cwd") or ""
    cwd_norm = cwd.replace("\\", "/").rstrip("/")
    dir_name = os.path.basename(cwd_norm) or "unknown"

    model = (d.get("model") or {}).get("display_name") or "unknown"

    used = (d.get("context_window") or {}).get("used_percentage")
    ctx_val = used if isinstance(used, (int, float)) else None
    ctx = f"{round(ctx_val)}%" if ctx_val is not None else "ctx:-"

    cost = (d.get("cost") or {}).get("total_cost_usd")
    cost_s = f"${cost:.2f}" if isinstance(cost, (int, float)) else "$-"

    project_key = detect_project(cwd_norm)
    suffix = ""

    if project_key and ctx_val is not None:
        session_id = d.get("session_id") or ""

        if session_id:
            paths = project_paths(project_key)
            try:
                os.makedirs(paths["dir"], exist_ok=True)
            except OSError:
                pass

            ctx_file = os.path.join(STATE_DIR, f"ctx-{session_id}.json")

            prev_ctx = None
            try:
                with open(ctx_file, "r") as f:
                    prev = json.load(f)
                    prev_ctx = prev.get("ctx_pct")
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                pass

            crossing = (
                prev_ctx is not None
                and prev_ctx < THRESHOLD
                and ctx_val >= THRESHOLD
            )

            if crossing:
                in_cooldown = False
                last_ts = None
                try:
                    with open(paths["last_checkpoint"], "r") as f:
                        last_ts = float(f.read().strip())
                        if time.time() - last_ts < COOLDOWN_SEC:
                            in_cooldown = True
                except (FileNotFoundError, ValueError, OSError):
                    pass

                if os.path.exists(paths["manual_mode"]):
                    # 이미 수동 모드 — 자동 트리거 무시.
                    pass
                elif in_cooldown:
                    try:
                        with open(paths["manual_mode"], "w") as f:
                            json.dump({
                                "trigger_time": time.time(),
                                "ctx_pct": ctx_val,
                                "last_checkpoint_ts": last_ts,
                                "session_id": session_id,
                                "project": project_key,
                            }, f)
                    except OSError:
                        pass
                else:
                    try:
                        with open(paths["cleanup_flag"], "w") as f:
                            json.dump({
                                "trigger_time": time.time(),
                                "ctx_pct": ctx_val,
                                "session_id": session_id,
                                "project": project_key,
                            }, f)
                    except OSError:
                        pass

            try:
                with open(ctx_file, "w") as f:
                    json.dump({
                        "ctx_pct": ctx_val,
                        "updated": time.time(),
                    }, f)
            except OSError:
                pass

            cleanup_stale_ctx_files()

            if os.path.exists(paths["manual_mode"]):
                suffix = " [MANUAL]"
            elif os.path.exists(paths["cleanup_flag"]):
                suffix = " [CLEANUP]"

    print(f"{dir_name} | {model} | {ctx} | {cost_s}{suffix}", end="")


if __name__ == "__main__":
    main()
