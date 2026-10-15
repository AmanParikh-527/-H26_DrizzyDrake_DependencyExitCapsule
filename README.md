# AgentSkill-Hermes

Maintenance evidence pipeline and Agent Skill (`dependency-exit-capsule`) for dependency upgrades, compatibility analysis, and replacements.

## Overview

This project implements an autonomous agent skill following the [agentskills.io](https://agentskills.io) standard to analyze dependencies, scan actual usage across codebases, run test suites, query open-weight LLMs, and produce a fully tagged **Dependency Exit Capsule** (JSON, Markdown, and self-contained interactive HTML).

## Project Structure

- `dependency-exit-capsule/` - Complete Agent Skill package:
  - `target/` - **Target folder** where the user places their target GitHub repository (e.g., `dependency-exit-capsule/target/LinkWatch`).
  - `SKILL.md` - Agent skill definition and interface specification.
  - `scripts/scan_usage.py` - AST/grep detector for imports, calls, decorators, and configurations.
  - `scripts/collect_metadata.py` - Manifest and PyPI registry metadata collector.
  - `scripts/risk_indicators.py` - Applies risk rubric rules.
  - `scripts/run_tests.py` - Automated test suite runner with baseline vs. post-upgrade diffing.
  - `scripts/ai_analyze.py` - Open-weight model analyzer with file-grounding validation and network retry.
  - `scripts/build_capsule.py` - Structured capsule assembler (`capsule.json` and `capsule.md`).
  - `scripts/build_report.py` - Offline, self-contained interactive HTML visual report generator (`report.html`).
  - `scripts/run_pipeline.py` - End-to-end orchestrator running all 6 steps.
  - `scripts/trial_patch.py` - Trial patch sandbox execution.
  - `scripts/license_check.py` - Conservative license compatibility screener.
  - `scripts/red_team.py` - Independent adversarial auditor.
  - `scripts/generate_diagram.py` - Mermaid blast radius diagram generator.
  - `references/` - Risk rubric, JSON contract, capsule schema, and evidence contract.
  - `examples/` - Verified sample capsules.
  - `tests/` - Comprehensive unit and regression test suite.
- `capsule_output/` - **Output folder** created next to `dependency-exit-capsule`:
  - `capsule.json` - Machine-readable structured capsule with every field tagged.
  - `capsule.md` - Tagged human-readable Markdown report.
  - `report.html` - Self-contained, interactive visual HTML dashboard.
  - `intermediate/` - Step-by-step intermediate reports (`usage_report.json`, `metadata_report.json`, `test_results.json`, `ai_analysis.json`).
- `scripts/` - Root CLI utilities (mirrored runners for local development).
- `tests/` - Top-level test runner suite (including `test_report.py` and `test_validation.py`).
- `Dockerfile` - Container specification for DigitalOcean App Platform and Droplets.
- `docker-compose.yml` - Multi-container / local Docker composition.
- `.do/app.yaml` - DigitalOcean App Platform 1-click deployment specification.
- `app.py` - Production HTTP server for DigitalOcean serving the visual report and health endpoint.

---

## DigitalOcean Deployment

This project is fully containerized and deployment-ready for **DigitalOcean App Platform** and **DigitalOcean Droplets**.

### 1. DigitalOcean App Platform (Recommended)

1. Connect your repository to **DigitalOcean App Platform**.
2. DigitalOcean will automatically detect the root `Dockerfile` and `.do/app.yaml`.
3. Set your environment variables in the App Platform settings:
   - `GROQ_API_KEY`: Your Groq API key for high-speed open-weight LLM inference.
   - `PORT`: `8080` (default).
4. Deploy! The service exposes:
   - `GET /` — Serves the interactive `capsule_output/report.html`.
   - `GET /health` — Health check endpoint for zero-downtime health monitoring.
   - `GET /capsule.json` & `GET /capsule.md` — Machine-readable outputs.

### 2. DigitalOcean Droplet (Docker)

Deploy using Docker on any Ubuntu Droplet:

```bash
# Clone the repository
git clone https://github.com/AmanParikh-527/AgentSkill-Hermes.git
cd AgentSkill-Hermes

# Configure API key
cp .env.example .env
nano .env

# Build and run with Docker Compose
docker compose up -d --build

# View container logs
docker compose logs -f
```

The server will be live at `http://<your-droplet-ip>:8080`.

---

## Run End-to-End Pipeline

To execute the pipeline against a target repository:

```bash
# 1. Place your target repository in the target folder:
#    dependency-exit-capsule/target/<your-repo>
#    (A sample 'LinkWatch' target is provided out of the box)

# 2. Run the end-to-end pipeline:
python dependency-exit-capsule/scripts/run_pipeline.py \
  --repo dependency-exit-capsule/target/LinkWatch \
  --dependency Jinja2 \
  --output ./capsule_output
```

All reports (`capsule.json`, `capsule.md`, `report.html`, and `intermediate/*`) will be written to `capsule_output/`.

### Run Individual Scripts

```bash
python scripts/scan_usage.py --repo dependency-exit-capsule/target/LinkWatch --dependency Jinja2
python scripts/collect_metadata.py --repo dependency-exit-capsule/target/LinkWatch --dependency Jinja2 --ecosystem pypi
python scripts/risk_indicators.py
python scripts/build_report.py --capsule capsule_output/capsule.json --out capsule_output/report.html
```

---

## Testing & Quality Assurance

Run both test suites to verify full functionality:

```bash
# Run root test suite
python -m unittest discover -s tests -v

# Run agent skill test suite
python -m unittest discover -s dependency-exit-capsule/tests -v
```
