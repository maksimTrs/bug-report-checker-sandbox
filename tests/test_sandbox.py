"""The e2e client against a fake GitHub API: no network, no waiting."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from sandbox import API, POLL, Sandbox

BOT = {"id": 9, "body": "Missing: ...\n\n<!-- bug-report-checker fingerprint=ab12 -->"}
USER = {"id": 8, "body": "Looks like a duplicate."}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def sandbox(handler) -> tuple[Sandbox, FakeClock]:
    clock = FakeClock()
    c = httpx.Client(base_url=API, transport=httpx.MockTransport(handler))
    return Sandbox(c, repo="o/r", clock=clock, sleep=clock.sleep), clock


def test_open_bug_files_a_labelled_bug():
    sent = []

    def handler(request):
        sent.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={"number": 7})

    box, _ = sandbox(handler)
    assert box.open_bug("Title", "Body", ("In Progress",)) == 7
    assert sent == [
        (
            "POST",
            "/repos/o/r/issues",
            {"title": "Title", "body": "Body", "labels": ["bug", "e2e", "In Progress"]},
        )
    ]


def test_close_marks_the_issue_completed():
    sent = []

    def handler(request):
        sent.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={})

    box, _ = sandbox(handler)
    box.close(7)
    assert sent == [
        (
            "PATCH",
            "/repos/o/r/issues/7",
            {"state": "closed", "state_reason": "completed"},
        )
    ]


def test_bot_comment_is_found_by_its_marker_on_a_later_page():
    def handler(request):
        page = request.url.params["page"]
        return httpx.Response(200, json=[USER] * 100 if page == "1" else [USER, BOT])

    box, _ = sandbox(handler)
    assert box.bot_comment(7) == BOT


def test_wait_polls_until_the_bot_comments():
    replies = iter([[], [USER], [USER, BOT]])
    box, clock = sandbox(lambda request: httpx.Response(200, json=next(replies)))
    assert box.wait_for_bot_comment(7) == BOT
    assert clock.now == 2 * POLL


def test_wait_gives_up_at_the_timeout():
    box, clock = sandbox(lambda request: httpx.Response(200, json=[USER]))
    with pytest.raises(TimeoutError, match="#7 after 60 s"):
        box.wait_for_bot_comment(7, timeout=60)
    assert clock.now == 60


def test_stale_e2e_issues_skip_fresh_ones_and_pull_requests():
    now = datetime.now(UTC)

    def issue(number, age, **extra):
        return {"number": number, "created_at": (now - age).isoformat(), **extra}

    def handler(request):
        assert request.url.params["labels"] == "e2e"
        assert request.url.params["state"] == "open"
        return httpx.Response(
            200,
            json=[
                issue(1, timedelta(hours=2)),
                issue(2, timedelta(minutes=5)),  # a parallel run's
                issue(3, timedelta(hours=2), pull_request={}),
            ],
        )

    box, _ = sandbox(handler)
    assert box.stale_e2e_issues() == [1]
