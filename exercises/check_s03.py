"""Checks for exercise 3. Run: uv run pytest exercises/check_s03.py -q"""

import pytest

from bluekite import shop
from bluekite.governance import guard
from bluekite.governance.identity import Identity
from bluekite.model import Call

SAM = Identity("sam", "r-test", "T-test", "david.lee@example.com", "C-102")
SMALL_REFUND = Call("issue_refund", {"order_id": "O-5002", "amount": 5.0})


@pytest.mark.parametrize("engine", ["python", "cedar"])
def test_no_refund_on_a_closed_account(db, engine):
    shop.close(db, "C-102")
    decision = guard.check(db, SAM, SMALL_REFUND, engine)
    assert (decision.effect, decision.rule) == ("deny", "no-refund-on-closed-account")


@pytest.mark.parametrize("engine", ["python", "cedar"])
def test_an_open_account_still_gets_its_refund(db, engine):
    assert guard.check(db, SAM, SMALL_REFUND, engine).effect == "allow"
