#!/usr/bin/env python3
"""Assemble observed, AI and execution evidence into Markdown and JSON capsules."""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
from pathlib import Path

if __package__:
    from .pipeline_common import read_json, write_json
    from .generate_diagram import dependency_version
else:
    from pipeline_common import read_json, write_json
    from generate_diagram import dependency_version


def assemble(evidence: Path) -> dict:
    gaps = []

    def load(name: str) -> dict:
        try:
            return read_json(evidence / name)
        except (OSError, ValueError) as error:
            gaps.append(f"{name}: unavailable ({error})")
            return {}

    usage, metadata, risk_data = load("usage.json"), load("metadata.json"), load("risk.json")
    analysis, critique = load("ai_analysis.json"), load("red_team_critique.json")
    trial_result, license_risk = load("trial_patch_result.json"), load("license_risk.json")
    risk = copy.deepcopy(risk_data.get("risk") or {"overall": "UNKNOWN", "indicators": []})
    unresolved = []
    if critique.get("critique_passed") is not True:
        unresolved.append("Independent AI critique did not pass; it is not execution-based verification.")
    for flaw in critique.get("flaws_identified", []):
        unresolved.append(f"[AI-CRITIQUE] {flaw.get('severity', 'UNKNOWN')} {flaw.get('file', '')}: {flaw.get('issue', '')}")
    if trial_result.get("outcome") != "VERIFIED_WORKING":
        unresolved.append(f"Trial patch: {trial_result.get('test_execution_status', 'NOT_RUN')}; "
                          f"{trial_result.get('error') or trial_result.get('reason') or trial_result.get('outcome', 'unavailable')}")
    else:
        gaps.append("Trial success applies only to one changed line and the executed suite; it does not verify the complete migration.")
    status = license_risk.get("compatibility_status", "REVIEW_REQUIRED")
    if status != "COMPATIBLE":
        level = license_risk.get("risk_level", "UNKNOWN")
        risk.setdefault("indicators", []).append({
            "name": "license-compatibility", "level": level,
            "reason": f"{status}: {license_risk.get('notes', 'License assessment unavailable')}",
            "evidence": license_risk.get("evidence", "UNKNOWN"),
        })
        unresolved.append(f"License screening: {status}. {license_risk.get('notes', '')}")
        levels = {"UNKNOWN": -1, "LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        risk["overall"] = max((risk.get("overall", "UNKNOWN"), level), key=lambda value: levels.get(value, -1))
    try:
        diagram = (evidence / "blast_radius.mmd").read_text(encoding="utf-8")
    except OSError:
        diagram = ""
        gaps.append("blast_radius.mmd is unavailable")
    registry = metadata.get("registry") or {}
    if registry.get("error"):
        gaps.append(f"Registry metadata unavailable: {registry['error']}")
    gaps.extend(risk_data.get("limitations", []))
    gaps.extend(analysis.get("risks", []))
    baseline = trial_result.get("baseline", {})
    pipeline = read_json(evidence / "pipeline.json").get("steps", []) if (evidence / "pipeline.json").exists() else []
    # Keep raw command results; do not invent test counts from return codes.
    return {"dependency": usage.get("dependency", metadata.get("dependency", "unknown")),
            "version": dependency_version(metadata), "scan": usage.get("scan", {}),
            "metadata": metadata, "risk": risk, "ai_analysis": analysis,
            "red_team_critique": critique, "trial_patch": trial_result,
            "license_risk": license_risk, "blast_radius_mermaid": diagram,
            "pipeline": pipeline,
            "tests": {"trial_baseline": baseline}, "unresolved": unresolved, "gaps": gaps}


def md(value: object) -> str:
    value = html.escape(str(value)).replace("\n", " ").replace("\r", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", value)


def code_block(value: str, language: str = "json") -> str:
    fence = "`" * max(3, max((len(match[0]) + 1 for match in re.finditer(r"`+", value)), default=3))
    return f"{fence}{language}\n{value.rstrip()}\n{fence}\n"


def render_markdown(data: dict) -> str:
    lines = [f"# Dependency Exit Capsule: {md(data['dependency'])}", "",
             f"Version: {md(data['version'])}. Overall risk: {md(data['risk'].get('overall', 'UNKNOWN'))}.", "",
             "## Pipeline Execution [EXECUTED]", ""]
    for stage in data.get("pipeline", []):
        lines.append(f"- {md(stage.get('name', ''))}: {md(stage.get('status', 'UNKNOWN'))} ({md(stage.get('duration', ''))})")
    if not data.get("pipeline"):
        lines.append("No pipeline execution record supplied.")
    lines += ["", "## Observed Usage [OBSERVED]", "",
             "| File | Line | Kind | Symbol |", "| --- | --- | --- | --- |"]
    for item in data["scan"].get("usages", []):
        lines.append("| " + " | ".join(md(item.get(key, "")) for key in ("file", "line", "kind", "symbol")) + " |")
    lines += ["", "## Visual Blast Radius [OBSERVED]", "",
              "Red marks high-risk or untested files. Yellow requires explicit passing test evidence in the scan. "
              "Static imports do not establish runtime reachability.", "",
              code_block(data.get("blast_radius_mermaid", ""), "mermaid"),
              "## RISK INDICATORS", ""]
    for indicator in data["risk"].get("indicators", []):
        lines.append(f"- [{md(indicator.get('evidence', 'OBSERVED'))}] **{md(indicator.get('level', 'UNKNOWN'))}** "
                     f"{md(indicator.get('name', ''))}: {md(indicator.get('reason', ''))}")
    if not data["risk"].get("indicators"):
        lines.append("No risk indicators recorded; this is not evidence of safety.")
    lines += ["", "## License Screening", "",
              code_block(json.dumps(data["license_risk"], indent=2)),
              "## Migration Plan [AI-SUGGESTED]", "", md(data["ai_analysis"].get("summary", "Unavailable")), "",
              f"Proposed replacement: {md(data['ai_analysis'].get('replacement', 'unknown'))}", ""]
    for step in data["ai_analysis"].get("steps", []):
        lines.append(f"- {md(step)}")
    lines += ["", "## Trial Patch", "", code_block(json.dumps(data["trial_patch"], indent=2)),
              "A passing trial verifies one line against the executed tests only.", "",
              "## UNRESOLVED CONCERNS & CRITIQUE", "",
              "The auditor is an independent model call and produces AI-CRITIQUE evidence.", "",
              code_block(json.dumps(data["red_team_critique"], indent=2))]
    lines.extend(f"- {md(issue)}" for issue in data["unresolved"])
    lines += ["", "## Gaps and Limitations", ""]
    lines.extend(f"- {md(gap)}" for gap in data["gaps"] + data["scan"].get("limitations", []))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence"))
    parser.add_argument("--out", type=Path, default=Path("capsule/exit-capsule.md"))
    parser.add_argument("--json-out", type=Path, default=Path("capsule/capsule.json"))
    args = parser.parse_args()
    capsule = assemble(args.evidence_dir)
    write_json(args.json_out, capsule)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(capsule), encoding="utf-8")
    print(f"Capsule -> {args.out}")


if __name__ == "__main__":
    main()
