"""The practice tickets, T-1001 to T-1005, and variants of them for attack tests."""

import json
from pathlib import Path

HERE = Path(__file__).parent


def load_tickets(variants: bool = False) -> dict[str, dict]:
    tickets = json.loads((HERE / "tickets.json").read_text())
    if variants:
        tickets += json.loads((HERE / "variants.json").read_text())
    return {t["id"]: t for t in tickets}


def get_ticket(ticket_id: str) -> dict:
    tickets = load_tickets(variants=True)
    if ticket_id not in tickets:
        raise SystemExit(f"no ticket {ticket_id} (try: bluekite tickets)")
    return tickets[ticket_id]


def prepare(db, ticket: dict) -> None:
    """Some variants need extra shop data first, for example a gift message."""
    for line in ticket.get("setup", {}).get("lines", []):
        found = db.execute("select 1 from order_lines where order_id = ? and "
                           "description = ?", (line[0], line[1])).fetchone()
        if not found:
            db.execute("insert into order_lines values (?,?,?,?)", line)
    db.commit()
