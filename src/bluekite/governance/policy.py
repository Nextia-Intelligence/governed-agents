"""A small policy engine in plain Python. Rules are data: an id, an effect, a test."""

from collections.abc import Callable
from dataclasses import dataclass

SAMS_TOOLS = ("look_up_order", "change_address", "issue_refund", "close_account")
ORDER_TOOLS = ("look_up_order", "issue_refund")
ACCOUNT_TOOLS = ("change_address", "close_account")
ASK_ABOVE_CENTS = 2500  # refunds up to $25.00 need no human


@dataclass(frozen=True)
class Decision:
    effect: str  # "allow", "deny" or "ask"
    rule: str  # the id of the rule that decided
    reason: str  # one sentence for people


@dataclass(frozen=True)
class Rule:
    id: str
    effect: str  # "deny" or "ask"
    applies: Callable[[dict], bool]
    reason: str  # a template, filled from the facts


RULES = [
    Rule("verified-customer-only", "deny",
         lambda f: f["requester"] is None,
         "the sender is not a known customer"),
    Rule("own-orders-only", "deny",
         lambda f: f["tool"] in ORDER_TOOLS and f["owner"] != f["requester"],
         "order {order_id} does not belong to {requester}"),
    Rule("own-account-only", "deny",
         lambda f: f["tool"] in ACCOUNT_TOOLS and f["customer_id"] != f["requester"],
         "{requester} cannot act on account {customer_id}"),
    Rule("refund-within-order-total", "deny",
         lambda f: f["tool"] == "issue_refund"
         and f["amount_cents"] > f["refundable_cents"],
         "refund {amount} is more than the {refundable} left on order {order_id}"),
    Rule("refund-over-25-needs-human", "ask",
         lambda f: f["tool"] == "issue_refund" and f["amount_cents"] > ASK_ABOVE_CENTS,
         "refunds above $25.00 need a person"),
    Rule("close-account-needs-human", "ask",
         lambda f: f["tool"] == "close_account",
         "closing an account cannot be undone after 30 days"),
]
REASONS = {rule.id: rule.reason for rule in RULES}


def evaluate(facts: dict) -> Decision:
    """Deny wins over ask, ask wins over allow. Unknown tools are denied."""
    if facts["tool"] not in SAMS_TOOLS:
        return Decision("deny", "sams-tools-only", "this is not one of Sam's tools")
    fired = [rule for rule in RULES if rule.applies(facts)]
    for effect in ("deny", "ask"):
        for rule in fired:
            if rule.effect == effect:
                return Decision(effect, rule.id, rule.reason.format(**facts))
    return Decision("allow", "sams-tools-only", "no rule stops this call")
