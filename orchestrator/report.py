"""Reporting: a Markdown file for the record, a table on stdout while it runs.

Both are rendered from state.json, so there is only one source of truth to keep
consistent.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _elapsed(task: dict[str, Any]) -> str:
    start, end = task.get("started_at"), task.get("finished_at") or _now()
    if not start:
        return "--"
    minutes = (
        datetime.fromisoformat(end) - datetime.fromisoformat(start)
    ).total_seconds() / 60
    return f"{minutes:.0f}m"


def _counts(state: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {"running": 0, "succeeded": 0, "failed": 0}
    for task in state.values():
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    return counts


def render_report(config: Any, state: dict[str, dict[str, Any]]) -> str:
    counts = _counts(state)
    lines = ["# Remediation run report", ""]
    if config.simulate:
        lines += [
            "> **SIMULATED RUN** -- no session or pull request below is real.",
            "",
        ]
    lines += [
        f"- Repository: `{config.repo}` (base branch `{config.branch}`)",
        f"- Generated: {_now()}",
        "",
        "## Summary",
        "",
        f"- Active: **{counts['running']}**",
        f"- Succeeded: **{counts['succeeded']}**",
        f"- Failed: **{counts['failed']}**",
        # Cost is deliberately absent: the API's `acus_consumed` reads 0 on
        # credit-based plans, and Devin bills in dollars only in its own billing
        # view. Reporting a number we cannot obtain would be worse than saying
        # where the number actually lives.
        "- Session cost: see Devin's billing view (the API does not expose it)",
        "",
        "## Tasks",
        "",
        "| Issue | Status | PR | Elapsed | Detail |",
        "|---|---|---|---|---|",
    ]
    for number, task in sorted(state.items(), key=lambda kv: int(kv[0])):
        pr = task.get("pr_url")
        pr_cell = f"[link]({pr})" if pr else "--"
        lines.append(
            f"| #{number} | {task['status']} | {pr_cell} | {_elapsed(task)} "
            f"| {task.get('error') or ''} |"
        )
    if not state:
        lines.append("| _nothing detected yet_ | | | | |")
    lines += [
        "",
        "Agent verification is self-reported by the session. PR target validation "
        "is checked against the GitHub API. Independent verification (CI) is not "
        "configured, so a human reviews every PR before merge.",
        "",
    ]
    return "\n".join(lines)


def write_report(config: Any, state: dict[str, dict[str, Any]]) -> None:
    path: Path = config.data_dir / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".report-", delete=False
    )
    try:
        with handle:
            handle.write(render_report(config, state))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


_COLUMNS = (("issue", 6), ("status", 10), ("pr", 6), ("elapsed", 8))


def render_terminal(state: dict[str, dict[str, Any]], tick_number: int) -> str:
    counts = _counts(state)
    lines = [
        f"[{_now()}] tick #{tick_number} -- {counts['running']} active / "
        f"{counts['succeeded']} succeeded / {counts['failed']} failed",
        "  ".join(name.ljust(width) for name, width in _COLUMNS),
    ]
    for number, task in sorted(state.items(), key=lambda kv: int(kv[0])):
        pr = task.get("pr_url")
        values = (
            f"#{number}",
            task["status"],
            "#" + pr.rsplit("/", 1)[-1] if pr else "--",
            _elapsed(task),
        )
        lines.append(
            "  ".join(v[:w].ljust(w) for v, (_, w) in zip(values, _COLUMNS))
        )
    if not state:
        lines.append("  (waiting for a labelled issue)")
    return "\n".join(lines)
