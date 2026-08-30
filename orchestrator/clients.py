"""GitHub and Devin API clients, plus the mocks that back simulate mode.

Both clients are thin: the orchestrator only moves metadata (issues, labels,
comments, session ids). It never runs git, never clones the repository and never
touches application code -- all of that happens inside the Devin session.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_HOST = "github.com"
DEVIN_API = "https://api.devin.ai"
HTTP_TIMEOUT = 30
UPSTREAM_REPO = "apache/superset"

# Resolved relative to the package, not the working directory.
FIXTURES_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "issues.json"


class ApiError(RuntimeError):
    """An API call failed. `status` is the HTTP status when there was one."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


def canonical_pr_url(repo: str, number: int) -> str:
    return f"https://{GITHUB_HOST}/{repo}/pull/{number}"


def parse_pr_url(url: str) -> tuple[str, int] | None:
    """-> (owner/repo, number), or None if this is not a github.com PR URL.

    Scheme and host are checked, not just the path: the URL comes from a session
    working on an issue body we treat as untrusted, so a lookalike host must not
    be accepted.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname != GITHUB_HOST:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 4 or parts[2] != "pull":
        return None
    try:
        number = int(parts[3])
    except ValueError:
        return None
    return (f"{parts[0]}/{parts[1]}", number) if number > 0 else None


class GitHubClient:
    def __init__(self, token: str | None, repo: str) -> None:
        self.repo = repo
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        """One request, no retries. A failed tick is simply retried by the loop."""
        url = f"{GITHUB_API}/repos/{self.repo}{path}"
        try:
            response = self._session.request(
                method, url, timeout=HTTP_TIMEOUT, **kwargs
            )
        except requests.RequestException as exc:
            raise ApiError(f"GitHub {method} {path}: {exc}") from exc
        if response.status_code in (404, 422):
            return None
        if not response.ok:
            raise ApiError(
                f"GitHub {method} {path} -> {response.status_code}: "
                f"{response.text[:300]}",
                response.status_code,
            )
        return response.json() if response.content else None

    def repository(self) -> dict[str, Any] | None:
        return self._call("GET", "")

    def label_exists(self, label: str) -> bool:
        return self._call("GET", f"/labels/{label}") is not None

    def labeled_issues(self, label: str) -> list[dict[str, Any]]:
        """Open issues with the trigger label.

        The Issues API also returns pull requests, so anything carrying a
        `pull_request` key is dropped.
        """
        data = self._call(
            "GET", "/issues", params={"labels": label, "state": "open", "per_page": 100}
        )
        return [item for item in (data or []) if "pull_request" not in item]

    def comment(self, issue_number: int, body: str) -> None:
        self._call("POST", f"/issues/{issue_number}/comments", json={"body": body})

    def remove_label(self, issue_number: int, label: str) -> None:
        self._call("DELETE", f"/issues/{issue_number}/labels/{label}")

    def pull_request(self, number: int) -> dict[str, Any] | None:
        """Fetch a PR *from the configured repository*.

        Asking our own repo for the number is deliberate: a PR that lives
        somewhere else simply will not be found here.
        """
        return self._call("GET", f"/pulls/{number}")

    def token_login(self) -> str | None:
        try:
            response = self._session.get(f"{GITHUB_API}/user", timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise ApiError(f"GitHub GET /user: {exc}") from exc
        return response.json().get("login") if response.ok else None


# ---------------------------------------------------------------------------
# Devin
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """One session as the orchestrator needs to see it."""

    id: str
    url: str | None
    status: str
    status_detail: str | None
    pr_url: str | None
    verification_passed: bool | None
    verification: list[str]
    summary: str
    acu: float

    @property
    def finished(self) -> bool:
        return self.status == "exit" or self.status_detail == "finished"

    @property
    def needs_human(self) -> bool:
        return self.status_detail in ("waiting_for_user", "waiting_for_approval")

    @property
    def broken(self) -> str | None:
        """A reason string when the session itself ended badly."""
        if self.status == "error":
            return "session reported an error"
        if self.status == "suspended":
            return f"session was suspended ({self.status_detail or 'no detail'})"
        return None


def _first(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _pr_url(payload: Any) -> str | None:
    """`pull_requests` may hold URLs or objects; accept either."""
    for item in payload or []:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            url = _first(item, "html_url", "url", "pr_url")
            if url:
                return url
    return None


class DevinClient:
    def __init__(self, api_key: str | None, org_id: str | None, max_acu: int) -> None:
        self._base = f"{DEVIN_API}/v3/organizations/{org_id}"
        self._max_acu = max_acu
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            response = self._session.request(
                method,
                f"{self._base}{path}",
                timeout=HTTP_TIMEOUT,
                data=json.dumps(body) if body else None,
            )
        except requests.RequestException as exc:
            raise ApiError(f"Devin {method} {path}: {exc}") from exc
        if not response.ok:
            raise ApiError(
                f"Devin {method} {path} -> {response.status_code}: "
                f"{response.text[:300]}",
                response.status_code,
            )
        return response.json() if response.content else None

    def create_session(self, prompt: str, repo: str, issue_number: int) -> Session:
        data = (
            self._call(
                "POST",
                "/sessions",
                {
                    "prompt": prompt,
                    # Which repository Devin may touch is named at the API
                    # level, never left to the prompt alone.
                    "repos": [repo],
                    "max_acu_limit": self._max_acu,
                    "resumable": False,
                    "structured_output_required": True,
                    "structured_output_schema": OUTPUT_SCHEMA,
                    "tags": ["orchestrator", f"issue-{issue_number}"],
                },
            )
            or {}
        )
        session = self._to_session(data)
        if not session.id:
            raise ApiError(f"No session id in the create response: keys={sorted(data)}")
        return session

    def get_session(self, session_id: str) -> Session:
        return self._to_session(self._call("GET", f"/sessions/{session_id}") or {})

    def terminate(self, session_id: str) -> bool:
        """True when nothing is left running remotely."""
        try:
            self._call("DELETE", f"/sessions/{session_id}")
            return True
        except ApiError as exc:
            if exc.status in (404, 410):
                return True  # already gone
            log.error("Terminate failed for %s: %s", session_id, exc)
            return False

    @staticmethod
    def _to_session(data: dict[str, Any]) -> Session:
        output = data.get("structured_output")
        output = output if isinstance(output, dict) else {}
        verification = output.get("verification")
        return Session(
            id=_first(data, "session_id", "devin_id", "id") or "",
            url=_first(data, "url", "session_url", "web_url"),
            status=data.get("status") or "new",
            status_detail=data.get("status_detail"),
            pr_url=_pr_url(data.get("pull_requests")),
            # Kept as-is rather than coerced: `bool("false")` is True, so the
            # caller type-checks it before trusting it.
            verification_passed=output.get("verification_passed"),
            verification=verification if isinstance(verification, list) else [],
            summary=str(output.get("summary") or ""),
            acu=float(data.get("acus_consumed") or 0),
        )


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "verification_passed": {"type": "boolean"},
        "verification": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "verification_passed", "verification"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Mocks -- simulate mode
# ---------------------------------------------------------------------------


class MockGitHubClient:
    """Serves fixtures/issues.json; comments and label changes are logged only."""

    def __init__(self, repo: str) -> None:
        self.repo = repo
        self._issues: list[dict[str, Any]] = json.loads(
            FIXTURES_PATH.read_text(encoding="utf-8")
        )
        self._removed: set[int] = set()

    def repository(self) -> dict[str, Any]:
        return {"has_issues": True, "default_branch": "master"}

    def label_exists(self, label: str) -> bool:
        return True

    def labeled_issues(self, label: str) -> list[dict[str, Any]]:
        return [
            issue
            for issue in self._issues
            if issue["number"] not in self._removed
            and label in [lab["name"] for lab in issue.get("labels", [])]
        ]

    def comment(self, issue_number: int, body: str) -> None:
        log.info("[simulate] comment on #%s:\n%s", issue_number, body)

    def remove_label(self, issue_number: int, label: str) -> None:
        self._removed.add(issue_number)
        log.info("[simulate] removed %s from #%s", label, issue_number)

    def pull_request(self, number: int) -> dict[str, Any]:
        return {
            "number": number,
            "html_url": canonical_pr_url(self.repo, number),
            "state": "open",
            "draft": False,
            "base": {"repo": {"full_name": self.repo}, "ref": "master"},
        }

    def token_login(self) -> str:
        return "simulated-bot"


class MockDevinClient:
    """Mirrors what the real API actually does, so simulate mode cannot hide
    bugs that only live runs would reveal:

    - a session that has opened its PR reports `waiting_for_user`, not
      `finished` — it is waiting for further instructions, not blocked
    - `acus_consumed` comes back as 0.0 on credit-based plans

    Issue numbers divisible by 3 report verification_passed=false, so a
    simulated run exercises both the success and the failure path.
    """

    def __init__(self, repo: str) -> None:
        self._repo = repo
        self._polls: dict[str, int] = {}
        self._issue: dict[str, int] = {}

    def create_session(self, prompt: str, repo: str, issue_number: int) -> Session:
        session_id = f"devin-simulated-{issue_number:03d}"
        self._polls[session_id] = 0
        self._issue[session_id] = issue_number
        log.info("[simulate] created %s for issue #%s", session_id, issue_number)
        return Session(
            id=session_id,
            url=f"https://app.devin.ai/sessions/{session_id}",
            status="running",
            status_detail="working",
            pr_url=None,
            verification_passed=None,
            verification=[],
            summary="",
            acu=0.0,
        )

    def get_session(self, session_id: str) -> Session:
        self._polls[session_id] += 1
        issue_number = self._issue[session_id]
        working = self._polls[session_id] < 2
        passed = issue_number % 3 != 0
        return Session(
            id=session_id,
            url=f"https://app.devin.ai/sessions/{session_id}",
            status="running",
            # Not "finished": a real session parks in waiting_for_user once the
            # PR is up. The orchestrator has to decide on the PR, not the label.
            status_detail="working" if working else "waiting_for_user",
            pr_url=None if working else canonical_pr_url(self._repo, 100 + issue_number),
            verification_passed=None if working else passed,
            verification=[] if working else ["npm audit"],
            summary=(
                ""
                if working
                else f"[simulated] remediated #{issue_number}"
                if passed
                else f"[simulated] npm audit still reports the advisory on #{issue_number}"
            ),
            acu=0.0,
        )

    def terminate(self, session_id: str) -> bool:
        log.info("[simulate] terminated %s", session_id)
        return True
