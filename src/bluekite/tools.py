"""Sam's four tools. In section 1 they are deliberately ungoverned."""

from dataclasses import dataclass

from bluekite import shop
from bluekite.money import dollars, to_cents


@dataclass
class Result:
    status: str  # "ok" or "error"
    summary: str  # one short line for the trace
    data: dict  # what the model sees


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


@dataclass
class ToolContext:
    db: object
    run_id: str


def look_up_order(ctx: ToolContext, order_id: str) -> Result:
    order = shop.get_order(ctx.db, order_id)
    if order is None:
        return Result("error", f"no order {order_id}", {"error": "not found"})
    customer = shop.get_customer(ctx.db, order["customer_id"])
    # The flaw: the whole customer record goes to the model, whoever is asking.
    order["customer"] = customer
    shop.record_change(ctx.db, ctx.run_id, "read", customer["id"],
                       f"{customer['name']} · name, email, address")
    lines = plural(len(order["lines"]), "line")
    return Result("ok", f"order {order_id} · {customer['name']} · {lines}", order)


def change_address(ctx: ToolContext, customer_name: str, address: str) -> Result:
    # The flaw: names are not unique, so this may change the wrong customer.
    customer = shop.first_customer_named(ctx.db, customer_name)
    if customer is None:
        return Result("error", f"no customer {customer_name}", {"error": "not found"})
    shop.set_address(ctx.db, customer["id"], address)
    shop.record_change(ctx.db, ctx.run_id, "address", customer["id"], address)
    return Result("ok", f"address changed for {customer['id']}", {"done": True})


def issue_refund(ctx: ToolContext, order_id: str, amount: float) -> Result:
    # The flaw: any amount, on any order, for anyone.
    cents = to_cents(amount)
    try:
        shop.refund(ctx.db, order_id, cents, ctx.run_id)
    except shop.ShopTimeout as error:
        return Result("error", f"error: {error}", {"error": str(error)})
    shop.record_change(ctx.db, ctx.run_id, "refund", order_id, dollars(cents))
    return Result("ok", f"refunded {dollars(cents)}", {"refunded": dollars(cents)})


def close_account(ctx: ToolContext, customer_name: str) -> Result:
    # The flaw: the first customer with that name, and no way back after 30 days.
    customer = shop.first_customer_named(ctx.db, customer_name)
    if customer is None:
        return Result("error", f"no customer {customer_name}", {"error": "not found"})
    shop.close(ctx.db, customer["id"])
    note = f"{customer['name']} · data deleted after 30 days"
    shop.record_change(ctx.db, ctx.run_id, "close", customer["id"], note)
    return Result("ok", f"closed {customer['id']} · data deleted after 30 days",
                  {"closed": customer["id"]})


TOOLS = {
    "look_up_order": look_up_order,
    "change_address": change_address,
    "issue_refund": issue_refund,
    "close_account": close_account,
}


def call_tool(ctx: ToolContext, tool: str, args: dict) -> Result:
    if tool not in TOOLS:
        return Result("error", f"no tool {tool}", {"error": "unknown tool"})
    try:
        return TOOLS[tool](ctx, **args)
    except TypeError:
        return Result("error", f"bad arguments for {tool}", {"error": "bad arguments"})


def _schema(name: str, description: str, **params: str) -> dict:
    """A function schema in the OpenAI format, used by the live model."""
    props = {key: {"type": kind} for key, kind in params.items()}
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props,
                       "required": list(params)}}}


SCHEMAS = [
    _schema("look_up_order", "Look up an order.", order_id="string"),
    _schema("change_address", "Change a customer's address.",
            customer_name="string", address="string"),
    _schema("issue_refund", "Refund an order.", order_id="string", amount="number"),
    _schema("close_account", "Close a customer's account.", customer_name="string"),
]
