# Independent verification of the agent's pull requests

The pipeline reports two things separately: what the Devin session says about
its own work (self-reported), and whether the pull request targets the right
repository and branch (machine-checked). Neither is proof that the fix is
correct — CI is not wired up on a fork, so the report says
`Independent verification: not configured`.

This file is that missing step, done by hand before merging. Each PR branch was
checked out into a clean git worktree and the acceptance criteria were re-run.

Verified on: 2026-08-30T05:43:52Z
Baseline for comparison: `scan-evidence/` (fork master, 13 npm findings, 4 ruff S704)

---

## PR #9 — issue #1, ruff S704 hardening

Claim to check: the four S704 findings are gone, achieved by rewriting the code
rather than by suppressing the rule.

### 1. The findings are gone

```
$ uvx ruff check superset/
All checks passed!
```

### 2. No new suppressions were added

```
$ grep -rn "noqa.*S704" superset/
superset/connectors/sqla/models.py:1669:        return Markup(anchor)  # noqa: S704
superset/models/helpers.py:1289:        return Markup(f'<span class="no-wrap">{self.changed_on}</span>')  # noqa: S704
superset/models/helpers.py:1321:        return Markup(f'<span class="no-wrap">{self.changed_on_humanized}</span>')  # noqa: S704
```

All three predate this change (they are present on fork master). The four sites
named in the issue carry no suppression.

### 3. The rule is still enforcing, not disabled

The PR declares `nh3.clean` as a sanitiser via ruff's `allowed-markup-calls`
instead of suppressing the site. To confirm that still enforces, the sanitiser
call was removed by hand and ruff re-run:

```
# temporarily replaced Markup(nh3.clean(...)) with Markup(safe)
$ uvx ruff check superset/utils/core.py
606 |     # nh3 preserves supported link attributes and enforces a safe rel value.
607 |     if markup_wrap:
608 |         return Markup(safe)
    |                ^^^^^^^^^^^^
609 |     return nh3.clean(safe, tags=safe_markdown_tags, attributes=safe_markdown_attrs)
    |

Found 1 error.
```

The rule fires again, so the safety property is checked by the linter rather
than silenced. **Verdict: the fix is real.**

---

## PR #10 — issue #2, nx and brace-expansion advisories

Claim to check: raising `nx` clears both high-severity findings, without making
anything else worse.

### 1. The vulnerable versions are gone from the lockfile

```
$ python3 - <<EOF   # read package-lock.json
nx resolves to: 23.1.2
brace-expansion copies still in the vulnerable range: none
```

### 2. `npm audit` no longer reports either advisory, and nothing regressed

```
$ npm audit --json    # counts and whether the two packages appear
after : {"info": 0, "low": 0, "moderate": 0, "high": 10, "critical": 1, "total": 11}
nx reported             : False
brace-expansion reported: False
before: {"info": 0, "low": 0, "moderate": 0, "high": 12, "critical": 1, "total": 13}  (from scan-evidence/)
```

High findings went from 12 to 10 and no severity got worse. **Verdict: the fix
is real, and one dependency bump cleared two advisories as intended.**

---

## PR #11 — issue #3, ESLint plugin name collision

Claim to check: the false-positive advisory is gone, the plugin still loads, and
the rename did not touch any of the rule-id references (the trap here — a
find-and-replace on `i18n-strings` would break seven of them).

### 1. The false critical is gone

```
$ npm audit --json
after : {"info": 0, "low": 0, "moderate": 0, "high": 12, "critical": 0, "total": 12}
eslint-plugin-i18n-strings reported: False
```

Critical went from 1 to 0. The remaining high findings are the deck.gl family and
other items deliberately left out of scope.

### 2. Only the package name changed; rule ids are untouched

```
$ grep -rn "eslint-plugin-i18n-strings" <the three files that name the package>
superset-frontend/package.json:264:    "@superset/eslint-plugin-i18n-strings": "file:eslint-rules/eslint-plugin-i18n-strings",
superset-frontend/eslint.config.minimal.js:42:const i18nStringsPlugin = require('@superset/eslint-plugin-i18n-strings');
superset-frontend/eslint-rules/eslint-plugin-i18n-strings/package.json:2:  "name": "@superset/eslint-plugin-i18n-strings",

$ grep -rn "'i18n-strings'|i18n-strings/" <config, check-custom-rules.js, types.ts>
eslint.config.minimal.js:90:      'i18n-strings': i18nStringsPlugin,
eslint.config.minimal.js:96:      'i18n-strings/no-template-vars': 'error',
eslint.config.minimal.js:98:      'i18n-strings/no-eager-t-in-config': 'off',
eslint.config.minimal.js:109:      'i18n-strings/no-eager-t-in-config': 'warn',
eslint.config.minimal.js:128:      'i18n-strings/no-template-vars': 'off',
scripts/check-custom-rules.js:238:      if (hasEslintDisable(path, 'i18n-strings/no-eager-t-in-config')) return;
packages/superset-ui-chart-controls/src/types.ts:213: *   `i18n-strings/no-eager-t-in-config` lint rule autofixes this.
```

All seven rule-id references are byte-for-byte unchanged. **Verdict: the fix is
real and the trap was avoided.**

### 3. What could not be checked locally

`npm ci --dry-run` fails in this environment, but it fails identically on fork
master, so it is not caused by the change: this repository pins
`node ^24.16.0 / npm ^11.13.0` and the check was run here with npm 10.8.2, which
resolves the lockfile differently (`Missing: @noble/hashes@1.8.0`). The session
ran it on the pinned toolchain and reported exit 0.

Worth noting: the session also corrected a flaw in the issue I wrote. The
verification command I specified pointed at a file under `packages/**`, which
eslint ignores, so `--print-config` returned `undefined` and proved nothing. It
noticed, switched to `src/preamble.ts`, and confirmed the rules were registered
there instead.

---

## What this does not cover

- The Python test suite was not re-run here; the session reported running the
  three targeted test files, and that report is in its structured output.
- Only the acceptance criteria were checked. A full review of behaviour under
  every input is what a human reviewer does on the pull request itself.
