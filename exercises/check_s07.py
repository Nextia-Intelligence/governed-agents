"""Checks for exercise 7. Run: uv run pytest exercises/check_s07.py -q"""

import pytest

from bluekite.governance.audit import redact_text


@pytest.mark.parametrize("phone", ["+1 416 555 0199", "416-555-0199",
                                   "(416) 555-0199"])
def test_phone_numbers_are_removed(db, phone):
    assert redact_text(db, f"Call me on {phone} please") == "Call me on [phone] please"


def test_ids_and_money_stay(db):
    text = "Order O-5002 of C-102 in run r-0001: refund $2,000.00"
    assert redact_text(db, text) == text
