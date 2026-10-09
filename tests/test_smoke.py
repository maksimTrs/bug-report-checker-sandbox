import pytest

BODY = """### Build version

2.4.1 (build 1873)

### Steps to reproduce

1. Open an order with two parcels.
2. Click "Print labels".

### Actual result

Only the first parcel's label is printed.

### Expected result

A label for each parcel.
"""


@pytest.mark.e2e
def test_bot_comments_on_a_new_bug(new_bug, sandbox):
    number = new_bug("Print labels skips the second parcel", BODY)
    comment = sandbox.wait_for_bot_comment(number)
    assert comment["user"]["login"] == "github-actions[bot]"
