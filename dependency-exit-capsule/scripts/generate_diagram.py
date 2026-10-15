#!/usr/bin/env python3
"""Turn observed dependency usages into a deterministic Mermaid blast radius."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

if __package__:
    from .pipeline_common import read_json, usages
else:
    from pipeline_common import read_json, usages


def label(value: object) -> str:
    # Mermaid numeric entities prevent labels from introducing nodes/directives.
    return "".join(char if char.isalnum() or char in " /._-:@" else f"#{ord(char)};"
                   for char in str(value).replace("\n", " ").replace("\r", " "))


def dependency_version(metadata: dict) -> str:
    local = metadata.get("local") or {}
    declared = metadata.get("declared") or {}
    constraint = str(declared.get("constraint") or "")
    if constraint.startswith("==") and not constraint.startswith("==="):
        return constraint[2:]
    return str(local.get("installed_version") or constraint or "unknown")


def generate(usage: dict, metadata: dict) -> str:
    groups = defaultdict(list)
    for item in usages(usage):
        groups[str(item["file"])].append(item)
    dependency = usage.get("dependency", metadata.get("dependency", "unknown"))
    lines = ["graph TD", "    classDef highRisk fill:#ffcccc,stroke:#b91c1c,stroke-width:2px;",
             "    classDef lowRisk fill:#fff3b0,stroke:#a16207,stroke-width:1px;",
             f'    DEP["{label(dependency)} v{label(dependency_version(metadata))}"]']
    for index, (filename, items) in enumerate(sorted(groups.items())):
        # No test evidence means untested, never implicitly low risk.
        tested = all(item.get("tested") is True or item.get("test_status") == "PASSED" for item in items)
        high = not tested or any(str(item.get("risk", "")).upper() in {"HIGH", "CRITICAL"} for item in items)
        risk = "highRisk" if high else "lowRisk"
        role = "Direct importer" if any(item.get("kind") == "import" for item in items) else "Observed file (import not traced)"
        lines.append(f'    DEP --> F{index}["{label(role)}: {label(filename)}"]:::{risk}')
        for number, item in enumerate(sorted(items, key=lambda entry: (entry.get("line", 0), str(entry.get("symbol", ""))))):
            symbol = item.get("symbol") or item.get("snippet") or item.get("kind", "usage")
            lines.append(f'    F{index} -->|{label(item.get("kind", "usage"))}| U{index}_{number}'
                         f'["{label(filename)}:{label(item.get("line", "?"))} — {label(symbol)}"]:::{risk}')
    if not groups:
        lines.append('    DEP --> EMPTY["No observed usage locations"]')
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage", type=Path, default=Path("evidence/usage.json"))
    parser.add_argument("--metadata", type=Path, default=Path("evidence/metadata.json"))
    parser.add_argument("--out", type=Path, default=Path("evidence/blast_radius.mmd"))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(generate(read_json(args.usage), read_json(args.metadata)), encoding="utf-8")


if __name__ == "__main__":
    main()
