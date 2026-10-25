"""Kit's controls, built from the course modules: identity, registry, policy."""

from bluekite.governance.identity import Identity
from bluekite.governance.policy import Decision, Rule
from bluekite.governance.registry import ToolSpec
from bluekite.money import dollars, to_cents
from kit import supply

TEAMS = {"warehouse@bluekite.example": "warehouse",
         "finance@bluekite.example": "finance"}
NUMBER = "number"


def identify(run_id: str, ticket: dict) -> Identity:
    """Kit acts for a Blue Kite team, known by its address. Anyone else: nobody."""
    return Identity("kit", run_id, ticket["id"], ticket["from"],
                    TEAMS.get(ticket["from"]))


REGISTRY = {spec.name: spec for spec in [
    ToolSpec("create_purchase_order", "write", "high", "purchasing:write",
             "only by asking the supplier", "Order stock from a supplier.",
             {"supplier_id": {"type": "string", "pattern": r"^SUP-\d$"},
              "item": {"type": "string", "minLength": 2, "maxLength": 40},
              "quantity": {"type": NUMBER, "exclusiveMinimum": 0, "maximum": 1000},
              "unit_price": {"type": NUMBER, "exclusiveMinimum": 0, "maximum": 500}}),
    ToolSpec("email_supplier", "write", "medium", "email:send", "no",
             "Email a supplier.",
             {"to": {"type": "string", "maxLength": 80},
              "subject": {"type": "string", "maxLength": 80},
              "body": {"type": "string", "maxLength": 2000}}),
    ToolSpec("pay_invoice", "write", "high", "payments:write",
             "no, the money is gone", "Pay a supplier's invoice.",
             {"invoice_id": {"type": "string", "pattern": r"^INV-\d{4}$"},
              "amount": {"type": NUMBER, "exclusiveMinimum": 0, "maximum": 10000}}),
]}

RULES = [
    Rule("known-team-only", "deny", lambda f: f["requester"] is None,
         "the sender is not a Blue Kite team"),
    Rule("finance-pays", "deny",
         lambda f: f["tool"] == "pay_invoice" and f["requester"] != "finance",
         "only the finance team can ask for a payment"),
    Rule("pay-only-with-purchase-order", "deny",
         lambda f: f["tool"] == "pay_invoice" and not f["po_id"],
         "invoice {invoice_id} has no purchase order"),
    Rule("pay-at-most-what-is-open", "deny",
         lambda f: f["tool"] == "pay_invoice" and f["amount_cents"] > f["open_cents"],
         "{amount} is more than the {open} still open on {invoice_id}"),
    Rule("email-only-address-on-file", "deny",
         lambda f: f["tool"] == "email_supplier" and f["to"] not in f["on_file"],
         "{to} is not a supplier address on file"),
    Rule("big-order-needs-human", "ask",
         lambda f: f["tool"] == "create_purchase_order" and f["total_cents"] > 200000,
         "orders above $2,000.00 need a person"),
    Rule("big-payment-needs-human", "ask",
         lambda f: f["tool"] == "pay_invoice" and f["amount_cents"] > 100000,
         "payments above $1,000.00 need a person"),
]


def check(db, identity: Identity, call) -> Decision:
    """The guard for Kit. Deny wins over ask; errors deny (fail closed)."""
    try:
        facts = gather_facts(db, identity, call)
        fired = [rule for rule in RULES if rule.applies(facts)]
        for effect in ("deny", "ask"):
            for rule in fired:
                if rule.effect == effect:
                    return Decision(effect, rule.id, rule.reason.format(**facts))
        return Decision("allow", "kits-tools-only", "no rule stops this call")
    except Exception as error:
        return Decision("deny", "guard-error", f"the guard failed: {error!r}")


def gather_facts(db, identity: Identity, call) -> dict:
    facts = {"tool": call.tool, "requester": identity.on_behalf_of, **call.args}
    facts["on_file"] = [r["email"] for r in db.execute("select email from suppliers")]
    if call.tool == "pay_invoice":
        invoice = supply.get_row(db, "invoices", call.args["invoice_id"]) or {}
        paid = db.execute("select coalesce(sum(cents), 0) from payments where "
                          "invoice_id = ?", (call.args["invoice_id"],)).fetchone()[0]
        facts["po_id"] = invoice.get("po_id")
        facts["open_cents"] = invoice.get("cents", 0) - paid
        facts["amount_cents"] = to_cents(call.args["amount"])
        facts["amount"] = dollars(facts["amount_cents"])
        facts["open"] = dollars(facts["open_cents"])
    if call.tool == "create_purchase_order":
        facts["total_cents"] = call.args["quantity"] * to_cents(call.args["unit_price"])
    return facts
