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
- `scripts/` - Root CLI utilities:
  - `scan_usage.py` - AST/grep detector for imports and usages.
  - `collect_metadata.py` - Manifest and registry metadata collector.
  - `risk_indicators.py` - Applies risk rubric rules.
  - `analyze_migration.py` - Generates initial migration recommendations.
  - `red_team.py` - Independently audits migration plans against observed usage.
  - `trial_patch.py` - Tries model-proposed lines in a temporary copy and runs tests.
  - `generate_diagram.py` - Creates Mermaid blast radius diagrams.
  - `license_check.py` - Applies conservative license screening rules.
  - `build_capsule.py` - Markdown and JSON capsule assembler.
  - `build_report.py` - Self-contained HTML report generator.
  - `run_all.py` - Multi-stage pipeline runner.
- `tests/` - Top-level test runner suite (including `test_report.py` and `test_validation.py`).
- `evidence/` - JSON contracts and repository baseline fixtures.
- `docs/problem-selection.md` - Explains how to select a real candidate dependency.

## Run End-to-End Pipeline

```bash
# Run all 6 steps end-to-end against a target repository
python dependency-exit-capsule/scripts/run_pipeline.py --repo target/LinkWatch --dependency Jinja2
```

## Run Individual Scripts Against Target Repository

```bash
python scripts/scan_usage.py --repo target/LinkWatch --dependency Jinja2
python scripts/collect_metadata.py --repo target/LinkWatch --dependency Jinja2 --ecosystem pypi
python scripts/risk_indicators.py
python scripts/build_report.py --capsule capsule_output/capsule.json --out capsule_output/report.html
```

Use `--import-name` when a package name differs from its import name, for
example `--dep pyyaml --import-name yaml`. The tools are offline-capable for
scanning; registry metadata failures are recorded in the output rather than
hidden.

## Visual HTML Report

The report generator accepts both full pipeline capsules and partial capsules, escaping repository content and visually separating `[OBSERVED]`, `[EXECUTED]`, and `[AI-SUGGESTED]` evidence tags. Open `report.html` locally after generation; no server, CDN, or extra package is required.

## Complete Validation Pipeline

Python 3.9+ is required; the pipeline itself uses only the standard library.
Configure a local OpenAI-compatible chat endpoint (for example, a local server
with its model already loaded):

```bash
export CAPSULE_MODEL=your-local-model
export CAPSULE_API_BASE=http://127.0.0.1:11434/v1
# Set CAPSULE_API_KEY only if the endpoint requires authentication.
# CAPSULE_TIMEOUT controls each model request's timeout (default: 120 seconds).

python scripts/run_all.py \
  --repo /path/to/repo --dep requests --ecosystem pypi \
  --replacement httpx \
  --test-command 'python -m pytest -q' --test-timeout 120
```

Outputs are `capsule/exit-capsule.md`, `capsule/capsule.json`, and
`capsule/report.html`. Use `--evidence-dir` and `--capsule-dir` to choose other
directories. The Markdown embeds the Mermaid diagram; the self-contained HTML
includes its source without requiring an online renderer.

Each validation stage can also run independently:

```bash
python scripts/red_team.py
python scripts/trial_patch.py --repo /path/to/repo --test-command 'python -m pytest -q'
python scripts/generate_diagram.py
python scripts/license_check.py --repo /path/to/repo
python scripts/build_capsule.py
python scripts/build_report.py
```

## Tests

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s dependency-exit-capsule/tests -v
```
