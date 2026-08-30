# How the three issues were chosen

A record of the decision the pipeline does *not* make. The orchestrator's trigger
is a human applying a label, so which work gets delegated is a judgement call —
and that judgement is the part worth writing down.

Target: [`TakeKiyo/superset`](https://github.com/TakeKiyo/superset) (fork of
`apache/superset`), `master` @ `96119ffefce6165efa4a655dd4674ec697b819d1`.
Scanned 2026-08-30. Raw output in [`scan-evidence/`](scan-evidence/) — the filed
issues refer to those files as `scan-evidence/<name>`.

## 1. Scan

Three scanners, none of which need Superset's dependencies installed:

```
uvx ruff check superset/                                    ->  4 findings (all S704)
cd superset-frontend && npm audit --json                    ->  1 critical, 12 high
pip-audit -r requirements/base.txt --skip-editable --no-deps ->  flask, paramiko
```

## 2. Filter: severity is not a proxy for delegability

`npm audit` reports 13 advisories (1 critical, 12 high). **Only two of them can
be fixed without a breaking change, and both come from one dependency.** These
were the rejected candidates:

| Candidate | Why not |
|---|---|
| `dompurify` GHSA-55q2-fjhq-7xh7 | Carried over from an earlier scan (2026-08-25, lockfile 3.4.12). By this scan it was already fixed upstream: an existing `^3.4.13` override resolves 3.4.14, so it no longer appears. Not a real issue |
| deck.gl / loaders.gl / luma.gl / image-size / texture-compressor (6 high) | Needs a semver-major bump of `@deck.gl/*`, which touches the whole visualization runtime |
| pacote / lerna (high) | The only available fix is a major *downgrade* of lerna to 6.4.1 |
| flask 2.3.3 (PYSEC-2026-2151) | Fix is Flask 3.x. A framework migration is not one session's work |
| paramiko 3.5.1 (PYSEC-2026-2858) | No fixed version released yet (`fix_versions` is empty) |

That is the useful finding from this exercise: a scanner's severity ranking says
nothing about whether an agent can finish the job. A critical with no released
fix is not delegable work; a "high" that resolves to a one-line lockfile change
is.

## 3. Triage with Ask Devin

The three survivors were then handed to **Ask Devin** for ranking, with the file
paths and the intended fixes withheld, so it had to locate the code itself and
judge difficulty, likely failure modes and how each would be verified.

Result: **S704 > nx bump > eslint scope**, which is the order they were filed and
run in.

What it caught that the author had missed:

| Devin's point | Checked |
|---|---|
| `brace-expansion` is already pinned by an existing override; only the copy under `nx` is outside its scope | Correct |
| `engines` pins `node ^24.16.0` / `npm ^11.13.0`, which matters when regenerating the lockfile | Correct |
| The repo already contains three `# noqa: S704` precedents, so an agent may copy them | Correct — the acceptance criteria were changed to forbid suppression explicitly |
| `ruff check` cannot tell a real fix from a `noqa` suppression | Correct, and a genuine hole in the acceptance criteria as first written |

What it got wrong:

| Devin's claim | Measured |
|---|---|
| "`npm audit` needs `npm install` first" | Wrong. It runs from the lockfile with no `node_modules` and reported all 13 findings |

**The eslint issue took two rounds.** Ask Devin's first verdict was *do not
delegate this*. The issue was rewritten — destructive fixes explicitly forbidden,
and a specific verification command supplied — and it was then asked to refute
the change rather than agree with it. Its second answer: the two original
objections were resolved, but three things still needed tightening. Those three
are in the filed issue:

- the verification command is the one CI's `lint-stats` runs, but that uploader
  treats a non-zero exit as normal, so the exit code cannot be the pass signal —
  judge the JSON instead
- `i18n-strings/` also exists as a rule ID in 7 places, so a blanket rename
  breaks linting. Only the *package name* references may change
- hand-editing the lockfile makes CI's `npm ci` fail

One question Ask Devin could not answer was settled from the scan output: whether
`npm audit` really attaches an advisory to a `file:` dependency. It does —
`scan-evidence/npm-audit.json` records it as critical, `isDirect: true`,
`fixAvailable: false`.

## 4. The three that were filed

| # | Issue | Why it is delegable |
|---|---|---|
| 1 | Eliminate ruff S704 without suppressing the rule | Offline, deterministic, and a real judgement call: four call sites needing three different techniques, including one where escaping again would be wrong |
| 2 | Clear the nx and brace-expansion advisories with a lockfile-only change | Self-verifying — `npm audit` either still reports it or does not |
| 3 | Scope the local ESLint plugin to remove an npm-audit name collision | Needs the agent to decide whether the alert is real at all (it is a name collision with a local `file:` package), then make a rename that must not touch identically-named rule IDs |

None of them is a "bump a version" task a script could do, and none needs a human
in the loop while it runs. That is the shape being tested here.
