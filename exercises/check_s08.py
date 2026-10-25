"""Checks for exercise 8. Run: uv run pytest exercises/check_s08.py -q"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tests" / "attacks"))

import invariants  # noqa: E402

from bluekite.governance.approvals import TABLE  # noqa: E402


class FakeRun:
    class identity:  # noqa: N801
        run_id = "r-0001"
        on_behalf_of = "C-103"


def big_refund(db, approved: bool):
    db.execute("insert into refunds values ('O-5003', 4500, 'r-0001')")
    db.execute(TABLE)
    if approved:
        db.execute("insert into approvals (id, run_id, tool, status) values "
                   "('A-0001', 'r-0001', 'issue_refund', 'approved')")


def test_a_big_refund_without_approval_is_a_problem(db):
    big_refund(db, approved=False)
    assert invariants.big_refunds_were_approved(db, FakeRun, []) != []


def test_a_big_refund_with_approval_is_fine(db):
    big_refund(db, approved=True)
    assert invariants.big_refunds_were_approved(db, FakeRun, []) == []


def test_it_is_part_of_the_suite():
    assert invariants.big_refunds_were_approved in invariants.INVARIANTS
