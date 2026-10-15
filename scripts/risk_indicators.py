#!/usr/bin/env python3
"""Calculate reproducible dependency risk indicators from evidence JSON files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LEVELS = ("LOW", "MEDIUM", "HIGH")


def major(version: Optional[str]) -> Optional[int]:
    if not version:
        return None
    try:
        return int(version.lstrip("v").split(".", maxsplit=1)[0])
    except ValueError:
        return None


def release_age_days(value: str) -> Optional[int]:
    try:
        release = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if release.tzinfo is None:
        release = release.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - release).days


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usage", default="evidence/usage.json", type=Path)
    parser.add_argument("--metadata", default="evidence/metadata.json", type=Path)
    parser.add_argument("--out", default="evidence/risk.json", type=Path)
    args = parser.parse_args()
    usage = json.loads(args.usage.read_text(encoding="utf-8"))
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    indicators: List[Dict[str, str]] = []

    registry = metadata.get("registry") or {}
    declared = metadata.get("declared") or {}
    last_release = registry.get("last_release")
    if last_release:
        age_days = release_age_days(last_release)
        if age_days is None:
            indicators.append({"name": "metadata-quality", "level": "LOW", "reason": "registry release date is invalid"})
        elif age_days > 1095:
            indicators.append({"name": "staleness", "level": "HIGH", "reason": "last release is more than 3 years old"})
        elif age_days > 365:
            indicators.append({"name": "staleness", "level": "MEDIUM", "reason": "last release is more than 1 year old"})

    if registry.get("yanked_or_deprecated") or registry.get("deprecated_message"):
        indicators.append({"name": "deprecation", "level": "HIGH", "reason": "registry marks the dependency deprecated or inactive"})

    declared_major = major(declared.get("constraint", "").lstrip("=<>~!^* "))
    latest_major = major(registry.get("latest_version"))
    if declared_major is not None and latest_major is not None and declared_major < latest_major:
        indicators.append(
            {
                "name": "version-lag",
                "level": "MEDIUM",
                "reason": f"declared major version {declared_major} is below latest major {latest_major}",
            }
        )

    if not declared.get("pinned"):
        indicators.append({"name": "unpinned", "level": "LOW", "reason": "declared version is a range or is absent"})

    usage_count = usage.get("scan", {}).get("usage_count", 0)
    if usage_count > 20:
        indicators.append({"name": "blast-radius", "level": "HIGH", "reason": f"{usage_count} usages detected"})
    elif usage_count >= 8:
        indicators.append({"name": "blast-radius", "level": "MEDIUM", "reason": f"{usage_count} usages detected"})

    files = {item["file"] for item in usage.get("scan", {}).get("usages", [])}
    if len(files) > 5:
        indicators.append({"name": "spread", "level": "MEDIUM", "reason": f"used in {len(files)} files"})

    for indicator in indicators:
        indicator["evidence"] = "OBSERVED"
    overall = max((item["level"] for item in indicators), key=LEVELS.index, default="LOW")
    result: Dict[str, Any] = {
        "dependency": usage.get("dependency", metadata.get("dependency")),
        "risk": {"overall": overall, "indicators": indicators},
        "evidence": "OBSERVED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Risk ({overall}) -> {args.out}")


if __name__ == "__main__":
    main()
