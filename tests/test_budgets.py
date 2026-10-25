from dataclasses import replace

import pytest

from bluekite import shop
from bluekite.agent import run_ticket
from bluekite.cli import main
from bluekite.governance import approvals, budgets
from bluekite.model import Call, Turn
from bluekite.tickets import get_ticket


@pytest.fixture
def limits(monkeypatch):
    """Change one limit for a test: limits(steps_per_run=2)."""

    def set_limits(**changes):
        monkeypatch.setattr(budgets, "LIMITS", replace(budgets.LIMITS, **changes))

    return set_limits


def test_the_step_limit(replay, limits):
    limits(steps_per_run=2)
    run, lines = replay("T-1005")
    assert lines[-2] == "⛔ budget: stop · steps · 2 of 2 used"
    assert run.status == "stopped"


def test_the_time_limit(replay, limits):
    limits(seconds_per_run=8)  # each timeout takes 5 s
    run, lines = replay("T-1005")
    assert lines[-2] == "⛔ budget: stop · time · 10 s of 8 s"


def test_the_cost_limit_per_run(replay, limits):
    limits(cost_per_run=0.005)
    run, lines = replay("T-1001")
    assert lines[-2].startswith("⛔ budget: stop · cost · $0.007 of $0.005")
    assert run.steps == 2


def test_the_cost_limit_per_day(replay, db):
    db.executescript(budgets.TABLES)
    db.execute("insert into spend values ('2026-10-25', 'sam', 'r-0000', 200000)")
    run, lines = replay("T-1001")
    assert lines[1] == "⛔ budget: stop · cost · $1.200 of $1.00 today"
    assert run.steps == 0


def test_a_killed_agent_does_nothing(replay, db):
    budgets.kill(db, "sam", "support-lead")
    run, _ = replay("T-1001")
    assert run.steps == 0 and run.tokens == 0
    assert shop.list_refunds(db) == []


class KillsMidRun:
    """A model that pulls the kill switch while it works, to test the check."""

    def __init__(self, db):
        self.db = db

    def next(self, messages, tools):
        budgets.kill(self.db, "sam", "on-call engineer")
        call = Call("issue_refund", {"order_id": "O-5002", "amount": 20.0})
        return Turn(call, None, 500)


def test_the_kill_switch_stops_a_running_agent(db):
    lines = []
    run = run_ticket(db, get_ticket("T-1001"), KillsMidRun(db), out=lines.append)
    assert lines[2] == "⛔ kill switch: sam is stopped by on-call engineer"
    assert shop.list_refunds(db) == []  # stopped before the tool ran
    assert run.status == "stopped"


def test_a_broken_budget_check_stops_the_run(replay, monkeypatch):
    def broken(*args):
        raise RuntimeError("no database")

    monkeypatch.setattr(budgets, "killed", broken)
    run, lines = replay("T-1001")
    assert run.status == "stopped"
    assert "error · cannot check the budget" in lines[1]


def test_no_approval_while_the_agent_is_stopped(replay, db):
    replay("T-1002")
    budgets.kill(db, "sam", "on-call engineer")
    with pytest.raises(approvals.ApprovalError, match="sam is stopped by on-call"):
        approvals.decide(db, "A-0001", "approved", "support-lead")
    assert approvals.get(db, "A-0001")["status"] == "pending"
    assert approvals.decide(db, "A-0001", "rejected", "support-lead")["status"] == \
        "rejected"  # saying no is always allowed


@pytest.mark.parametrize("ticket_id, option, value, stop", [
    ("T-1005", "--max-steps", "3", "⛔ budget: stop · steps · 3 of 3 used"),
    ("T-1005", "--max-seconds", "8", "⛔ budget: stop · time · 10 s of 8 s"),
    ("T-1001", "--max-cost", "0.005",
     "⛔ budget: stop · cost · $0.007 of $0.005 for this run"),
])
def test_limits_from_the_command_line(db, capsys, monkeypatch, ticket_id, option,
                                      value, stop):
    monkeypatch.setattr(budgets, "LIMITS", budgets.LIMITS)  # put back after the test
    main(["run", ticket_id, option, value])
    assert stop in capsys.readouterr().out.splitlines()
