"""Save and load runs, so a paused run can wait for a person and then go on."""

import json
from dataclasses import asdict, dataclass, field

from bluekite.governance.identity import Identity

TABLE = """create table if not exists runs (id text primary key, status text,
           identity text, ticket text, messages text, pending text,
           steps integer, tokens integer)"""


@dataclass
class Run:
    identity: Identity
    ticket: dict
    messages: list = field(default_factory=list)
    steps: int = 0
    tokens: int = 0
    reply: str | None = None
    status: str = "running"  # running, paused, done (later: stopped)
    pending: dict | None = None  # the tool call that waits for approval


def save(db, run: Run) -> None:
    db.execute(TABLE)
    db.execute("insert or replace into runs values (?,?,?,?,?,?,?,?)", (
        run.identity.run_id, run.status, json.dumps(asdict(run.identity)),
        json.dumps(run.ticket), json.dumps(run.messages), json.dumps(run.pending),
        run.steps, run.tokens))
    db.commit()


def load(db, run_id: str) -> Run:
    db.execute(TABLE)
    row = db.execute("select * from runs where id = ?", (run_id,)).fetchone()
    if row is None:
        raise SystemExit(f"no run {run_id}")
    return Run(Identity(**json.loads(row["identity"])), json.loads(row["ticket"]),
               json.loads(row["messages"]), row["steps"], row["tokens"],
               status=row["status"], pending=json.loads(row["pending"]))
