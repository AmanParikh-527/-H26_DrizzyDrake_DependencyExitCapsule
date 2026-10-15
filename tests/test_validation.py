import json
import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from scripts.build_capsule import assemble, render_markdown
from scripts.generate_diagram import generate
from scripts.license_check import check, evaluate, host_license
from scripts.pipeline_common import query_model, write_json
from scripts.red_team import critique
from scripts.trial_patch import execute_tests, select_usage, trial


def fixture(root):
    (root / "target.py").write_bytes(b'from os.path import join\r\n\r\ndef combine():\r\n    return join("a", "b")\r\n')
    (root / "tests").mkdir()
    (root / "tests" / "test_target.py").write_text(
        "import unittest\nfrom target import combine\n"
        "class Example(unittest.TestCase):\n"
        "    def test_combine(self):\n        self.assertEqual('a/b', combine())\n",
        encoding="utf-8",
    )
    return {"dependency": "os", "scan": {"usages": [
        {"file": "target.py", "line": 1, "snippet": "from os.path import join", "kind": "import", "symbol": "from os.path"},
        {"file": "target.py", "line": 4, "snippet": 'return join("a", "b")', "kind": "call", "symbol": "join"},
    ]}}


COMMAND = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]


class AuditorTests(unittest.TestCase):
    def test_omitted_location_or_flaws_cannot_pass(self):
        usage = {"scan": {"usages": [{"file": "a.py", "line": 3}]}}
        with patch("scripts.red_team.query_model", return_value={"critique_passed": True, "flaws_identified": []}):
            result = critique(usage, {"replacement": "httpx"})
        self.assertFalse(result["critique_passed"])
        self.assertIn("line 3", result["flaws_identified"][0]["issue"])
        with patch("scripts.red_team.query_model", return_value={"critique_passed": True,
                   "checked_locations": [{"file": "a.py", "line": 3}],
                   "flaws_identified": [{"severity": "HIGH", "file": "a.py", "issue": "API missing"}]}):
            self.assertFalse(critique(usage, {"replacement": "httpx"})["critique_passed"])

    def test_complete_review_and_malformed_response(self):
        with patch("scripts.red_team.query_model", return_value={"critique_passed": True,
                   "checked_locations": [], "flaws_identified": []}):
            self.assertTrue(critique({"scan": {"usages": []}}, {"replacement": "httpx"})["critique_passed"])
        with patch("scripts.red_team.query_model", return_value={"critique_passed": "true"}):
            self.assertEqual("ERROR", critique({}, {"replacement": "httpx"})["status"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(critique({}, {"replacement": "httpx"})["critique_passed"])

    def test_model_client_rejects_bad_envelopes_and_accepts_fenced_json(self):
        with patch.dict(os.environ, {"CAPSULE_MODEL": "test-model"}):
            for response in [{}, {"choices": []}, {"choices": [{"message": {"content": "[]"}}]}]:
                with patch("scripts.pipeline_common.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                    with self.assertRaises(ValueError):
                        query_model("audit", {})
            response = {"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]}
            with patch("scripts.pipeline_common.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                self.assertEqual({"ok": True}, query_model("audit", {}))


class TrialTests(unittest.TestCase):
    def test_passing_and_failing_trials_restore_exact_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            usage = fixture(root)
            original = (root / "target.py").read_bytes()
            for proposed, status, outcome in [
                ("from posixpath import join", "PASSED", "VERIFIED_WORKING"),
                ("from pathlib import Path as join", "FAILED", "COMPATIBILITY_BREAKAGE"),
            ]:
                with self.subTest(status=status), patch("scripts.trial_patch.query_model", return_value={"patched_code": proposed}):
                    result = trial(root, usage, {"replacement": "posixpath"}, COMMAND)
                    self.assertEqual(status, result["test_execution_status"], result)
                    self.assertEqual(outcome, result["outcome"])
                    self.assertEqual(original, (root / "target.py").read_bytes())
                    self.assertFalse(list(root.rglob("*.bak")))
                    self.assertFalse(list(root.rglob("__pycache__")))

    def test_timeout_errors_and_interruption_leave_source_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            usage = fixture(root)
            original = (root / "target.py").read_bytes()
            with patch("scripts.trial_patch.query_model", return_value={"patched_code": "from posixpath import join"}):
                for failure in [OSError("test executable disappeared"), KeyboardInterrupt()]:
                    with patch("scripts.trial_patch.execute_tests", side_effect=[{"status": "PASSED"}, failure]):
                        if isinstance(failure, KeyboardInterrupt):
                            with self.assertRaises(KeyboardInterrupt):
                                trial(root, usage, {"replacement": "posixpath"}, COMMAND)
                        else:
                            self.assertEqual("ERROR", trial(root, usage, {"replacement": "posixpath"}, COMMAND)["test_execution_status"])
                    self.assertEqual(original, (root / "target.py").read_bytes())
            execution = execute_tests([sys.executable, "-c", "import time; time.sleep(10)"], root, .1)
            self.assertEqual("TIMED_OUT", execution["status"])

    def test_invalid_patch_stale_and_escaping_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            usage = fixture(root)
            for proposed in ["from x import (", "one\ntwo", "from os.path import join", None]:
                with patch("scripts.trial_patch.query_model", return_value={"patched_code": proposed}):
                    result = trial(root, usage, {"replacement": "posixpath"}, COMMAND)
                    self.assertEqual("ERROR", result["test_execution_status"])
                    self.assertEqual("NOT_EXECUTED", result["evidence"])
            (root / "link.py").symlink_to(root / "target.py")
            for filename in ["../outside.py", str(root / "target.py"), "link.py"]:
                with self.assertRaises(ValueError):
                    select_usage(root, {"scan": {"usages": [{**usage["scan"]["usages"][0], "file": filename}]}})
            for item in usage["scan"]["usages"]:
                item["snippet"] = "stale content"
            with self.assertRaises(ValueError):
                select_usage(root, usage)

    def test_broken_baseline_and_empty_suite_are_not_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            usage = fixture(root)
            for command in [[sys.executable, "-c", "raise SystemExit(1)"],
                            [sys.executable, "-c", "print('Ran 0 tests')"]]:
                with patch("scripts.trial_patch.query_model", return_value={"patched_code": "from posixpath import join"}):
                    result = trial(root, usage, {"replacement": "posixpath"}, command)
                    self.assertEqual("BASELINE_FAILED", result["test_execution_status"])
                    self.assertEqual("INCONCLUSIVE", result["outcome"])


class DiagramAndLicenseTests(unittest.TestCase):
    def test_diagram_groups_usages_and_escapes_injection(self):
        usage = {"dependency": 'bad\"] --> EVIL["x', "scan": {"usages": [
            {"file": "safe.py", "line": 2, "kind": "import", "symbol": "lib", "tested": True},
            {"file": "safe.py", "line": 3, "kind": "call", "symbol": "lib.get", "tested": True},
            {"file": 'unsafe\"]\n%%{init: x}%%.py', "line": 1, "symbol": "lib.post"},
        ]}}
        diagram = generate(usage, {"declared": {"constraint": "==2.0"}})
        self.assertTrue(diagram.startswith("graph TD\n"))
        self.assertIn('Direct importer: safe.py"]:::lowRisk', diagram)
        self.assertIn(":::highRisk", diagram)
        self.assertIn("lib.get", diagram)
        self.assertNotIn('bad"]', diagram)
        self.assertNotIn("%%{init", diagram)
        self.assertEqual(diagram, generate(usage, {"declared": {"constraint": "==2.0"}}))

    def test_license_rules_preserve_unknowns_and_expressions(self):
        pairs = [("Proprietary", "GPL-3.0", "INCOMPATIBLE", "CRITICAL"),
                 ("MIT", "AGPL-3.0-only", "HIGH RISK", "HIGH"),
                 ("Apache-2.0", "LGPL-2.1", "COMPATIBLE", "LOW"),
                 ("MIT", "BSD-3-Clause", "COMPATIBLE", "LOW"),
                 ("UNKNOWN", "MIT", "REVIEW_REQUIRED", "UNKNOWN"),
                 ("MIT", "GPL-3.0 OR MIT", "REVIEW_REQUIRED", "UNKNOWN"),
                 ("MIT", "GPL-3.0 WITH custom-exception", "REVIEW_REQUIRED", "UNKNOWN")]
        for target, replacement, status, risk in pairs:
            with self.subTest(target=target, replacement=replacement):
                self.assertEqual((status, risk), evaluate(target, replacement)[:2])

    def test_host_license_sources_and_unverified_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual("UNKNOWN", host_license(root)[0])
            (root / "pyproject.toml").write_text('[project]\nlicense = {text = "MIT"}\n[tool.fake]\nlicense="GPL-3.0"\n')
            self.assertEqual("MIT", host_license(root)[0])
            (root / "package.json").write_text('{"license": "Apache-2.0"}')
            self.assertEqual("Apache-2.0", host_license(root)[0])
            (root / "LICENSE.md").write_text("SPDX-License-Identifier: MIT\n")
            self.assertEqual("MIT", host_license(root)[0])
            result = check(root, {"registry": {"license": "Apache-2.0"}}, {"replacement": "httpx"})
            self.assertEqual("COMPATIBLE", result["compatibility_status"])
            self.assertEqual("Apache-2.0", result["current_dependency_license"])
            with patch("scripts.license_check.query_model", return_value={"license": "MIT", "source": "guess"}):
                result = check(root, {}, {"replacement": "unknown-library"})
            self.assertEqual("REVIEW_REQUIRED", result["compatibility_status"])
            self.assertEqual("AI-SUGGESTED_RULE_EVALUATION", result["evidence"])

    def test_capsule_embeds_warning_diagram_and_critique(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "license_risk.json", {"compatibility_status": "INCOMPATIBLE", "risk_level": "CRITICAL", "notes": "Copyleft concern"})
            write_json(root / "red_team_critique.json", {"critique_passed": False, "flaws_identified": [
                {"severity": "HIGH", "file": "api.py", "issue": "missing async method"}]})
            (root / "blast_radius.mmd").write_text("graph TD\n    DEP --> F0\n")
            data = assemble(root)
            result = render_markdown(data)
            self.assertIn("## Visual Blast Radius [OBSERVED]", result)
            self.assertIn("```mermaid\ngraph TD", result)
            self.assertIn("## UNRESOLVED CONCERNS & CRITIQUE", result)
            self.assertIn("missing async method", result)
            self.assertEqual("CRITICAL", data["risk"]["overall"])
            self.assertEqual("license-compatibility", data["risk"]["indicators"][0]["name"])


class LocalModelIntegrationTests(unittest.TestCase):
    def test_pipeline_with_local_http_model_and_real_tests(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(request)
                system = request["messages"][0]["content"]
                payload = json.loads(request["messages"][1]["content"])
                if "Principal" in system:
                    result = {"critique_passed": True, "flaws_identified": [],
                              "checked_locations": [{"file": item["file"], "line": item["line"]}
                                                    for item in payload["observed_usage"]["scan"]["usages"]]}
                elif "patch engineer" in system:
                    result = {"patched_code": "from posixpath import join"}
                else:
                    result = {"summary": "Replace path join", "replacement": "posixpath",
                              "steps": ["Replace import in target.py at line 1; join at line 4 remains supported"], "risks": []}
                response = json.dumps({"choices": [{"message": {"content": json.dumps(result)}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo = root / "target"
                repo.mkdir()
                fixture(repo)
                original = (repo / "target.py").read_bytes()
                env = dict(os.environ, CAPSULE_MODEL="test-auditor", CAPSULE_API_BASE=f"http://127.0.0.1:{server.server_port}/v1")
                process = subprocess.run([
                    sys.executable, "scripts/run_all.py", "--repo", str(repo), "--dep", "os", "--offline",
                    "--replacement", "posixpath", "--target-license", "MIT", "--replacement-license", "PSF-2.0",
                    "--test-command", " ".join(COMMAND), "--evidence-dir", str(root / "evidence"),
                    "--capsule-dir", str(root / "capsule"),
                ], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(0, process.returncode, process.stdout + process.stderr)
                result = json.loads((root / "capsule" / "capsule.json").read_text())
                self.assertTrue(result["red_team_critique"]["critique_passed"])
                self.assertEqual("VERIFIED_WORKING", result["trial_patch"]["outcome"])
                self.assertEqual("COMPATIBLE", result["license_risk"]["compatibility_status"])
                stages = {stage["name"]: stage["status"] for stage in result["pipeline"]}
                self.assertEqual("PASSED", stages["red_team"])
                self.assertEqual("PASSED", stages["trial_patch"])
                self.assertEqual("COMPATIBLE", stages["license_check"])
                self.assertIn("graph TD", (root / "capsule" / "exit-capsule.md").read_text())
                self.assertNotIn("No pipeline steps recorded", (root / "capsule" / "report.html").read_text())
                self.assertIn("AI-CRITIQUE", (root / "capsule" / "report.html").read_text())
                self.assertEqual(original, (repo / "target.py").read_bytes())
                self.assertEqual(3, len(requests))
                self.assertTrue(all(request["model"] == "test-auditor" for request in requests))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
