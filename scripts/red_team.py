#!/usr/bin/env python3
"""Independently audit an AI migration plan against observed usage evidence."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

if __package__:
    from .pipeline_common import query_model, read_json, replacement_name, usages, write_json
else:
    from pipeline_common import query_model, read_json, replacement_name, usages, write_json


SYSTEM_PROMPT = """You are a Senior Principal Security & Systems Auditor.
You are an aggressive code reviewer. Your job is to find hallucinated API methods,
missed breaking changes, and subtle syntax traps in the proposed migration plan.
Verify whether the replacement supports every currently used API, synchronous vs
asynchronous behavior, positional vs keyword arguments, defaults, and return values.
Check that the plan covers EVERY file and line in the observed scan. Flag unsupported
claims and unknown API compatibility as concerns; model knowledge is not execution.
Return {"critique_passed": boolean, "flaws_identified": [{"severity": "HIGH"|"MEDIUM"|"LOW",
"file": string, "issue": string}], "checked_locations": [{"file": string, "line": integer}]}.
Only pass when all locations and all requested checks are covered with no concerns.
"""


def critique(usage: dict, analysis: dict) -> dict:
    try:
        if analysis.get("status") == "ERROR" or not replacement_name(analysis):
            raise ValueError("A migration plan with a proposed replacement is required")
        result = query_model(SYSTEM_PROMPT, {"observed_usage": usage, "ai_recommendations": analysis})
        if type(result.get("critique_passed")) is not bool:
            raise ValueError("critique_passed must be a boolean")
        flaws = result.get("flaws_identified")
        if not isinstance(flaws, list) or not all(
            isinstance(flaw, dict) and flaw.get("severity") in {"HIGH", "MEDIUM", "LOW"}
            and isinstance(flaw.get("file"), str) and isinstance(flaw.get("issue"), str)
            and flaw["issue"].strip() for flaw in flaws
        ):
            raise ValueError("invalid flaws_identified response")
        checked = result.get("checked_locations", [])
        if not isinstance(checked, list) or not all(
            isinstance(item, dict) and isinstance(item.get("file"), str)
            and type(item.get("line")) is int for item in checked
        ):
            raise ValueError("invalid checked_locations response")
        reviewed = {(item["file"], item["line"]) for item in checked}
        for item in usages(usage):
            if (item["file"], item["line"]) not in reviewed:
                flaws.append({"severity": "HIGH", "file": item["file"],
                              "issue": f"Auditor did not confirm review of observed line {item['line']}."})
        if not result["critique_passed"] and not flaws:
            flaws.append({"severity": "HIGH", "file": "", "issue": "Auditor rejected the plan without an explanation."})
        return {"critique_passed": result["critique_passed"] and not flaws,
                "flaws_identified": flaws, "checked_locations": checked,
                "status": "COMPLETED", "model": os.environ.get("CAPSULE_MODEL"),
                "evidence_tag": "AI-CRITIQUE"}
    except (OSError, ValueError) as error:
        return {"critique_passed": False, "flaws_identified": [
            {"severity": "HIGH", "file": "", "issue": f"Critique unavailable: {error}"}],
            "status": "ERROR", "evidence_tag": "AI-CRITIQUE"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage", type=Path, default=Path("evidence/usage.json"))
    parser.add_argument("--analysis", type=Path, default=Path("evidence/ai_analysis.json"))
    parser.add_argument("--out", type=Path, default=Path("evidence/red_team_critique.json"))
    args = parser.parse_args()
    write_json(args.out, critique(read_json(args.usage), read_json(args.analysis)))


if __name__ == "__main__":
    main()
