#!/usr/bin/env python3
"""Apply conservative license screening rules, preserving unknowns and sources."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.9/3.10; use the narrow PEP 621 fallback below.
    tomllib = None

if __package__:
    from .pipeline_common import query_model, read_json, replacement_name, write_json
else:
    from pipeline_common import query_model, read_json, replacement_name, write_json


LOOKUP = {
    "httpx": ("BSD-3-Clause", "https://github.com/encode/httpx/blob/master/LICENSE.md"),
    "requests": ("Apache-2.0", "https://github.com/psf/requests/blob/main/LICENSE"),
    "urllib3": ("MIT", "https://github.com/urllib3/urllib3/blob/main/LICENSE.txt"),
    "simplejson": ("MIT", "https://github.com/simplejson/simplejson/blob/master/LICENSE.txt"),
    "pyyaml": ("MIT", "https://github.com/yaml/pyyaml/blob/main/LICENSE"),
    "lodash": ("MIT", "https://github.com/lodash/lodash/blob/main/LICENSE"),
    "axios": ("MIT", "https://github.com/axios/axios/blob/v1.x/LICENSE"),
    "json": ("PSF-2.0", "https://docs.python.org/3/license.html"),
}
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "CC0-1.0", "PSF-2.0"}
WEAK = {"MPL-2.0", "LGPL-2.1", "LGPL-3.0", "LGPL-2.1-only", "LGPL-2.1-or-later",
        "LGPL-3.0-only", "LGPL-3.0-or-later"}
RULE_SOURCES = ["https://www.gnu.org/licenses/gpl-faq.html",
                "https://www.gnu.org/licenses/license-compatibility.en.html",
                "https://www.apache.org/licenses/GPL-compatibility.html"]


def normalize(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "UNKNOWN"
    value = value.strip()
    aliases = {"mit license": "MIT", "apache 2.0": "Apache-2.0", "apache license 2.0": "Apache-2.0",
               "closed source": "Proprietary",
               "closed-source": "Proprietary", "proprietary": "Proprietary", "unlicensed": "Proprietary"}
    known = PERMISSIVE | WEAK
    return next((name for name in known if name.lower() == value.lower()), aliases.get(value.lower(), value))


def identify_text(text: str) -> str:
    spdx = re.search(r"SPDX-License-Identifier:\s*([^\r\n]+)", text)
    if spdx:
        return normalize(spdx.group(1))
    lower = text.lower()
    matches = []
    if "permission is hereby granted, free of charge" in lower and "software" in lower:
        matches.append("MIT")
    if "apache license" in lower and "version 2.0" in lower:
        matches.append("Apache-2.0")
    if "gnu affero general public license" in lower and "version 3" in lower:
        matches.append("AGPL-3.0")
    elif "gnu lesser general public license" in lower:
        matches.append("LGPL-3.0" if "version 3" in lower else "LGPL-2.1" if "version 2.1" in lower else "UNKNOWN")
    elif "gnu general public license" in lower:
        matches.append("GPL-3.0" if "version 3" in lower else "GPL-2.0" if "version 2" in lower else "UNKNOWN")
    if "redistribution and use in source and binary forms" in lower:
        matches.append("BSD-3-Clause" if "neither the name" in lower else "BSD-2-Clause")
    if "proprietary" in lower and not matches:
        matches.append("Proprietary")
    return matches[0] if len(set(matches)) == 1 else "UNKNOWN"


def host_license(repo: Path) -> tuple[str, str]:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        path = repo / name
        if path.is_file():
            license_id = identify_text(path.read_text(encoding="utf-8"))
            if license_id != "UNKNOWN":
                return license_id, name
    package = repo / "package.json"
    if package.is_file():
        value = read_json(package).get("license")
        if isinstance(value, dict):
            value = value.get("type")
        if value:
            return normalize(value), "package.json:license"
    project = repo / "pyproject.toml"
    if project.is_file():
        raw = project.read_text(encoding="utf-8")
        if tomllib:
            value = tomllib.loads(raw).get("project", {}).get("license")
        else:
            # Parse only the project section, never a tool's unrelated license setting.
            section = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", raw)
            field = re.search(r'''(?m)^license\s*=\s*["']([^"']+)["']''', section.group(1)) if section else None
            table = re.search(r"(?m)^license\s*=\s*\{([^}]+)\}", section.group(1)) if section else None
            value = field.group(1) if field else None
            if table:
                match = re.search(r'''(text|file)\s*=\s*["']([^"']+)["']''', table.group(1))
                value = {match.group(1): match.group(2)} if match else None
        if isinstance(value, dict):
            if value.get("file"):
                path = (repo / value["file"]).resolve()
                if path.is_relative_to(repo.resolve()) and path.is_file():
                    return identify_text(path.read_text(encoding="utf-8")), "pyproject.toml:project.license.file"
            value = value.get("text")
        if value:
            license_id = normalize(value)
            if license_id not in PERMISSIVE | WEAK and "\n" in str(value):
                license_id = identify_text(str(value))
            return license_id, "pyproject.toml:project.license"
    return "UNKNOWN", "not detected"


def evaluate(target: str, replacement: str) -> tuple[str, str, str]:
    target, replacement = normalize(target), normalize(replacement)
    strong = bool(re.fullmatch(r"(?:A?GPL)-(?:2\.0|3\.0)(?:-only|-or-later)?", replacement, re.I))
    if strong and target == "Proprietary":
        return "INCOMPATIBLE", "CRITICAL", "Potential copyleft conflict with closed-source distribution; review linking, distribution and network-use obligations."
    if strong and target in PERMISSIVE:
        return "HIGH RISK", "HIGH", "Strong copyleft may require licensing the combined work under copyleft terms; review the intended distribution."
    if target in PERMISSIVE | {"Proprietary"} and replacement in PERMISSIVE:
        return "COMPATIBLE", "LOW", "Permissive replacement; preserve required notices, attribution and applicable patent terms."
    if target in PERMISSIVE and replacement in WEAK:
        return "COMPATIBLE", "LOW", "Conditional compatibility: comply with weak-copyleft source, modification and relinking obligations."
    return "REVIEW_REQUIRED", "UNKNOWN", "Unknown, compound, exception-bearing or unsupported license pairing; no compatibility conclusion."


def check(repo: Path, metadata: dict, analysis: dict, target_override: str = "",
          replacement_override: str = "") -> dict:
    target, host_source = (normalize(target_override), "explicit override") if target_override else host_license(repo)
    name = replacement_name(analysis)
    license_id, source, model_error = "UNKNOWN", "unavailable", None
    if replacement_override:
        license_id, source = normalize(replacement_override), "explicit override"
    elif name.lower() in LOOKUP:
        license_id, url = LOOKUP[name.lower()]
        source = f"bundled lookup (unversioned; verify chosen release): {url}"
    elif name:
        try:
            result = query_model("Identify the SPDX license of the proposed replacement. Return "
                                 "{license: string, source: string}. Return UNKNOWN if uncertain.",
                                 {"replacement": name})
            license_id = normalize(result.get("license"))
            source = "AI-SUGGESTED (unverified): " + str(result.get("source", "no source"))
        except (OSError, ValueError) as error:
            model_error = str(error)
    status, risk, notes = evaluate(target, license_id)
    if source.startswith("AI-SUGGESTED"):
        # A model guess cannot establish observed license compatibility.
        status, risk = "REVIEW_REQUIRED", "UNKNOWN"
        notes = "Verify model-suggested license against the selected release before relying on rules. " + notes
    current = (metadata.get("registry") or {}).get("license") or (metadata.get("local") or {}).get("license") or metadata.get("license")
    return {"target_repo_license": target, "target_license_source": host_source,
            "current_dependency_license": current or "UNKNOWN", "proposed_replacement": name,
            "replacement_license": license_id, "replacement_license_source": source,
            "compatibility_status": status, "risk_level": risk, "notes": notes,
            "lookup_error": model_error, "rule_sources": RULE_SOURCES,
            "evidence": "AI-SUGGESTED_RULE_EVALUATION" if source.startswith("AI-SUGGESTED") else "OBSERVED_RULE_EVALUATION"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--metadata", type=Path, default=Path("evidence/metadata.json"))
    parser.add_argument("--analysis", type=Path, default=Path("evidence/ai_analysis.json"))
    parser.add_argument("--target-license", default="")
    parser.add_argument("--replacement-license", default="")
    parser.add_argument("--out", type=Path, default=Path("evidence/license_risk.json"))
    args = parser.parse_args()
    write_json(args.out, check(args.repo, read_json(args.metadata), read_json(args.analysis),
                               args.target_license, args.replacement_license))


if __name__ == "__main__":
    main()
