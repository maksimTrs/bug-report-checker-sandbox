import os
import re
import subprocess

import pytest

from sandbox import Sandbox, client, summary_table

_REPORT = []  # one row per scenario, for the Job Summary


def _token() -> str:
    """CI: a fine-grained PAT in E2E_TOKEN. Locally: the gh login."""
    if token := os.environ.get("E2E_TOKEN"):
        return token
    try:
        gh = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.fail("e2e tests need E2E_TOKEN or a gh login")
    return gh.stdout.strip()


@pytest.fixture(scope="session")
def sandbox():
    with client(_token()) as c:
        box = Sandbox(c)
        for number in box.stale_e2e_issues():
            box.close(number)
        yield box


@pytest.fixture
def new_bug(sandbox, record_property):
    """Files bugs for one test and closes them after it, pass or fail."""
    opened = []

    def open_bug(title: str, body: str, labels: tuple[str, ...] = ()) -> int:
        number = sandbox.open_bug(title, body, labels)
        opened.append(number)
        record_property("issue", number)
        return number

    yield open_bug
    for number in opened:
        sandbox.close(number)


def pytest_runtest_logreport(report):
    props = dict(report.user_properties)
    if report.when == "call" and "scenario" in props and "issue" in props:
        _REPORT.append(
            {
                "scenario": props["scenario"],
                "issue": props["issue"],
                "expected": props["expected"],
                "found": props.get("found", "no comment"),
                "passed": report.passed,
            }
        )


def _order(row: dict) -> tuple[int, str]:
    """Scenario number first: 2 before 10, 6a before 6b."""
    return int(re.match(r"\d+", row["scenario"])[0]), row["scenario"]


def pytest_terminal_summary(terminalreporter):
    """In CI the scenarios' table goes to the run's Job Summary. Under xdist only
    the controller writes it: workers send it their reports, in finishing order."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path and _REPORT and "PYTEST_XDIST_WORKER" not in os.environ:
        with open(path, "a", encoding="utf-8") as f:
            f.write(summary_table(sorted(_REPORT, key=_order)))
