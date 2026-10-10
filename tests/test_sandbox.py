"""The e2e client against a fake GitHub API: no network, no waiting."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from sandbox import API, POLL, Findings, Sandbox, findings, summary_table

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


# Comments as the bot renders them (comment.py in bug-report-checker).
COMPLETE = (
    "✅ **Bug report complete.**\n\n"
    "<sub>Checked in status **Submitted** by bug-report-checker.</sub>"
)
MISSING = """**Some details are missing from this bug report.**

Missing:
- **Steps to reproduce**: list at least two steps.
- **Build version**: name the exact build.

Not sure about: **Actual result**, **Expected result**. Please check them yourself.

This report is long and was read in parts, so details could not be confirmed.

<details>
<summary>Suggestions (2)</summary>

- Say in the title what is wrong, not what to do.
- Describe the actual result in text too, not only as a screenshot.

</details>

<sub>Checked in status **Submitted** by bug-report-checker.\
 Environment: staging, prod.</sub>"""


def test_findings_of_a_complete_report():
    assert findings(COMPLETE) == Findings(complete=True)


def test_findings_read_blockers_hints_and_environment():
    found = findings(MISSING)
    assert found == Findings(
        complete=False,
        missing=frozenset({"steps", "build_version"}),
        unsure=frozenset({"actual", "expected"}),
        long=True,
        environments=("staging", "prod"),
    )
    assert found.hints == frozenset({"title_what", "image_actual"})


def test_hints_do_not_decide_equality():
    # Soft and noisy: a scenario names the hints it needs, not all of them.
    assert Findings(complete=True, hints=frozenset({"title_when"})) == Findings(
        complete=True
    )


@pytest.mark.parametrize(
    "body",
    [
        "Missing:\n- **Severity**: say how bad it is.",
        "<details>\n\n- Attach the logs.\n\n</details>",
    ],
)
def test_findings_fail_loudly_on_an_unknown_check_or_hint(body):
    with pytest.raises(KeyError):
        findings(body)


@pytest.mark.parametrize(
    ("found", "text"),
    [
        (Findings(complete=True), "complete"),
        (
            Findings(complete=False, missing=frozenset({"steps", "expected"})),
            "missing expected, steps",
        ),
        (
            Findings(complete=False, unsure=frozenset({"actual"}), long=True),
            "unsure actual (read in parts)",
        ),
        (
            Findings(
                complete=True,
                hints=frozenset({"title_when", "image_actual"}),
                environments=("prod",),
            ),
            "complete; hints image_actual, title_when; environment prod",
        ),
    ],
)
def test_findings_as_text(found, text):
    assert str(found) == text


def test_summary_table_links_issues_and_marks_results():
    table = summary_table(
        [
            {
                "scenario": "1. full",
                "issue": 15,
                "expected": "complete",
                "found": "complete",
                "passed": True,
            },
            {
                "scenario": "3. one line",
                "issue": 16,
                "expected": "missing steps",
                "found": "no comment",
                "passed": False,
            },
        ]
    )
    lines = table.splitlines()
    assert lines[0] == "## E2E scenarios"
    assert lines[4] == (
        "| 1. full | [#15](https://github.com/maksimTrs/bug-report-checker-sandbox"
        "/issues/15) | complete | complete | ✅ pass |"
    )
    assert lines[5].endswith("| missing steps | no comment | ❌ fail |")
