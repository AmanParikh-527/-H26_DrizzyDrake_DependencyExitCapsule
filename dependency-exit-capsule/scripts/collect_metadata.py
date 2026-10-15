#!/usr/bin/env python3
"""Collect dependency metadata using local project data and optional registries."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from importlib import metadata as installed_metadata
from pathlib import Path
from typing import Any, Dict, Optional


def declared_version(repo: Path, dependency: str) -> Optional[Dict[str, Any]]:
    for filename in ("requirements.txt", "requirements-dev.txt"):
        path = repo / filename
        if not path.exists():
            continue
        pattern = re.compile(rf"^\s*{re.escape(dependency)}\s*([=<>~!]+)\s*([\w.*+-]+)", re.I)
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line)
            if match:
                constraint = match.group(1) + match.group(2)
                return {
                    "constraint": constraint,
                    "version": match.group(2),
                    "file": filename,
                    "pinned": match.group(1) == "==",
                    "source": "repo-file",
                }

    pyproject = repo / "pyproject.toml"
    if pyproject.exists():
        pattern = re.compile(rf"""['"]{re.escape(dependency)}\s*([=<>~!]+)\s*([\w.*+-]+)['"]""", re.I)
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            match = pattern.search(line)
            if match:
                constraint = match.group(1) + match.group(2)
                return {
                    "constraint": constraint,
                    "version": match.group(2),
                    "file": "pyproject.toml",
                    "pinned": match.group(1) == "==",
                    "source": "repo-file",
                }

    package_json = repo / "package.json"
    if package_json.exists():
        data = json.loads(package_json.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies"):
            value = data.get(section, {}).get(dependency)
            if value is not None:
                return {
                    "constraint": str(value),
                    "version": str(value).lstrip("^~=<>"),
                    "file": "package.json",
                    "pinned": not str(value).startswith(("^", "~", ">", "<", "*")),
                    "source": "repo-file",
                }
    return None


def local_installed(dependency: str) -> Optional[Dict[str, Any]]:
    try:
        metadata = installed_metadata.metadata(dependency)
    except installed_metadata.PackageNotFoundError:
        return None
    return {
        "installed_version": metadata.get("Version"),
        "license": metadata.get("License"),
        "summary": metadata.get("Summary"),
        "source": "local-install",
    }


def fetch_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) dependency-exit-capsule/1.0"}
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.load(response)


def pypi_info(dependency: str) -> Dict[str, Any]:
    try:
        data = fetch_json(f"https://pypi.org/pypi/{dependency}/json")
    except (OSError, urllib.error.URLError, ValueError) as error:
        return {"error": str(error), "source": "pypi-api-failed"}
    releases = data.get("releases", {})
    dates = sorted(
        upload["upload_time"]
        for files in releases.values()
        for upload in files
        if upload.get("upload_time")
    )
    info = data.get("info", {})
    classifiers = " ".join(info.get("classifiers", []))
    return {
        "latest_version": info.get("version"),
        "license": info.get("license"),
        "last_release": dates[-1] if dates else None,
        "first_release": dates[0] if dates else None,
        "yanked_or_deprecated": "Inactive" in classifiers,
        "project_urls": info.get("project_urls") or {},
        "source": "pypi-api",
    }


def npm_info(dependency: str) -> Dict[str, Any]:
    try:
        data = fetch_json(f"https://registry.npmjs.org/{dependency}")
    except (OSError, urllib.error.URLError, ValueError) as error:
        return {"error": str(error), "source": "npm-registry-failed"}
    latest = data.get("dist-tags", {}).get("latest")
    version = data.get("versions", {}).get(latest, {}) if latest else {}
    return {
        "latest_version": latest,
        "license": version.get("license"),
        "last_release": data.get("time", {}).get(latest),
        "deprecated_message": version.get("deprecated"),
        "source": "npm-registry",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--dep", "--dependency", dest="dep", required=True)
    parser.add_argument("--ecosystem", choices=("pypi", "npm"), default="pypi")
    parser.add_argument("--out", "--output", dest="out", default="evidence/metadata.json", type=Path)
    args = parser.parse_args()

    declared = declared_version(args.repo, args.dep)
    local = local_installed(args.dep) if args.ecosystem == "pypi" else None
    registry = pypi_info(args.dep) if args.ecosystem == "pypi" else npm_info(args.dep)

    current_ver = (declared.get("version") if declared else None) or (local.get("installed_version") if local else None) or "unknown"
    req_ver = declared.get("constraint", "unknown") if declared else "unknown"
    latest_ver = registry.get("latest_version", "unknown") if registry else "unknown"

    # Build risk indicators
    risk_indicators = []
    if declared and declared.get("pinned"):
        risk_indicators.append({
            "indicator": "Strict version pinning",
            "severity": "low",
            "evidence": f"Pinned to {declared.get('constraint')} in {declared.get('file')}",
            "tag": "[OBSERVED]"
        })

    last_rel = registry.get("last_release") if registry else None
    if last_rel:
        from datetime import datetime, timezone
        try:
            rel_dt = datetime.fromisoformat(last_rel.replace("Z", "+00:00"))
            if rel_dt.tzinfo is None:
                rel_dt = rel_dt.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - rel_dt).days
            if days > 1095:
                risk_indicators.append({
                    "indicator": "Stale dependency (3+ years without release)",
                    "severity": "high",
                    "evidence": f"Last release was {last_rel} ({days} days ago)",
                    "tag": "[OBSERVED]"
                })
            elif days > 365:
                risk_indicators.append({
                    "indicator": "Outdated release (1+ years without release)",
                    "severity": "medium",
                    "evidence": f"Last release was {last_rel} ({days} days ago)",
                    "tag": "[OBSERVED]"
                })
        except Exception:
            pass

    if registry.get("yanked_or_deprecated") or registry.get("deprecated_message"):
        risk_indicators.append({
            "indicator": "Officially deprecated or inactive",
            "severity": "high",
            "evidence": registry.get("deprecated_message") or "Inactive classifier on PyPI",
            "tag": "[OBSERVED]"
        })

    result = {
        "dependency": {
            "name": args.dep,
            "current_version": current_ver,
            "required_version": req_ver,
            "latest_version": latest_ver,
            "source_files": [declared.get("file")] if declared and declared.get("file") else [],
        },
        "metadata": {
            "license": registry.get("license") or (local.get("license") if local else "unknown") or "unknown",
            "last_release_date": last_rel or "unknown",
            "is_deprecated": bool(registry.get("yanked_or_deprecated") or registry.get("deprecated_message")),
            "repository_url": registry.get("project_urls", {}).get("Source") or registry.get("project_urls", {}).get("Homepage") or "unknown",
            "pypi_url": f"https://pypi.org/project/{args.dep}/" if args.ecosystem == "pypi" else f"https://www.npmjs.com/package/{args.dep}",
            "python_requires": "unknown",
        },
        "risk_indicators": risk_indicators,
        "version_conflict": {
            "detected": False,
            "details": "No manifest conflict detected"
        },
        "declared": declared,
        "local": local,
        "registry": registry,
        "evidence": "OBSERVED",
        "evidence_tag": "OBSERVED",
        "tag": "[OBSERVED]",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Metadata -> {args.out}")


if __name__ == "__main__":
    main()
