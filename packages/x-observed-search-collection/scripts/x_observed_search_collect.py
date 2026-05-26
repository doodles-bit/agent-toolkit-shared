#!/usr/bin/env python3
"""Collect observed X.com public search results into CSV artifacts.

This is a small POC-oriented collector. Fixture and dry-run modes need only the
Python standard library. Live X.com collection imports Playwright lazily and
uses a user-provided persistent browser profile; it does not handle account
credentials or export cookies.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SOURCE_LABEL = "Observed X.com public searchable posts"
SOURCE_DETAIL = "X.com web search observed public searchable posts"
RAW_COLUMNS = [
    "collect_date",
    "tweet_date",
    "author_handle",
    "author_name",
    "content",
    "tweet_url",
    "view_count",
    "like_count",
    "hashtags",
    "language",
    "image_urls",
    "media_type",
    "query",
    "window_start",
    "window_end",
]


@dataclass(frozen=True)
class DateWindow:
    start: date
    end_exclusive: date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect Observed X.com public searchable posts into raw.csv, "
            "observed_posts.csv, manifest.json, and gap_check.md."
        )
    )
    query_group = parser.add_mutually_exclusive_group()
    query_group.add_argument("--queries", help="Comma-separated query list.")
    query_group.add_argument("--query-file", type=Path, help="UTF-8 file with one query per line.")
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--start-date", help="Inclusive start date, YYYY-MM-DD.")
    date_group.add_argument("--recent-days", type=int, help="Collect the most recent N days.")
    parser.add_argument("--end-date", help="Inclusive end date, YYYY-MM-DD. Required with --start-date.")
    parser.add_argument("--timezone", default="Asia/Tokyo", help="IANA timezone, default Asia/Tokyo.")
    parser.add_argument("--output-dir", type=Path, help="Output directory for this run.")
    parser.add_argument("--window-days", type=int, default=1, help="Date window size, default 1.")
    parser.add_argument("--max-posts-per-query-window", type=int, default=100)
    parser.add_argument("--max-no-new", type=int, default=10)
    parser.add_argument("--scroll-delay", type=float, default=2.0)
    parser.add_argument("--page-delay", type=float, default=2.0, help="Delay between query-window search pages.")
    parser.add_argument("--profile-dir", type=Path, default=Path(".state/x_chrome_profile"))
    parser.add_argument("--headless", action="store_true", help="Use only after login profile is ready.")
    parser.add_argument("--fixture-csv", type=Path, help="Read observed rows from a fixture CSV instead of X.com.")
    parser.add_argument("--dry-run", action="store_true", help="Create empty artifacts and manifest without X.com access.")
    parser.add_argument(
        "--prepare-login",
        action="store_true",
        help="Open X.com home with the persistent profile and exit without collecting.",
    )
    parser.add_argument(
        "--login-wait-seconds",
        type=int,
        default=180,
        help="Seconds to wait for a visible login during --prepare-login.",
    )
    args = parser.parse_args()
    validate_args(args, parser)
    return args


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.prepare_login:
        if args.headless:
            parser.error("--prepare-login opens a visible browser; remove --headless.")
        if args.fixture_csv or args.dry_run:
            parser.error("--prepare-login cannot be combined with --fixture-csv or --dry-run.")
        if args.login_wait_seconds <= 0:
            parser.error("--login-wait-seconds must be positive.")
        return
    if not args.queries and not args.query_file:
        parser.error("one of --queries or --query-file is required unless --prepare-login is used.")
    if not args.start_date and args.recent_days is None:
        parser.error("one of --start-date or --recent-days is required unless --prepare-login is used.")
    if not args.output_dir:
        parser.error("--output-dir is required unless --prepare-login is used.")


def resolve_timezone(value: str) -> tzinfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        fixed_offsets = {
            "Asia/Tokyo": timezone(timedelta(hours=9), "Asia/Tokyo"),
            "Asia/Seoul": timezone(timedelta(hours=9), "Asia/Seoul"),
            "UTC": timezone.utc,
        }
        if value in fixed_offsets:
            return fixed_offsets[value]
        raise


def load_queries(args: argparse.Namespace) -> list[str]:
    if args.queries:
        raw_queries = args.queries.split(",")
    else:
        raw_queries = args.query_file.read_text(encoding="utf-8").splitlines()
    queries: list[str] = []
    seen: set[str] = set()
    for raw in raw_queries:
        query = raw.strip()
        if not query or query.startswith("# "):
            continue
        if query not in seen:
            seen.add(query)
            queries.append(query)
    if not queries:
        raise ValueError("query list is empty")
    return queries


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


def resolve_dates(args: argparse.Namespace, tz: tzinfo) -> tuple[date, date]:
    if args.recent_days is not None:
        if args.recent_days <= 0:
            raise ValueError("--recent-days must be positive")
        today = datetime.now(tz).date()
        return today - timedelta(days=args.recent_days - 1), today
    if not args.end_date:
        raise ValueError("--end-date is required with --start-date")
    start = parse_iso_date(args.start_date)
    end = parse_iso_date(args.end_date)
    if end < start:
        raise ValueError("--end-date must be on or after --start-date")
    return start, end


def build_windows(start: date, end: date, window_days: int) -> list[DateWindow]:
    if window_days <= 0:
        raise ValueError("--window-days must be positive")
    windows: list[DateWindow] = []
    cursor = start
    last_exclusive = end + timedelta(days=1)
    while cursor < last_exclusive:
        end_exclusive = min(cursor + timedelta(days=window_days), last_exclusive)
        windows.append(DateWindow(cursor, end_exclusive))
        cursor = end_exclusive
    return windows


def normalize_url(url: str) -> str:
    url = url.strip()
    url = re.sub(r"^https://twitter\.com/", "https://x.com/", url)
    url = url.split("?")[0]
    return url.rstrip("/")


def normalize_row(row: dict[str, str], query: str | None = None, window: DateWindow | None = None) -> dict[str, str]:
    output = {column: (row.get(column) or "").strip() for column in RAW_COLUMNS}
    output["tweet_url"] = normalize_url(output["tweet_url"])
    if query and not output["query"]:
        output["query"] = query
    if window:
        output["window_start"] = output["window_start"] or window.start.isoformat()
        output["window_end"] = output["window_end"] or window.end_exclusive.isoformat()
    output["media_type"] = output["media_type"] or "text"
    return output


def read_fixture(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [normalize_row(row) for row in reader if (row.get("tweet_url") or "").strip()]


def write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in RAW_COLUMNS})


def dedupe_by_url(rows: Iterable[dict[str, str]]) -> tuple[list[dict[str, str]], int, int]:
    deduped: dict[str, dict[str, str]] = {}
    duplicate_rows = 0
    date_conflicts: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        url = normalize_url(row.get("tweet_url", ""))
        if not url:
            continue
        if row.get("tweet_date"):
            date_conflicts[url].add(row["tweet_date"])
        if url in deduped:
            duplicate_rows += 1
            continue
        new_row = dict(row)
        new_row["tweet_url"] = url
        deduped[url] = new_row
    conflict_count = sum(1 for dates in date_conflicts.values() if len(dates) > 1)
    return list(deduped.values()), duplicate_rows, conflict_count


def filter_rows(rows: Iterable[dict[str, str]], queries: list[str], start: date, end: date) -> list[dict[str, str]]:
    query_set = set(queries)
    filtered: list[dict[str, str]] = []
    for row in rows:
        tweet_date = row.get("tweet_date")
        if tweet_date:
            try:
                parsed = date.fromisoformat(tweet_date)
            except ValueError:
                continue
            if parsed < start or parsed > end:
                continue
        row_query = row.get("query")
        if row_query and row_query not in query_set:
            content = row.get("content", "")
            if not any(query in content for query in queries):
                continue
        filtered.append(row)
    return filtered


def detect_login_state(page) -> str:
    current_url = page.url.lower()
    if "/i/flow/login" in current_url or "/login" in current_url:
        return "login-required"
    try:
        logged_in_selectors = [
            '[data-testid="SideNav_AccountSwitcher_Button"]',
            '[data-testid="AppTabBar_Home_Link"]',
            'a[href="/home"]',
        ]
        for selector in logged_in_selectors:
            if page.locator(selector).count() > 0:
                return "logged-in"
        login_selectors = [
            'a[href="/login"]',
            'a[href*="/i/flow/login"]',
            '[data-testid="loginButton"]',
        ]
        for selector in login_selectors:
            if page.locator(selector).count() > 0:
                return "login-required"
    except Exception:
        return "unknown"
    return "unknown"


def prepare_login(args: argparse.Namespace, tz: tzinfo) -> dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for X.com login preparation. Install with "
            "`python -m pip install -r requirements.txt` and `python -m playwright install chromium`."
        ) from exc

    args.profile_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.login_wait_seconds
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(args.profile_dir),
            headless=False,
            viewport={"width": 1365, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=45_000)
            login_state = detect_login_state(page)
            while login_state != "logged-in" and time.monotonic() < deadline:
                page.wait_for_timeout(2_000)
                login_state = detect_login_state(page)
            return {
                "ok": login_state == "logged-in",
                "mode": "prepare-login",
                "generated_at": datetime.now(tz).isoformat(),
                "profile_dir_used": str(args.profile_dir),
                "login_state": login_state,
                "current_url": page.url,
                "headless": False,
                "collection_started": False,
                "credentials_handled_by_script": False,
                "cookie_exported": False,
            }
        finally:
            context.close()


def collect_from_x(args: argparse.Namespace, queries: list[str], windows: list[DateWindow], tz: tzinfo) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for live X.com collection. Install with "
            "`python -m pip install -r requirements.txt` and `python -m playwright install chromium`."
        ) from exc

    args.profile_dir.mkdir(parents=True, exist_ok=True)
    collect_date = datetime.now(tz).date().isoformat()
    rows: list[dict[str, str]] = []
    window_log: list[dict[str, object]] = []
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(args.profile_dir),
            headless=args.headless,
            viewport={"width": 1365, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=45_000)
            if "login" in page.url.lower():
                raise RuntimeError(
                    "X.com login is required. Run without --headless and log in manually; "
                    "the profile directory stays local and must not be committed."
                )
            for query in queries:
                for window in windows:
                    before = len(rows)
                    search_query = f"{query} since:{window.start.isoformat()} until:{window.end_exclusive.isoformat()}"
                    search_url = f"https://x.com/search?q={quote_plus(search_query)}&src=typed_query&f=live"
                    status = "ok"
                    error = ""
                    try:
                        page.goto(search_url, wait_until="domcontentloaded", timeout=45_000)
                        page.wait_for_selector('article[data-testid="tweet"]', timeout=15_000)
                        rows.extend(scrape_search_page(page, query, window, collect_date, args))
                    except PlaywrightTimeoutError:
                        status = "no-visible-results"
                    except Exception as exc:  # pragma: no cover - live path only
                        status = "error"
                        error = str(exc)
                    window_log.append(
                        {
                            "query": query,
                            "window_start": window.start.isoformat(),
                            "window_end": window.end_exclusive.isoformat(),
                            "rows_added": len(rows) - before,
                            "status": status,
                            "error": error,
                        }
                    )
                    if args.page_delay > 0:
                        page.wait_for_timeout(int(args.page_delay * 1000))
        finally:
            context.close()
    return rows, window_log


def scrape_search_page(page, query: str, window: DateWindow, collect_date: str, args: argparse.Namespace) -> list[dict[str, str]]:
    seen_urls: set[str] = set()
    no_new = 0
    rows: list[dict[str, str]] = []
    while len(rows) < args.max_posts_per_query_window and no_new < args.max_no_new:
        added = 0
        articles = page.locator('article[data-testid="tweet"]')
        for idx in range(articles.count()):
            if len(rows) >= args.max_posts_per_query_window:
                break
            article = articles.nth(idx)
            row = row_from_article(article, query, window, collect_date)
            url = row.get("tweet_url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            rows.append(row)
            added += 1
        if added == 0:
            no_new += 1
        else:
            no_new = 0
        page.mouse.wheel(0, 1400)
        page.wait_for_timeout(int(args.scroll_delay * 1000))
    return rows


def row_from_article(article, query: str, window: DateWindow, collect_date: str) -> dict[str, str]:
    url = ""
    for href in article.locator('a[href*="/status/"]').evaluate_all("(els) => els.map((a) => a.href)"):
        if "/status/" in href:
            url = normalize_url(href)
            break
    text_parts = article.locator('[data-testid="tweetText"]').evaluate_all("(els) => els.map((e) => e.innerText)")
    content = "\n".join(part.strip() for part in text_parts if part.strip())
    time_value = ""
    time_elements = article.locator("time")
    if time_elements.count() > 0:
        time_value = time_elements.first.get_attribute("datetime") or ""
    tweet_date = time_value[:10] if time_value else ""
    author_handle = ""
    match = re.match(r"https://x\.com/([^/]+)/status/", url)
    if match:
        author_handle = match.group(1)
    return normalize_row(
        {
            "collect_date": collect_date,
            "tweet_date": tweet_date,
            "author_handle": author_handle,
            "author_name": "",
            "content": content,
            "tweet_url": url,
            "media_type": detect_media_type(article),
        },
        query=query,
        window=window,
    )


def detect_media_type(article) -> str:
    try:
        if article.locator('[data-testid="videoPlayer"], video').count() > 0:
            return "video"
        if article.locator('[data-testid="tweetPhoto"], [data-testid="card.wrapper"]').count() > 0:
            return "image"
    except Exception:
        return "text"
    return "text"


def count_by_date(rows: Iterable[dict[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        if row.get("tweet_date"):
            counts[row["tweet_date"]] += 1
    return counts


def count_by_query_window(rows: Iterable[dict[str, str]]) -> Counter[tuple[str, str, str]]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        counts[(row.get("query", ""), row.get("window_start", ""), row.get("window_end", ""))] += 1
    return counts


def build_manifest(
    args: argparse.Namespace,
    queries: list[str],
    start: date,
    end: date,
    windows: list[DateWindow],
    raw_rows: list[dict[str, str]],
    observed_rows: list[dict[str, str]],
    duplicate_rows: int,
    date_conflicts: int,
    mode: str,
    tz: tzinfo,
    window_log: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "source": SOURCE_LABEL,
        "source_detail": SOURCE_DETAIL,
        "collection_scope_note": (
            "Observed public X.com search surface only; not X full archive, not total public opinion, "
            "and not total mention volume."
        ),
        "mode": mode,
        "generated_at": datetime.now(tz).isoformat(),
        "timezone": str(tz),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "window_days": args.window_days,
        "windows": [
            {"since": window.start.isoformat(), "until": window.end_exclusive.isoformat()} for window in windows
        ],
        "queries": queries,
        "raw_rows": len(raw_rows),
        "distinct_urls": len(observed_rows),
        "duplicate_url_rows": duplicate_rows,
        "date_conflict_url_count": date_conflicts,
        "output_files": ["raw.csv", "observed_posts.csv", "manifest.json", "gap_check.md"],
        "live_x_smoke": mode == "live",
        "headless": bool(args.headless),
        "profile_dir_used": "" if mode != "live" else str(args.profile_dir),
        "window_log": window_log,
    }


def write_gap_check(path: Path, start: date, end: date, queries: list[str], windows: list[DateWindow], observed_rows: list[dict[str, str]], raw_rows: list[dict[str, str]]) -> None:
    daily_counts = count_by_date(observed_rows)
    query_window_counts = count_by_query_window(raw_rows)
    dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    zero_dates = [day.isoformat() for day in dates if daily_counts[day.isoformat()] == 0]
    lines = [
        "# X Observed Search Gap Check",
        "",
        f"Source label: `{SOURCE_LABEL}`",
        "",
        "본 파일은 X.com 공개 검색 화면에서 관측된 포스트만 기준으로 한다.",
        "전체 여론, 전체 트윗, 전체 언급량으로 해석 금지.",
        "",
        "## Daily distinct URL counts",
        "",
        "| date | distinct tweet_url count |",
        "|---|---:|",
    ]
    for day in dates:
        day_text = day.isoformat()
        lines.append(f"| {day_text} | {daily_counts[day_text]} |")
    lines.extend(["", "## Zero-observed dates", ""])
    if zero_dates:
        lines.extend(f"- {day_text}" for day_text in zero_dates)
    else:
        lines.append("- none")
    lines.extend(["", "## Query-window raw counts", "", "| query | since | until | raw rows |", "|---|---|---|---:|"])
    for query in queries:
        for window in windows:
            key = (query, window.start.isoformat(), window.end_exclusive.isoformat())
            lines.append(f"| {query} | {key[1]} | {key[2]} | {query_window_counts[key]} |")
    lines.extend(
        [
            "",
            "## Follow-up guidance",
            "",
            "- 0건 날짜는 실제 무활동으로 단정하지 말고 1일 window와 expanded query로 재검색한다.",
            "- 검색 surface는 비결정적이므로 여러 pass를 union하고 `tweet_url` 기준 dedupe한다.",
            "- raw, browser profile, login session, cookie는 공유 repo에 커밋하지 않는다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_window_log(path: Path, window_log: list[dict[str, object]]) -> None:
    columns = ["query", "window_start", "window_end", "rows_added", "status", "error"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in window_log:
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    try:
        tz = resolve_timezone(args.timezone)
        if args.prepare_login:
            print(json.dumps(prepare_login(args, tz), ensure_ascii=False))
            return 0
        queries = load_queries(args)
        start, end = resolve_dates(args, tz)
        windows = build_windows(start, end, args.window_days)
        args.output_dir.mkdir(parents=True, exist_ok=True)

        mode = "live"
        window_log: list[dict[str, object]] = []
        if args.fixture_csv:
            mode = "fixture"
            raw_rows = filter_rows(read_fixture(args.fixture_csv), queries, start, end)
            for query in queries:
                for window in windows:
                    count = sum(
                        1
                        for row in raw_rows
                        if row.get("query") == query
                        and row.get("window_start") == window.start.isoformat()
                        and row.get("window_end") == window.end_exclusive.isoformat()
                    )
                    window_log.append(
                        {
                            "query": query,
                            "window_start": window.start.isoformat(),
                            "window_end": window.end_exclusive.isoformat(),
                            "rows_added": count,
                            "status": "fixture",
                            "error": "",
                        }
                    )
        elif args.dry_run:
            mode = "dry-run"
            raw_rows = []
            for query in queries:
                for window in windows:
                    window_log.append(
                        {
                            "query": query,
                            "window_start": window.start.isoformat(),
                            "window_end": window.end_exclusive.isoformat(),
                            "rows_added": 0,
                            "status": "dry-run",
                            "error": "",
                        }
                    )
        else:
            raw_rows, window_log = collect_from_x(args, queries, windows, tz)

        observed_rows, duplicate_rows, date_conflicts = dedupe_by_url(raw_rows)
        write_csv(args.output_dir / "raw.csv", raw_rows)
        write_csv(args.output_dir / "observed_posts.csv", observed_rows)
        write_window_log(args.output_dir / "window_log.csv", window_log)
        manifest = build_manifest(
            args,
            queries,
            start,
            end,
            windows,
            raw_rows,
            observed_rows,
            duplicate_rows,
            date_conflicts,
            mode,
            tz,
            window_log,
        )
        (args.output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_gap_check(args.output_dir / "gap_check.md", start, end, queries, windows, observed_rows, raw_rows)
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": mode,
                    "output_dir": str(args.output_dir),
                    "raw_rows": len(raw_rows),
                    "distinct_urls": len(observed_rows),
                    "duplicate_url_rows": duplicate_rows,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
