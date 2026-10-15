#!/usr/bin/env python3
"""Try one model-proposed line in a disposable repository copy, then run tests."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:
    from .pipeline_common import query_model, read_json, replacement_name, usages, write_json
    from .scan_usage import SKIP_DIRS
else:
    from pipeline_common import query_model, read_json, replacement_name, usages, write_json
    from scan_usage import SKIP_DIRS


def target_path(repo: Path, filename: str) -> Path:
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("usage path must be relative and inside the target repository")
    path = repo / relative
    if any((repo / Path(*relative.parts[:index])).is_symlink()
           for index in range(1, len(relative.parts) + 1)):
        raise ValueError("symlinked trial targets are not supported")
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError("trial target escapes the repository")
    if not path.is_file():
        raise ValueError("trial target is not a file")
    return path


def select_usage(repo: Path, usage: dict) -> dict:
    """Rank real source lines by AST complexity, file length, then stable location."""
    candidates = []
    for item in usages(usage):
        if item.get("kind") not in {"import", "call"}:
            continue
        try:
            path = target_path(repo, item["file"])
            if path.suffix not in {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            line = item["line"]
            if type(line) is not int or not 1 <= line <= len(lines):
                continue
            # The scan truncates snippets to 200 characters. Reject stale evidence.
            if lines[line - 1].strip()[:200] != item.get("snippet"):
                continue
            try:
                complexity = sum(1 for _ in ast.walk(ast.parse(lines[line - 1].strip())))
            except SyntaxError:
                complexity = len(lines[line - 1]) + 100
            candidates.append(((complexity, len(lines), item["file"], line), item))
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
            continue
    if not candidates:
        raise ValueError("No safe, current single-line source usage found")
    return min(candidates, key=lambda entry: entry[0])[1]


def discover_tests(repo: Path) -> list[str]:
    package = repo / "package.json"
    if package.exists():
        data = read_json(package)
        if data.get("scripts", {}).get("test"):
            return ["npm", "test"]
    tests_dir = repo / "tests"
    has_tests = any(repo.glob("test_*.py")) or (
        tests_dir.is_dir() and any(tests_dir.rglob("test*.py"))
    )
    if not has_tests:
        raise ValueError("No test suite detected; supply --test-command")
    if importlib.util.find_spec("pytest") is not None:
        return [sys.executable, "-m", "pytest", "-q"]
    return [sys.executable, "-m", "unittest", "discover", "-s", "tests" if tests_dir.is_dir() else "."]


def execute_tests(command: list[str], cwd: Path, timeout: float) -> dict:
    """Bound the wait and captured report; terminate the whole test process group."""
    if timeout <= 0:
        raise ValueError("test timeout must be positive")
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CI=os.environ.get("CI", "1"))
    environment.pop("PYTHONPATH", None)
    # Test processes do not need model credentials.
    for key in list(environment):
        if key.startswith("CAPSULE_"):
            environment.pop(key)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr,
                                   env=environment, start_new_session=True)
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        captures = []
        truncated = False
        for stream in (stdout, stderr):
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - 12000))
            captures.append(stream.read().decode("utf-8", errors="replace"))
            truncated = truncated or size > 12000
    combined = "\n".join(captures).strip()
    empty_suite = "Ran 0 tests" in combined or "no tests ran" in combined.lower()
    return {"status": "TIMED_OUT" if timed_out else "NO_TESTS" if empty_suite else
            "PASSED" if process.returncode == 0 else "FAILED",
            "returncode": process.returncode, "stdout": captures[0], "stderr": captures[1],
            "stdout_stderr_summary": combined, "output_truncated": truncated}


def trial(repo: Path, usage: dict, analysis: dict, command: list[str] | None = None,
          timeout: float = 120) -> dict:
    result = {"target_file": None, "line_number": None, "original_code": None,
              "patched_code": None, "test_execution_status": "SKIPPED",
              "outcome": "INCONCLUSIVE", "stdout_stderr_summary": "",
              "evidence": "NOT_EXECUTED", "source_unchanged": True,
              "isolation": "disposable repository copy (not an OS security sandbox)"}
    try:
        repo = repo.resolve()
        replacement = replacement_name(analysis)
        if not replacement or analysis.get("status") == "ERROR":
            raise ValueError("A proposed replacement is required")
        selected = select_usage(repo, usage)
        source = target_path(repo, selected["file"])
        original = source.read_bytes()
        lines = original.decode("utf-8").splitlines(keepends=True)
        index = selected["line"] - 1
        old_line = lines[index].rstrip("\r\n")
        result.update(target_file=selected["file"], line_number=index + 1, original_code=old_line)
        command = command or discover_tests(repo)
        if not command:
            raise ValueError("test command cannot be empty")
        if any(str(repo) in argument for argument in command[1:]):
            raise ValueError("Use relative test paths so the command runs against the disposable copy")
        proposed = query_model(
            "You are a migration patch engineer. Replace ONLY the supplied source line to use the "
            "replacement library. Preserve indentation and semantics. No new lines, fences or other edits. "
            "If a correct single-line migration is impossible, return {\"patched_code\": null}. "
            "Otherwise return {\"patched_code\": string}.",
            {"file": selected["file"], "line_number": index + 1, "original_code": old_line,
             "context": "".join(lines[max(0, index - 10):index + 11]),
             "replacement": replacement, "migration_plan": analysis},
        ).get("patched_code")
        if not isinstance(proposed, str) or not proposed.strip() or any(c in proposed for c in "\r\n\x00"):
            raise ValueError("Model did not return a single nonempty replacement line")
        if proposed == old_line:
            raise ValueError("Model returned an unchanged line")
        result["patched_code"] = proposed
        newline = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
        lines[index] = proposed + newline
        patched = "".join(lines).encode("utf-8")
        if source.suffix == ".py":
            ast.parse(patched)  # Syntax traps are rejected before execution.

        def ignore(directory, names):
            return [name for name in names if name in SKIP_DIRS or (Path(directory) / name).is_symlink()]

        with tempfile.TemporaryDirectory(prefix="capsule-trial-") as directory:
            copy = Path(directory) / "repo"
            shutil.copytree(repo, copy, ignore=ignore)
            target = target_path(copy, selected["file"])
            if target.read_bytes() != original:
                raise ValueError("Source changed while preparing trial")
            backup = Path(directory) / "original-file.bak"
            backup.write_bytes(original)
            result["test_command"] = command
            baseline = execute_tests(command, copy, timeout)
            result["baseline"] = baseline
            result["evidence"] = "EXECUTED_BASELINE_ONLY"
            if baseline["status"] != "PASSED":
                result.update(test_execution_status="BASELINE_FAILED",
                              stdout_stderr_summary=baseline["stdout_stderr_summary"],
                              evidence="EXECUTED_BASELINE_ONLY")
                return result
            try:
                target.write_bytes(patched)
                execution = execute_tests(command, copy, timeout)
                result.update(test_execution_status=execution["status"], execution=execution,
                              stdout_stderr_summary=execution["stdout_stderr_summary"],
                              outcome="VERIFIED_WORKING" if execution["status"] == "PASSED" else
                              "COMPATIBILITY_BREAKAGE" if execution["status"] == "FAILED" else "INCONCLUSIVE",
                              evidence="EXECUTED_AND_VERIFIED" if execution["status"] == "PASSED" else "EXECUTED")
            finally:
                # Restore the trial file even if tests fail, timeout or are interrupted.
                if target.is_symlink():
                    target.unlink()
                if target.is_dir():
                    shutil.rmtree(target)
                target.write_bytes(backup.read_bytes())
        return result
    except (OSError, ValueError, SyntaxError) as error:
        result.update(test_execution_status="ERROR", error=str(error))
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--usage", type=Path, default=Path("evidence/usage.json"))
    parser.add_argument("--analysis", type=Path, default=Path("evidence/ai_analysis.json"))
    parser.add_argument("--test-command", help="Explicit command, parsed without a shell; use relative test paths")
    parser.add_argument("--test-timeout", type=float, default=120)
    parser.add_argument("--out", type=Path, default=Path("evidence/trial_patch_result.json"))
    args = parser.parse_args()
    write_json(args.out, trial(args.repo, read_json(args.usage), read_json(args.analysis),
                               shlex.split(args.test_command) if args.test_command else None, args.test_timeout))


if __name__ == "__main__":
    main()
