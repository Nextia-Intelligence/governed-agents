"""Sam's four tools. They take ids, not names, and call the shop with a token."""

from dataclasses import dataclass

from bluekite import shop, shop_api
from bluekite.governance.credentials import Token
from bluekite.governance.identity import Identity
from bluekite.money import dollars, to_cents


@dataclass
class Result:
    status: str  # "ok", "error" or "denied"
    summary: str  # one short line for the trace
    data: dict  # what the model sees
    note: str = ""  # an extra line for the trace, for example an approval


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


@dataclass
class ToolContext:
    db: object
    identity: Identity
    token: Token  # the one credential for this call


def look_up_order(ctx: ToolContext, order_id: str) -> Result:
    order = shop_api.get_order(ctx.db, ctx.token, order_id)
    if order is None:
        return Result("error", f"no order {order_id}", {"error": "not found"})
    # Least privilege for data: the customer id, never the name, email or address.
    data = {key: order[key] for key in ("id", "customer_id", "status", "lines")}
    lines = plural(len(order["lines"]), "line")
    return Result("ok", f"order {order_id} · {order['customer_id']} · {lines}", data)


def change_address(ctx: ToolContext, customer_id: str, address: str) -> Result:
    if shop.get_customer(ctx.db, customer_id) is None:
        return Result("error", f"no customer {customer_id}", {"error": "not found"})
    shop_api.set_address(ctx.db, ctx.token, customer_id, address)
    shop.record_change(ctx.db, ctx.identity.run_id, "address", customer_id, address)
    return Result("ok", f"address changed for {customer_id}", {"done": True})


def issue_refund(ctx: ToolContext, order_id: str, amount: float) -> Result:
    cents = to_cents(amount)
    try:
        shop_api.refund(ctx.db, ctx.token, order_id, cents)
    except shop.ShopTimeout as error:
        return Result("error", f"error: {error}", {"error": str(error)})
    shop.record_change(ctx.db, ctx.identity.run_id, "refund", order_id,
                       dollars(cents))
    return Result("ok", f"refunded {dollars(cents)}", {"refunded": dollars(cents)})


def close_account(ctx: ToolContext, customer_id: str) -> Result:
    customer = shop.get_customer(ctx.db, customer_id)
    if customer is None:
        return Result("error", f"no customer {customer_id}", {"error": "not found"})
    shop_api.close(ctx.db, ctx.token, customer_id)
    note = f"{customer['name']} · data deleted after 30 days"
    shop.record_change(ctx.db, ctx.identity.run_id, "close", customer_id, note)
    return Result("ok", f"closed {customer_id} · data deleted after 30 days",
                  {"closed": customer_id})


TOOLS = {
    "look_up_order": look_up_order,
    "change_address": change_address,
    "issue_refund": issue_refund,
    "close_account": close_account,
}


def call_tool(ctx: ToolContext, tool: str, args: dict) -> Result:
    return TOOLS[tool](ctx, **args)
