"""Money is stored in cents (integers) and shown in dollars."""


def to_cents(amount: float) -> int:
    return round(amount * 100)


def dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"
