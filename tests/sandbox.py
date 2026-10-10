"""The sandbox repository through the GitHub REST API, for end-to-end tests.

A test files a real bug, waits for the bot's comment, reads its findings and
closes the bug. The bot
runs only on issues opened with a user's token: events from a workflow's
GITHUB_TOKEN start no workflows. Every issue filed here carries the `e2e` label,
so one left open by a killed run is closed by the next run.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

API = "https://api.github.com"
API_VERSION = "2022-11-28"
REPO = "maksimTrs/bug-report-checker-sandbox"
E2E_LABEL = "e2e"
BOT_MARKER = "<!-- bug-report-checker fingerprint="
BOT_WORKFLOW = "bug-checker.yml"
PER_PAGE = 100  # the REST API maximum
# The bot's job: ~1.5 min with a cold model cache, under 1 min warm, plus the queue.
WAIT = 300
POLL = 5


def client(token: str) -> httpx.Client:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }
    return httpx.Client(base_url=API, headers=headers, timeout=30)


class Sandbox:
    def __init__(
        self,
        client: httpx.Client,
        repo: str = REPO,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client
        self.path = f"/repos/{repo}/issues"
        self.runs = f"/repos/{repo}/actions/workflows/{BOT_WORKFLOW}/runs"
        self.clock, self.sleep = clock, sleep

    def open_bug(self, title: str, body: str, labels: tuple[str, ...] = ()) -> int:
        r = self.client.post(
            self.path,
            json={"title": title, "body": body, "labels": ["bug", E2E_LABEL, *labels]},
        )
        r.raise_for_status()
        return r.json()["number"]

    def close(self, number: int) -> None:
        r = self.client.patch(
            f"{self.path}/{number}",
            json={"state": "closed", "state_reason": "completed"},
        )
        r.raise_for_status()

    def edit(self, number: int, body: str) -> str:
        """When GitHub recorded the edit, by its clock: the bot's run starts later."""
        r = self.client.patch(f"{self.path}/{number}", json={"body": body})
        r.raise_for_status()
        return r.json()["updated_at"]

    def wait_for_bot_runs(
        self, title: str, since: str, timeout: float = WAIT
    ) -> list[dict]:
        """The bot's runs for issue events on `title` since `since`, once all have
        finished: proof the bot saw an event even when it stays silent."""
        deadline = self.clock() + timeout
        while True:
            r = self.client.get(
                self.runs,
                params={
                    "event": "issues",
                    "created": f">={since}",
                    "per_page": PER_PAGE,
                },
            )
            r.raise_for_status()
            runs = [x for x in r.json()["workflow_runs"] if x["display_title"] == title]
            if runs and all(x["status"] == "completed" for x in runs):
                return runs
            if self.clock() >= deadline:
                raise TimeoutError(
                    f"no finished bot run for {title!r} after {timeout:.0f} s"
                )
            self.sleep(POLL)

    def bot_comment(self, number: int) -> dict | None:
        page = 1
        while True:
            r = self.client.get(
                f"{self.path}/{number}/comments",
                params={"per_page": PER_PAGE, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            for comment in batch:
                if BOT_MARKER in (comment["body"] or ""):
                    return comment
            if len(batch) < PER_PAGE:
                return None
            page += 1

    def wait_for_bot_comment(self, number: int, timeout: float = WAIT) -> dict:
        deadline = self.clock() + timeout
        while True:
            comment = self.bot_comment(number)
            if comment:
                return comment
            if self.clock() >= deadline:
                raise TimeoutError(f"no bot comment on #{number} after {timeout:.0f} s")
            self.sleep(POLL)

    def stale_e2e_issues(self, older_than: timedelta = timedelta(hours=1)) -> list[int]:
        """Open e2e issues no running test can still own: a parallel run's are fresh."""
        r = self.client.get(
            self.path,
            params={"labels": E2E_LABEL, "state": "open", "per_page": PER_PAGE},
        )
        r.raise_for_status()
        cutoff = datetime.now(UTC) - older_than
        return [
            i["number"]
            for i in r.json()
            if "pull_request" not in i
            and datetime.fromisoformat(i["created_at"]) < cutoff
        ]


# The bot's comment, as comment.py in bug-report-checker writes it: blockers by name.
CHECKS = {
    "Steps to reproduce": "steps",
    "Expected result": "expected",
    "Actual result": "actual",
    "Build version": "build_version",
}
HINTS = {  # the start of each suggestion
    "Say in the title what is wrong": "title_what",
    "Name in the title where": "title_where",
    "Name in the title when": "title_when",
    "Describe the actual result in text too": "image_actual",
    "Describe the expected result in text too": "image_expected",
}
_MISSING = re.compile(r"^- \*\*(.+?)\*\*:", re.M)
_UNSURE = re.compile(r"^Not sure about: (.+?)\. Please", re.M)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HINT = re.compile(r"^- (.+)$", re.M)
_ENVIRONMENT = re.compile(r"Environment: (.+?)\.</sub>")
_STATUS = re.compile(r"Checked in status \*\*(.+?)\*\*")


def _hint(text: str) -> str:
    for start, key in HINTS.items():
        if text.startswith(start):
            return key
    raise KeyError(text)


@dataclass(frozen=True)
class Findings:
    complete: bool
    missing: frozenset[str] = frozenset()
    unsure: frozenset[str] = frozenset()
    long: bool = False  # read in parts: the bot says it could not confirm details
    environments: tuple[str, ...] = ()
    status: str = "Submitted"  # the status the bot checked the bug in
    # Soft and noisy: a scenario checks the hints it needs are there, no more.
    hints: frozenset[str] = field(default=frozenset(), compare=False)

    def __str__(self) -> str:
        if self.complete:
            parts = ["complete"]
        else:
            parts = [f"missing {', '.join(sorted(self.missing))}"] * bool(self.missing)
            parts += [f"unsure {', '.join(sorted(self.unsure))}"] * bool(self.unsure)
        parts[-1] += " (read in parts)" * self.long
        parts += [f"hints {', '.join(sorted(self.hints))}"] * bool(self.hints)
        env = ", ".join(self.environments)
        parts += [f"environment {env}"] * bool(env)
        parts += [f"in {self.status}"] * (self.status != "Submitted")
        return "; ".join(parts)


def findings(body: str) -> Findings:
    """An unknown check or hint, or no status, raises KeyError: the comment format
    has changed."""
    main, _, folded = body.partition("<details>")  # the suggestions are folded
    unsure = _UNSURE.search(main)
    env = _ENVIRONMENT.search(body)
    status = _STATUS.search(body)
    if not status:
        raise KeyError("no status in the comment's footer")
    return Findings(
        complete="Bug report complete." in main,
        missing=frozenset(CHECKS[name] for name in _MISSING.findall(main)),
        unsure=frozenset(CHECKS[n] for n in _BOLD.findall(unsure[1]))
        if unsure
        else frozenset(),
        long="read in parts" in main,
        environments=tuple(env[1].split(", ")) if env else (),
        status=status[1],
        hints=frozenset(_hint(h) for h in _HINT.findall(folded)),
    )


def summary_table(rows: list[dict]) -> str:
    """The e2e report for the Job Summary: scenario -> issue -> bot -> result."""
    lines = [
        "## E2E scenarios",
        "",
        "| Scenario | Issue | Expected | Bot found | Result |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        issue = f"[#{r['issue']}](https://github.com/{REPO}/issues/{r['issue']})"
        result = "✅ pass" if r["passed"] else "❌ fail"
        lines.append(
            f"| {r['scenario']} | {issue} | {r['expected']} | {r['found']} | {result} |"
        )
    return "\n".join(lines) + "\n"
