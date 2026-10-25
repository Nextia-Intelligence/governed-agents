"""Checks for exercise 5. Run: uv run pytest exercises/check_s05.py -q"""

from bluekite.governance import budgets
from bluekite.governance.identity import Identity
from bluekite.model import Call
from bluekite.runs import Run


def refund(amount: float) -> Call:
    return Call("issue_refund", {"order_id": "O-5002", "amount": amount})


def run_with_refunds(*amounts: float) -> Run:
    me = Identity("sam", "r-0001", "T-1001", "david.lee@example.com", "C-102")
    run = Run(me, {"id": "T-1001"}, started="2026-10-25T10:00:00")
    for amount in amounts:
        run.messages.append({"role": "assistant", "id": "x", "call": {
            "tool": "issue_refund", "args": refund(amount).args}})
    return run


def test_two_refunds_are_fine(db):
    assert budgets.before_call(db, run_with_refunds(5.00), refund(5.01)) is None


def test_the_third_refund_stops_the_run(db):
    stop = budgets.before_call(db, run_with_refunds(5.00, 5.01), refund(5.02))
    assert stop is not None
    assert stop.reason == "refunds · 3 of 2 per run"
