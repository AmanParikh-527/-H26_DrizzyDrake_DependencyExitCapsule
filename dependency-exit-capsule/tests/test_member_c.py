"""test_member_c.py - Automated test suite for Member C deliverables:
build_capsule.py and run_pipeline.py.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
BUILD_CAPSULE = str(SCRIPTS_DIR / "build_capsule.py")
RUN_PIPELINE = str(SCRIPTS_DIR / "run_pipeline.py")


class TestMemberC(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="capsule_test_")
        self.output_dir = os.path.join(self.test_dir, "output")

        # Mock usage report
        self.usage_file = os.path.join(self.test_dir, "usage_report.json")
        with open(self.usage_file, "w", encoding="utf-8") as f:
            json.dump({
                "dependency": {
                    "name": "pydantic",
                    "version": "1.10.13",
                    "required_version": ">=2",
                    "source_files": ["requirements.txt", "pyproject.toml"]
                },
                "usages": [
                    {
                        "file": "linkwatch/config.py",
                        "line": 3,
                        "snippet": "from pydantic import BaseModel, validator",
                        "type": "import",
                        "api_version": "v1"
                    },
                    {
                        "file": "linkwatch/config.py",
                        "line": 13,
                        "snippet": "@validator('name')",
                        "type": "decorator",
                        "api_version": "v1"
                    }
                ],
                "summary": {
                    "total_usages": 2,
                    "v1_usages": 2,
                    "v2_usages": 0,
                    "files_affected": 1
                },
                "additional_findings": [
                    {
                        "dependency": "toml",
                        "issue": "Archived library",
                        "severity": "medium",
                        "recommendation": "Use tomllib"
                    }
                ]
            }, f)

        # Mock metadata report
        self.metadata_file = os.path.join(self.test_dir, "metadata_report.json")
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump({
                "dependency": {
                    "name": "pydantic",
                    "current_version": "1.10.13",
                    "required_version": ">=2",
                    "latest_version": "2.11.0"
                },
                "metadata": {
                    "license": "MIT",
                    "last_release_date": "2025-02-14",
                    "repository_url": "https://github.com/pydantic/pydantic",
                    "is_deprecated": False
                },
                "version_conflict": {
                    "detected": True,
                    "details": "requirements.txt pins 1.10.13 but pyproject.toml requires >=2"
                },
                "risk_indicators": [
                    {
                        "indicator": "Manifest version conflict",
                        "severity": "critical",
                        "evidence": "requirements.txt:7 vs pyproject.toml:14",
                        "tag": "[OBSERVED]"
                    }
                ]
            }, f)

        # Mock test results
        self.test_file = os.path.join(self.test_dir, "test_results.json")
        with open(self.test_file, "w", encoding="utf-8") as f:
            json.dump({
                "framework": "pytest",
                "command": "pytest tests/",
                "total": 10,
                "passed": 9,
                "failed": 1,
                "errors": 0,
                "skipped": 0,
                "raw_output": "1 failed, 9 passed in 0.42s"
            }, f)

        # Mock AI analysis
        self.ai_file = os.path.join(self.test_dir, "ai_analysis.json")
        with open(self.ai_file, "w", encoding="utf-8") as f:
            json.dump({
                "model_used": "qwen2.5-coder:7b",
                "problem_summary": "Pydantic v1 vs v2 conflict in config.py",
                "recommended_approach": "Migrate to Pydantic v2 native API",
                "migration_steps": [
                    "Update imports to field_validator and ConfigDict",
                    "Migrate class Config to model_config"
                ],
                "code_changes": [
                    {
                        "file": "linkwatch/config.py",
                        "description": "Migrate @validator to @field_validator",
                        "before": "@validator('name')\ndef check(cls, v): return v",
                        "after": "@field_validator('name')\n@classmethod\ndef check(cls, v): return v"
                    }
                ],
                "estimated_effort": "1-2 hours",
                "risks": [
                    "Validation timing differs in v2"
                ],
                "suggested_tests": [
                    "test_field_validation"
                ]
            }, f)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_build_capsule_full_pipeline(self):
        """Test build_capsule.py with all 4 JSON inputs."""
        cmd = [
            sys.executable, BUILD_CAPSULE,
            "--usage", self.usage_file,
            "--metadata", self.metadata_file,
            "--tests", self.test_file,
            "--ai", self.ai_file,
            "--output", self.output_dir,
            "--repo-url", "https://github.com/rishrek/LinkWatch",
            "--repo-name", "LinkWatch"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"build_capsule failed:\n{res.stderr}")

        # Check capsule.json exists and is valid
        json_path = os.path.join(self.output_dir, "capsule.json")
        self.assertTrue(os.path.isfile(json_path))
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["capsule_version"], "1.0.0")
        self.assertEqual(data["target_dependency"], "pydantic")
        self.assertIn("sections", data)
        self.assertIn("evidence_summary", data)

        # Check evidence tags exist
        sections = data["sections"]
        self.assertEqual(sections["problem_identified"]["tag"], "[OBSERVED]")
        self.assertEqual(sections["dependency_details"]["tag"], "[OBSERVED]")
        self.assertEqual(sections["ai_analysis"]["tag"], "[AI-SUGGESTED]")
        self.assertEqual(sections["test_results"]["tag"], "[EXECUTED]")

        # Check counts
        s = data["evidence_summary"]
        self.assertGreater(s["observed_count"], 0)
        self.assertGreater(s["executed_count"], 0)
        self.assertGreater(s["ai_suggested_count"], 0)

        # Check capsule.md exists
        md_path = os.path.join(self.output_dir, "capsule.md")
        self.assertTrue(os.path.isfile(md_path))
        with open(md_path, "r", encoding="utf-8") as f:
            md = f.read()

        self.assertIn("# Dependency Exit Capsule", md)
        self.assertIn("[OBSERVED]", md)
        self.assertIn("[EXECUTED]", md)
        self.assertIn("[AI-SUGGESTED]", md)
        self.assertIn("diff", md)

    def test_build_capsule_partial_inputs(self):
        """Test build_capsule.py with only usage and metadata (no tests, no AI)."""
        cmd = [
            sys.executable, BUILD_CAPSULE,
            "--usage", self.usage_file,
            "--metadata", self.metadata_file,
            "--output", self.output_dir
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Partial build_capsule failed:\n{res.stderr}")

        md_path = os.path.join(self.output_dir, "capsule.md")
        with open(md_path, "r", encoding="utf-8") as f:
            md = f.read()

        self.assertIn("Tests were not executed.", md)
        self.assertIn("AI analysis was not performed.", md)

    def test_build_capsule_zero_inputs(self):
        """Test build_capsule.py fails cleanly with exit code 1 when no inputs exist."""
        cmd = [sys.executable, BUILD_CAPSULE, "--output", self.output_dir]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 1)

    def test_run_pipeline_dry_run(self):
        """Test run_pipeline.py in --dry-run mode."""
        cmd = [
            sys.executable, RUN_PIPELINE,
            "--repo", self.test_dir,
            "--dependency", "pydantic",
            "--dry-run"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Dry run complete", res.stdout)
        self.assertIn("SKIPPED (dry run)", res.stdout)

    def test_run_pipeline_skip_flags(self):
        """Test run_pipeline.py with --skip-ai and --skip-tests."""
        cmd = [
            sys.executable, RUN_PIPELINE,
            "--repo", self.test_dir,
            "--dependency", "pydantic",
            "--skip-ai",
            "--skip-tests",
            "--dry-run"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Skip AI:     True", res.stdout)
        self.assertIn("Skip tests:  True", res.stdout)


if __name__ == "__main__":
    unittest.main()