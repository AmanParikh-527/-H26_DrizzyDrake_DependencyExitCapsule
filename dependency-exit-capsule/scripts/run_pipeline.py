#!/usr/bin/env python3
"""run_pipeline.py - Orchestrates the dependency-exit-capsule pipeline.

Runs all five scripts in sequence:
  1. scan_usage.py
  2. collect_metadata.py
  3. run_tests.py
  4. ai_analyze.py
  5. build_capsule.py

Handles failures gracefully and produces a capsule even with partial data.
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent


def timestamp():
    """Return a formatted timestamp for progress messages."""
    return datetime.now().strftime("[%H:%M:%S]")


def run_step(step_num, total, label, cmd, dry_run=False):
    """Run a single pipeline step, returning True on success."""
    print("\n%s Step %d/%d: %s" % (timestamp(), step_num, total, label))
    print("  Command: %s" % " ".join(cmd))

    if dry_run:
        print("  [DRY RUN] Skipped.")
        return False

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print("  [FAILED] Exit code %d" % result.returncode)
            if result.stderr:
                print("  Stderr: %s" % result.stderr[:500])
            return False
        print("  [OK] Completed successfully.")
        if result.stdout:
            for line in result.stdout.strip().splitlines()[-3:]:
                print("  > %s" % line)
        return True
    except subprocess.TimeoutExpired:
        print("  [TIMEOUT] Step exceeded 5 minute limit.")
        return False
    except FileNotFoundError:
        print("  [ERROR] Script not found: %s" % cmd[0])
        return False
    except OSError as exc:
        print("  [ERROR] %s" % exc)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run the dependency-exit-capsule pipeline end-to-end."
    )
    parser.add_argument(
        "--repo", required=True,
        help="Path to the cloned target repository."
    )
    parser.add_argument(
        "--dependency", required=True,
        help="PyPI package name to analyse (e.g. 'pydantic')."
    )
    parser.add_argument(
        "--model", default="qwen2.5-coder:7b",
        help="Ollama model for AI analysis (default: qwen2.5-coder:7b)."
    )
    parser.add_argument(
        "--output", default="./capsule_output",
        help="Output directory (default: ./capsule_output)."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print commands without executing."
    )
    parser.add_argument(
        "--skip-ai", action="store_true",
        help="Skip the AI analysis step."
    )
    parser.add_argument(
        "--skip-tests", action="store_true",
        help="Skip test execution."
    )
    args = parser.parse_args()

    python = sys.executable
    output_dir = os.path.abspath(args.output)
    intermediate = os.path.join(output_dir, "intermediate")

    if not args.dry_run:
        os.makedirs(intermediate, exist_ok=True)

    usage_json = os.path.join(intermediate, "usage_report.json")
    metadata_json = os.path.join(intermediate, "metadata_report.json")
    test_json = os.path.join(intermediate, "test_results.json")
    ai_json = os.path.join(intermediate, "ai_analysis.json")

    total_steps = 5
    if args.skip_ai:
        total_steps -= 1
    if args.skip_tests:
        total_steps -= 1

    print("=" * 60)
    print("Dependency Exit Capsule Pipeline")
    print("=" * 60)
    print("Repository:  %s" % args.repo)
    print("Dependency:  %s" % args.dependency)
    print("Model:       %s" % args.model)
    print("Output:      %s" % output_dir)
    print("Dry run:     %s" % args.dry_run)
    print("Skip AI:     %s" % args.skip_ai)
    print("Skip tests:  %s" % args.skip_tests)
    print("=" * 60)

    step = 0
    results = {}

    # Step 1: Scan usage
    step += 1
    scan_script = str(SCRIPTS_DIR / "scan_usage.py")
    results["scan"] = run_step(step, total_steps, "Scanning dependency usage...", [
        python, scan_script,
        "--repo", args.repo,
        "--dependency", args.dependency,
        "--output", usage_json,
    ], dry_run=args.dry_run)

    # Step 2: Collect metadata
    step += 1
    meta_script = str(SCRIPTS_DIR / "collect_metadata.py")
    results["metadata"] = run_step(step, total_steps, "Collecting dependency metadata...", [
        python, meta_script,
        "--repo", args.repo,
        "--dependency", args.dependency,
        "--output", metadata_json,
    ], dry_run=args.dry_run)

    # Step 3: Run tests (optional)
    if not args.skip_tests:
        step += 1
        test_script = str(SCRIPTS_DIR / "run_tests.py")
        results["tests"] = run_step(step, total_steps, "Running test suite...", [
            python, test_script,
            "--repo", args.repo,
            "--output", test_json,
        ], dry_run=args.dry_run)
    else:
        print("\n%s Skipping test execution (--skip-tests)." % timestamp())
        results["tests"] = False

    # Step 4: AI analysis (optional)
    if not args.skip_ai:
        step += 1
        ai_script = str(SCRIPTS_DIR / "ai_analyze.py")
        ai_cmd = [
            python, ai_script,
            "--evidence", usage_json,
            "--metadata", metadata_json,
            "--model", args.model,
            "--output", ai_json,
        ]
        results["ai"] = run_step(step, total_steps, "Running AI analysis...",
                                  ai_cmd, dry_run=args.dry_run)
    else:
        print("\n%s Skipping AI analysis (--skip-ai)." % timestamp())
        results["ai"] = False

    # Step 5: Build capsule
    step += 1
    capsule_script = str(SCRIPTS_DIR / "build_capsule.py")
    capsule_cmd = [
        python, capsule_script,
        "--output", output_dir,
    ]
    if results.get("scan") and os.path.isfile(usage_json):
        capsule_cmd.extend(["--usage", usage_json])
    if results.get("metadata") and os.path.isfile(metadata_json):
        capsule_cmd.extend(["--metadata", metadata_json])
    if results.get("tests") and os.path.isfile(test_json):
        capsule_cmd.extend(["--tests", test_json])
    if results.get("ai") and os.path.isfile(ai_json):
        capsule_cmd.extend(["--ai", ai_json])

    capsule_ok = run_step(step, total_steps, "Building capsule...",
                           capsule_cmd, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 60)
    print("Pipeline Summary")
    print("=" * 60)
    for name, ok in results.items():
        status = "OK" if ok else ("SKIPPED" if args.dry_run else "FAILED/SKIPPED")
        print("  %-12s %s" % (name, status))
        capsule_status = "SKIPPED (dry run)" if args.dry_run else ("OK" if capsule_ok else "FAILED")
    print("  %-12s %s" % ("capsule", capsule_status))
    print("=" * 60)

    if capsule_ok:
        print("\nCapsule written to: %s" % output_dir)
        sys.exit(0)
    elif args.dry_run:
        print("\nDry run complete. No files were created.")
        sys.exit(0)
    else:
        print("\nCapsule generation failed. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
