import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path so test can run standalone
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_report import build_html, main


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

    def test_report_renders_full_pipeline_capsule(self):
        capsule_data = {
            "capsule_version": "1.0.0",
            "target_dependency": "Jinja2",
            "sections": {
                "dependency_details": {
                    "value": {"name": "Jinja2", "current_version": "2.11.3"}
                },
                "risk_indicators": {
                    "value": [
                        {"indicator": "Strict pin", "severity": "medium", "evidence": "requirements.txt"}
                    ]
                },
                "usage_locations": {
                    "value": [
                        {"file": "app.py", "line": 10, "kind": "import", "snippet": "import jinja2"}
                    ]
                },
                "test_results": {
                    "value": {"passed": 10, "failed": 0, "skipped": 0, "command": "pytest"}
                },
                "ai_analysis": {
                    "value": {
                        "problem_summary": "Jinja2 2.11 is outdated.",
                        "recommended_approach": "upgrade to 3.1.4",
                        "migration_steps": ["Step 1: update pyproject.toml"],
                        "risks": ["Breaking syntax"],
                    }
                },
            },
        }
        html = build_html(capsule_data)
        self.assertIn("Jinja2", html)
        self.assertIn("2.11.3", html)
        self.assertIn("app.py", html)
        self.assertIn("10/10", html)
        self.assertIn("upgrade to 3.1.4", html)

    def test_report_cli_writes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capsule = root / "capsule.json"
            output = root / "nested" / "report.html"
            capsule.write_text(json.dumps({"dependency": "demo"}), encoding="utf-8")

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
