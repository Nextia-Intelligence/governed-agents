"""Human approval: a queue in SQLite. An approval is bound to the exact arguments."""

import hashlib
import json

from bluekite import clock, shop
from bluekite.governance import budgets
from bluekite.governance.policy import Decision
from bluekite.model import Call
from bluekite.money import dollars

EXPIRES_AFTER_MINUTES = 60
TABLE = """create table if not exists approvals (id text primary key,
           run_id text, agent text, on_behalf_of text, ticket_id text,
           tool text, args text, args_hash text, rule text, reason text,
           evidence text, status text, created_at text, expires_at text,
           decided_by text, decided_at text, used_at text)"""


class ApprovalError(Exception):
    """The approval cannot be given or used."""


def args_hash(call: Call) -> str:
    """A fingerprint of the exact call. Change one argument and it no longer fits."""
    text = json.dumps({"tool": call.tool, "args": call.args}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def request(db, run, call: Call, decision: Decision) -> dict:
    db.execute(TABLE)
    approval_id = f"A-{shop.next_id(db, 'approval'):04d}"
    me = run.identity
    db.execute(
        "insert into approvals values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (approval_id, me.run_id, me.agent, me.on_behalf_of, me.ticket_id,
         call.tool, json.dumps(call.args), args_hash(call), decision.rule,
         decision.reason, json.dumps(evidence(db, run, call)), "pending",
         clock.now().isoformat(), clock.later(EXPIRES_AFTER_MINUTES).isoformat(),
         None, None, None))
    db.commit()
    return get(db, approval_id)


def evidence(db, run, call: Call) -> list[str]:
    """What the approver needs to decide, collected by the system, not by Sam."""
    me = run.identity
    facts = [f"sender {me.sender} is customer {me.on_behalf_of}",
             f'ticket says: "{run.ticket["text"].splitlines()[0][:60]}"']
    if "order_id" in call.args:
        order = shop.get_order(db, call.args["order_id"])
        sold = sum(x["cents"] for x in order["lines"] if x["kind"] == "item")
        done = shop.refunded_cents(db, order["id"])
        facts.append(f"order {order['id']} · sold {dollars(sold)} · "
                     f"refunded so far {dollars(done)}")
    return facts


def get(db, approval_id: str) -> dict:
    db.execute(TABLE)
    row = db.execute("select * from approvals where id = ?", (approval_id,))
    found = row.fetchone()
    if found is None:
        raise ApprovalError(f"no approval {approval_id}")
    return expire_if_late(db, dict(found))


def expire_if_late(db, approval: dict) -> dict:
    late = clock.now().isoformat() > approval["expires_at"]
    if approval["status"] in ("pending", "approved") and late:  # approved, not used
        db.execute("update approvals set status = 'expired' where id = ?",
                   (approval["id"],))
        db.commit()
        approval["status"] = "expired"
    return approval


def for_call(db, run_id: str, call: Call) -> dict | None:
    """The approval for exactly this call in this run, if there is one."""
    db.execute(TABLE)
    row = db.execute(
        "select id from approvals where run_id = ? and args_hash = ? "
        "order by id desc", (run_id, args_hash(call))).fetchone()
    return get(db, row["id"]) if row else None


def decide(db, approval_id: str, status: str, by: str) -> dict:
    approval = get(db, approval_id)
    if approval["status"] != "pending":
        raise ApprovalError(f"{approval_id} is {approval['status']}, not pending")
    stopped = budgets.killed(db, approval["agent"])
    if stopped and status == "approved":  # no approval while the kill switch is on
        raise ApprovalError(f"cannot approve {approval_id}: {stopped.reason}")
    db.execute(
        "update approvals set status = ?, decided_by = ?, decided_at = ? "
        "where id = ?", (status, by, clock.now().isoformat(), approval_id))
    db.commit()
    return get(db, approval_id)


def list_all(db, everything: bool = False) -> list[dict]:
    db.execute(TABLE)
    rows = db.execute("select id from approvals order by id").fetchall()
    found = [get(db, row["id"]) for row in rows]
    return found if everything else [a for a in found if a["status"] == "pending"]


def use(db, approval_id: str) -> None:
    """An approval is good for one call. When that call runs, it is used up."""
    db.execute("update approvals set status = 'used', used_at = ? "
               "where id = ? and status = 'approved'",
               (clock.now().isoformat(), approval_id))
    db.commit()
