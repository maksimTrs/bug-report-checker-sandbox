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

    @property
    def expected(self) -> Findings:
        return Findings(
            complete=not self.missing,
            missing=self.missing,
            environments=self.environments,
            hints=self.hints,
        )


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
]


def test_scenarios_mention_no_one():
    mention = re.compile(r"(?<![\w`])@[A-Za-z0-9-]")
    assert not [s.id for s in SCENARIOS if mention.search(s.title + s.body)]


@pytest.mark.e2e
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id.split(".")[0])
def test_scenario(scenario, new_bug, sandbox, record_property):
    record_property("scenario", scenario.id)
    record_property("expected", str(scenario.expected))
    number = new_bug(scenario.title, scenario.body)
    found = findings(sandbox.wait_for_bot_comment(number)["body"])
    record_property("found", str(found))
    assert found == scenario.expected
    assert scenario.hints <= found.hints
