"""The sandbox repository through the GitHub REST API, for end-to-end tests.

A test files a real bug, waits for the bot's comment and closes the bug. The bot
runs only on issues opened with a user's token: events from a workflow's
GITHUB_TOKEN start no workflows. Every issue filed here carries the `e2e` label,
so one left open by a killed run is closed by the next run.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

API = "https://api.github.com"
API_VERSION = "2022-11-28"
REPO = "maksimTrs/bug-report-checker-sandbox"
E2E_LABEL = "e2e"
BOT_MARKER = "<!-- bug-report-checker fingerprint="
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
