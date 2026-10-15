#!/usr/bin/env python3
"""Statically scan a repository for Python, JavaScript, and config usages."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
JS_EXTENSIONS = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
CONFIG_NAMES = {
    "Dockerfile",
    "Pipfile",
    "package.json",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    "tox.ini",
}


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and not any(part in SKIP_DIRS for part in path.parts):
            yield path


def scan_python(module: str, lines: List[str]) -> Optional[List[Tuple[int, str, str]]]:
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:
        return None

    aliases: Set[str] = set()
    hits: List[Tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == module or item.name.startswith(f"{module}."):
                    alias = item.asname or item.name.split(".", maxsplit=1)[0]
                    aliases.add(alias)
                    hits.append((node.lineno, "import", item.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == module or node.module.startswith(f"{module}."):
                for item in node.names:
                    aliases.add(item.asname or item.name)
                hits.append((node.lineno, "import", f"from {node.module}"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id in aliases
        ):
            hits.append((node.lineno, "call", f"{function.value.id}.{function.attr}"))
        elif isinstance(function, ast.Name) and function.id in aliases:
            hits.append((node.lineno, "call", function.id))
    return hits


def scan_text(
    dependency: str, lines: List[str], javascript: bool = False
) -> List[Tuple[int, str, str]]:
    escaped = re.escape(dependency)
    patterns = [re.compile(rf"\b(import|from)\s+{escaped}\b")]
    if javascript:
        patterns.extend(
            [
                re.compile(rf"""require\(\s*['"]{escaped}(?:/[^'"]*)?['"]\s*\)"""),
                re.compile(rf"""from\s+['"]{escaped}(?:/[^'"]*)?['"]"""),
            ]
        )
    return [
        (line_number, "import", line.strip())
        for line_number, line in enumerate(lines, start=1)
        if any(pattern.search(line) for pattern in patterns)
    ]


def scan_config(dependency: str, lines: List[str]) -> List[Tuple[int, str, str]]:
    pattern = re.compile(rf"(?<![\w-]){re.escape(dependency)}(?![\w-])", re.IGNORECASE)
    return [
        (line_number, "config", line.strip())
        for line_number, line in enumerate(lines, start=1)
        if pattern.search(line)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--dep", required=True)
    parser.add_argument("--import-name")
    parser.add_argument("--out", default="evidence/usage.json", type=Path)
    args = parser.parse_args()

    root = args.repo.resolve()
    if not root.is_dir():
        parser.error(f"--repo must be an existing directory: {args.repo}")
    module = args.import_name or args.dep.replace("-", "_")
    usages: List[dict[str, object]] = []
    scanned = 0
    limitations: list[str] = []
    for path in iter_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            limitations.append(f"{path.relative_to(root)}: unreadable file")
            continue

        relative = str(path.relative_to(root))
        if path.suffix == ".py":
            scanned += 1
            hits = scan_python(module, lines)
            if hits is None:
                limitations.append(f"{relative}: syntax error, fell back to regex")
                hits = scan_text(module, lines)
        elif path.suffix in JS_EXTENSIONS:
            scanned += 1
            hits = scan_text(args.dep, lines, javascript=True)
        elif path.name in CONFIG_NAMES:
            scanned += 1
            hits = scan_config(args.dep, lines)
        else:
            continue

        for line_number, kind, symbol in hits:
            usages.append(
                {
                    "file": relative,
                    "line": line_number,
                    "kind": kind,
                    "snippet": lines[line_number - 1].strip()[:200],
                    "symbol": symbol,
                    "evidence": "OBSERVED",
                }
            )

    limitations.extend(
        [
            "Dynamic imports, eval, and runtime-generated module names are not detected",
            "Re-exports and wrapper modules are not traced",
            "Only Python, JavaScript/TypeScript, and named config files are scanned",
        ]
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "dependency": args.dep,
        "scan": {
            "files_scanned": scanned,
            "usage_count": len(usages),
            "usages": sorted(usages, key=lambda item: (str(item["file"]), int(item["line"]))),
            "limitations": limitations,
        },
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Found {len(usages)} usages in {scanned} files -> {args.out}")


if __name__ == "__main__":
    main()
