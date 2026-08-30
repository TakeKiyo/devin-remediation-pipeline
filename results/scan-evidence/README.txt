Scan evidence for the issue candidates. See ../issue-selection.md for how
these findings were filtered down to the three issues that were filed.

Target: TakeKiyo/superset (fork of apache/superset), branch master
Commit: 96119ffefce6165efa4a655dd4674ec697b819d1
Scan date: 2026-08-30

Tool versions:
  Python 3.12.3 / node v20.18.2 / npm 10.8.2
  pip-audit 2.7.3
  ruff 0.16.5

Commands (from the clone root unless noted):
  1. uvx ruff check superset/                     -> ruff.txt        (4 x S704)
  2. cd superset-frontend && npm audit --json     -> npm-audit.json  (1 critical, 12 high)
  3. pip-audit -r requirements/base.txt --skip-editable --no-deps -f json
                                                  -> pip-audit.json  (flask, paramiko)

All three run without installing Superset's dependencies: ruff via uvx, npm audit
from the lockfile, pip-audit from the requirements file.

Note: these tools exit non-zero when findings exist; the output files are the record.
