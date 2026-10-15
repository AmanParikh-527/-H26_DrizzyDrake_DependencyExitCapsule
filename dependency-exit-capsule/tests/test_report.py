import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

# Support running from root or elsewhere
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_report import build_html, main


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

    def test_validation_results_are_visible_and_escaped(self):
        html = build_html({
            "tests": {"trial_baseline": {"status": "PASSED"}},
            "red_team_critique": {"flaws_identified": [{"issue": "<script>unsafe</script>"}]},
            "trial_patch": {"outcome": "VERIFIED_WORKING"},
            "license_risk": {"compatibility_status": "INCOMPATIBLE"},
            "blast_radius_mermaid": 'graph TD\n DEP["<unsafe>"]',
        })
        self.assertIn("Trial baseline parameters", html)
        self.assertIn("PASSED", html)
        self.assertIn("INCOMPATIBLE", html)
        self.assertIn("AI critique parameters", html)
        self.assertIn("VERIFIED_WORKING", html)
        self.assertNotIn("<script>unsafe</script>", html)
        self.assertIn("&lt;script&gt;unsafe&lt;/script&gt;", html)
        self.assertIn("Blast radius parameters", html)
        self.assertNotIn("<pre>", html)
        self.assertNotIn("DEP[", html)

    def test_new_parameters_preserve_original_sections_and_charts(self):
        class Headings(HTMLParser):
            def __init__(self):
                super().__init__()
                self.headings = []
                self.active = False

            def handle_starttag(self, tag, attrs):
                if tag == "h2":
                    self.active = True
                    self.headings.append("")

            def handle_endtag(self, tag):
                if tag == "h2":
                    self.active = False

            def handle_data(self, value):
                if self.active:
                    self.headings[-1] += value

        data = {
            "tests": {"baseline": {"passed": 8, "failed": 2, "skipped": 0}},
            "scan": {"usages": [{"file": "client.py", "kind": "call", "symbol": "requests.get"}]},
            "red_team_critique": {"critique_passed": False, "evidence_tag": "AI-CRITIQUE"},
            "trial_patch": {"outcome": "COMPATIBILITY_BREAKAGE"},
            "license_risk": {"risk_level": "HIGH"},
            "blast_radius_mermaid": "graph TD\n DEP --> F0",
        }
        html = build_html(data)
        parser = Headings()
        parser.feed(html)
        self.assertEqual([
            "Pipeline", "Risk indicators OBSERVED", "Usage hotspots OBSERVED", "Test results EXECUTED",
            "All usage locations OBSERVED", "AI analysis AI-SUGGESTED", "Gaps and limitations", "Unresolved concerns",
        ], parser.headings)
        self.assertIn('aria-label="tests 80% passed"', html)
        self.assertIn('<b>8/10</b><span>tests passed', html)
        self.assertIn('class="bar"', html)
        self.assertIn('id="q"', html)
        self.assertIn("License screening parameters", html)
        self.assertIn("COMPATIBILITY_BREAKAGE", html)


if __name__ == "__main__":
    unittest.main()
