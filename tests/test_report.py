import json
import tempfile
import unittest
from html.parser import HTMLParser
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
