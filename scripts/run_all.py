#!/usr/bin/env python3
"""Run scan, planning, independent critique, trial and capsule/report generation."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

if __package__:
    from .pipeline_common import read_json, write_json
else:
    from pipeline_common import read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--dep", required=True)
    parser.add_argument("--ecosystem", choices=("pypi", "npm"), default="pypi")
    parser.add_argument("--import-name")
    parser.add_argument("--replacement", default="")
    parser.add_argument("--analysis", type=Path, help="Use an existing AI analysis instead of generating one")
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence"))
    parser.add_argument("--capsule-dir", type=Path, default=Path("capsule"))
    parser.add_argument("--offline", action="store_true", help="Skip registry requests")
    parser.add_argument("--test-command", help="Target test command (no shell); paths must be relative")
    parser.add_argument("--test-timeout", type=float, default=120)
    parser.add_argument("--skip-trial", action="store_true")
    parser.add_argument("--target-license", default="")
    parser.add_argument("--replacement-license", default="")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not repo.is_dir():
        parser.error("--repo must be an existing directory")
    if args.test_timeout <= 0:
        parser.error("--test-timeout must be positive")
    supplied_analysis = read_json(args.analysis) if args.analysis else None
    evidence, capsule = args.evidence_dir, args.capsule_dir
    evidence.mkdir(parents=True, exist_ok=True)
    scripts = Path(__file__).resolve().parent
    stages = []

    def record(name: str, status: str, duration: float = 0) -> None:
        stages.append({"name": name, "status": status, "duration": f"{duration:.2f}s", "evidence": "EXECUTED"})
        write_json(evidence / "pipeline.json", {"steps": stages})

    write_json(evidence / "pipeline.json", {"steps": []})

    def run(script: str, *arguments) -> None:
        started = time.perf_counter()
        try:
            subprocess.run([sys.executable, str(scripts / (script + ".py")), *map(str, arguments)], check=True)
        except subprocess.CalledProcessError:
            record(script, "ERROR", time.perf_counter() - started)
            raise
        status = "COMPLETED"
        if script == "analyze_migration":
            status = read_json(evidence / "ai_analysis.json").get("status", "UNKNOWN")
        elif script == "red_team":
            result = read_json(evidence / "red_team_critique.json")
            status = "ERROR" if result.get("status") == "ERROR" else "PASSED" if result.get("critique_passed") else "CONCERNS"
        elif script == "trial_patch":
            status = read_json(evidence / "trial_patch_result.json").get("test_execution_status", "UNKNOWN")
        elif script == "license_check":
            status = read_json(evidence / "license_risk.json").get("compatibility_status", "UNKNOWN")
        record(script, status, time.perf_counter() - started)

    scan_args = ["--repo", repo, "--dep", args.dep, "--out", evidence / "usage.json"]
    if args.import_name:
        scan_args += ["--import-name", args.import_name]
    run("scan_usage", *scan_args)
    metadata_args = ["--repo", repo, "--dep", args.dep, "--ecosystem", args.ecosystem,
                     "--out", evidence / "metadata.json"]
    if args.offline:
        metadata_args.append("--offline")
    run("collect_metadata", *metadata_args)
    run("risk_indicators", "--usage", evidence / "usage.json", "--metadata", evidence / "metadata.json",
        "--out", evidence / "risk.json")
    if supplied_analysis is not None:
        if args.replacement:
            supplied_analysis["replacement"] = args.replacement
        supplied_analysis["evidence"] = "AI-SUGGESTED"
        write_json(evidence / "ai_analysis.json", supplied_analysis)
        record("analyze_migration", "SUPPLIED")
    else:
        run("analyze_migration", "--usage", evidence / "usage.json", "--metadata", evidence / "metadata.json",
            "--replacement", args.replacement, "--out", evidence / "ai_analysis.json")
    run("red_team", "--usage", evidence / "usage.json", "--analysis", evidence / "ai_analysis.json",
        "--out", evidence / "red_team_critique.json")
    if args.skip_trial:
        write_json(evidence / "trial_patch_result.json", {"test_execution_status": "SKIPPED",
                   "outcome": "INCONCLUSIVE", "reason": "Skipped by --skip-trial", "evidence": "NOT_EXECUTED"})
        record("trial_patch", "SKIPPED")
    else:
        trial_args = ["--repo", repo, "--usage", evidence / "usage.json", "--analysis", evidence / "ai_analysis.json",
                      "--out", evidence / "trial_patch_result.json", "--test-timeout", args.test_timeout]
        if args.test_command:
            trial_args += ["--test-command", args.test_command]
        run("trial_patch", *trial_args)
    run("generate_diagram", "--usage", evidence / "usage.json", "--metadata", evidence / "metadata.json",
        "--out", evidence / "blast_radius.mmd")
    run("license_check", "--repo", repo, "--metadata", evidence / "metadata.json",
        "--analysis", evidence / "ai_analysis.json", "--target-license", args.target_license,
        "--replacement-license", args.replacement_license, "--out", evidence / "license_risk.json")
    run("build_capsule", "--evidence-dir", evidence, "--out", capsule / "exit-capsule.md",
        "--json-out", capsule / "capsule.json")
    run("build_report", "--capsule", capsule / "capsule.json", "--out", capsule / "report.html")


if __name__ == "__main__":
    main()
