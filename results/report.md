<!-- Snapshot of data/report.md after the live run. Do not edit by hand. -->

# Live run — 2026-08-30

Snapshot of the orchestrator's own report after running against
[TakeKiyo/superset](https://github.com/TakeKiyo/superset). Every pull request and
session below is real.

**How to read this.** Five issues were processed, but only three are
remediations:

| Issue | What it was | Counted as a remediation? |
|---|---|---|
| [#1](https://github.com/TakeKiyo/superset/issues/1) | ruff S704 hardening | yes |
| [#2](https://github.com/TakeKiyo/superset/issues/2) | nx / brace-expansion advisories | yes |
| [#3](https://github.com/TakeKiyo/superset/issues/3) | ESLint plugin name collision | yes |
| [#4](https://github.com/TakeKiyo/superset/issues/4) | pipeline smoke test, first attempt | no |
| [#6](https://github.com/TakeKiyo/superset/issues/6) | pipeline smoke test, re-run | no |

So: **3 remediations, 3 open pull requests, all three verified by hand**
(see [verification.md](verification.md)). The smoke tests only proved the wiring;
their pull requests were closed without merging.

The one failure, #4, was not Devin's: the orchestrator judged the session before
checking whether a pull request existed, and terminated it. The session had in
fact done the work. That bug is fixed, and #6 is the re-run that proved it.

---

# Remediation run report

- Repository: `TakeKiyo/superset` (base branch `master`)
- Generated: 2026-08-30T05:50:39+00:00

## Summary

- Active: **0**
- Succeeded: **4**
- Failed: **1**
- Session cost: see Devin's billing view (the API does not expose it)

## Tasks

| Issue | Status | PR | Elapsed | Detail |
|---|---|---|---|---|
| #1 | succeeded | [link](https://github.com/TakeKiyo/superset/pull/9) | 7m |  |
| #2 | succeeded | [link](https://github.com/TakeKiyo/superset/pull/10) | 4m |  |
| #3 | succeeded | [link](https://github.com/TakeKiyo/superset/pull/11) | 5m |  |
| #4 | failed | -- | 2m | session was waiting on a human; terminated |
| #6 | succeeded | [link](https://github.com/TakeKiyo/superset/pull/7) | 2m |  |

Agent verification is self-reported by the session. PR target validation is checked against the GitHub API. Independent verification (CI) is not configured, so a human reviews every PR before merge.

## Devin sessions

Each session is inspectable in the Devin dashboard (org members only).

| Issue | Session | Result | Pull request |
|---|---|---|---|
| #1 | [cdd0bbd04baa…](https://app.devin.ai/sessions/cdd0bbd04baa4d16b278d84d6ec255cf) | succeeded | https://github.com/TakeKiyo/superset/pull/9 |
| #2 | [5eb32c6a96af…](https://app.devin.ai/sessions/5eb32c6a96af48489b1cd297369c9c7f) | succeeded | https://github.com/TakeKiyo/superset/pull/10 |
| #3 | [84a3690d7771…](https://app.devin.ai/sessions/84a3690d777141728458b388b15a443b) | succeeded | https://github.com/TakeKiyo/superset/pull/11 |
| #4 | [7d96cff60dde…](https://app.devin.ai/sessions/7d96cff60dde4ba49b4355f7d27cb410) | failed | -- |
| #6 | [58398b065083…](https://app.devin.ai/sessions/58398b0650834b8e97806f67368c48a2) | succeeded | https://github.com/TakeKiyo/superset/pull/7 |

## Cost

Read from Devin's billing view. The API reports `acus_consumed` as 0 on
credit-based plans, so this is the only authoritative source.

| Session | Issue | Result | Cost |
|---|---|---|---|
| Eliminate ruff S704 in TakeKiyo/superset | #1 | PR #9 | $2.30 |
| Fix nx brace-expansion npm audit advisories | #2 | PR #10 | $0.87 |
| Scope eslint-plugin-i18n-strings collision | #3 | PR #11 | $1.38 |
| **three remediations** | | | **$4.55** (average $1.52) |
| Append README verification line | #6 | smoke test, PR #7 | $0.46 |
| Add README provenance line… | #4 | smoke test, killed by the orchestrator bug | $0.48 |
| Fix S704 in TakeKiyo/superset#1 | #1, first attempt | killed by the orchestrator bug | $1.56 |
| **spent on runs that produced nothing** | | | **$2.04** |

Two caveats worth stating plainly. These are three small, well-scoped issues —
$1.52 is not a rate that generalises to arbitrary maintenance work. And $2.04 of
the total was wasted by orchestrator bugs, not by the agent: both wasted sessions
had done their work correctly before being cut off.
