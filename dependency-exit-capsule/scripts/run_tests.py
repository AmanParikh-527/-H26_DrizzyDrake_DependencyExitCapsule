#!/usr/bin/env python3
"""
run_tests.py - Run the target repo's test suite and record the results as
EXECUTED evidence. Also compares a baseline run against a post-change run.

Subcommands:
  run      run tests (auto-detects the framework, or use --cmd)
  compare  diff two run results (baseline vs after)

Examples:
  python run_tests.py run --repo ../target --label baseline
  python run_tests.py run --repo ../target --label after --cmd "npm test -- --ci"
  python run_tests.py compare --before out/tests_baseline.json --after out/tests_after.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# --------------------------------------------------------------------------- #
# Framework detection
# --------------------------------------------------------------------------- #
def detect(repo: Path) -> tuple[str | None, str | None]:
    """Return (framework, command), or (None, None) if nothing was found."""
    pkg = repo / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        except json.JSONDecodeError:
            scripts = {}
        test = scripts.get("test", "")
        if test and "no test specified" not in test:
            fw = "jest" if "jest" in test else "mocha" if "mocha" in test else \
                 "vitest" if "vitest" in test else "npm"
            return fw, "npm test"
    py_markers = ["pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "conftest.py"]
    if any((repo / m).exists() for m in py_markers) or (repo / "tests").is_dir() or (repo / "test").is_dir():
        if any(repo.rglob("test_*.py")) or any(repo.rglob("*_test.py")):
            py_bin = sys.executable
            for venv_dir in [".venv", "venv", "env"]:
                cand = repo / venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / ("python.exe" if sys.platform == "win32" else "python")
                if cand.exists():
                    py_bin = str(cand)
                    break
            return "pytest", f'"{py_bin}" -m pytest -q -rfE --no-header -p no:cacheprovider'
    if (repo / "go.mod").exists():
        return "go", "go test ./..."
    if (repo / "Cargo.toml").exists():
        return "cargo", "cargo test"
    if (repo / "pom.xml").exists():
        return "maven", "mvn -q -B test"
    if (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists():
        wrapper = "gradlew.bat" if sys.platform == "win32" else "./gradlew"
        return "gradle", f"{wrapper} test" if (repo / wrapper.lstrip('./')).exists() else "gradle test"
    return None, None


# --------------------------------------------------------------------------- #
# Output parsers - each returns (counts, failed_tests, confidence)
# --------------------------------------------------------------------------- #
def _n(pattern: str, text: str) -> int:
    m = re.findall(pattern, text, flags=re.IGNORECASE)
    return int(m[-1]) if m else 0


def parse(output: str, framework: str | None) -> tuple[dict, list[str], str]:
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    failed: list[str] = []
    conf = "low"

    # pytest: "== 3 failed, 12 passed, 1 skipped in 2.1s =="
    if re.search(r"\d+ (passed|failed)", output) and re.search(r" in [\d.]+s", output):
        counts.update(passed=_n(r"(\d+) passed", output), failed=_n(r"(\d+) failed", output),
                      errors=_n(r"(\d+) errors?", output), skipped=_n(r"(\d+) skipped", output))
        failed = re.findall(r"^(?:FAILED|ERROR) (\S+)", output, flags=re.MULTILINE)
        conf = "high"
    # jest / vitest: "Tests:       3 failed, 12 passed, 15 total"
    elif re.search(r"Tests:\s+.*\d+ total", output):
        line = re.findall(r"Tests:\s+(.*\d+ total)", output)[-1]
        counts.update(passed=_n(r"(\d+) passed", line), failed=_n(r"(\d+) failed", line),
                      skipped=_n(r"(\d+) (?:skipped|todo)", line))
        failed = re.findall(r"●\s+(.+?)\s*$", output, flags=re.MULTILINE)
        conf = "high"
    # mocha: "12 passing", "3 failing", "1 pending"
    elif re.search(r"\d+ passing", output):
        counts.update(passed=_n(r"(\d+) passing", output), failed=_n(r"(\d+) failing", output),
                      skipped=_n(r"(\d+) pending", output))
        failed = re.findall(r"^\s+\d+\) (.+)$", output, flags=re.MULTILINE)
        conf = "high"
    # cargo: "test result: ok. 5 passed; 0 failed; 1 ignored"
    elif "test result:" in output:
        for m in re.finditer(r"test result: \w+\. (\d+) passed; (\d+) failed; (\d+) ignored", output):
            counts["passed"] += int(m.group(1)); counts["failed"] += int(m.group(2))
            counts["skipped"] += int(m.group(3))
        failed = re.findall(r"^test (\S+) \.\.\. FAILED", output, flags=re.MULTILINE)
        conf = "high"
    # maven / gradle surefire: "Tests run: 15, Failures: 2, Errors: 1, Skipped: 0"
    elif "Tests run:" in output:
        m = re.findall(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", output)
        if m:
            run, f, e, s = map(int, m[-1])
            counts.update(passed=run - f - e - s, failed=f, errors=e, skipped=s)
            conf = "medium"
    # go: "--- PASS: TestX", "--- FAIL: TestY", "ok pkg", "FAIL pkg"
    elif framework == "go" or re.search(r"^(ok|FAIL)\s+\S+", output, flags=re.MULTILINE):
        counts.update(passed=len(re.findall(r"--- PASS:", output)),
                      failed=len(re.findall(r"--- FAIL:", output)),
                      skipped=len(re.findall(r"--- SKIP:", output)))
        failed = re.findall(r"--- FAIL: (\S+)", output)
        if counts["passed"] == 0 and counts["failed"] == 0:  # not verbose: count packages
            counts["passed"] = len(re.findall(r"^ok\s+", output, flags=re.MULTILINE))
            counts["failed"] = len(re.findall(r"^FAIL\s+\S+", output, flags=re.MULTILINE))
            conf = "low (package-level counts)"
        else:
            conf = "medium"

    counts["total"] = sum(counts[k] for k in ("passed", "failed", "errors", "skipped"))
    return counts, sorted(set(f.strip() for f in failed))[:200], conf


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def cmd_run(args) -> int:
    repo = Path(args.repo).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"tests_{args.label}.log"
    json_path = out_dir / f"tests_{args.label}.json"

    framework, command = (args.framework, args.cmd) if args.cmd else detect(repo)
    result = {
        "evidence_tag": "EXECUTED",
        "label": args.label,
        "repo": str(repo),
        "framework": framework,
        "command": command,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    if not command:
        result.update(status="not_run", reason="No test framework detected. Pass --cmd explicitly.",
                      exit_code=None, counts=None, failed_tests=[], log_path=None)
        json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[run_tests] {args.label}: NOT RUN - no test framework detected -> {json_path}")
        return 2

    print(f"[run_tests] {args.label}: running `{command}` in {repo} (timeout {args.timeout}s)")
    t0 = time.time()
    try:
        proc = subprocess.run(command, cwd=repo, shell=True, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=args.timeout)
        output = (proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or "")
        exit_code, timed_out = proc.returncode, False
    except subprocess.TimeoutExpired as e:
        def _s(x): return x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")
        output = _s(e.stdout) + "\n--- STDERR ---\n" + _s(e.stderr)
        exit_code, timed_out = None, True
    duration = round(time.time() - t0, 2)
    log_path.write_text(output, encoding="utf-8")

    counts, failed, conf = parse(output, framework)
    if timed_out:
        status = "timeout"
    elif exit_code == 0:
        status = "passed"
    elif counts["failed"] or counts["errors"]:
        status = "failed"
    else:
        status = "error"  # non-zero exit with no failures parsed: likely a crash/setup problem

    result.update(
        status=status, exit_code=exit_code, duration_seconds=duration, counts=counts,
        failed_tests=failed, parse_confidence=conf if counts["total"] else "none",
        log_path=str(log_path), output_tail=output.strip()[-1500:],
    )
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[run_tests] {args.label}: status={status} exit={exit_code} "
          f"passed={counts['passed']} failed={counts['failed']} errors={counts['errors']} "
          f"skipped={counts['skipped']} ({duration}s) -> {json_path}")
    return 0


# --------------------------------------------------------------------------- #
# Compare
# --------------------------------------------------------------------------- #
def cmd_compare(args) -> int:
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    bc, ac = before.get("counts") or {}, after.get("counts") or {}
    bf, af = set(before.get("failed_tests", [])), set(after.get("failed_tests", []))

    delta = {k: (ac.get(k, 0) or 0) - (bc.get(k, 0) or 0)
             for k in ("passed", "failed", "errors", "skipped", "total")}
    newly_failing, fixed = sorted(af - bf), sorted(bf - af)

    if before.get("status") == "not_run" or after.get("status") == "not_run":
        verdict = "inconclusive: at least one run did not execute"
    elif after.get("status") in ("error", "timeout"):
        verdict = f"regression: post-change run {after.get('status')}"
    elif newly_failing or delta["failed"] > 0 or delta["errors"] > 0:
        verdict = "regression: new failures after change"
    elif delta["total"] < 0:
        verdict = "suspicious: fewer tests ran after change"
    else:
        verdict = "no regression detected"

    result = {
        "evidence_tag": "EXECUTED",
        "note": "Derived by diffing two executed test runs.",
        "before": {"label": before.get("label"), "status": before.get("status"), "counts": bc},
        "after": {"label": after.get("label"), "status": after.get("status"), "counts": ac},
        "delta": delta,
        "newly_failing": newly_failing,
        "fixed": fixed,
        "still_failing": sorted(af & bf),
        "verdict": verdict,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[run_tests] compare: {verdict} | delta={delta} | newly_failing={len(newly_failing)} "
          f"fixed={len(fixed)} -> {out}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)

    r = sub.add_parser("run", help="run the test suite")
    r.add_argument("--repo", required=True)
    r.add_argument("--label", default="baseline", help="baseline | after | anything")
    r.add_argument("--cmd", help="override the auto-detected test command")
    r.add_argument("--framework", help="parser hint when using --cmd (pytest, jest, go, ...)")
    r.add_argument("--out-dir", default="out")
    r.add_argument("--timeout", type=int, default=900)

    c = sub.add_parser("compare", help="compare two runs")
    c.add_argument("--before", required=True)
    c.add_argument("--after", required=True)
    c.add_argument("--out", default="out/tests_compare.json")

    args = p.parse_args()
    sys.exit(cmd_run(args) if args.action == "run" else cmd_compare(args))


if __name__ == "__main__":
    main()
