"""Checks for exercise 4. Run: uv run pytest exercises/check_s04.py -q"""

import pytest

from bluekite.governance import approvals


@pytest.mark.parametrize("by", ["sam", ""])
def test_the_agent_cannot_approve(replay, db, by):
    replay("T-1002")
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(db, "A-0001", "approved", by)
    assert approvals.get(db, "A-0001")["status"] == "pending"


def test_a_person_can_approve(replay, db):
    replay("T-1002")
    approval = approvals.decide(db, "A-0001", "approved", "support-lead")
    assert approval["status"] == "approved"
