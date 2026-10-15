# AgentSkill-Hermes

Maintenance evidence pipeline for dependency upgrades and replacements.

## Structure

- `scripts/scan_usage.py` detects Python, JavaScript/TypeScript, and common
  configuration usages.
- `scripts/collect_metadata.py` records declared, locally installed, and
  registry metadata while preserving source and network failures.
- `scripts/risk_indicators.py` applies the rules in
  [`references/risk-rubric.md`](references/risk-rubric.md).
- `scripts/build_report.py` turns a capsule JSON file into an offline,
  self-contained HTML report with evidence tags, risk indicators, usage
  hotspots, test results, AI recommendations, and limitations.
- `scripts/run_all.py` runs scanning, planning, independent AI critique, a
  disposable trial patch, license screening, and capsule/report generation.
- `scripts/red_team.py` audits API coverage, signature changes, and missed
  locations against the scanner's evidence using a separate model call.
- `scripts/trial_patch.py` tries one source line in a temporary repository copy,
  runs baseline and patched tests, and restores the trial file on exit.
- `scripts/generate_diagram.py` creates a Mermaid blast radius from observed
  imports and symbols, marking untested files red and explicitly tested files yellow.
- `scripts/license_check.py` detects the host license and applies conservative
  compatibility rules to the proposed replacement, retaining sources and unknowns.
- `scripts/build_capsule.py` writes the Markdown capsule and the JSON consumed
  by the HTML report, including critique, trial results, and license warnings.
- `evidence/` contains JSON contracts and the current repository baseline.
- [`docs/problem-selection.md`](docs/problem-selection.md) explains how to
  select a real candidate dependency.

## Run against a target repository

```bash
python scripts/scan_usage.py --repo /path/to/repo --dep requests
python scripts/collect_metadata.py --repo /path/to/repo --dep requests --ecosystem pypi
python scripts/risk_indicators.py
python scripts/build_report.py --capsule capsule/capsule.json
```

Use `--import-name` when a package name differs from its import name, for
example `--dep pyyaml --import-name yaml`. The tools are offline-capable for
scanning; registry metadata failures are recorded in the output rather than
hidden.

The report generator accepts partial capsules and does not treat AI-generated
recommendations as verified facts. Open `capsule/report.html` locally after
generation; no server, CDN, or extra package is required.

## Complete validation pipeline

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

Use `--analysis /path/to/ai_analysis.json` to supply an existing plan instead of
generating one. The plan contract is:

```json
{
  "summary": "Migrate requests to httpx",
  "replacement": "httpx",
  "steps": ["Describe file/line-specific changes, API mappings and tests"],
  "risks": ["Describe any uncertainty"]
}
```

The model receives repository snippets at the configured endpoint. Planning and
auditing use independent requests to `CAPSULE_MODEL`; an audit remains
`AI-CRITIQUE`, even when it passes. The auditor must return every observed
`file`/`line` in `checked_locations`; omitted locations prevent a passing critique.
Model failures are recorded as unresolved concerns, never successful verification.

The trial chooses a current source usage by line complexity, then file length.
It rejects stale snippets, path traversal, symlink targets, multiline patches,
unchanged patches, and invalid Python syntax. It copies the repository without
Git data, symlinks, build outputs, or dependency environment directories, saves a
backup inside the temporary workspace, runs the unmodified suite, patches one
line, runs the suite again, and restores the backup in `finally`. The original
checkout and Git state are never edited by the patcher. Failed baselines, empty
Python suites, timeouts, and unavailable tooling do not establish a working patch.
Test output is retained with a 12 KB tail per stream and a truncation flag.

The test command executes without a shell, in the disposable copy. Use relative
test paths and a prepared test environment containing both libraries and the
repository's test dependencies; the tool does not install packages. A test command
can use an absolute interpreter path if needed. Automatic discovery supports
Python tests and `package.json` test scripts; use `--test-command` for other suites.
This protects the checkout from the patch operation; it is not an OS security
sandbox for untrusted tests or generated code. Tests must be trusted. A passing
single-line trial does not verify the entire migration.

`--offline` disables registry metadata requests (model requests still use the
configured endpoint). `--skip-trial` records an explicit unverified result.
`--target-license` and `--replacement-license` supply explicit license overrides.
The license checker reads `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `package.json`,
and PEP 621 `pyproject.toml` fields, and records the current dependency's license
from metadata. Its small bundled replacement lookup is unversioned; verify it
against the chosen release. Unknown replacements may be queried from the model,
but model-suggested licenses always require review.

The requested license rules are screening indicators: strong copyleft with a
proprietary host is CRITICAL; strong copyleft with a permissive host is HIGH;
permissive/weak-copyleft combinations receive conditional LOW results when covered
by the rules. Unknown, compound, and exception-bearing expressions remain
`REVIEW_REQUIRED`. The rules reflect the [GNU license compatibility guidance](https://www.gnu.org/licenses/license-compatibility.en.html)
and [Apache's GPL compatibility guidance](https://www.apache.org/licenses/GPL-compatibility.html);
actual obligations depend on the licenses and how software is combined and distributed.

Each validation stage can also run independently:

```bash
python scripts/red_team.py
python scripts/trial_patch.py --repo /path/to/repo --test-command 'python -m pytest -q'
python scripts/generate_diagram.py
python scripts/license_check.py --repo /path/to/repo
python scripts/build_capsule.py
python scripts/build_report.py
```

The additional evidence files are `ai_analysis.json`, `red_team_critique.json`,
`trial_patch_result.json`, `blast_radius.mmd`, and `license_risk.json` under
`evidence/`. The capsule includes `UNRESOLVED CONCERNS & CRITIQUE`, `Visual Blast
Radius [OBSERVED]`, and `RISK INDICATORS`, with license warnings elevated into
the overall risk. `evidence/pipeline.json` records stage statuses and durations
for the execution summary in both capsule formats.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests include a localhost-only HTTP model stub, a complete pipeline run, actual
passing/failing test subprocesses, timeout/interruption recovery, source-byte
preservation, malformed model output, omitted audit locations, and license rules.
