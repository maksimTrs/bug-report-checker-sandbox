"""End-to-end scenarios: a real bug in, the bot's findings out.

The sandbox runs the bot with `strict: true`, so the expected findings follow the
strict criteria: steps, expected and actual count only when the description
itself states them. All texts are made up.
"""

from dataclasses import dataclass

import pytest

from sandbox import Findings, findings


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    body: str
    missing: frozenset[str] = frozenset()  # none: the bot calls the report complete

    @property
    def expected(self) -> Findings:
        return Findings(complete=not self.missing, missing=self.missing)


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
]


@pytest.mark.e2e
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id.split(".")[0])
def test_scenario(scenario, new_bug, sandbox, record_property):
    record_property("scenario", scenario.id)
    record_property("expected", str(scenario.expected))
    number = new_bug(scenario.title, scenario.body)
    found = findings(sandbox.wait_for_bot_comment(number)["body"])
    record_property("found", str(found))
    assert found == scenario.expected
