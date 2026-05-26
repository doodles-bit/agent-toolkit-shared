import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE_ROOT / "scripts" / "x_observed_search_collect.py"
FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "japan_tourism_observed_fixture.csv"
QUERY_FILE = PACKAGE_ROOT / "queries" / "japan-tourism-ja.txt"


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
            for name in ("raw.csv", "observed_posts.csv", "manifest.json", "gap_check.md"):
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


if __name__ == "__main__":
    unittest.main()
