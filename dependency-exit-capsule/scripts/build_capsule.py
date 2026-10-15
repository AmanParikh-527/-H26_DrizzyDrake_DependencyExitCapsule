#!/usr/bin/env python3
"""build_capsule.py - Assembles the Dependency Exit Capsule from intermediate JSON outputs.

Reads usage, metadata, test, and AI analysis JSON files and produces:
  - capsule.json  (machine-readable, every field tagged)
  - capsule.md    (human-readable Markdown report)

All evidence tags: [OBSERVED], [EXECUTED], [AI-SUGGESTED]
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("build_capsule")

CAPSULE_VERSION = "1.0.0"


def load_json(path, label):
    """Load a JSON file, returning None if missing or invalid."""
    if not path or not os.path.isfile(path):
        log.warning("Missing %s file: %s", label, path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read %s: %s", label, exc)
        return None


def tagged(value, tag):
    """Wrap a value with its evidence tag."""
    return {"value": value, "tag": tag}


def build_capsule_json(usage, metadata, tests, ai, repo_url, repo_name):
    """Build the structured capsule JSON."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    obs = 0
    exe = 0
    ais = 0

    # --- Problem Identified ---
    problems = []
    if metadata and metadata.get("version_conflict", {}).get("detected"):
        problems.append(metadata["version_conflict"].get("details", "Version conflict detected"))
    if usage:
        v1 = usage.get("summary", {}).get("v1_usages", 0)
        if v1 > 0:
            problems.append(
                "Code uses %d Pydantic v1 API patterns but pyproject.toml requires v2." % v1
            )
    problem_text = " ".join(problems) if problems else "No critical problems detected."
    obs += 1

    # --- Dependency Details ---
    dep_details = {}
    if metadata:
        dep = metadata.get("dependency", {})
        meta = metadata.get("metadata", {})
        dep_details = {
            "name": dep.get("name", "unknown"),
            "current_version": dep.get("current_version", "unknown"),
            "required_version": dep.get("required_version", "unknown"),
            "latest_version": dep.get("latest_version", "unknown"),
            "license": meta.get("license", "unknown"),
            "last_release_date": meta.get("last_release_date", "unknown"),
            "repository_url": meta.get("repository_url", "unknown"),
            "is_deprecated": meta.get("is_deprecated", False),
        }
        obs += len(dep_details)
    else:
        obs += 1

    # --- Risk Indicators ---
    risks = []
    if metadata:
        risks = metadata.get("risk_indicators", [])
        obs += len(risks)

    # --- Usage Locations ---
    usages = []
    if usage:
        usages = usage.get("usages", [])
        obs += len(usages)

    # --- AI Analysis ---
    ai_section = None
    if ai:
        ai_section = {
            "model_used": ai.get("model_used", "unknown"),
            "problem_summary": ai.get("problem_summary", ""),
            "recommended_approach": ai.get("recommended_approach", ""),
            "migration_steps": ai.get("migration_steps", []),
            "code_changes": ai.get("code_changes", []),
            "estimated_effort": ai.get("estimated_effort", "unknown"),
            "risks": ai.get("risks", []),
            "suggested_tests": ai.get("suggested_tests", []),
        }
        ais += 1 + len(ai_section["migration_steps"]) + len(ai_section["code_changes"]) + len(ai_section["risks"])

    # --- Test Results ---
    test_section = None
    if tests:
        test_section = {
            "framework": tests.get("framework", "pytest"),
            "command": tests.get("command", "unknown"),
            "total": tests.get("total", 0),
            "passed": tests.get("passed", 0),
            "failed": tests.get("failed", 0),
            "errors": tests.get("errors", 0),
            "skipped": tests.get("skipped", 0),
            "raw_output": tests.get("raw_output", "")[:5000],
        }
        exe += 7

    # --- Additional Findings ---
    additional = []
    if usage:
        additional = usage.get("additional_findings", [])
        obs += len(additional)

    # --- Gaps ---
    gaps = []
    if ai_section and not test_section:
        gaps.append(tagged("Test suite was not executed; AI suggestions are unverified.", "[AI-SUGGESTED]"))
        ais += 1
    if usages:
        v1_count = sum(1 for u in usages if u.get("api_version") == "v1")
        if v1_count > 0 and ai_section:
            code_changes = ai_section.get("code_changes", [])
            if len(code_changes) < v1_count:
                gaps.append(tagged(
                    "AI proposed %d code changes but %d v1 usages were found. %d usages lack migration suggestions."
                    % (len(code_changes), v1_count, v1_count - len(code_changes)),
                    "[OBSERVED]"
                ))
                obs += 1

    # --- Unresolved Concerns ---
    concerns = [
        tagged("AI-suggested code changes have not been applied or tested.", "[AI-SUGGESTED]"),
        tagged("Only the primary dependency was analysed in depth; secondary findings need individual capsules for full coverage.", "[OBSERVED]"),
    ]
    ais += 1
    obs += 1

    capsule = {
        "capsule_version": CAPSULE_VERSION,
        "generated_at": now,
        "repository": repo_url or repo_name or "unknown",
        "target_dependency": dep_details.get("name", "unknown"),
        "sections": {
            "problem_identified": tagged(problem_text, "[OBSERVED]"),
            "dependency_details": tagged(dep_details, "[OBSERVED]"),
            "risk_indicators": tagged(risks, "[OBSERVED]"),
            "usage_locations": tagged(usages, "[OBSERVED]"),
            "ai_analysis": tagged(ai_section, "[AI-SUGGESTED]") if ai_section else tagged("AI analysis was not performed.", "[AI-SUGGESTED]"),
            "test_results": tagged(test_section, "[EXECUTED]") if test_section else tagged("Tests were not executed.", "[EXECUTED]"),
            "additional_findings": tagged(additional, "[OBSERVED]"),
            "gaps": gaps,
            "unresolved_concerns": concerns,
        },
        "evidence_summary": {
            "observed_count": obs,
            "executed_count": exe,
            "ai_suggested_count": ais,
        },
    }
    return capsule


def render_markdown(capsule):
    """Render the capsule as a Markdown report."""
    lines = []
    a = lines.append

    sections = capsule["sections"]
    dep = sections["dependency_details"]["value"]
    risks = sections["risk_indicators"]["value"]
    usages = sections["usage_locations"]["value"]
    ai = sections["ai_analysis"]["value"]
    tests = sections["test_results"]["value"]
    additional = sections["additional_findings"]["value"]
    gaps = sections["gaps"]
    concerns = sections["unresolved_concerns"]
    summary = capsule["evidence_summary"]

    a("# Dependency Exit Capsule")
    a("")
    a("| Field | Value |")
    a("|---|---|")
    a("| **Generated** | %s |" % capsule["generated_at"])
    a("| **Repository** | %s |" % capsule["repository"])
    a("| **Target Dependency** | %s |" % capsule["target_dependency"])
    a("| **Capsule Version** | %s |" % capsule["capsule_version"])
    a("")
    a("---")
    a("")

    # 1. Problem Identified
    a("## 1. Problem Identified")
    a("")
    a("`[OBSERVED]`")
    a("")
    a(sections["problem_identified"]["value"])
    a("")

    # 2. Dependency Details
    a("## 2. Dependency Details")
    a("")
    if isinstance(dep, dict) and dep:
        a("| Field | Value | Tag |")
        a("|---|---|---|")
        for key, val in dep.items():
            a("| %s | %s | `[OBSERVED]` |" % (key.replace("_", " ").title(), val))
    else:
        a("Dependency metadata was not collected. `[OBSERVED]`")
    a("")

    # 3. Risk Indicators
    a("## 3. Risk Indicators")
    a("")
    if risks:
        for r in risks:
            a("- **%s** (%s): %s `[OBSERVED]`" % (
                r.get("indicator", "unknown"),
                r.get("severity", "unknown"),
                r.get("evidence", "")
            ))
    else:
        a("No risk indicators recorded. `[OBSERVED]`")
    a("")

    # 4. Usage Locations
    a("## 4. Usage Locations")
    a("")
    if usages:
        a("Found **%d** usages across **%d** files. `[OBSERVED]`" % (
            len(usages),
            len(set(u.get("file", "") for u in usages))
        ))
        a("")
        a("| File | Line | Type | API Version | Snippet |")
        a("|---|---|---|---|---|")
        for u in usages:
            a("| `%s` | %s | %s | %s | `%s` |" % (
                u.get("file", ""),
                u.get("line", ""),
                u.get("type", ""),
                u.get("api_version", ""),
                u.get("snippet", "").replace("|", "\\|")
            ))
    else:
        a("No usages found. `[OBSERVED]`")
    a("")

    # 5. AI-Generated Analysis
    a("## 5. AI-Generated Analysis & Recommendations")
    a("")
    a("> **Note**: This entire section contains AI-generated content.")
    a("> Recommendations have NOT been independently verified unless stated")
    a("> otherwise. `[AI-SUGGESTED]`")
    a("")

    if isinstance(ai, dict):
        a("**Model:** %s" % ai.get("model_used", "unknown"))
        a("")
        a("### Problem Summary")
        a("")
        a(ai.get("problem_summary", "Not available."))
        a("")
        a("### Recommended Approach")
        a("")
        a(ai.get("recommended_approach", "Not available."))
        a("")
        a("### Migration Steps")
        a("")
        for i, step in enumerate(ai.get("migration_steps", []), 1):
            a("%d. %s `[AI-SUGGESTED]`" % (i, step))
        a("")

        changes = ai.get("code_changes", [])
        if changes:
            a("### Proposed Code Changes")
            a("")
            for ch in changes:
                a("**%s** -- %s `[AI-SUGGESTED]`" % (ch.get("file", ""), ch.get("description", "")))
                a("")
                a("```diff")
                for line in ch.get("before", "").splitlines():
                    a("- %s" % line)
                for line in ch.get("after", "").splitlines():
                    a("+ %s" % line)
                a("```")
                a("")

        a("### Estimated Effort")
        a("")
        a(ai.get("estimated_effort", "Unknown") + " `[AI-SUGGESTED]`")
        a("")

        a("### AI-Identified Risks")
        a("")
        for risk in ai.get("risks", []):
            a("- %s `[AI-SUGGESTED]`" % risk)
        a("")

        suggested_tests = ai.get("suggested_tests", [])
        if suggested_tests:
            a("## 6. Suggested Verification Tests")
            a("")
            for t in suggested_tests:
                a("- %s `[AI-SUGGESTED]`" % t)
            a("")
    else:
        a(str(ai))
        a("")

    # 7. Executed Test Results
    a("## 7. Executed Test Results")
    a("")
    if isinstance(tests, dict):
        a("| Metric | Value |")
        a("|---|---|")
        a("| Framework | %s |" % tests.get("framework", "unknown"))
        a("| Command | `%s` |" % tests.get("command", "unknown"))
        a("| Total | %s |" % tests.get("total", 0))
        a("| Passed | %s |" % tests.get("passed", 0))
        a("| Failed | %s |" % tests.get("failed", 0))
        a("| Errors | %s |" % tests.get("errors", 0))
        a("| Skipped | %s |" % tests.get("skipped", 0))
        a("")
        a("`[EXECUTED]`")
        raw = tests.get("raw_output", "")
        if raw:
            a("")
            a("### Raw Output (excerpt)")
            a("")
            a("```")
            a(raw[:3000])
            a("```")
    else:
        a(str(tests) + " `[EXECUTED]`")
    a("")

    # 8. Additional Dependency Issues
    a("## 8. Additional Dependency Issues")
    a("")
    if additional:
        a("| Dependency | Issue | Severity | Recommendation | Tag |")
        a("|---|---|---|---|---|")
        for f in additional:
            a("| %s | %s | %s | %s | `[OBSERVED]` |" % (
                f.get("dependency", ""),
                f.get("issue", ""),
                f.get("severity", ""),
                f.get("recommendation", "")
            ))
    else:
        a("No additional issues recorded. `[OBSERVED]`")
    a("")

    # 9. Gaps
    a("## 9. Compatibility & Maintenance Gaps")
    a("")
    if gaps:
        for g in gaps:
            a("- %s `%s`" % (g["value"], g["tag"]))
    else:
        a("No gaps identified.")
    a("")

    # 10. Unresolved Concerns
    a("## 10. Unresolved Concerns & Limitations")
    a("")
    for c in concerns:
        a("- %s `%s`" % (c["value"], c["tag"]))
    a("")

    # Footer
    a("---")
    a("")
    a("*Generated by dependency-exit-capsule skill v%s*" % CAPSULE_VERSION)
    a("*Evidence summary: %d observed, %d executed, %d AI-suggested*" % (
        summary["observed_count"], summary["executed_count"], summary["ai_suggested_count"]
    ))
    a("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build a Dependency Exit Capsule from intermediate JSON files.")
    parser.add_argument("--usage", required=False, help="Path to usage_report.json")
    parser.add_argument("--metadata", required=False, help="Path to metadata_report.json")
    parser.add_argument("--tests", required=False, help="Path to test_results.json")
    parser.add_argument("--ai", required=False, help="Path to ai_analysis.json")
    parser.add_argument("--output", default="./capsule_output", help="Output directory (default: ./capsule_output)")
    parser.add_argument("--repo-url", default="", help="Repository URL for the capsule header")
    parser.add_argument("--repo-name", default="", help="Repository name for the capsule header")
    args = parser.parse_args()

    usage = load_json(args.usage, "usage report")
    metadata = load_json(args.metadata, "metadata report")
    tests = load_json(args.tests, "test results")
    ai = load_json(args.ai, "AI analysis")

    if not any([usage, metadata, tests, ai]):
        log.error("No input files could be loaded. Cannot build capsule.")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    capsule = build_capsule_json(usage, metadata, tests, ai, args.repo_url, args.repo_name)

    json_path = os.path.join(args.output, "capsule.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(capsule, fh, indent=2, ensure_ascii=False)
    log.info("Wrote %s", json_path)

    md_content = render_markdown(capsule)
    md_path = os.path.join(args.output, "capsule.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md_content)
    log.info("Wrote %s", md_path)

    s = capsule["evidence_summary"]
    print("\nCapsule generated: %d observed facts, %d executed results, %d AI suggestions" % (
        s["observed_count"], s["executed_count"], s["ai_suggested_count"]
    ))
    print("Output: %s" % args.output)


if __name__ == "__main__":
    main()
