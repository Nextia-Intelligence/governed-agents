"""The attack suite: every practice ticket and variant, checked against every rule
of what must never happen. If one control breaks, this suite fails the release."""

import pytest
from invariants import check_all

from bluekite.governance import guard
from bluekite.governance.policy import Decision
from bluekite.tickets import load_tickets

ATTACKS = sorted(load_tickets(variants=True))


@pytest.mark.parametrize("ticket_id", ATTACKS)
def test_the_attack_is_contained(replay, db, ticket_id):
    run, lines = replay(ticket_id)
    assert check_all(db, run, lines) == []


@pytest.mark.parametrize("ticket_id", ["T-1001", "T-1004", "T-1004-note"])
def test_the_suite_catches_a_broken_guard(replay, db, monkeypatch, ticket_id):
    """Prove the gate works: turn the guard off, and the suite must find a problem."""

    def allow_everything(db, identity, call, engine=None):
        return Decision("allow", "broken", "the guard is switched off")

    monkeypatch.setattr(guard, "check", allow_everything)
    run, lines = replay(ticket_id)
    assert check_all(db, run, lines) != []
