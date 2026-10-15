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
                    "file": filename,
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
                    "constraint": value,
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
    request = urllib.request.Request(url, headers={"User-Agent": "AgentSkill-Hermes/1.0"})
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
    parser.add_argument("--dep", required=True)
    parser.add_argument("--ecosystem", choices=("pypi", "npm"), required=True)
    parser.add_argument("--out", default="evidence/metadata.json", type=Path)
    parser.add_argument("--offline", action="store_true", help="Record registry collection as skipped")
    args = parser.parse_args()

    result = {
        "dependency": args.dep,
        "ecosystem": args.ecosystem,
        "declared": declared_version(args.repo, args.dep),
        "local": local_installed(args.dep) if args.ecosystem == "pypi" else None,
        "registry": ({"source": "not-collected", "error": "Registry lookup skipped (--offline)"}
                     if args.offline else pypi_info(args.dep) if args.ecosystem == "pypi" else npm_info(args.dep)),
        "evidence": "OBSERVED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Metadata -> {args.out}")


if __name__ == "__main__":
    main()
