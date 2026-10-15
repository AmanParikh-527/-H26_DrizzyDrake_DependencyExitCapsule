# JSON Contract -- Inter-Script Data Schema

This document defines the exact JSON structures passed between the five
pipeline scripts. Every script that produces output **must** conform to
this contract. Every script that consumes input **must** tolerate missing
optional fields gracefully.

---

## 1. Usage Report (usage_report.json)

**Produced by:** scan_usage.py  
**Consumed by:** ai_analyze.py, build_capsule.py  
**Evidence tag:** `[OBSERVED]`

```json
{
  "dependency": {
    "name": "string",
    "source_files": ["string"]
  },
  "usages": [
    {
      "file": "string -- relative file path",
      "line": "number -- 1-indexed",
      "snippet": "string -- trimmed source line",
      "type": "string -- import | call | config | decorator",
      "api_version": "string -- v1 | v2 | unknown"
    }
  ],
  "summary": {
    "total_usages": "number",
    "files_affected": "number",
    "v1_usages": "number",
    "v2_usages": "number",
    "unknown_usages": "number"
  },
  "additional_findings": [
    {
      "dependency": "string",
      "issue": "string",
      "severity": "string -- low | medium | high | critical",
      "files": ["string"],
      "recommendation": "string"
    }
  ],
  "tag": "[OBSERVED]"
}
```

---

## 2. Metadata Report (metadata_report.json)

**Produced by:** collect_metadata.py  
**Consumed by:** ai_analyze.py, build_capsule.py  
**Evidence tag:** `[OBSERVED]`

```json
{
  "dependency": {
    "name": "string",
    "current_version": "string",
    "required_version": "string",
    "latest_version": "string",
    "source_files": ["string"]
  },
  "metadata": {
    "license": "string",
    "last_release_date": "string -- ISO 8601",
    "is_deprecated": "boolean",
    "repository_url": "string",
    "pypi_url": "string",
    "python_requires": "string",
    "maintainer_count": "number or null",
    "open_issues": "number or null"
  },
  "risk_indicators": [
    {
      "indicator": "string",
      "severity": "string -- low | medium | high | critical",
      "evidence": "string",
      "tag": "[OBSERVED]"
    }
  ],
  "version_conflict": {
    "detected": "boolean",
    "details": "string"
  },
  "tag": "[OBSERVED]"
}
```

---

## 3. Test Results (test_results.json)

**Produced by:** run_tests.py  
**Consumed by:** build_capsule.py  
**Evidence tag:** `[EXECUTED]`

```json
{
  "framework": "string -- e.g. pytest",
  "command": "string -- exact command executed",
  "total": "number",
  "passed": "number",
  "failed": "number",
  "errors": "number",
  "skipped": "number",
  "duration_seconds": "number",
  "raw_output": "string -- truncated to 10000 chars",
  "raw_output_file": "string -- path to full output",
  "exit_code": "number",
  "tag": "[EXECUTED]"
}
```

---

## 4. AI Analysis (ai_analysis.json)

**Produced by:** ai_analyze.py  
**Consumed by:** build_capsule.py  
**Evidence tag:** `[AI-SUGGESTED]`

```json
{
  "model_used": "string",
  "problem_summary": "string",
  "recommended_approach": "string",
  "migration_steps": ["string"],
  "code_changes": [
    {
      "file": "string",
      "description": "string",
      "before": "string",
      "after": "string"
    }
  ],
  "estimated_effort": "string",
  "risks": ["string"],
  "suggested_tests": ["string"],
  "tag": "[AI-SUGGESTED]"
}
```

---

## 5. Final Capsule (capsule.json)

**Produced by:** build_capsule.py  
**Consumed by:** End user / reviewer

Every value is wrapped in `{"value": ..., "tag": "..."}`.

---

## Tag Assignments Summary

| Data Source | Evidence Tag |
|---|---|
| Code scanner output | `[OBSERVED]` |
| Manifest file parsing | `[OBSERVED]` |
| PyPI metadata | `[OBSERVED]` |
| Risk indicator scoring | `[OBSERVED]` |
| Test suite results | `[EXECUTED]` |
| AI model output | `[AI-SUGGESTED]` |
