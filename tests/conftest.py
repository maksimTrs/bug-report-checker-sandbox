import os
import subprocess

import pytest

from sandbox import Sandbox, client


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
def new_bug(sandbox):
    """Files bugs for one test and closes them after it, pass or fail."""
    opened = []

    def open_bug(title: str, body: str, labels: tuple[str, ...] = ()) -> int:
        number = sandbox.open_bug(title, body, labels)
        opened.append(number)
        return number

    yield open_bug
    for number in opened:
        sandbox.close(number)
