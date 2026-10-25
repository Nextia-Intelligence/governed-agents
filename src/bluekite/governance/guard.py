"""The guard: one check before every tool call. Any error in the guard denies."""

import os

from bluekite import shop
from bluekite.governance import cedar_policy, policy
from bluekite.governance.identity import Identity
from bluekite.governance.policy import Decision
from bluekite.model import Call
from bluekite.money import dollars, to_cents

ENGINES = {"python": policy.evaluate, "cedar": cedar_policy.evaluate}


def engine_name() -> str:
    return os.environ.get("BLUEKITE_ENGINE", "cedar")


def check(db, identity: Identity, call: Call, engine: str | None = None) -> Decision:
    try:
        facts = gather_facts(db, identity, call)
        return ENGINES[engine or engine_name()](facts)
    except Exception as error:  # fail closed: if we cannot decide, we deny
        return Decision("deny", "guard-error", f"the guard failed: {error!r}")


def gather_facts(db, identity: Identity, call: Call) -> dict:
    """What the rules need to know, read from the shop, not from the model."""
    facts = {"tool": call.tool, "agent": identity.agent,
             "requester": identity.on_behalf_of, **call.args}
    if "order_id" in call.args:
        order = shop.get_order(db, call.args["order_id"])
        facts["owner"] = order["customer_id"] if order else None
        facts["refundable_cents"] = refundable(db, order)
    if "amount" in call.args:
        facts["amount_cents"] = to_cents(call.args["amount"])
        facts["amount"] = dollars(facts["amount_cents"])
        facts["refundable"] = dollars(facts["refundable_cents"])
    return facts


def refundable(db, order: dict | None) -> int:
    """What is left to refund: the items sold (not notes), minus earlier refunds."""
    if order is None:
        return 0
    sold = sum(line["cents"] for line in order["lines"] if line["kind"] == "item")
    return sold - shop.refunded_cents(db, order["id"])
