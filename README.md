# AgentSkill-Hermes

Maintenance evidence pipeline for dependency upgrades and replacements.

## Structure

- `scripts/scan_usage.py` detects Python, JavaScript/TypeScript, and common
  configuration usages.
- `scripts/collect_metadata.py` records declared, locally installed, and
  registry metadata while preserving source and network failures.
- `scripts/risk_indicators.py` applies the rules in
  [`references/risk-rubric.md`](references/risk-rubric.md).
- `evidence/` contains JSON contracts and the current repository baseline.
- [`docs/problem-selection.md`](docs/problem-selection.md) explains how to
  select a real candidate dependency.

## Run against a target repository

```bash
python scripts/scan_usage.py --repo /path/to/repo --dep requests
python scripts/collect_metadata.py --repo /path/to/repo --dep requests --ecosystem pypi
python scripts/risk_indicators.py
```

Use `--import-name` when a package name differs from its import name, for
example `--dep pyyaml --import-name yaml`. The tools are offline-capable for
scanning; registry metadata failures are recorded in the output rather than
hidden.
