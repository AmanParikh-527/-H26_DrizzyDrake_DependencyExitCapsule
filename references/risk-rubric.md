# Dependency risk rubric

Risk is calculated only from observed scanner and metadata fields. The overall
level is the highest indicator level; an empty indicator set is `LOW`.

| Indicator | Rule | Level |
| --- | --- | --- |
| Staleness | Last release is more than three years old | HIGH |
| Staleness | Last release is one to three years old | MEDIUM |
| Deprecation | Registry marks the package deprecated or inactive | HIGH |
| Version lag | Declared major version is below the registry major version | MEDIUM |
| Unpinned | Version is absent or declared as a range | LOW |
| Blast radius | More than 20 detected usages | HIGH |
| Blast radius | 8–20 detected usages | MEDIUM |
| Spread | Detected in more than five files | MEDIUM |

The scanner is static and conservative. A missing field is not treated as
evidence of safety. Network failures are preserved in `metadata.json` and
must be reported as a limitation rather than silently converted to a result.
