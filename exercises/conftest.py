"""Fixtures for the exercise checks: the same as in tests/conftest.py."""

import pytest

from bluekite import clock, shop
from bluekite.agent import run_ticket
from bluekite.model import ReplayModel
from bluekite.tickets import get_ticket, prepare


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh shop in a temporary folder, for every test."""
    monkeypatch.setenv("BLUEKITE_HOME", str(tmp_path))
    monkeypatch.setattr(clock, "_waited", clock.timedelta())
    shop.reset()
    connection = shop.connect()
    yield connection
    connection.close()


@pytest.fixture
def replay(db):
    """Run a ticket with its recording. Returns the run and the trace lines."""

    def run(ticket_id: str, recording: str | None = None):
        lines = []
        model = ReplayModel(recording or ticket_id)
        ticket = get_ticket(ticket_id)
        prepare(db, ticket)
        result = run_ticket(db, ticket, model, out=lines.append)
        return result, lines

    return run

