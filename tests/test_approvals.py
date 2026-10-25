import pytest

from bluekite import shop
from bluekite.agent import resume_run, run_ticket
from bluekite.governance import approvals
from bluekite.model import Call, ReplayModel, Turn
from bluekite.tickets import get_ticket


def resume(db, run_id="r-0001", ticket_id="T-1002"):
    lines = []
    run = resume_run(db, run_id, ReplayModel(ticket_id), out=lines.append)
    return run, lines


def test_closing_an_account_waits_for_a_person(replay, db):
    run, lines = replay("T-1002")
    assert run.status == "paused"
    assert lines[-2].startswith("⏸ guard: ask close_account")
    assert approvals.list_all(db)[0]["id"] == "A-0001"
    assert shop.get_customer(db, "C-103")["status"] == "open"


def test_approve_then_resume_closes_the_right_account(replay, db):
    replay("T-1002")
    approvals.decide(db, "A-0001", "approved", "support-lead")
    run, lines = resume(db)
    assert "✔ approval A-0001 · approved by support-lead" in lines
    assert run.status == "done"
    assert shop.get_customer(db, "C-103")["status"] == "closed"


def test_reject_then_resume_does_nothing(replay, db):
    replay("T-1002")
    approvals.decide(db, "A-0001", "rejected", "support-lead")
    run, lines = resume(db)
    assert "✋ approval A-0001 · rejected by support-lead" in lines
    assert "team member" in run.reply
    assert shop.get_customer(db, "C-103")["status"] == "open"


def test_resume_before_a_decision_keeps_waiting(replay, db):
    replay("T-1002")
    run, _ = resume(db)
    assert run.status == "paused"
    assert len(approvals.list_all(db)) == 1  # no second request


def test_an_approval_expires(replay, db, monkeypatch):
    replay("T-1002")
    monkeypatch.setenv("BLUEKITE_CLOCK", "2026-10-25T11:30:00")
    with pytest.raises(approvals.ApprovalError, match="expired"):
        approvals.decide(db, "A-0001", "approved", "support-lead")


def test_the_approval_is_bound_to_the_exact_arguments(replay, db):
    replay("T-1002")
    asked = Call("close_account", {"customer_id": "C-103"})
    other = Call("close_account", {"customer_id": "C-102"})
    assert approvals.for_call(db, "r-0001", asked)["id"] == "A-0001"
    assert approvals.for_call(db, "r-0001", other) is None


def test_a_changed_approval_record_no_longer_fits(replay, db):
    replay("T-1002")
    db.execute("update approvals set args = '{\"customer_id\": \"C-102\"}'")
    asked = Call("close_account", {"customer_id": "C-102"})
    assert approvals.for_call(db, "r-0001", asked) is None  # the hash still says C-103


def test_small_refunds_need_no_person(replay, db):
    run, _ = replay("T-1001")  # $20.00 is under the $25.00 threshold
    assert run.status == "done"
    assert approvals.list_all(db) == []


class ClosesTwice:
    """A model that asks for the same call again after it ran once."""

    def next(self, messages, tools):
        if sum(1 for m in messages if m["role"] == "tool") < 2:
            return Turn(Call("close_account", {"customer_id": "C-103"}), None, 500)
        return Turn(None, "Done.", 300)


def test_an_approval_is_used_only_once(db):
    run_ticket(db, get_ticket("T-1002"), ClosesTwice(), out=lambda line: None)
    approvals.decide(db, "A-0001", "approved", "support-lead")
    run = resume_run(db, "r-0001", ClosesTwice(), out=lambda line: None)
    assert approvals.get(db, "A-0001")["status"] == "used"
    assert run.status == "paused"  # the same call again: a person must decide again
    assert [a["id"] for a in approvals.list_all(db)] == ["A-0002"]


def test_a_used_approval_cannot_be_decided_again(replay, db):
    replay("T-1002")
    approvals.decide(db, "A-0001", "approved", "support-lead")
    resume(db)
    with pytest.raises(approvals.ApprovalError, match="A-0001 is used, not pending"):
        approvals.decide(db, "A-0001", "approved", "support-lead")


def test_an_approval_expires_after_it_was_given_too(replay, db, monkeypatch):
    replay("T-1002")
    approvals.decide(db, "A-0001", "approved", "support-lead")
    monkeypatch.setenv("BLUEKITE_CLOCK", "2026-10-25T11:30:00")
    run, lines = resume(db)
    assert "✋ approval A-0001 · expired" in lines
    assert approvals.get(db, "A-0001")["status"] == "expired"
    assert shop.get_customer(db, "C-103")["status"] == "open"
