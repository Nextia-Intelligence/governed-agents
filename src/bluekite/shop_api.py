"""The shop's API, as the agent's tools see it. Every call needs a scoped token."""

from bluekite import shop
from bluekite.governance.credentials import Token, require


def get_order(db, token: Token, order_id: str) -> dict | None:
    require(token, "orders:read")
    return shop.get_order(db, order_id)


def refund(db, token: Token, order_id: str, cents: int) -> None:
    require(token, "refunds:write")
    shop.refund(db, order_id, cents, token.run_id)


def close(db, token: Token, customer_id: str) -> None:
    require(token, "accounts:close")
    shop.close(db, customer_id)


def set_address(db, token: Token, customer_id: str, address: str) -> None:
    require(token, "customers:write")
    shop.set_address(db, customer_id, address)
