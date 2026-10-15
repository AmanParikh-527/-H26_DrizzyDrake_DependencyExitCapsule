# Problem selection

## Current repository assessment

The initial repository contains only a README and no dependency manifest or
source files. Therefore there is no candidate dependency to select from the
target project yet. This implementation provides the evidence pipeline and
uses `requests` only as the documented command-line example from the supplied
brief; it does not claim that `requests` is a project dependency.

When a real target repository is available, selection should score candidates
against the following criteria:

- deprecated, unmaintained, or has a clear successor;
- five to thirty usage locations;
- used by code covered by existing tests;
- selected for maintenance evidence, never solely because of a CVE;
- realistic to replace or upgrade within the project timebox.

The selected record must state the exact dependency, version constraint,
observable evidence, usage count, and proposed upgrade or replacement. All
facts belong in `evidence/`; recommendations belong in the subsequent
maintenance decision.
