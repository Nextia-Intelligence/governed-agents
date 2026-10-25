"""Kit's three tools. Like Sam in section 1, they have no controls."""

from bluekite import shop
from bluekite.money import dollars, to_cents
from bluekite.tools import Result
from kit import supply


def create_purchase_order(db, run_id: str, supplier_id: str, item: str,
                          quantity: int, unit_price: float) -> Result:
    po_id = f"PO-{shop.next_id(db, 'po'):04d}"
    cents = to_cents(unit_price)
    db.execute("insert into purchase_orders values (?,?,?,?,?)",
               (po_id, supplier_id, item, quantity, cents))
    db.commit()
    total = dollars(quantity * cents)
    shop.record_change(db, run_id, "order", po_id, f"{quantity:,} × {item} · {total}")
    return Result("ok", f"{po_id} · {quantity:,} × {item} · {total}", {"po": po_id})


def email_supplier(db, run_id: str, to: str, subject: str, body: str) -> Result:
    db.execute("insert into emails values (?,?,?,?)", (to, subject, body, run_id))
    db.commit()
    shop.record_change(db, run_id, "email", to, subject)
    return Result("ok", f"sent to {to}", {"sent": True})


def pay_invoice(db, run_id: str, invoice_id: str, amount: float) -> Result:
    if supply.get_row(db, "invoices", invoice_id) is None:
        return Result("error", f"no invoice {invoice_id}", {"error": "not found"})
    cents = to_cents(amount)
    try:
        supply.pay(db, invoice_id, cents, run_id)
    except supply.PaymentTimeout as error:
        shop.record_change(db, run_id, "payment", invoice_id, dollars(cents))
        return Result("error", f"error: {error}", {"error": str(error)})
    shop.record_change(db, run_id, "payment", invoice_id, dollars(cents))
    return Result("ok", f"paid {dollars(cents)} on {invoice_id}", {"paid": True})


TOOLS = {
    "create_purchase_order": create_purchase_order,
    "email_supplier": email_supplier,
    "pay_invoice": pay_invoice,
}


def call_tool(db, run_id: str, tool: str, args: dict) -> Result:
    if tool not in TOOLS:
        return Result("error", f"no tool {tool}", {"error": "unknown tool"})
    try:
        return TOOLS[tool](db, run_id, **args)
    except TypeError:
        return Result("error", f"bad arguments for {tool}", {"error": "bad arguments"})
