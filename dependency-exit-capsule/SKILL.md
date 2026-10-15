---
name: dependency-exit-capsule
description: >
  Analyses a Python repository for dependency version conflicts, API
  incompatibilities, and migration needs. Scans actual code for usage patterns,
  collects package metadata, runs the test suite, uses an open-weight AI model
  for migration analysis, and generates a tagged Dependency Exit Capsule that
  clearly separates observed facts from AI recommendations.
version: 1.0.0
license: MIT
tags:
  - maintenance
  - dependency-management
  - migration
  - python
compatibility:
  - any
---

# Dependency Exit Capsule

## Overview

The **Dependency Exit Capsule** skill performs end-to-end dependency maintenance
analysis on a Python repository. Given a target dependency name and a local
clone, it:

1. **Scans** every source file for imports, calls, decorators, and configuration
   that reference the dependency -- recording file paths, line numbers, code
   snippets, and API-version markers.
2. **Collects metadata** from the project manifest files and from PyPI --
   version pins, latest releases, license, deprecation status.
3. **Runs the existing test suite** and captures pass/fail/error counts together
   with raw output.
4. **Sends the evidence** to an open-weight AI model (default:
   `qwen2.5-coder:7b` via Ollama) which returns a structured migration plan,
   code-change suggestions, effort estimate, and risk assessment.
5. **Assembles a Dependency Exit Capsule** -- a portable JSON + Markdown report
   where every statement is tagged `[OBSERVED]`, `[EXECUTED]`, or
   `[AI-SUGGESTED]` so a reader can always tell what was verified and what was
   inferred.

The skill also surfaces additional dependency issues (deprecated libraries,
unmaintained packages, unnecessary shims) as secondary findings.

## When to Use

Activate this skill when any of the following conditions apply:

- A dependency version pin **conflicts** between manifest files (e.g.
  `requirements.txt` says v1 but `pyproject.toml` says v2).
- Code uses a **deprecated API** of an installed library (e.g. Pydantic v1
  decorators in a project that installs Pydantic v2).
- A dependency is **unmaintained**, archived, or has an official successor.
- A **major-version upgrade** is available and may introduce breaking changes.
- You need a **structured, evidence-tagged report** to hand off maintenance
  work to another team member or future maintainer.

## Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.10 or later (scripts are 3.8+ compatible) |
| Ollama | Installed and running with an open-weight model pulled |
| Default model | `qwen2.5-coder:7b` (override with `--model`) |
| Target repo | Cloned locally with dependencies installable |
| pip | For installing target repo dependencies before test runs |

## Inputs

| Argument | Required | Default | Description |
|---|---|---|---|
| `--repo PATH` | Yes | -- | Absolute or relative path to the cloned repository |
| `--dependency NAME` | Yes | -- | PyPI package name to analyse (e.g. `pydantic`) |
| `--model NAME` | No | `qwen2.5-coder:7b` | Ollama model to use for AI analysis |
| `--output DIR` | No | `./capsule_output/` | Directory for the final capsule files |
| `--skip-ai` | No | `false` | Skip the AI analysis step |
| `--skip-tests` | No | `false` | Skip test execution |
| `--dry-run` | No | `false` | Print commands without executing |

## Pipeline Steps

Run the pipeline with a single command:

    python scripts/run_pipeline.py --repo /path/to/repo --dependency pydantic

Under the hood the pipeline executes these steps in order:

### Step 1 -- Scan Usage

    python scripts/scan_usage.py --repo <path> --dependency <name>

**Produces:** `intermediate/usage_report.json`

Walks every `.py` file in the repository and records each import, function
call, decorator, or configuration block that references the target dependency.

### Step 2 -- Collect Metadata

    python scripts/collect_metadata.py --repo <path> --dependency <name>

**Produces:** `intermediate/metadata_report.json`

Parses `requirements.txt`, `pyproject.toml`, `setup.cfg`, and `setup.py`
for the dependency version pin. Queries PyPI for the latest version, license,
last release date, and deprecation status.

### Step 3 -- Run Tests

    python scripts/run_tests.py --repo <path>

**Produces:** `intermediate/test_results.json`

Runs the test suite using `pytest` and records pass/fail/error counts.

### Step 4 -- AI Analysis

    python scripts/ai_analyze.py --evidence usage_report.json --metadata metadata_report.json --model <model>

**Produces:** `intermediate/ai_analysis.json`

Sends the scanned evidence and metadata to the open-weight model. Returns a
structured migration plan, code changes, effort estimate, and risks.

### Step 5 -- Build Capsule

    python scripts/build_capsule.py --usage usage_report.json --metadata metadata_report.json --tests test_results.json --ai ai_analysis.json --output capsule_output/

**Produces:** `capsule_output/capsule.json` + `capsule_output/capsule.md`

Assembles all intermediate outputs into the final Dependency Exit Capsule.

## Outputs

| File | Format | Description |
|---|---|---|
| `capsule.json` | JSON | Machine-readable capsule with tagged evidence |
| `capsule.md` | Markdown | Human-readable capsule for review and handoff |

## Evidence Tagging Protocol

Every statement in the capsule carries exactly one of three tags:

| Tag | Meaning | Example |
|---|---|---|
| `[OBSERVED]` | Directly extracted from source code, manifest files, or package registries. Verifiable by re-running the scanner. | pydantic is pinned at 1.10.13 in requirements.txt |
| `[EXECUTED]` | Result of actually running a command (test suite, linter). Reproducible. | pytest: 9 passed, 1 failed, 0 errors |
| `[AI-SUGGESTED]` | Generated by the AI model. May be incorrect. Must be reviewed by a human. | Replace @validator with @field_validator |

This separation is the **most important quality signal** in the capsule.

## Limitations

- **Does not auto-apply code changes.** The capsule proposes but does not modify.
- **Requires a local clone.** Cannot analyse remote repositories directly.
- **AI quality depends on the model.** Larger models produce better plans.
- **Test execution assumes pytest.** Other frameworks may need manual config.
- **Security vulnerabilities (CVEs) are out of scope.** Focuses on maintenance.
