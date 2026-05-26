import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE_ROOT / "scripts" / "x_observed_search_collect.py"
FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "japan_tourism_observed_fixture.csv"
QUERY_FILE = PACKAGE_ROOT / "queries" / "japan-tourism-ja.txt"


def load_collector_module():
    module_name = "x_observed_search_collect_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


class XObservedSearchCollectTest(unittest.TestCase):
    def test_fixture_mode_writes_expected_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--query-file",
                    str(QUERY_FILE),
                    "--start-date",
                    "2026-05-24",
                    "--end-date",
                    "2026-05-26",
                    "--timezone",
                    "Asia/Tokyo",
                    "--output-dir",
                    str(out_dir),
                    "--fixture-csv",
                    str(FIXTURE),
                ],
                cwd=PACKAGE_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ("raw.csv", "observed_posts.csv", "manifest.json", "gap_check.md", "window_log.csv"):
                self.assertTrue((out_dir / name).exists(), name)

            with (out_dir / "manifest.json").open(encoding="utf-8") as f:
                manifest = json.load(f)
            self.assertEqual(manifest["source"], "Observed X.com public searchable posts")
            self.assertEqual(manifest["mode"], "fixture")
            self.assertEqual(manifest["raw_rows"], 4)
            self.assertEqual(manifest["distinct_urls"], 3)
            self.assertEqual(manifest["duplicate_url_rows"], 1)

            with (out_dir / "observed_posts.csv").open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 3)
            self.assertEqual(len({row["tweet_url"] for row in rows}), 3)

            gap_text = (out_dir / "gap_check.md").read_text(encoding="utf-8")
            self.assertIn("Observed X.com public searchable posts", gap_text)
            self.assertIn("전체 언급량으로 해석 금지", gap_text)

    def test_prepare_login_does_not_require_query_date_or_output(self):
        for flag in ("--prepare-login", "--open-login-profile"):
            with self.subTest(flag=flag):
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        flag,
                        "--headless",
                    ],
                    cwd=PACKAGE_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(proc.returncode, 2)
                self.assertIn("--prepare-login opens a visible browser", proc.stderr)
                self.assertNotIn("--output-dir is required", proc.stderr)
                self.assertNotIn("one of --queries", proc.stderr)

    def test_help_describes_login_browser_for_live_collection(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--help",
            ],
            cwd=PACKAGE_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--login-browser", proc.stdout)
        self.assertIn("--debug-snapshot", proc.stdout)
        self.assertIn("--collection-mode", proc.stdout)
        self.assertIn("--open-cdp-browser", proc.stdout)
        self.assertIn("Installed browser for --prepare-login", proc.stdout)
        self.assertIn("--open-cdp-browser", proc.stdout)
        self.assertIn("playwright-launch", proc.stdout)

    def test_collection_browser_auto_prefers_installed_chrome(self):
        module = load_collector_module()

        def fake_candidates(kind):
            return {
                "chrome": [Path("C:/Program Files/Google/Chrome/Application/chrome.exe")],
                "edge": [Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe")],
            }.get(kind, [])

        with patch.object(module, "installed_browser_candidates", side_effect=fake_candidates):
            browser = module.resolve_collection_browser("auto")

        self.assertEqual(browser.channel, "chrome")
        self.assertEqual(browser.label, "installed Chrome binary under Playwright automation")
        self.assertFalse(browser.fallback_to_bundled_chromium)

    def test_collection_browser_auto_uses_edge_before_chromium_fallback(self):
        module = load_collector_module()

        def fake_candidates(kind):
            return {
                "chrome": [],
                "edge": [Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe")],
            }.get(kind, [])

        with patch.object(module, "installed_browser_candidates", side_effect=fake_candidates):
            browser = module.resolve_collection_browser("auto")

        self.assertEqual(browser.channel, "msedge")
        self.assertEqual(browser.label, "installed Edge binary under Playwright automation")
        self.assertFalse(browser.fallback_to_bundled_chromium)

    def test_collection_browser_auto_limits_chromium_to_last_fallback(self):
        module = load_collector_module()

        with patch.object(module, "installed_browser_candidates", return_value=[]):
            browser = module.resolve_collection_browser("auto")

        self.assertIsNone(browser.channel)
        self.assertEqual(browser.label, "Playwright bundled Chromium")
        self.assertTrue(browser.fallback_to_bundled_chromium)

    def test_collection_browser_explicit_choice_fails_without_installed_browser(self):
        module = load_collector_module()

        with patch.object(module, "installed_browser_candidates", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "No installed Chrome browser found"):
                module.resolve_collection_browser("chrome")

    def test_open_cdp_browser_does_not_require_query_date_or_output(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--open-cdp-browser",
                "--headless",
            ],
            cwd=PACKAGE_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2)
        self.assertIn("--open-cdp-browser opens a visible browser", proc.stderr)
        self.assertNotIn("--output-dir is required", proc.stderr)
        self.assertNotIn("one of --queries", proc.stderr)

    def test_headless_requires_explicit_playwright_launch_collection_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--queries",
                    "韓国旅行",
                    "--recent-days",
                    "1",
                    "--output-dir",
                    str(Path(tmp) / "run"),
                    "--headless",
                ],
                cwd=PACKAGE_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertIn("--headless is only supported with --collection-mode playwright-launch", proc.stderr)

    def test_page_state_classification_distinguishes_live_zero_causes(self):
        module = load_collector_module()
        cases = [
            (
                module.PageSignals(
                    page_kind="home",
                    url="https://x.com/i/flow/login",
                    account_input_count=1,
                ),
                "login-required",
            ),
            (
                module.PageSignals(
                    page_kind="home",
                    url="https://x.com/home",
                    temporary_restriction_text=True,
                ),
                "rate-limited-or-temporary-restricted",
            ),
            (
                module.PageSignals(
                    page_kind="search",
                    url="https://x.com/search?q=example&src=typed_query&f=live",
                    search_empty_text=True,
                ),
                "search-empty-state",
            ),
            (
                module.PageSignals(
                    page_kind="search",
                    url="https://x.com/search?q=example&src=typed_query&f=live",
                    article_count=0,
                    status_link_count=0,
                ),
                "selector-no-articles",
            ),
            (
                module.PageSignals(
                    page_kind="search",
                    url="https://x.com/search?q=example&src=typed_query&f=live",
                    article_count=2,
                    status_link_count=0,
                ),
                "selector-no-status-links",
            ),
        ]

        for signals, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(module.classify_page_state(signals), expected)

    def test_debug_diagnostic_keeps_url_query_values_out(self):
        module = load_collector_module()
        signals = module.PageSignals(
            page_kind="search",
            url="https://x.com/search?q=secret+query&src=typed_query&f=live",
            article_count=0,
        )

        diagnostic = module.signals_to_diagnostic(
            "search-1",
            signals,
            "selector-no-articles",
            module.timezone.utc,
        )
        diagnostic_json = json.dumps(diagnostic, ensure_ascii=False)

        self.assertEqual(diagnostic["url_host"], "x.com")
        self.assertEqual(diagnostic["url_path"], "/search")
        self.assertEqual(diagnostic["url_query_keys"], ["f", "q", "src"])
        self.assertNotIn("secret+query", diagnostic_json)
        self.assertNotIn("raw_html", diagnostic.get("signals", {}))
        self.assertIn("localStorage", diagnostic["not_saved"])


if __name__ == "__main__":
    unittest.main()
