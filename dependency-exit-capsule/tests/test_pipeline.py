import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent
for p in (SCRIPTS_DIR, SKILL_DIR, REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from scripts.risk_indicators import main as risk_main, major, release_age_days
    from scripts.scan_usage import scan_python, scan_text
except ImportError:
    from risk_indicators import main as risk_main, major, release_age_days
    from scan_usage import scan_python, scan_text


class PipelineTests(unittest.TestCase):
    def test_python_imports_calls_and_aliases(self):
        hits = scan_python(
            "requests",
            [
                "import requests as http",
                "from requests import get as fetch",
                "http.get(url)",
                "fetch(url)",
            ],
        )
        self.assertEqual(
            [(1, "import", "requests"), (2, "import", "from requests"), (3, "call", "http.get"), (4, "call", "fetch")],
            hits,
        )

    def test_syntax_error_returns_no_ast_result(self):
        self.assertIsNone(scan_python("requests", ["import requests", "if"]))

    def test_javascript_require_and_subpath(self):
        hits = scan_text("lodash", ['require("lodash/fp")', 'from "lodash"'], javascript=True)
        self.assertEqual(2, len(hits))

    def test_release_dates_handle_timezone_and_invalid_values(self):
        self.assertIsNotNone(release_age_days("2020-01-01"))
        self.assertIsNone(release_age_days("not-a-date"))
        self.assertEqual(2, major("v2.4.0"))
        self.assertIsNone(major("not-a-version"))

    def test_risk_main_preserves_invalid_date_as_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "usage.json").write_text(
                json.dumps({"dependency": "demo", "scan": {"usage_count": 0, "usages": []}}),
                encoding="utf-8",
            )
            (root / "metadata.json").write_text(
                json.dumps({"dependency": "demo", "registry": {"last_release": "invalid"}}),
                encoding="utf-8",
            )
            output = root / "risk.json"
            import sys

            original = sys.argv
            try:
                sys.argv = [
                    "risk_indicators.py",
                    "--usage",
                    str(root / "usage.json"),
                    "--metadata",
                    str(root / "metadata.json"),
                    "--out",
                    str(output),
                ]
                risk_main()
            finally:
                sys.argv = original
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("LOW", result["risk"]["overall"])
            self.assertEqual("metadata-quality", result["risk"]["indicators"][0]["name"])


if __name__ == "__main__":
    unittest.main()
