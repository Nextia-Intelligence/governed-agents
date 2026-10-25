import json

import pytest

from bluekite.agent import resume_run, run_ticket
from bluekite.governance import approvals, audit
from bluekite.governance.replay import replay as replay_events
from bluekite.model import Call, ReplayModel, Turn
from bluekite.tickets import get_ticket

ALL = ["T-1001", "T-1002", "T-1003", "T-1004", "T-1005"]


@pytest.fixture
def all_runs(replay):
    return {ticket_id: replay(ticket_id) for ticket_id in ALL}


def test_every_step_is_one_event(all_runs):
    kinds = [e["kind"] for e in audit.for_run("r-0001")]
    assert kinds == ["start", "call", "call", "call", "reply", "end"]


def test_the_chain_is_intact(all_runs):
    assert audit.verify() == (True, "ok · 25 events · chain intact")


def test_a_changed_event_is_found(all_runs):
    path = audit.log_path()
    lines = path.read_text().splitlines()
    lines[2] = lines[2].replace('"amount": 2000.0', '"amount": 20.0')
    path.write_text("\n".join(lines) + "\n")
    assert audit.verify() == (False, "broken at event #3: the hash does not match")


def test_a_deleted_event_is_found(all_runs):
    path = audit.log_path()
    lines = path.read_text().splitlines()
    del lines[4]
    path.write_text("\n".join(lines) + "\n")
    assert audit.verify() == (False, "broken at event #5: the chain is cut")


@pytest.mark.parametrize("ticket_id", ALL)
def test_replay_shows_the_same_trace(all_runs, ticket_id):
    run, lines = all_runs[ticket_id]
    replayed = []
    replay_events(audit.for_run(run.identity.run_id), out=replayed.append)
    assert replayed == lines


class MovesHouse:
    """A model that changes an address, to check what the log keeps."""

    def __init__(self):
        self.turns = [Turn(Call("change_address", {"customer_id": "C-101",
                                                   "address": "9 Pine Road, Halifax"}),
                           None, 500),
                      Turn(None, "Done, Anna Silva: 9 Pine Road, Halifax.", 400)]

    def next(self, messages, tools):
        return self.turns.pop(0)


def test_no_personal_data_in_the_log(db):
    run_ticket(db, get_ticket("T-1005"), MovesHouse(), out=lambda line: None)
    text = audit.log_path().read_text()
    for personal in ("anna.silva@example.com", "Anna Silva", "Pine Road"):
        assert personal not in text
    call = [e for e in audit.read_events() if e["kind"] == "call"][0]
    assert call["args"] == {"customer_id": "C-101", "address": "[redacted]"}
    assert json.loads(json.dumps(call))["args_hash"]  # the exact call can be proved


def test_approve_and_reject_are_events_in_the_chain(replay, db):
    replay("T-1002")
    approvals.decide(db, "A-0001", "approved", "support-lead")
    resume_run(db, "r-0001", ReplayModel("T-1002"), out=lambda line: None)
    kinds = [e["kind"] for e in audit.for_run("r-0001")]
    assert kinds == ["start", "call", "end", "decide", "resume", "call", "reply", "end"]
    decision = [e for e in audit.read_events() if e["kind"] == "decide"][0]
    assert (decision["approval"], decision["decision"], decision["by"]) == \
        ("A-0001", "approved", "support-lead")
    assert decision["args_hash"] == approvals.get(db, "A-0001")["args_hash"]
    assert decision["at"] == "2026-10-25T10:00:00"
    assert audit.verify()[0]


def test_a_rejection_is_recorded_too(replay, db):
    replay("T-1002")
    approvals.decide(db, "A-0001", "rejected", "support-lead")
    assert audit.read_events()[-1]["decision"] == "rejected"
