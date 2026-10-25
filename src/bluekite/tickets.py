"""The practice tickets, T-1001 to T-1005."""

import json
from pathlib import Path

TICKETS = Path(__file__).parent / "tickets.json"


def load_tickets() -> dict[str, dict]:
    return {t["id"]: t for t in json.loads(TICKETS.read_text())}


def get_ticket(ticket_id: str) -> dict:
    tickets = load_tickets()
    if ticket_id not in tickets:
        raise SystemExit(f"no ticket {ticket_id} (try: bluekite tickets)")
    return tickets[ticket_id]
