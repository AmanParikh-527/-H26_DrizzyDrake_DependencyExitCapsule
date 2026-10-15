#!/usr/bin/env python3
"""Produce the initial migration recommendation, independently of the auditor."""

from __future__ import annotations

import argparse
from pathlib import Path

if __package__:
    from .pipeline_common import query_model, read_json, replacement_name, write_json
else:
    from pipeline_common import query_model, read_json, replacement_name, write_json


def analyze(usage: dict, metadata: dict, replacement: str = "") -> dict:
    try:
        result = query_model(
            "You are a dependency migration engineer. Propose a concrete migration plan covering "
            "every observed location, API mapping, signature changes, async behavior and tests. "
            "Return {summary: string, replacement: string, steps: [string], risks: [string]}. "
            "Use the requested replacement when supplied.",
            {"observed_usage": usage, "observed_metadata": metadata, "requested_replacement": replacement},
        )
        if not replacement_name(result) or not isinstance(result.get("steps"), list) or not all(
            isinstance(step, str) for step in result["steps"]
        ):
            raise ValueError("migration response lacks a replacement or steps")
        if replacement and replacement_name(result) != replacement:
            raise ValueError("model did not use the requested replacement")
        result.update(status="COMPLETED", evidence="AI-SUGGESTED")
        return result
    except (OSError, ValueError) as error:
        return {"summary": "Migration analysis unavailable", "replacement": replacement,
                "steps": [], "risks": [str(error)], "status": "ERROR", "evidence": "AI-SUGGESTED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage", type=Path, default=Path("evidence/usage.json"))
    parser.add_argument("--metadata", type=Path, default=Path("evidence/metadata.json"))
    parser.add_argument("--replacement", default="")
    parser.add_argument("--out", type=Path, default=Path("evidence/ai_analysis.json"))
    args = parser.parse_args()
    write_json(args.out, analyze(read_json(args.usage), read_json(args.metadata), args.replacement))


if __name__ == "__main__":
    main()
