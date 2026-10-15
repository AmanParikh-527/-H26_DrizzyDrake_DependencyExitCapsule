# AgentSkill-Hermes

Maintenance evidence pipeline and Agent Skill (`dependency-exit-capsule`) for dependency upgrades, compatibility analysis, and replacements.

## Overview

This project implements an autonomous agent skill following the [agentskills.io](https://agentskills.io) standard to analyze dependencies, scan actual usage across codebases, run test suites, query open-weight LLMs, and produce a fully tagged **Dependency Exit Capsule** (JSON, Markdown, and self-contained interactive HTML).

## Structure

- `dependency-exit-capsule/` - Complete Agent Skill package:
  - `SKILL.md` - Agent skill definition and interface specification.
  - `scripts/scan_usage.py` - AST/grep detector for imports, calls, decorators, and configurations.
  - `scripts/collect_metadata.py` - Manifest and PyPI registry metadata collector.
  - `scripts/risk_indicators.py` - Applies risk rubric rules.
  - `scripts/run_tests.py` - Automated test suite runner with baseline vs. post-upgrade diffing.
  - `scripts/ai_analyze.py` - Open-weight model analyzer with file-grounding validation and network retry.
  - `scripts/build_capsule.py` - Structured capsule assembler (`capsule.json` and `capsule.md`).
  - `scripts/build_report.py` - Offline, self-contained interactive HTML visual report generator (`report.html`).
  - `scripts/run_pipeline.py` - End-to-end orchestrator running all 6 steps.
  - `references/` - Risk rubric, JSON contract, capsule schema, and evidence contract.
  - `examples/` - Verified sample capsules.
  - `tests/` - Comprehensive unit and regression test suite.
- `scripts/` - Root CLI utilities (including `build_report.py`).
- `tests/` - Top-level test runner suite.

## Run End-to-End Pipeline

```bash
# Run all 6 steps end-to-end against a target repository
python dependency-exit-capsule/scripts/run_pipeline.py --repo target/LinkWatch --dependency Jinja2
```

## Generate Visual HTML Report Directly

```bash
python dependency-exit-capsule/scripts/build_report.py --capsule capsule_output/capsule.json --out capsule_output/report.html
```

The report generator accepts both full pipeline capsules and partial capsules, escaping repository content and visually separating `[OBSERVED]`, `[EXECUTED]`, and `[AI-SUGGESTED]` evidence tags. Open `report.html` directly in any browser—no server, CDN, or external packages required.
