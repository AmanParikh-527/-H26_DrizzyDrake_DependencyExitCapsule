#!/usr/bin/env python3
"""Build an offline, self-contained HTML report from a Dependency Exit Capsule."""

from __future__ import annotations

import argparse
import json
import webbrowser
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List

CSS = """
:root{--bg:#fff;--card:#f6f7f9;--text:#1a1d21;--muted:#667085;--line:#e4e7ec;
--obs:#067647;--obs-bg:#dcfae6;--exe:#175cd3;--exe-bg:#d1e9ff;--ai:#b54708;--ai-bg:#fef0c7;
--high:#d92d20;--med:#dc6803;--low:#067647}
@media(prefers-color-scheme:dark){:root{--bg:#101828;--card:#182230;--text:#f2f4f7;--muted:#98a2b3;
--line:#344054;--obs:#75e0a7;--obs-bg:#073b28;--exe:#84caff;--exe-bg:#0b2d57;--ai:#fec84b;--ai-bg:#4a2a05;
--high:#f97066;--med:#fdb022;--low:#75e0a7}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--text)}
main{max-width:1000px;margin:0 auto;padding:24px 16px 64px}h1{margin:0;font-size:26px}
h2{font-size:17px;margin:32px 0 12px}.sub{color:var(--muted);margin:4px 0 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}.card b{display:block;font-size:22px;word-break:break-word}
.card span{color:var(--muted);font-size:13px}.tag{display:inline-block;font:600 11px/1 monospace;padding:4px 7px;
border-radius:5px;letter-spacing:.04em}.OBSERVED{color:var(--obs);background:var(--obs-bg)}
.EXECUTED{color:var(--exe);background:var(--exe-bg)}.AI-SUGGESTED{color:var(--ai);background:var(--ai-bg)}
.AI-CRITIQUE{color:var(--ai);background:var(--ai-bg)}
.lvl{font-weight:700}.HIGH{color:var(--high)}.MEDIUM{color:var(--med)}.LOW{color:var(--low)}
.INCOMPATIBLE{color:var(--high)}.COMPATIBLE{color:var(--low)}.REVIEW_REQUIRED{color:var(--med)}
.VERIFIED_WORKING{color:var(--low)}.COMPATIBILITY_BREAKAGE{color:var(--high)}.INCONCLUSIVE{color:var(--med)}
.PASSED{color:var(--low)}.FAILED{color:var(--high)}.CONCERNS{color:var(--med)}
.steps{display:flex;gap:8px;flex-wrap:wrap}.step{flex:1;min-width:140px;border-left:4px solid var(--obs);
background:var(--card);padding:10px 12px;border-radius:6px;font-size:13px}.bar{display:flex;align-items:center;
gap:8px;margin:5px 0;font:13px monospace}.bar i{display:block;height:14px;background:var(--exe);border-radius:3px}
.bar em{min-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-style:normal}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}th,td{text-align:left;padding:7px 8px;
border-bottom:1px solid var(--line);vertical-align:top}code{font-family:ui-monospace,monospace;font-size:12px}
input{width:100%;padding:9px;margin-bottom:8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--text)}
.notice{border-left:4px solid var(--ai);background:var(--ai-bg);padding:10px 14px;border-radius:6px;margin-bottom:12px}
.split{display:flex;gap:24px;align-items:center;flex-wrap:wrap}ul{margin:6px 0;padding-left:20px}
@media print{input{display:none}}
"""


def text(value: Any) -> str:
    return escape("" if value is None else str(value))


def tag(value: str) -> str:
    safe = text(value)
    return f'<span class="tag {safe}">{safe}</span>'


def list_html(items: Iterable[Any]) -> str:
    values = list(items)
    if not values:
        return "<p class='sub'>None recorded.</p>"
    return "<ul>" + "".join(f"<li>{text(item)}</li>" for item in values) + "</ul>"


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def parameter_table(title: str, values: Dict[str, Any]) -> str:
    """Display feature parameters and scores using the report's existing table styles."""
    if not values:
        return ""
    rows = []

    def append(prefix: str, value: Any) -> None:
        if isinstance(value, dict) and value:
            for key, nested in value.items():
                append(f"{prefix}.{key}" if prefix else str(key), nested)
        else:
            rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, bool)) else value
            rows.append(f"<tr><td>{text(prefix)}</td><td><code>{text(rendered)}</code></td></tr>")

    for key, value in values.items():
        append(str(key), value)
    return (f"<p><b>{text(title)}</b></p><table><tr><th>Parameter</th><th>Value</th></tr>"
            + "".join(rows) + "</table>")


def donut(passed: int, failed: int, skipped: int) -> str:
    total = passed + failed + skipped
    if total == 0:
        return '<p class="sub">No executed test results recorded.</p>'
    circumference = 251.2
    passed_length = passed / total * circumference
    failed_length = failed / total * circumference
    percentage = round(passed / total * 100)
    return (
        f'<svg width="120" height="120" viewBox="0 0 100 100" role="img" '
        f'aria-label="tests {percentage}% passed">'
        f'<circle cx="50" cy="50" r="40" fill="none" stroke="var(--line)" stroke-width="14"/>'
        f'<circle cx="50" cy="50" r="40" fill="none" stroke="var(--low)" stroke-width="14" '
        f'stroke-dasharray="{passed_length} {circumference}" transform="rotate(-90 50 50)"/>'
        f'<circle cx="50" cy="50" r="40" fill="none" stroke="var(--high)" stroke-width="14" '
        f'stroke-dasharray="{failed_length} {circumference}" stroke-dashoffset="{-passed_length}" '
        f'transform="rotate(-90 50 50)"/><text x="50" y="55" text-anchor="middle" '
        f'font-size="16" fill="currentColor">{percentage}%</text></svg>'
    )


def normalize_capsule_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize capsule data from either Member A contract or full pipeline capsule format."""
    if not isinstance(data, dict):
        return {}
    if "sections" in data and isinstance(data["sections"], dict):
        sections = data["sections"]

        dep_details = as_dict(as_dict(sections.get("dependency_details")).get("value"))
        dep_name = data.get("target_dependency") or dep_details.get("name") or data.get("dependency", "")
        version = dep_details.get("current_version") or data.get("version", "")

        usages_val = as_dict(sections.get("usage_locations")).get("value")
        usages = as_list(usages_val) if isinstance(usages_val, list) else []
        scan = {
            "usage_count": len(usages),
            "usages": usages,
            "limitations": as_list(as_dict(sections.get("gaps_and_limitations")).get("value")),
        }

        risk_val = as_dict(sections.get("risk_indicators")).get("value")
        risk_indicators = as_list(risk_val) if isinstance(risk_val, list) else []
        formatted_indicators = []
        high_count, med_count = 0, 0
        for ind in risk_indicators:
            if isinstance(ind, dict):
                lvl = ind.get("severity") or ind.get("level") or "LOW"
                lvl_upper = str(lvl).upper()
                if "HIGH" in lvl_upper:
                    high_count += 1
                elif "MED" in lvl_upper:
                    med_count += 1
                formatted_indicators.append({
                    "name": ind.get("indicator") or ind.get("name") or "",
                    "level": lvl_upper,
                    "reason": ind.get("evidence") or ind.get("reason") or "",
                })
        overall_risk = "HIGH" if high_count > 0 else ("MEDIUM" if med_count > 0 else "LOW")
        risk = {
            "overall": overall_risk,
            "indicators": formatted_indicators,
        }

        test_sec = as_dict(sections.get("test_results") or sections.get("test_suite_status"))
        tests_val = test_sec.get("value") if "value" in test_sec else test_sec
        tests_dict = as_dict(tests_val)
        baseline = as_dict(tests_dict.get("baseline")) if "baseline" in tests_dict else tests_dict
        tests = {"baseline": baseline}

        ai_sec = as_dict(sections.get("ai_analysis"))
        ai_val = ai_sec.get("value") if "value" in ai_sec else ai_sec
        ai_dict = as_dict(ai_val)
        ai_analysis = {
            "summary": ai_dict.get("problem_summary") or ai_dict.get("summary", ""),
            "replacement": ai_dict.get("recommended_approach") or ai_dict.get("replacement", "n/a"),
            "steps": ai_dict.get("migration_steps") or ai_dict.get("steps", []),
            "risks": ai_dict.get("risks") or ai_dict.get("potential_risks", []),
        }

        gaps_val = sections.get("gaps")
        if isinstance(gaps_val, dict):
            gaps_val = gaps_val.get("value", [])
        gaps = as_list(gaps_val)

        unres_val = sections.get("unresolved_concerns") or sections.get("unresolved")
        if isinstance(unres_val, dict):
            unres_val = unres_val.get("value", [])
        unresolved = []
        for u in as_list(unres_val):
            if isinstance(u, dict) and "value" in u:
                unresolved.append(u["value"])
            elif u:
                unresolved.append(str(u))

        # Check for new features in sections or at root
        license_risk = data.get("license_risk") or as_dict(as_dict(sections.get("license_risk")).get("value"))
        trial_patch = data.get("trial_patch") or as_dict(as_dict(sections.get("trial_patch")).get("value"))
        red_team_critique = data.get("red_team_critique") or as_dict(as_dict(sections.get("red_team_critique")).get("value"))
        blast_radius = data.get("blast_radius_mermaid") or sections.get("blast_radius_mermaid")
        if isinstance(blast_radius, dict) and "value" in blast_radius:
            blast_radius = blast_radius["value"]

        pipeline = data.get("pipeline")
        if not pipeline:
            pipeline = [
                {"name": "Scan Usage", "status": "done", "duration": "OBSERVED"},
                {"name": "Collect Metadata", "status": "done", "duration": "OBSERVED"},
                {"name": "Test Suite", "status": "done", "duration": "EXECUTED"},
                {"name": "AI Analysis", "status": "done", "duration": "AI-SUGGESTED"},
            ]
            if trial_patch:
                t_stat = trial_patch.get("outcome") or trial_patch.get("test_execution_status") or "done"
                pipeline.append({"name": "Trial Patch", "status": str(t_stat), "duration": "EXECUTED"})
            if license_risk:
                l_stat = license_risk.get("compatibility_status") or "done"
                pipeline.append({"name": "License Check", "status": str(l_stat), "duration": "OBSERVED"})
            if red_team_critique:
                c_stat = "PASSED" if red_team_critique.get("critique_passed") else "CONCERNS"
                pipeline.append({"name": "Red Team Audit", "status": str(c_stat), "duration": "AI-CRITIQUE"})
            pipeline.append({"name": "Build Capsule", "status": "done", "duration": "TAGGED"})

        normalized = {
            "dependency": dep_name,
            "version": version,
            "scan": scan,
            "risk": risk,
            "tests": tests,
            "ai_analysis": ai_analysis,
            "gaps": gaps,
            "unresolved": unresolved,
            "pipeline": pipeline,
        }
        if license_risk:
            normalized["license_risk"] = license_risk
        if trial_patch:
            normalized["trial_patch"] = trial_patch
        if red_team_critique:
            normalized["red_team_critique"] = red_team_critique
        if blast_radius:
            normalized["blast_radius_mermaid"] = blast_radius
        return normalized

    return data


def build_html(data: Dict[str, Any]) -> str:
    data = normalize_capsule_data(data)
    scan = as_dict(data.get("scan"))
    risk = as_dict(data.get("risk"))
    ai = as_dict(data.get("ai_analysis"))
    tests = as_dict(as_dict(data.get("tests")).get("baseline"))
    usages = [as_dict(item) for item in as_list(scan.get("usages"))]
    by_file = Counter(str(item.get("file", "")) for item in usages).most_common(10)
    largest = max((count for _, count in by_file), default=1)
    overall = str(risk.get("overall", "UNKNOWN"))
    passed = int(tests.get("passed", 0) or 0)
    failed = int(tests.get("failed", 0) or 0)
    skipped = int(tests.get("skipped", 0) or 0)

    # Feature parameters and scores
    license_risk = as_dict(data.get("license_risk"))
    license_parameters = parameter_table("License screening parameters", license_risk)

    trial_patch = as_dict(data.get("trial_patch"))
    trial_parameters = parameter_table("Trial patch parameters", trial_patch)
    trial_baseline = as_dict(as_dict(data.get("tests")).get("trial_baseline"))
    if trial_baseline and not trial_patch.get("baseline"):
        trial_parameters += parameter_table("Trial baseline parameters", trial_baseline)

    critique = as_dict(data.get("red_team_critique"))
    critique_parameters = parameter_table("AI critique parameters", {
        **{key: value for key, value in critique.items() if key != "flaws_identified"},
        "flaws_identified_count": len(as_list(critique.get("flaws_identified"))),
    }) if critique else ""
    flaws = [as_dict(item) for item in as_list(critique.get("flaws_identified"))]
    if flaws:
        critique_parameters += (
            "<table><tr><th>Severity</th><th>File</th><th>Issue</th></tr>"
            + "".join(f"<tr><td>{text(item.get('severity', ''))}</td>"
                      f"<td>{text(item.get('file', ''))}</td><td>{text(item.get('issue', ''))}</td></tr>"
                      for item in flaws) + "</table>"
        )

    diagram = data.get("blast_radius_mermaid")
    diagram_parameters = parameter_table("Blast radius parameters", {
        "diagram_available": bool(diagram),
        "format": "Mermaid graph TD" if diagram else "Not recorded",
        "usage_files": len({item.get("file") for item in usages}),
        "called_symbols": len({str(item.get("symbol")) for item in usages
                               if item.get("kind") == "call" and item.get("symbol")}),
    }) if "blast_radius_mermaid" in data else ""

    # Feature cards for scores
    extra_cards = []
    if license_risk and license_risk.get("compatibility_status"):
        l_stat = str(license_risk.get("compatibility_status"))
        extra_cards.append(f'<div class="card"><b class="lvl {text(l_stat)}">{text(l_stat)}</b><span>license {tag("OBSERVED")}</span></div>')
    if trial_patch and trial_patch.get("outcome"):
        t_stat = str(trial_patch.get("outcome"))
        extra_cards.append(f'<div class="card"><b class="lvl {text(t_stat)}">{text(t_stat)}</b><span>trial patch {tag("EXECUTED")}</span></div>')
    if critique and "critique_passed" in critique:
        c_stat = "PASSED" if critique.get("critique_passed") else "CONCERNS"
        extra_cards.append(f'<div class="card"><b class="lvl {text(c_stat)}">{text(c_stat)}</b><span>auditor critique {tag("AI-CRITIQUE")}</span></div>')

    # Pipeline steps
    pipeline_steps = as_list(data.get("pipeline"))
    if not pipeline_steps and any((license_risk, trial_patch, critique)):
        pipeline_steps = [
            {"name": "Scan Usage", "status": "done", "duration": "OBSERVED"},
            {"name": "Collect Metadata", "status": "done", "duration": "OBSERVED"},
            {"name": "Test Suite", "status": "done", "duration": "EXECUTED"},
            {"name": "AI Analysis", "status": "done", "duration": "AI-SUGGESTED"},
        ]
        if trial_patch:
            pipeline_steps.append({"name": "Trial Patch", "status": str(trial_patch.get("outcome", "done")), "duration": "EXECUTED"})
        if license_risk:
            pipeline_steps.append({"name": "License Check", "status": str(license_risk.get("compatibility_status", "done")), "duration": "OBSERVED"})
        if critique:
            pipeline_steps.append({"name": "Red Team Audit", "status": "PASSED" if critique.get("critique_passed") else "CONCERNS", "duration": "AI-CRITIQUE"})
        pipeline_steps.append({"name": "Build Capsule", "status": "done", "duration": "TAGGED"})

    steps = "".join(
        f'<div class="step"><b>{text(as_dict(step).get("name", ""))}</b><br>'
        f'{text(as_dict(step).get("status", "done"))} · {text(as_dict(step).get("duration", ""))}</div>'
        for step in pipeline_steps
    )
    bars = "".join(
        f'<div class="bar"><em title="{text(filename)}">{text(filename)}</em>'
        f'<i style="width:{count / largest * 300:.1f}px"></i>{count}</div>'
        for filename, count in by_file
    ) or '<p class="sub">No usage hotspots recorded.</p>'
    rows = "".join(
        f'<tr data-q="{text((str(item.get("file", "")) + str(item.get("snippet", ""))).lower())}">'
        f'<td><code>{text(item.get("file", ""))}</code></td><td>{text(item.get("line", ""))}</td>'
        f'<td>{text(item.get("kind", ""))}</td><td><code>{text(item.get("snippet", ""))}</code></td></tr>'
        for item in usages
    ) or '<tr><td colspan="4" class="sub">No usage locations recorded.</td></tr>'
    indicators = "".join(
        f'<tr><td>{text(item.get("name", ""))}</td><td class="lvl {text(item.get("level", ""))}">'
        f'{text(item.get("level", ""))}</td><td>{text(item.get("reason", ""))}</td></tr>'
        for item in (as_dict(item) for item in as_list(risk.get("indicators")))
    ) or '<tr><td colspan="3" class="sub">No risk indicators recorded.</td></tr>'
    gaps = as_list(data.get("gaps")) + as_list(scan.get("limitations"))
    dependency = text(data.get("dependency", scan.get("dependency", "")))
    version = text(data.get("version", ""))

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dependency Exit Capsule: {dependency}</title><style>{CSS}</style></head><body><main>
<h1>Dependency Exit Capsule: {dependency} {version}</h1>
<p class="sub">Overall risk: <span class="lvl {text(overall)}">{text(overall)}</span> · Evidence legend:
{tag("OBSERVED")} {tag("EXECUTED")} {tag("AI-SUGGESTED")} {tag("AI-CRITIQUE")}</p>
<div class="grid"><div class="card"><b>{text(scan.get("usage_count", len(usages)))}</b><span>usages {tag("OBSERVED")}</span></div>
<div class="card"><b>{len({item.get("file") for item in usages})}</b><span>files affected {tag("OBSERVED")}</span></div>
<div class="card"><b>{passed}/{passed + failed}</b><span>tests passed {tag("EXECUTED")}</span></div>
<div class="card"><b class="lvl {text(overall)}">{text(overall)}</b><span>risk {tag("OBSERVED")}</span></div>
{"".join(extra_cards)}</div>
<h2>Pipeline</h2><div class="steps">{steps or '<p class="sub">No pipeline steps recorded.</p>'}</div>
<h2>Risk indicators {tag("OBSERVED")}</h2><table><tr><th>Indicator</th><th>Level</th><th>Reason</th></tr>{indicators}</table>
{license_parameters}
<h2>Usage hotspots {tag("OBSERVED")}</h2>{bars}
{diagram_parameters}
<h2>Test results {tag("EXECUTED")}</h2><div class="split">{donut(passed, failed, skipped)}
<div>{text(tests.get("command", ""))}<br>Passed: {passed} · Failed: {failed} · Skipped: {skipped}</div></div>
{trial_parameters}
<h2>All usage locations {tag("OBSERVED")}</h2><input id="q" placeholder="Filter by file or code…" aria-label="Filter usages">
<table id="t"><tr><th>File</th><th>Line</th><th>Kind</th><th>Snippet</th></tr>{rows}</table>
<h2>AI analysis {tag("AI-SUGGESTED")}</h2><div class="notice">Generated by an open-weight model.
Not verified by execution unless stated in the test section.</div><p>{text(ai.get("summary", ""))}</p>
<p><b>Suggested replacement:</b> {text(ai.get("replacement", "n/a"))}</p><b>Migration steps</b>{list_html(ai.get("steps", []))}
<b>Model-identified risks</b>{list_html(ai.get("risks", []))}
<h2>Gaps and limitations</h2>{list_html(gaps)}<h2>Unresolved concerns</h2>{list_html(data.get("unresolved", []))}
{critique_parameters}
</main><script>document.getElementById('q').oninput=function(){{var v=this.value.toLowerCase();
document.querySelectorAll('#t tr[data-q]').forEach(function(r){{r.style.display=r.dataset.q.includes(v)?'':'none'}})}};</script>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsule", default="capsule/capsule.json", type=Path)
    parser.add_argument("--out", default="capsule/report.html", type=Path)
    parser.add_argument("--open", action="store_true", dest="open_report")
    args = parser.parse_args()
    try:
        data = json.loads(args.capsule.read_text(encoding="utf-8"))
    except FileNotFoundError:
        parser.error(f"capsule file does not exist: {args.capsule}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        parser.error(f"cannot read capsule {args.capsule}: {error}")
    if not isinstance(data, dict):
        parser.error("capsule root must be a JSON object")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_html(data), encoding="utf-8")
    print(f"Visual report written to {args.out}")
    if args.open_report:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
