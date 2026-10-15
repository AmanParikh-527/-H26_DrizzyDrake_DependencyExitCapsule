# Risk Rubric -- Dependency Health Scoring

This rubric defines how risk indicators are scored in the Dependency Exit
Capsule. Every risk indicator receives a **severity** rating and a **numeric
score** based on the criteria below.

---

## Severity Levels

| Severity | Score Range | Definition |
|---|---|---|
| **Critical** | 9-10 | Broken functionality or API incompatibility that causes runtime errors. The project cannot work correctly in its current state. |
| **High** | 7-8 | The dependency is unmaintained (2+ years without a release), officially deprecated, end-of-life, or has a well-known successor. Continued use carries significant risk. |
| **Medium** | 4-6 | The dependency is outdated by one or more major versions, is unnecessary for the project Python version target, or adds avoidable complexity. |
| **Low** | 1-3 | The dependency is behind by minor or patch versions, or has cosmetic issues that do not affect functionality. |

---

## Specific Indicators

### Critical (Score 9-10)

| Indicator | Example | Score |
|---|---|---|
| Version conflict between manifest files | requirements.txt pins pydantic==1.10.13 but pyproject.toml declares pydantic>=2 | 10 |
| Code uses removed or renamed API of the installed version | @validator decorator used but pydantic v2 is installed | 10 |
| Fresh install is broken | pyproject.toml gets pydantic v2 but code uses v1 patterns | 10 |
| Dependency has known data-loss bugs at pinned version | A retracted release on PyPI | 9 |

### High (Score 7-8)

| Indicator | Example | Score |
|---|---|---|
| No releases in 2+ years | appdirs -- last release in 2020 | 8 |
| Officially deprecated by maintainers | pkg_resources -- setuptools docs recommend importlib.resources | 8 |
| Library is archived on GitHub | toml -- archived, no longer accepting contributions | 8 |
| End-of-life version series | Jinja2==2.11.3 -- Jinja2 2.x is EOL | 8 |
| Library has an official successor | appdirs replaced by platformdirs, nose replaced by pytest | 7 |
| Test framework is abandoned | nose==1.3.7 -- last release 2015 | 7 |
| Major API breaking changes between pinned and latest | @validator replaced by @field_validator in pydantic v2 | 7 |

### Medium (Score 4-6)

| Indicator | Example | Score |
|---|---|---|
| Behind by 1+ major versions | idna==2.7 when idna 3.x is current | 6 |
| Unnecessary dependency for the target Python version | six in a project requiring Python >=3.10 | 5 |
| Stdlib replacement available | toml can be replaced by tomllib (stdlib in Python 3.11+) | 5 |
| Dependency declared but never imported | six in requirements.txt but unused in source files | 4 |
| Uses deprecated sub-API of an otherwise current library | Using requests.utils._parse_content_type_header (private API) | 4 |

### Low (Score 1-3)

| Indicator | Example | Score |
|---|---|---|
| Behind by minor versions | requests==2.31.0 when 2.32.x is current | 3 |
| Behind by patch versions only | chardet==5.2.0 when 5.2.1 is current | 1 |
| Pinning strategy is overly strict | Using == pins for all deps instead of >= or ~= ranges | 2 |
| Missing type stubs for a typed project | No types-requests in dev dependencies | 1 |

---

## Composite Risk Score

When multiple indicators apply to the same dependency, the composite score is
the **maximum** of all individual indicator scores -- not the sum.

Example for pydantic in LinkWatch:
- Version conflict between manifests -> **10** (Critical)
- Code uses removed v1 API -> **10** (Critical)
- Major API breaking changes -> **7** (High)
- **Composite score: 10 (Critical)**

---

## How Scores Are Used

The capsule reports risk indicators with their severity labels. Scores are
internal to the rubric and guide ordering: Critical items appear first,
followed by High, Medium, and Low.

A capsule with any **Critical** indicator should be treated as requiring
**immediate attention** -- the project may be broken in its current state.
