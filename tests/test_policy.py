"""Table-driven policy tests. Every row runs on both engines: Python and Cedar."""

import pytest

from bluekite.governance import guard
from bluekite.governance.identity import Identity
from bluekite.model import Call

ROWS = [  # requester, tool, args, effect, rule
    ("C-102", "look_up_order", {"order_id": "O-5002"}, "allow", "sams-tools-only"),
    ("C-101", "look_up_order", {"order_id": "O-5002"}, "deny", "own-orders-only"),
    (None, "look_up_order", {"order_id": "O-5001"}, "deny", "verified-customer-only"),
    ("C-101", "look_up_order", {"order_id": "O-9999"}, "deny", "own-orders-only"),
    ("C-102", "issue_refund", {"order_id": "O-5002", "amount": 20.0},
     "allow", "sams-tools-only"),
    ("C-102", "issue_refund", {"order_id": "O-5002", "amount": 2000.0},
     "deny", "refund-within-order-total"),
    ("C-101", "issue_refund", {"order_id": "O-5003", "amount": 5.0},
     "deny", "own-orders-only"),
    ("C-103", "issue_refund", {"order_id": "O-5003", "amount": 45.0},
     "ask", "refund-over-25-needs-human"),
    ("C-103", "issue_refund", {"order_id": "O-5003", "amount": 5.0},
     "allow", "sams-tools-only"),
    ("C-103", "close_account", {"customer_id": "C-103"},
     "ask", "close-account-needs-human"),
    ("C-103", "close_account", {"customer_id": "C-102"}, "deny", "own-account-only"),
    ("C-101", "change_address", {"customer_id": "C-101", "address": "1 New Road"},
     "allow", "sams-tools-only"),
    ("C-101", "change_address", {"customer_id": "C-102", "address": "1 New Road"},
     "deny", "own-account-only"),
    ("C-101", "send_email", {"to": "someone@example.com"}, "deny", "sams-tools-only"),
]


def who(requester: str | None) -> Identity:
    return Identity("sam", "r-test", "T-test", "test@example.com", requester)


@pytest.mark.parametrize("engine", ["python", "cedar"])
@pytest.mark.parametrize("requester, tool, args, effect, rule", ROWS)
def test_policy_table(db, engine, requester, tool, args, effect, rule):
    decision = guard.check(db, who(requester), Call(tool, args), engine)
    assert (decision.effect, decision.rule) == (effect, rule)


@pytest.mark.parametrize("engine", ["python", "cedar"])
def test_closed_account_gets_no_refund(db, engine):
    db.execute("update customers set status = 'closed' where id = 'C-103'")
    call = Call("issue_refund", {"order_id": "O-5003", "amount": 5.0})
    decision = guard.check(db, who("C-103"), call, engine)
    assert decision.rule == "no-refund-on-closed-account"


def test_earlier_refunds_count(db):
    db.execute("insert into refunds values ('O-5002', 2000, 'r-0000')")
    call = Call("issue_refund", {"order_id": "O-5002", "amount": 1.0})
    assert guard.check(db, who("C-102"), call).rule == "refund-within-order-total"


def test_the_guard_fails_closed(db, monkeypatch):
    def broken(*args):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(guard, "gather_facts", broken)
    call = Call("look_up_order", {"order_id": "O-5002"})
    decision = guard.check(db, who("C-102"), call)
    assert (decision.effect, decision.rule) == ("deny", "guard-error")


def test_a_broken_cedar_file_denies(db, monkeypatch, tmp_path):
    bad = tmp_path / "bad.cedar"
    bad.write_text("permit (principal, action, resource) when { 1 + };")
    monkeypatch.setattr("bluekite.governance.cedar_policy.POLICY_FILE", bad)
    call = Call("look_up_order", {"order_id": "O-5002"})
    assert guard.check(db, who("C-102"), call, "cedar").effect == "deny"
