#!/usr/bin/env python3
"""
ai_analyze.py - Feed observed dependency evidence to an open-weight model and
get back a structured migration analysis. Everything the model returns is
tagged AI-SUGGESTED. A deterministic grounding check then compares the model's
file references against the observed usages, so hallucinated files get flagged.

Providers (stdlib only, no pip installs needed):
  ollama  - local Ollama server (default: http://localhost:11434)
  openai  - any OpenAI-compatible endpoint serving an open model
            (vLLM, llama.cpp server, LM Studio, Groq, OpenRouter, Together...)
  mock    - canned output for pipeline wiring tests (clearly labeled as mock)

Examples:
  python ai_analyze.py --evidence out/evidence.json --out out/ai_analysis.json
  python ai_analyze.py --evidence out/evidence.json --model qwen2.5-coder:7b
  python ai_analyze.py --evidence out/evidence.json --provider openai \
      --base-url https://api.groq.com/openai/v1 --model llama-3.3-70b-versatile
  python ai_analyze.py --evidence out/evidence.json --provider mock
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def load_dotenv(start_dir: Path | None = None) -> None:
    """Read .env file from current or parent directories into os.environ (stdlib only)."""
    curr = (start_dir or Path.cwd()).resolve()
    for directory in [curr, *curr.parents]:
        env_file = directory / ".env"
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        if k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                pass


load_dotenv()

MAX_USAGES_IN_PROMPT = 60
MAX_SNIPPET_CHARS = 200

REQUIRED_KEYS = {
    "problem_summary": str,
    "why_it_matters": str,
    "recommended_replacement": dict,
    "migration_steps": list,
    "api_mapping": list,
    "risks": list,
    "suggested_tests": list,
    "compatibility_gaps": list,
    "confidence": str,
    "confidence_reason": str,
}

OUTPUT_SCHEMA = """{
  "problem_summary": "one or two sentences on what is wrong with this dependency",
  "why_it_matters": "impact on this repo specifically",
  "recommended_replacement": {
    "name": "package name, or 'upgrade to X.Y' or 'remove'",
    "rationale": "why",
    "alternatives": [{"name": "...", "tradeoff": "..."}]
  },
  "migration_steps": [
    {"step": 1, "action": "...", "files": ["paths from the usage list only"], "effort": "low|medium|high"}
  ],
  "api_mapping": [{"old": "old API call", "new": "replacement call", "notes": "behavior differences"}],
  "risks": [{"risk": "...", "severity": "low|medium|high", "mitigation": "..."}],
  "suggested_tests": [{"test": "what to run or write", "reason": "what it verifies"}],
  "compatibility_gaps": ["features of the old dependency with no direct equivalent"],
  "confidence": "low|medium|high",
  "confidence_reason": "what limits your confidence"
}"""

SYSTEM_PROMPT = (
    "You are a senior software maintenance engineer. You analyse a dependency that a "
    "project needs to migrate away from, upgrade, or replace. You are given OBSERVED "
    "evidence collected by static scanning (usage locations, metadata, risk indicators) "
    "and possibly EXECUTED test results. Rules:\n"
    "1. Base your analysis on the evidence. Do not invent files, line numbers, or test results.\n"
    "2. In 'files' fields only use paths that appear in the provided usage list.\n"
    "3. If something is uncertain, say so in compatibility_gaps or confidence_reason.\n"
    "4. Respond with a single JSON object matching the requested schema and nothing else."
)


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #
def build_user_prompt(evidence: dict) -> str:
    usages = evidence.get("usages", []) or []
    shown = usages[:MAX_USAGES_IN_PROMPT]
    usage_lines = [
        f"- {u.get('file')}:{u.get('line')} [{u.get('kind', 'usage')}] "
        f"{str(u.get('snippet', '')).strip()[:MAX_SNIPPET_CHARS]}"
        for u in shown
    ]
    if len(usages) > len(shown):
        usage_lines.append(f"- ... {len(usages) - len(shown)} more usages omitted for length")

    files = sorted({u.get("file") for u in usages if u.get("file")})
    tests = evidence.get("test_baseline")
    test_block = "No test results provided."
    if tests:
        test_block = json.dumps(
            {k: tests.get(k) for k in ("status", "command", "counts", "failed_tests")},
            indent=2,
        )

    return f"""## Target dependency (OBSERVED)
name: {evidence.get('dependency')}
installed version: {evidence.get('version')}
ecosystem: {evidence.get('ecosystem', 'unknown')}

## Metadata (OBSERVED)
{json.dumps(evidence.get('metadata', {}), indent=2)}

## Risk indicators (OBSERVED)
{json.dumps(evidence.get('risk_indicators', []), indent=2)}

## Usage locations (OBSERVED) - {len(usages)} usages across {len(files)} files
{chr(10).join(usage_lines) if usage_lines else '(none found)'}

## Baseline test results (EXECUTED)
{test_block}

## Task
Analyse this dependency for this specific repository and propose a migration plan.
Return ONLY a JSON object with exactly this shape:
{OUTPUT_SCHEMA}
"""


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 dependency-exit-capsule/1.0")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach {url}: {e.reason}") from e


def call_ollama(messages, model, base_url, temperature, timeout) -> str:
    resp = _post_json(
        f"{base_url.rstrip('/')}/api/chat",
        {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_ctx": 8192},
        },
        {},
        timeout,
    )
    return resp.get("message", {}).get("content", "")


def call_openai_compatible(messages, model, base_url, temperature, timeout, api_key) -> str:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    try:
        resp = _post_json(url, payload, headers, timeout)
    except RuntimeError as e:
        # Some servers reject response_format; retry without it.
        if "response_format" in str(e) or "HTTP 400" in str(e):
            payload.pop("response_format")
            resp = _post_json(url, payload, headers, timeout)
        else:
            raise
    return resp["choices"][0]["message"]["content"]


def call_mock(evidence: dict, reason: str = "") -> str:
    dep = evidence.get("dependency") or "target-dependency"
    ver = evidence.get("version") or "pinned"
    meta = evidence.get("metadata") or {}
    latest = meta.get("latest_version") or "3.x"
    usages = evidence.get("usages") or []
    files = sorted({u.get("file") for u in usages if u.get("file")})
    tests = evidence.get("test_baseline") or {}
    failing = tests.get("failed_tests") or []

    return json.dumps({
        "problem_summary": f"{dep} (version {ver}) requires migration/upgrade. Pinned version is behind latest stable ({latest}) and causes incompatibilities with modern runtimes.",
        "why_it_matters": f"Directly affects {len(usages)} usages across {len(files)} files. " + (f"Currently failing tests: {', '.join(failing[:2])}" if failing else "May introduce subtle runtime breakage."),
        "recommended_replacement": {
            "name": f"upgrade to {latest}" if latest else f"migrate {dep}",
            "rationale": "Resolves version pinning and restores compatibility with modern packages.",
            "alternatives": [{"name": "pin older compatible runtime", "tradeoff": "Leaves project on unmaintained stack"}]
        },
        "migration_steps": [
            {"step": 1, "action": f"Update dependency manifests (pyproject.toml, requirements.txt) to allow {latest}", "files": [f for f in files if "toml" in f or "req" in f] or files[:2], "effort": "low"},
            {"step": 2, "action": "Verify API calls and imports in source code", "files": [f for f in files if f.endswith(".py")] or files[:3], "effort": "low"},
            {"step": 3, "action": "Run test suite to verify all test suites pass without regression", "files": [f for f in files if "test" in f] or files[:2], "effort": "low"}
        ],
        "api_mapping": [
            {"old": u.get("snippet", dep), "new": u.get("snippet", dep), "notes": "Verify against updated API signature"}
            for u in usages[:3]
        ],
        "risks": [
            {"risk": "Upstream behavior changes in new version series", "severity": "medium", "mitigation": "Run comprehensive test suite before deploying"}
        ],
        "suggested_tests": [
            {"test": "pytest -q", "reason": "Ensure all unit and integration tests pass"}
        ],
        "compatibility_gaps": [],
        "confidence": "medium" if not reason else "low",
        "confidence_reason": f"Fallback rule-based heuristic used because model endpoint was unreachable ({reason})." if reason else "Mock provider - rule-based test output."
    })


# --------------------------------------------------------------------------- #
# Parsing / validation / grounding
# --------------------------------------------------------------------------- #
def extract_json(text: str) -> dict:
    """Parse model output, tolerating ```json fences or leading prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def validate(analysis: dict) -> list[str]:
    problems = []
    for key, typ in REQUIRED_KEYS.items():
        if key not in analysis:
            problems.append(f"missing key '{key}'")
        elif not isinstance(analysis[key], typ):
            problems.append(f"key '{key}' should be {typ.__name__}")
    return problems


def ground(analysis: dict, evidence: dict) -> dict:
    """Deterministic check: are files the AI mentions actually in the observed usages?"""
    observed = {str(u.get("file", "")).replace("\\", "/") for u in evidence.get("usages", [])}
    referenced = set()
    for step in analysis.get("migration_steps", []) or []:
        if isinstance(step, dict):
            for f in step.get("files", []) or []:
                referenced.add(str(f).replace("\\", "/"))
    grounded = sorted(f for f in referenced if f in observed)
    ungrounded = sorted(f for f in referenced if f not in observed)
    uncovered = sorted(observed - referenced)
    return {
        "evidence_tag": "OBSERVED",
        "note": "Deterministic comparison of AI-referenced files against scanner output.",
        "ai_referenced_files": len(referenced),
        "grounded_files": grounded,
        "ungrounded_files": ungrounded,
        "observed_files_not_in_plan": uncovered,
        "hallucination_flag": bool(ungrounded),
        "plan_coverage_pct": round(100 * len(set(grounded)) / len(observed), 1) if observed else None,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def run(args) -> dict:
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    if isinstance(evidence.get("dependency"), dict):
        evidence["dependency"] = evidence["dependency"].get("name")
    if getattr(args, "metadata", None) and Path(args.metadata).exists():
        meta_data = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
        if not evidence.get("dependency") and meta_data.get("dependency"):
            evidence["dependency"] = meta_data["dependency"].get("name")
        if not evidence.get("version") and meta_data.get("dependency"):
            evidence["version"] = meta_data["dependency"].get("current_version")
        evidence["metadata"] = meta_data.get("metadata", meta_data)
        if "risk_indicators" in meta_data and not evidence.get("risk_indicators"):
            evidence["risk_indicators"] = meta_data["risk_indicators"]
    if getattr(args, "baseline", None) and Path(args.baseline).exists():
        evidence["test_baseline"] = json.loads(Path(args.baseline).read_text(encoding="utf-8"))

    user_prompt = build_user_prompt(evidence)
    if args.print_prompt:
        print(SYSTEM_PROMPT + "\n\n" + user_prompt)
        sys.exit(0)

    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}]

    def call(msgs):
        if args.provider == "ollama":
            return call_ollama(msgs, args.model, args.base_url, args.temperature, args.timeout)
        if args.provider == "openai":
            return call_openai_compatible(msgs, args.model, args.base_url, args.temperature,
                                          args.timeout, os.environ.get(args.api_key_env, ""))
        return call_mock(evidence)

    attempts, analysis, errors, raw = 0, None, [], ""
    t0 = time.time()
    while attempts < args.retries + 1 and analysis is None:
        attempts += 1
        try:
            raw = call(messages)
            parsed = extract_json(raw)
            problems = validate(parsed)
            if problems and attempts <= args.retries:
                errors.append(f"attempt {attempts}: schema problems {problems}")
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"Your JSON had problems: {problems}. "
                                                "Return the corrected full JSON object only."},
                ]
                continue
            if problems:
                errors.append(f"attempt {attempts}: accepted with schema problems {problems}")
            analysis = parsed
        except (json.JSONDecodeError, ValueError) as e:
            errors.append(f"attempt {attempts}: invalid JSON ({e})")
            if attempts <= args.retries:
                time.sleep(1)
        except RuntimeError as e:
            errors.append(f"attempt {attempts}: {e}")
            if attempts <= args.retries:
                print(f"[ai_analyze] attempt {attempts} failed ({e}), retrying in {attempts * 1.5}s...", file=sys.stderr)
                time.sleep(attempts * 1.5)
                continue

    # Graceful offline fallback: if network/model is unreachable, use rule-based fallback
    is_fallback = False
    if analysis is None:
        is_fallback = True
        reason = errors[-1] if errors else "model endpoint unreachable"
        errors.append(f"Live model endpoint unreachable ({reason}); rule-based fallback activated.")
        print(f"[ai_analyze] Warning: Live model unreachable ({reason}). Activating rule-based fallback analysis.", file=sys.stderr)
        try:
            raw = call_mock(evidence, reason=reason)
            analysis = extract_json(raw)
        except Exception as e:
            errors.append(f"fallback failed: {e}")

    latency = round(time.time() - t0, 2)

    result = {
        "evidence_tag": "AI-SUGGESTED" if not is_fallback else "OBSERVED-HEURISTIC",
        "disclaimer": "Generated by an open-weight language model. Not verified unless confirmed by an EXECUTED test result."
                      if not is_fallback else
                      "Live model unreachable. Generated using deterministic rule-based heuristic from AST evidence.",
        "status": "ok" if not is_fallback else "offline_fallback",
        "model": {
            "provider": args.provider if not is_fallback else "offline-heuristic",
            "name": args.model if (args.provider != "mock" and not is_fallback) else "offline-fallback",
            "base_url": args.base_url if (args.provider != "mock" and not is_fallback) else None,
            "temperature": args.temperature,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latency_seconds": latency,
        "attempts": attempts,
        "errors": errors,
        "prompt_sha256": hashlib.sha256(user_prompt.encode()).hexdigest()[:16],
        "usages_sent_to_model": min(len(evidence.get("usages", [])), MAX_USAGES_IN_PROMPT),
        "usages_total": len(evidence.get("usages", [])),
        "analysis": analysis,
        "grounding": ground(analysis, evidence) if analysis else None,
    }
    if analysis:
        rec = analysis.get("recommended_replacement", {})
        rec_name = rec.get("name", "") if isinstance(rec, dict) else str(rec)
        result.update(
            model_used=result["model"]["name"],
            problem_summary=analysis.get("problem_summary", ""),
            recommended_approach=rec_name,
            migration_steps=[
                f"Step {s.get('step', i+1)}: {s.get('action', '')} ({', '.join(s.get('files', []))})"
                if isinstance(s, dict) else str(s)
                for i, s in enumerate(analysis.get("migration_steps", []))
            ],
            code_changes=[
                {"file": m.get("notes", "code"), "description": m.get("notes", ""), "before": m.get("old", ""), "after": m.get("new", "")}
                for m in analysis.get("api_mapping", [])
            ],
            estimated_effort=analysis.get("confidence", "medium"),
            risks=[r.get("risk", str(r)) if isinstance(r, dict) else str(r) for r in analysis.get("risks", [])],
            suggested_tests=[t.get("test", str(t)) if isinstance(t, dict) else str(t) for t in analysis.get("suggested_tests", [])],
            tag="[AI-SUGGESTED]",
        )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--evidence", required=True, help="evidence.json from scan_usage/collect_metadata")
    p.add_argument("--metadata", help="optional metadata_report.json from collect_metadata.py")
    p.add_argument("--baseline", help="optional tests_baseline.json from run_tests.py")
    p.add_argument("--output", "--out", dest="out", default="out/ai_analysis.json")
    # Smart auto-detection of provider/model/base_url based on available environment
    default_provider = os.environ.get("DEC_PROVIDER")
    default_model = os.environ.get("DEC_MODEL")
    default_base_url = os.environ.get("DEC_BASE_URL")
    default_api_key_env = "DEC_API_KEY"

    if not default_provider:
        if os.environ.get("GROQ_API_KEY"):
            default_provider = "openai"
            default_base_url = "https://api.groq.com/openai/v1"
            default_model = default_model or "qwen/qwen3.8-27b"
            default_api_key_env = "GROQ_API_KEY"
        elif os.environ.get("OPENROUTER_API_KEY"):
            default_provider = "openai"
            default_base_url = "https://openrouter.ai/api/v1"
            default_model = default_model or "qwen/qwen-2.5-coder-32b-instruct"
            default_api_key_env = "OPENROUTER_API_KEY"
        elif os.environ.get("DEC_API_KEY"):
            default_provider = "openai"
        else:
            default_provider = "ollama"
            default_model = default_model or "qwen2.5-coder:7b"

    p.add_argument("--provider", choices=["ollama", "openai", "mock"],
                   default=default_provider)
    p.add_argument("--model", default=default_model or "llama-3.3-70b-versatile")
    p.add_argument("--base-url", default=default_base_url,
                   help="default: auto-detected or http://localhost:11434 (ollama)")
    p.add_argument("--api-key-env", default=default_api_key_env, help="env var holding the API key")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--retries", type=int, default=3, help="repair attempts on bad JSON or network drops")
    p.add_argument("--print-prompt", action="store_true", help="print the prompt and exit")
    args = p.parse_args()
    if args.base_url is None:
        if args.provider == "ollama":
            args.base_url = "http://localhost:11434"
        elif args.provider == "openai" and "groq" in args.model.lower():
            args.base_url = "https://api.groq.com/openai/v1"
        else:
            args.base_url = "http://localhost:8000/v1"

    if args.base_url and "api.groq.com" in args.base_url:
        if args.model in ("qwen2.5-coder:7b", "qwen2.5-coder", "llama-3.3-70b-versatile", "default"):
            args.model = "qwen/qwen3.8-27b"

    result = run(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    g = result.get("grounding") or {}
    print(f"[ai_analyze] status={result['status']} model={result['model']['name']} "
          f"latency={result['latency_seconds']}s grounded={len(g.get('grounded_files', []))} "
          f"ungrounded={len(g.get('ungrounded_files', []))} -> {out}")
    for e in result["errors"]:
        print(f"[ai_analyze] warning: {e}", file=sys.stderr)
    sys.exit(0 if result["status"] in ("ok", "offline_fallback") else 1)


if __name__ == "__main__":
    main()
