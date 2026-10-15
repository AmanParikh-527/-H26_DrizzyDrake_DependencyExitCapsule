# 🔍 Dependency Exit Capsule

> An AI-powered Agent Skill that identifies dependency maintenance problems, analyses migration paths, and generates evidence-tagged reports separating verified facts from AI recommendations.

[![Agent Skills Open Standard](https://img.shields.io/badge/Agent%20Skills-Open%20Standard%20v1.0-blue)](https://agentskills.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)

---

## 📖 What It Does

`dependency-exit-capsule` is an autonomous software-maintenance capability developed under the **Agent Skills Open Standard** for **Track 2 (Maintenance Agent Skill)**. 

Modern projects often suffer from "dependency drift": manifest files disagree with code imports, deprecated APIs remain in use, and fresh installs crash unexpectedly. This skill automates the diagnosis and migration planning for troubled dependencies by combining deterministic static code analysis with open-weight language models.

Key capabilities:
- **AST & Heuristic Code Scanning**: Discovers every import, decorator, class configuration, and invocation of the target package across all repository files.
- **Manifest Divergence Detection**: Identifies conflicts between packaging files (e.g., `requirements.txt` pinning v1 while `pyproject.toml` pins v2).
- **Automated Sandbox Test Execution**: Captures test suite baseline runs before and after changes.
- **Open-Weight AI Migration Reasoning**: Uses local LLMs (e.g., `qwen2.5-coder:7b` via Ollama) to synthesize migration diffs, step-by-step procedures, and effort estimations.
- **Rigorous Evidence Tagging**: Every single statement in both JSON and Markdown outputs is tagged with `[OBSERVED]`, `[EXECUTED]`, or `[AI-SUGGESTED]` to eliminate hallucinations and establish clear auditability.

---

## 📂 Folder Structure

```
dependency-exit-capsule/
├── SKILL.md                          # Standard Agent Skill specification & prompt rules
├── README.md                         # Architecture overview & documentation
├── assets/
│   └── capsule-template.md           # Markdown blueprint for capsule outputs
├── references/
│   ├── capsule-schema.md             # Data dictionary and evidence tagging protocol
│   ├── json-contract.md              # Inter-script JSON pipeline contract
│   └── risk-rubric.md                # Quantitative scoring rubric for dependency risks
├── scripts/
│   ├── run_pipeline.py               # Orchestrator for all 6 pipeline stages
│   ├── scan_usage.py                 # AST/regex code usage analyzer (Member A)
│   ├── collect_metadata.py           # PyPI and package metadata collector (Member A)
│   ├── risk_indicators.py            # Risk indicators rule evaluation (Member A)
│   ├── run_tests.py                  # Pytest runner and output parser (Member B)
│   ├── ai_analyze.py                 # Open-weight LLM reasoning bridge (Member B)
│   ├── build_capsule.py              # Capsule generator (JSON + Markdown) (Member C)
│   └── build_report.py               # Interactive visual HTML report generator
└── examples/
    └── sample-capsule.md             # Ground-truth report for LinkWatch (Pydantic v1→v2)
```

---

## ⚙️ Prerequisites

1. **Python**: Python 3.10 or higher.
2. **Pip & Git**: Standard Python development environment.
3. **Ollama (Optional for AI analysis)**: Running locally with an open-weight model:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
   *(Note: The pipeline includes a `--skip-ai` flag for headless CI or environments without local LLMs).*

---

## 🚀 Quick Start (Testing on LinkWatch)

Run the full end-to-end pipeline against the target repository:

```bash
# 1. Clone LinkWatch (target repo) if not already cloned
git clone https://github.com/rishrek/LinkWatch.git ../LinkWatch

# 2. Navigate to dependency-exit-capsule
cd dependency-exit-capsule

# 3. Run the orchestration pipeline
python scripts/run_pipeline.py --repo ../LinkWatch --dependency pydantic --output ./capsule_output
```

Inspect the generated artifacts in `./capsule_output/`:
- `capsule.md` — Human-readable, evidence-tagged audit report.
- `capsule.json` — Machine-readable structured capsule data.

---

## 🛠️ Usage & CLI Reference

### `run_pipeline.py`

```bash
python scripts/run_pipeline.py [OPTIONS]
```

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--repo` | Path | **Required** | Path to the target git repository |
| `--dependency` | String | **Required** | Package name to analyze (e.g., `pydantic`) |
| `--model` | String | `qwen2.5-coder:7b` | Ollama model tag for migration reasoning |
| `--output` | Path | `./capsule_output` | Destination directory for final reports |
| `--dry-run` | Flag | `False` | Prints planned pipeline steps without execution |
| `--skip-ai` | Flag | `False` | Runs deterministic analysis only; skips LLM call |
| `--skip-tests` | Flag | `False` | Skips running the target repo's test suite |

### Individual Pipeline Components

Each tool can be run independently for modularity:

```bash
# Step 1: AST Usage Scanner
python scripts/scan_usage.py --repo ../LinkWatch --dependency pydantic --output intermediate/usage_report.json

# Step 2: Metadata Collector
python scripts/collect_metadata.py --repo ../LinkWatch --dependency pydantic --output intermediate/metadata_report.json

# Step 3: Test Suite Runner
python scripts/run_tests.py --repo ../LinkWatch --output intermediate/test_results.json

# Step 4: AI Analysis Generator
python scripts/ai_analyze.py --evidence intermediate/usage_report.json --metadata intermediate/metadata_report.json --model qwen2.5-coder:7b --output intermediate/ai_analysis.json

# Step 5: Capsule Assembler
python scripts/build_capsule.py --usage intermediate/usage_report.json --metadata intermediate/metadata_report.json --tests intermediate/test_results.json --ai intermediate/ai_analysis.json --output capsule_output/
```

---

## 🔄 How It Works

```
Target Repository
       │
       ├──► [1. scan_usage.py]       ──► usage_report.json     [OBSERVED]
       ├──► [2. collect_metadata.py] ──► metadata_report.json  [OBSERVED]
       ├──► [3. run_tests.py]        ──► test_results.json     [EXECUTED]
       │             │
       │             ▼
       └──► [4. ai_analyze.py]       ──► ai_analysis.json      [AI-SUGGESTED]
                     │
                     ▼
            [5. build_capsule.py]
                     │
       ┌─────────────┴─────────────┐
       ▼                           ▼
  capsule.json                capsule.md
```

---

## 🏷️ Evidence Tagging Protocol

A primary criteria in autonomous maintenance is verifiability and trust. Every datum produced by the skill is assigned one of three immutable tags:

- **`[OBSERVED]`**: Ground truth facts retrieved directly from code ASTs, regex matching, filesystem manifests (`requirements.txt`, `pyproject.toml`), or the official PyPI JSON API.
- **`[EXECUTED]`**: Empirical facts obtained by running executables in a test harness (e.g., exit codes, passing/failing test counters).
- **`[AI-SUGGESTED]`**: Deductions, migration steps, and code patches synthesized by the AI model. Marked with clear disclaimers for human engineer review.

See [`references/capsule-schema.md`](references/capsule-schema.md) for field-level schemas.

---

## 🌟 Original Contributions

1. **Deterministic AST API Version Classifier**: Differentiates legacy vs modern API patterns (e.g., detecting `@validator` and `class Config` as Pydantic v1 vs `@field_validator` and `ConfigDict` in v2).
2. **Standardized Evidence Tagging System**: Explicitly segregates deterministic observations from probabilistic AI suggestions across both human and machine interfaces.
3. **Resilient Pipeline Orchestration**: Gracefully tolerates absent environments (e.g., missing test suites or offline LLMs) while still emitting a valid partial capsule.
4. **Multi-Vector Dependency Assessment**: Evaluates secondary risks (abandoned libraries like `nose`, unmaintained packages like `appdirs`, obsolete shims like `six`) alongside the primary target.
5. **Open Standard Compliance**: Implements the `agentskills.io` standard format with comprehensive frontmatter and documentation.

---

## 📄 License & Hackathon Info

- **Track**: Track 2 (Maintenance Agent Skill)
- **License**: MIT License
- **Reference Example**: [LinkWatch Pydantic Migration Sample Capsule](examples/sample-capsule.md)