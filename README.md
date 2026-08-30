# Devin remediation pipeline

Label a GitHub issue `devin-fix` and a [Devin](https://devin.ai) session picks it
up, fixes it, and opens a pull request — with a report an engineering leader can
read at a glance. Built against a fork of
[apache/superset](https://github.com/apache/superset).

```
  human applies `devin-fix`
            |
            v
   +--------------------+        Devin API         +---------------------+
   |    orchestrator    | ----------------------> |   Devin session     |
   |  (this container)  |  create / poll / stop   |  (Cognition cloud)  |
   +--------------------+                         +---------------------+
     |            ^                                        |
     | comments   | issues, labels, PR metadata            | branch, tests, PR
     v            |                                        v
   +----------------------------------------------------------------+
   |                     GitHub (your superset fork)                |
   +----------------------------------------------------------------+
```

The orchestrator moves metadata only — issues, labels, comments, session ids. It
never runs git and never touches application code, which is why the container is
`python:3.12-slim` plus `requests`. The engineering happens inside the session.

## Try it without credentials

```bash
docker compose up --build
```

Simulate mode mocks both integrations using `fixtures/issues.json`, so this needs
no GitHub account and no Devin key. Three issues are picked up, including one
deliberate failure:

```
[2026-08-30T03:15:07+00:00] tick #4 -- 0 active / 2 succeeded / 1 failed
issue   status      pr      elapsed
#1      succeeded   #101    0m
#2      succeeded   #102    0m
#3      failed      #103    0m
```

Output lands in `data/report.md` and `data/state.json`, watermarked
`SIMULATED RUN`. Without Docker:
`pip install -r requirements.txt && SIMULATE=true python -m orchestrator.main`

## Run it for real

You need a fork of `apache/superset` with **Issues enabled** (forks have them
off), the **Devin GitHub App** granted access to it, a **fine-grained PAT**
scoped to the fork (Metadata read, Issues read and write, Pull requests read), a
**Devin service-user key** and org id, the `devin-fix` label, and some
unlabelled issues.

```bash
cp .env.example .env    # credentials and REPO_FULL_NAME
SIMULATE=false docker compose up --build
```

Then apply the label to one issue. Startup checks the token, repository
visibility, whether Issues are enabled and whether the label exists, and exits
naming what is missing — the mistakes that otherwise look like silence.

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_TOKEN`, `DEVIN_API_KEY`, `DEVIN_ORG_ID` | — | Credentials |
| `REPO_FULL_NAME` | `demo-user/superset` | The fork. `apache/superset` is rejected at startup |
| `DEFAULT_BRANCH` | `master` | Branch every PR must target |
| `TRIGGER_LABEL` | `devin-fix` | The label that means "delegate this" |
| `POLL_INTERVAL_SEC` | `30` | Tick interval |
| `SESSION_TIMEOUT_MIN` | `45` | Exceeded → the session is terminated |
| `MAX_ACU_LIMIT` | `10` | Per-session ACU ceiling requested from the Devin API |
| `MAX_CONCURRENT_SESSIONS` | `3` | Sessions allowed at once |
| `SIMULATE` | `false` | `true` → both integrations mocked |

Either everything is mocked or everything is live: a mock Devin pointed at a real
repository would comment on real issues, and a live Devin pointed at a mock
GitHub would spend credits while validation always passed.

## How it works

Three modules — `main.py` (loop, state, validation, config), `clients.py` (GitHub
and Devin, plus mocks), `report.py` — and one loop:

```
detect     labelled issues we have not seen yet
dispatch   create a Devin session, comment the session link
reconcile  poll each running session and close it out
report     regenerate report.md and print the live table
```

Nothing blocks on a session, so several can be in flight up to the concurrency
limit. Failures are caught per issue and again around the whole tick, so no
single error stops the loop; a failed request is simply retried next tick.

**Polling, not webhooks.** No inbound connectivity means this runs behind NAT and
anyone can reproduce it with `docker compose up`. It also fits the work: Devin has
no webhook announcing completion, so that side must be polled regardless. In
production you would swap the trigger for a webhook.

**Not Devin Automations.** Automations is the right answer for simple wiring, but
this needs to be a runnable repository, the reporting goes beyond per-automation
activity views, and "issue labelled" is not one of the GitHub triggers on offer
(checked 2026-08-25).

## What counts as success

`state.json` holds one record per issue with three statuses — `running`,
`succeeded`, `failed` — and a plain `error` string when something went wrong. A
task is `succeeded` only when:

```
the session finished
AND a pull request exists, is open, and is not a draft   (read from the GitHub API)
AND that PR targets REPO_FULL_NAME:DEFAULT_BRANCH        (machine-checked)
AND the agent reported verification_passed == true, listing the commands it ran
```

Everything else is `failed` with the reason recorded: the session errored, was
suspended, waited on a human, timed out, opened no PR, pointed the PR somewhere
unexpected, or failed its own verification. A session being stopped is only
closed out once `terminate` succeeds — otherwise the task stays `running` and the
next tick retries, because a running session is still spending credits.

Either way the label comes off: failures hand the issue back, successes drop the
"please work on this" signal. **One issue = one attempt, no automatic retry** —
re-applying the label does nothing, since the record stays in state.

Three signals are kept apart on purpose:

- **Agent verification** is *self-reported*. Its structured output is
  type-checked locally, because `bool("false")` is True in Python.
- **PR target validation** is *machine-checked* against the GitHub API, so a PR
  aimed at `apache/superset` — the default base for a fork — at another
  repository, or at a lookalike host is flagged, not counted.
- **Independent verification** is *not configured*: a fork has Actions disabled
  by default, so a human reviews every PR before merge. What that review actually
  consisted of is written down in
  [`results/verification.md`](results/verification.md) — each PR branch checked
  out into a clean worktree, acceptance criteria re-run, output recorded.

## Trust model

Issues in a public repository can be opened and edited by anyone, so issue data
is untrusted input. The target repository is pinned by config and cannot be
`apache/superset`. The issue's title, URL and body are JSON-serialized into the
prompt as untrusted request data, with the orchestrator's rules outside that JSON
taking precedence. The repository Devin may touch is named through the `repos`
API field, never left to the prompt. Agent-authored text is length-capped before
posting. The PR target is verified afterwards regardless of what the prompt said.
The orchestrator's PAT and Devin's GitHub App installation stay separate.

The approval gate is **GitHub label permissions** — applying a label needs triage
access or above. Prompt separation reduces risk; it is not a security boundary.

## Observability

*How would an engineering leader know this is working?* One file, regenerated
every tick: `data/report.md` has the active / succeeded / failed counts at the
top, then a row per issue — status, pull request, elapsed time, and on a failure,
why. That answers what is in flight, what landed, what did not, and how long it
took. Cost lives in Devin's own billing view, which the report points to. The same table prints to stdout, so a live
run is readable in the terminal. Both render from `state.json`, which is small
enough to `cat` and written atomically.

## Real-run results

[`results/issue-selection.md`](results/issue-selection.md) records the decision
the pipeline does not make: why these three issues and not the rest of what the
scanners reported, and the Ask Devin triage that ranked them — including the hole it
found in the acceptance criteria, and the one thing it got wrong. Raw scanner
output is in [`results/scan-evidence/`](results/scan-evidence/).

`results/report.md` holds the snapshot of the live run; every pull request and
session link in it is real. `results/verification.md` records the independent
check of each pull request — the commands re-run by hand, and their output.
Simulated output is never committed here.

## Known limitations

Scope choices for a working end-to-end demo, not oversights:

- **Duplicate prevention is best-effort.** State is written after Devin accepts
  the session, so a crash in between can leave an unknown session running.
- **Status delivery is best-effort.** The issue comment is posted before state is
  saved, so a crash in between can repeat a comment. The recorded outcome stays
  correct.
- **No automatic retry**, and **no independent verification** — agent-reported
  success is evidence, not proof.
- **Polling stops when the container stops**, and resumes from `state.json`.
  Deleting that file loses the history.
- **The Devin API response shape is confirmed on the first live call**; until
  then the client tolerates a couple of plausible field names.

## Production extensions

In priority order:

1. **Independent verification.** The agent's own check is currently the only
   check, which is why the report calls it self-reported. Merging CI check-run
   results into the signals — or a verifier job that re-runs the scanner on the
   PR branch — makes `succeeded` mean a green build.
2. **Close the detection loop.** A scheduled scanner (`pip-audit`, `npm audit`)
   filing the issues automatically. Nothing else changes.
3. **The controls for running it unattended.** Slack notifications, per-repo
   policy, and retries with attempt tracking. Plus a real budget: spend is only
   visible in Devin's billing view, not the API, so a budget gate has to read it
   from there — and reserve in-flight cost rather than count what is already
   spent.

Then: **durable delivery** (an outbox for comments, and a session id recorded
before the create call, closing the two best-effort gaps above), a **webhook
trigger**, **richer telemetry** (structured event log, run ids, lead-time
percentiles), and a trusted-author allowlist for issue sources.
