import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_report import build_html


class ReportTests(unittest.TestCase):
    def test_empty_capsule_is_renderable(self):
        html = build_html({})
        self.assertIn("No usage locations recorded", html)
        self.assertIn("No executed test results recorded", html)

    def test_report_escapes_repository_content(self):
        html = build_html(
            {
                "dependency": "<demo>",
                "scan": {
                    "usage_count": 1,
                    "usages": [{"file": "a<&.py", "line": 4, "snippet": "<unsafe>&"}],
                },
            }
        )
        self.assertIn("&lt;demo&gt;", html)
        self.assertIn("&lt;unsafe&gt;&amp;", html)
        self.assertNotIn("<unsafe>&", html)

    def test_report_cli_writes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capsule = root / "capsule.json"
            output = root / "nested" / "report.html"
            capsule.write_text(json.dumps({"dependency": "demo"}), encoding="utf-8")
            from scripts.build_report import main
            import sys

            original = sys.argv
            try:
                sys.argv = ["build_report.py", "--capsule", str(capsule), "--out", str(output)]
                main()
            finally:
                sys.argv = original
            self.assertTrue(output.exists())
            self.assertIn("Dependency Exit Capsule", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
