"""End-to-end scenarios: a real bug in, the bot's findings out.

The sandbox runs the bot with `strict: true`, so the expected findings follow the
strict criteria: steps, expected and actual count only when the description
itself states them. All texts are made up and mention no one: an @name in an
issue notifies that GitHub user.
"""

import re
from dataclasses import dataclass

import pytest

from sandbox import Findings, findings


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    body: str
    missing: frozenset[str] = frozenset()  # none: the bot calls the report complete
    hints: frozenset[str] = frozenset()  # must be there; others may be too
    environments: tuple[str, ...] = ()
    status: str = "Submitted"  # a status label on filing, if not the default

    @property
    def expected(self) -> Findings:
        return Findings(
            complete=not self.missing,
            missing=self.missing,
            environments=self.environments,
            status=self.status,
            hints=self.hints,
        )

    @property
    def labels(self) -> tuple[str, ...]:
        return () if self.status == "Submitted" else (self.status,)


STACKTRACE = "\n".join(
    [
        "```",
        "java.lang.NullPointerException: Cannot invoke"
        ' "com.parcelwise.track.Event.getStatus()" because "last" is null',
    ]
    + [
        f"\tat com.parcelwise.track.TimelineView.render(TimelineView.java:{n})"
        for n in range(80, 120)
    ]
    + ["```"]
)

SCENARIOS = [
    Scenario(
        "1. full template, optional fields left as hints",
        "Route planner drops the last stop after reordering",
        """### Build version

2.4.1 (build 1873)

### Steps to reproduce

1. Open Route planner for a route with five stops.
2. Drag the last stop to the top of the list.
3. Click Save.

### Actual result

The route is saved with four stops; the dragged stop is gone.

### Expected result

The route keeps all five stops in the new order.

### Workaround

<!-- Optional: how to get around the bug, if you know. -->

### Notes

<!-- Optional: anything else that helps. -->
""",
    ),
    Scenario(
        "2. template, steps and expected left empty",
        "Customs form total ignores the shipping cost",
        """### Build version

2.4.1 (build 1873)

### Steps to reproduce

_No response_

### Actual result

The customs form total is 24.90: the parcel value without the 6.50 shipping.

### Expected result

_No response_
""",
        frozenset({"steps", "expected"}),
    ),
    Scenario(
        "3. no template, one line without a symptom or a build",
        "PDF export is broken",
        "PDF export doesn't work for me since yesterday.",
        frozenset({"steps", "expected", "actual", "build_version"}),
    ),
    Scenario(
        "4. no template, only a long stack trace",
        "Tracking page crashes",
        STACKTRACE,
        frozenset({"steps", "expected", "build_version"}),
    ),
    Scenario(
        "5. title phrased as a task",
        "Fix the duplicate tracking emails",
        """### Build version

2.4.1 (build 1873)

### Steps to reproduce

1. Create a shipment with e-mail notifications on.
2. Mark it as Out for delivery.

### Actual result

The customer gets two identical "Out for delivery" e-mails.

### Expected result

One e-mail per status change.
""",
        hints=frozenset({"title_what"}),
    ),
    Scenario(
        "6a. actual result only as a screenshot",
        "Label preview cuts off the barcode",
        """### Build version

2.4.1 (build 1873)

### Steps to reproduce

1. Open a shipment.
2. Click Preview label.

### Actual result

![preview](https://github.com/user-attachments/assets/label-preview.png)

### Expected result

The whole barcode is visible in the preview.
""",
        hints=frozenset({"image_actual"}),
    ),
    Scenario(
        "6b. expected result only as a screenshot",
        "Invoice header shows the old company address",
        """### Build version

2.4.1 (build 1873)

### Steps to reproduce

1. Open Billing.
2. Download the invoice for September.

### Actual result

The header shows the old address, 12 Dock Road.

### Expected result

![mockup](https://github.com/user-attachments/assets/invoice-header.png)
""",
        hints=frozenset({"image_expected"}),
    ),
    Scenario(
        "7. build version is current prod",
        "Bulk relabel skips cancelled parcels",
        """### Build version

current prod

### Steps to reproduce

1. Select ten parcels, two of them cancelled.
2. Click Relabel.

### Actual result

Only eight labels are created; the cancelled parcels get none.

### Expected result

All ten parcels get a new label.
""",
        frozenset({"build_version"}),
        environments=("prod",),
    ),
    Scenario(
        "8. OS and browser in the build version field",
        "Address autocomplete freezes the checkout form",
        """### Build version

Windows 11, Chrome 120

### Steps to reproduce

1. Log in to staging.
2. Open Checkout and type "Main St" in the address field.

### Actual result

The form freezes for about 10 seconds after each key press.

### Expected result

Suggestions appear while typing, without delays.
""",
        frozenset({"build_version"}),
        environments=("staging",),
    ),
    Scenario(
        "9. expected result asked as a question to a colleague",
        "Parcel list sorted by date starts from 2019",
        """Build 2.4.1 (build 1873)

Steps to reproduce:
1. Log in as a dispatcher with parcels from 2019 to 2026.
2. Open Parcels.
3. Click the Date column header to sort by date.

Actual: the list starts with parcels from 2019.

Dana, shouldn't the newest be on top?
""",
        frozenset({"expected"}),
    ),
    Scenario(
        "10. filed straight into In Progress",
        "Pickup slots show yesterday's date",
        """### Build version

latest

### Steps to reproduce

1. Open Pickups.
2. Click Book a pickup.

### Actual result

The slot list is headed with yesterday's date.

### Expected result

Today's date heads the slot list.
""",
        frozenset({"build_version"}),
        status="In Progress",
    ),
]

# Scenario 11. On GitHub a status is a label and an unknown label is no status, so an
# open bug is always in a checked status; the bug leaves them when it is closed.
CLOSED_TITLE = "Return label prints the sender's address twice"
CLOSED_BODY = """### Build version

latest

### Steps to reproduce

1. Open a delivered shipment.
2. Click Create return label.

### Actual result

The sender's address is printed in both address boxes.

### Expected result

The customer's address is in the sender box.
"""
CLOSED_EDIT = CLOSED_BODY.replace(
    "1. Open a delivered shipment.\n2. Click Create return label.\n", ""
)


def test_scenarios_mention_no_one():
    mention = re.compile(r"(?<![\w`])@[A-Za-z0-9-]")
    texts = {s.id: s.title + s.body for s in SCENARIOS}
    texts["11"] = CLOSED_TITLE + CLOSED_BODY
    assert not [i for i, text in texts.items() if mention.search(text)]


@pytest.mark.e2e
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id.split(".")[0])
def test_scenario(scenario, new_bug, sandbox, record_property):
    record_property("scenario", scenario.id)
    record_property("expected", str(scenario.expected))
    number = new_bug(scenario.title, scenario.body, scenario.labels)
    found = findings(sandbox.wait_for_bot_comment(number)["body"])
    record_property("found", str(found))
    assert found == scenario.expected
    assert scenario.hints <= found.hints


@pytest.mark.e2e
def test_closed_bug_is_not_checked(new_bug, sandbox, record_property):
    """The bot runs on the edit but stays silent: its comment does not change,
    though the edit drops the steps."""
    record_property("scenario", "11. closed, then edited: out of the checked statuses")
    record_property("expected", "bot ran, comment unchanged")
    number = new_bug(CLOSED_TITLE, CLOSED_BODY)
    before = sandbox.wait_for_bot_comment(number)
    sandbox.close(number)
    runs = sandbox.wait_for_bot_runs(
        CLOSED_TITLE, since=sandbox.edit(number, CLOSED_EDIT)
    )
    after = sandbox.bot_comment(number)
    conclusions = ", ".join(r["conclusion"] for r in runs)
    unchanged = "comment unchanged" if after == before else "comment changed"
    record_property("found", f"bot ran ({conclusions}), {unchanged}")
    assert [r["conclusion"] for r in runs] == ["success"]
    assert after == before
